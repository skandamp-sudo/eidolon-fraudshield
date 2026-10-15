#!/usr/bin/env python3
"""Out-of-domain evaluation of the synthetic-trained baseline on PaySim CSV.

Outputs metrics for specified streamed rows. No train/test claim is made;
PaySim is also simulation data and never trains the bundled model.
"""
import argparse,csv,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fraudshield.features import clean_event
from fraudshield.model import RiskModel

p=argparse.ArgumentParser(description='Evaluate baseline on labeled PaySim records without storing them')
p.add_argument('csv_path',type=Path)
p.add_argument('--min-step',type=int,default=0)
p.add_argument('--max-rows',type=int,default=0,help='0 = full CSV')

def main():
    args=p.parse_args()
    if args.min_step<0 or args.max_rows<0: p.error('Step/row limits must be nonnegative')
    model=RiskModel(Path(__file__).resolve().parents[1]/'models'/'baseline.json')
    tp=fp=tn=fn=rows=0
    with args.csv_path.open(newline='',encoding='utf8') as fh:
        reader=csv.DictReader(fh)
        required={'step','type','amount','oldbalanceOrg','oldbalanceDest','isFraud'}
        if not required.issubset(set(reader.fieldnames or [])):
            p.error('CSV must include columns: '+', '.join(sorted(required)))
        for index,row in enumerate(reader,1):
            if int(row['step'])<args.min_step:continue
            event=clean_event(row)
            truth=int(row['isFraud'])
            if truth not in (0,1):raise ValueError('isFraud must be 0 or 1')
            predicted=model.predict(event)['decision']=='ESCALATE'
            if predicted and truth:tp+=1
            elif predicted:fp+=1
            elif truth:fn+=1
            else:tn+=1
            rows+=1
            if rows%100_000==0:print(f'Processed {rows:,} records...',file=sys.stderr)
            if args.max_rows and rows>=args.max_rows:break
    precision=tp/max(tp+fp,1);recall=tp/max(tp+fn,1)
    f1=2*precision*recall/max(precision+recall,1e-12)
    print('Out-of-domain PaySim evaluation (model was NOT trained on PaySim)')
    print('Rows:',f'{rows:,}','Fraud labels:',f'{tp+fn:,}')
    print('TP/FP/FN/TN:',tp,fp,fn,tn)
    print('Precision:',f'{precision:.4f}','Recall:',f'{recall:.4f}','F1:',f'{f1:.4f}','FPR:',f'{fp/max(fp+tn,1):.4f}')
    print('CAUTION: PaySim is synthetic, and this is an external-dataset check, not a real-bank benchmark.')

if __name__=='__main__':main()
