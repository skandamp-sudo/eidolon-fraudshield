#!/usr/bin/env python3
"""Stream real PaySim CSV *rows* (dataset itself is synthetic) into local demo.

Example:
 python scripts/replay_paysim.py /path/to/PS_20174392719_1491204439457_log.csv --limit 80 --delay .08
"""
import argparse,csv,json,sys,time
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fraudshield.features import clean_event

parser=argparse.ArgumentParser(description='Stream PaySim CSV records to a running FRAUDSHIELD server')
parser.add_argument('csv_path',type=Path)
parser.add_argument('--url',default='http://127.0.0.1:8000')
parser.add_argument('--limit',type=int,default=100)
parser.add_argument('--delay',type=float,default=.12)
parser.add_argument('--min-step',type=int,default=0,help='Skip dataset rows before this time step')

def main():
    args=parser.parse_args()
    if not 1<=args.limit<=10_000 or not 0<=args.delay<=30: parser.error('Invalid limit or delay')
    count=0
    with args.csv_path.open(newline='',encoding='utf8') as fh:
        reader=csv.DictReader(fh)
        required={'step','type','amount','oldbalanceOrg','oldbalanceDest'}
        if not required.issubset(set(reader.fieldnames or [])):
            parser.error('PaySim CSV is missing required columns: '+', '.join(sorted(required)))
        for index,row in enumerate(reader,1):
            if int(row['step']) < args.min_step:continue
            event=clean_event({**row,'transactionId':f'PAYSIM-{index:08d}'})
            req=Request(args.url.rstrip('/')+'/api/score',data=json.dumps(event).encode('utf8'),headers={'Content-Type':'application/json'},method='POST')
            try:
                with urlopen(req,timeout=15) as res:
                    result=json.load(res)
            except (HTTPError,URLError) as e:
                parser.error('Cannot reach FRAUDSHIELD server: '+str(e))
            count+=1
            print(f"{count:>5}  {event['type']:<9} {event['amount']:>12,.2f}  risk={result['score']:>6.2f}  {result['decision']}")
            if count>=args.limit:break
            time.sleep(args.delay)
    print(f'Replayed {count} PaySim records. PaySim is a synthetic financial dataset, not bank production traffic.')

if __name__=='__main__':main()
