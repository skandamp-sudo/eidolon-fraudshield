"""Zero-runtime-dependency HTTP API and static web server (localhost by default)."""
from __future__ import annotations
import json, threading, time, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from .features import clean_event
from .model import RiskModel
from .store import Store
from .synthetic import generate

ROOT=Path(__file__).resolve().parents[1]

def reject_json_constant(value):
    raise ValueError(f'Invalid JSON constant: {value}')

class App:
    def __init__(self,root=ROOT,database=None):
        self.root=Path(root)
        self.model=RiskModel(self.root/'models'/'baseline.json')
        self.store=Store(database or self.root/'data'/'fraudshield.sqlite3')
        self.worker=None
        self.worker_lock=threading.Lock()
        self.replay={'running':False,'done':0,'target':0,'error':None}

    def score_event(self,payload,source='manual',truth=None):
        event=clean_event(payload)
        result=self.model.predict(event)
        result['id']=self.store.insert(event,result,source=source,truth=truth)
        return result

    def begin_replay(self,count=85,speed=.16):
        if isinstance(count,bool) or not isinstance(count,int) or count<1 or count>300:
            raise ValueError('count must be 1..300')
        with self.worker_lock:
            if self.replay['running']:
                raise RuntimeError('Replay already running')
            self.replay={'running':True,'done':0,'target':count,'error':None}
            self.worker=threading.Thread(target=self._replay,args=(count,speed),daemon=True)
            self.worker.start()
            return dict(self.replay)

    def _replay(self,count,speed):
        try:
            # Seed intentionally varies each run so subsequent demonstrations are not identical.
            seed=74+int(time.time()*1000)%999999
            for event,truth in generate(count,seed=seed):
                self.score_event(event,source='synthetic',truth=truth)
                with self.worker_lock: self.replay['done']+=1
                time.sleep(speed)
        except Exception as exc:
            with self.worker_lock: self.replay['error']=str(exc)
        finally:
            with self.worker_lock: self.replay['running']=False

    def state(self):
        with self.worker_lock: rep=dict(self.replay)
        return {'summary':self.store.summary(),'events':self.store.events(65),
                'replay':rep,'model':{k:v for k,v in self.model.artifact.items() if k not in ('weights','bias')}}

    def handler(self):
        app=self
        class Handler(BaseHTTPRequestHandler):
            server_version='FraudShield/0.1'
            def setup(self):
                super().setup()
                self.connection.settimeout(10)
            def log_message(self,format,*args):
                print(f'[{self.log_date_time_string()}] {format%args}')
            def send_bytes(self,body,status=200,ctype='application/json; charset=utf-8'):
                self.send_response(status)
                self.send_header('Content-Type',ctype)
                self.send_header('Content-Length',str(len(body)))
                self.send_header('Cache-Control','no-store')
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('X-Frame-Options','DENY')
                self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; object-src 'none'")
                self.end_headers()
                self.wfile.write(body)
            def send_json(self,obj,status=200):
                self.send_bytes(json.dumps(obj,allow_nan=False).encode('utf8'),status)
            def err(self,msg,status=400):
                self.send_json({'error':msg},status)
            def read_json(self):
                if self.headers.get('Transfer-Encoding'):
                    raise ValueError('Transfer-Encoding is not supported')
                if self.headers.get_content_type() != 'application/json':
                    raise ValueError('Content-Type must be application/json')
                try: size=int(self.headers.get('Content-Length','0'))
                except ValueError: raise ValueError('Invalid Content-Length')
                if size<=0 or size>65_536: raise ValueError('JSON payload must be 1 to 65536 bytes')
                try:
                    result=json.loads(self.rfile.read(size), parse_constant=reject_json_constant)
                except (ValueError,UnicodeDecodeError,RecursionError) as e: raise ValueError('Invalid JSON body') from e
                if not isinstance(result,dict): raise ValueError('JSON object expected')
                return result
            def valid_origin(self):
                host=self.headers.get('Host','')
                if host not in {f'{name}:{self.server.server_port}' for name in ('127.0.0.1','localhost')} | {'127.0.0.1','localhost'}:
                    return False
                origin=self.headers.get('Origin')
                return not origin or origin == f'http://{host}'
            def do_GET(self):
                try:
                    if not self.valid_origin(): return self.err('Invalid host or origin',403)
                    parsed=urlsplit(self.path);route=parsed.path
                    if route=='/api/health': return self.send_json({'ok':True,'name':'EIDOLON FRAUDSHIELD','mode':'demo','model':app.model.artifact['version']})
                    if route=='/api/state':return self.send_json(app.state())
                    if route=='/api/events':
                        query=parse_qs(parsed.query)
                        return self.send_json({'events':app.store.events(int(query.get('limit',['60'])[0]))})
                    static={'/':'index.html','/index.html':'index.html','/styles.css':'styles.css','/app.js':'app.js'}
                    if route not in static:return self.err('Not found',404)
                    filepath=app.root/'web'/static[route]
                    if not filepath.is_file():return self.err('Static file missing',404)
                    suffix=filepath.suffix
                    ctype={'html':'text/html','css':'text/css','js':'text/javascript'}.get(suffix[1:],'application/octet-stream')
                    return self.send_bytes(filepath.read_bytes(),ctype=ctype+'; charset=utf-8')
                except (ValueError,TypeError) as exc:self.err(str(exc))
                except Exception as exc:
                    traceback.print_exc();self.err('Internal server error',500)
            def do_POST(self):
                try:
                    if not self.valid_origin(): return self.err('Invalid host or origin',403)
                    parsed=urlsplit(self.path);route=parsed.path
                    if route=='/api/score':
                        result=app.score_event(self.read_json());return self.send_json(result,201)
                    if route=='/api/demo/start':
                        payload=self.read_json()
                        return self.send_json(app.begin_replay(payload.get('count',85)),202)
                    if route=='/api/demo/reset':
                        self.read_json()
                        with app.worker_lock:
                            if app.replay['running']:return self.err('Stop replay before reset',409)
                            app.store.reset()
                        return self.send_json({'ok':True})
                    if route=='/api/review':
                        payload=self.read_json()
                        app.store.review(int(payload['id']),str(payload['disposition']))
                        return self.send_json({'ok':True})
                    return self.err('Not found',404)
                except (ValueError,TypeError,KeyError) as exc:self.err(str(exc),404 if str(exc)=="'Event not found'" else 400)
                except RuntimeError as exc:self.err(str(exc),409)
                except Exception as exc:
                    traceback.print_exc();self.err('Internal server error',500)
        return Handler

def serve(host='127.0.0.1',port=8000):
    if host not in ('127.0.0.1','localhost'):
        raise ValueError('Unauthenticated demo must bind to loopback only')
    app=App()
    http=ThreadingHTTPServer((host,port),app.handler())
    print(f'\n  EIDOLON // FRAUDSHIELD  →  http://{host}:{port}\n  Mode: synthetic demo • no live financial data\n  Ctrl+C to stop\n')
    try: http.serve_forever()
    except KeyboardInterrupt: pass
    finally: http.server_close()

if __name__=='__main__':serve()
