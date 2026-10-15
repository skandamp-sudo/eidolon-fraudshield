#!/usr/bin/env python3
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fraudshield.train import train
import json
if __name__ == '__main__':
    model=Path(__file__).resolve().parents[1]/'models'/'baseline.json'
    artifact=train(model)
    print('Saved:',model)
    print(json.dumps(artifact['test'],indent=2))
    print('IMPORTANT: These metrics are on generated synthetic data, NOT real payments.')
