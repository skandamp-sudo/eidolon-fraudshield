from pathlib import Path
from tempfile import TemporaryDirectory
import http.client, json, threading, unittest
from http.server import ThreadingHTTPServer
from fraudshield.features import clean_event,vector,FEATURE_NAMES
from fraudshield.model import RiskModel
from fraudshield.store import Store
from fraudshield.server import App, ROOT
from fraudshield.synthetic import generate
from fraudshield.train import metrics,average_precision

class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model=RiskModel(ROOT/'models'/'baseline.json')

    def test_feature_vector_and_no_label_leakage(self):
        event,truth=next(generate(1))
        clone=dict(event,isFraud=1,isFlaggedFraud=1,newbalanceOrig=999999999,newbalanceDest=0,oldbalanceOrg=999999,oldbalanceDest=0)
        self.assertEqual(vector(event),vector(clone))
        self.assertEqual(len(vector(event)),len(FEATURE_NAMES))

    def test_untrusted_inputs_rejected(self):
        for raw in [dict(type='WIRE',amount=10),dict(type='TRANSFER',amount=-1),dict(type='TRANSFER',amount=float('nan'))]:
            with self.assertRaises(ValueError):clean_event(raw)

    def test_demo_reproducibility(self):
        self.assertEqual(list(generate(8,seed=12)),list(generate(8,seed=12)))

    def test_decisions_and_reasons(self):
        event,_=next(generate(1));result=self.model.predict(event)
        self.assertIn(result['decision'],{'ALLOW','REVIEW','ESCALATE'})
        self.assertTrue(0<=result['score']<=100)
        self.assertGreaterEqual(len(result['reasons']),1)

    def test_metrics(self):
        self.assertEqual(metrics([(.9,1),(.8,0),(.1,0)],.5)['fp'],1)
        self.assertEqual(average_precision([(.9,1),(.8,0),(.1,1)]),round((1+2/3)/2,4))

    def test_store_and_review_audit(self):
        with TemporaryDirectory() as temp:
            store=Store(Path(temp)/'test.sqlite3')
            event,_=next(generate(1));result=self.model.predict(event)
            id=store.insert(event,result,truth=0)
            self.assertEqual(store.summary()['total'],1)
            store.review(id,'INVESTIGATING')
            self.assertEqual(store.events()[0]['reviewed_as'],'INVESTIGATING')
            store.reset();self.assertEqual(store.summary()['total'],0)

    def test_background_replay(self):
        import time
        with TemporaryDirectory() as temp:
            app=App(database=Path(temp)/'demo.sqlite3')
            self.assertTrue(app.begin_replay(count=8,speed=0)['running'])
            deadline=time.monotonic()+5
            while app.state()['replay']['running'] and time.monotonic()<deadline:
                time.sleep(.01)
            state=app.state()
            self.assertIsNone(state['replay']['error'])
            self.assertEqual(state['summary']['total'],8)
            self.assertEqual(state['replay']['done'],8)

    def test_http_api(self):
        with TemporaryDirectory() as temp:
            app=App(database=Path(temp)/'test.sqlite3')
            server=ThreadingHTTPServer(('127.0.0.1',0),app.handler())
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                conn.request('GET','/api/health');res=conn.getresponse();health=json.loads(res.read())
                self.assertEqual(res.status,200);self.assertTrue(health['ok'])
                event,_=next(generate(1));payload=json.dumps(event)
                conn.request('POST','/api/score',payload,{'Content-Type':'application/json'})
                res=conn.getresponse();event_result=json.loads(res.read())
                self.assertEqual(res.status,201);self.assertIn('id',event_result)
                conn.request('GET','/api/state');res=conn.getresponse();state=json.loads(res.read())
                self.assertEqual(state['summary']['total'],1)
                conn.request('POST','/api/review',json.dumps({'id':event_result['id'],'disposition':'INVESTIGATING'}),{'Content-Type':'application/json'})
                res=conn.getresponse();self.assertEqual(res.status,200);res.read()
                conn.request('POST','/api/demo/reset','{}',{'Content-Type':'application/json'})
                res=conn.getresponse();self.assertEqual(res.status,200);res.read()
                conn.close()
            finally:
                server.shutdown();server.server_close();thread.join(timeout=5)

if __name__=='__main__':unittest.main()
