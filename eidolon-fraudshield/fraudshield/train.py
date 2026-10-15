"""Synthetic baseline training and evaluation (no third-party dependencies).

Split is chronological by generation order. The holdout test is evaluated once.
PR-AUC reported on synthetic test distribution; do not extrapolate to real banks.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import json, math, random
from .synthetic import generate
from .features import FEATURE_NAMES, vector

def sigmoid(z):
    return 1.0 / (1.0 + math.exp(-max(-45, min(45, z))))

def raw_scores(pairs, weights, bias):
    return [(sigmoid(bias + sum(w*x for w,x in zip(weights, vector(ev)))), y) for ev,y in pairs]

def metrics(scored, threshold):
    tp = sum(s>=threshold and y==1 for s,y in scored)
    fp = sum(s>=threshold and y==0 for s,y in scored)
    fn = sum(s<threshold and y==1 for s,y in scored)
    tn = sum(s<threshold and y==0 for s,y in scored)
    precision = tp / max(tp+fp, 1)
    recall = tp / max(tp+fn, 1)
    f1 = 2*precision*recall/max(precision+recall, 1e-12)
    return dict(precision=round(precision,4), recall=round(recall,4), f1=round(f1,4),
                false_positive_rate=round(fp/max(fp+tn,1),4),
                tp=tp,fp=fp,fn=fn,tn=tn, positives=tp+fn,total=len(scored))

def average_precision(scored):
    positives = sum(y for _,y in scored)
    if not positives: return 0.0
    # Stable ranking uses one incrementally evaluated precision per positive example.
    tp=0; acc=0.0
    for rank,(_score,y) in enumerate(sorted(scored, key=lambda v:v[0], reverse=True), 1):
        if y:
            tp+=1; acc+=tp/rank
    return round(acc/positives,4)

def train(output: Path, size=12000):
    if size < 300: raise ValueError('size must be >= 300')
    data=list(generate(size,seed=74))
    n=len(data); train_pairs=data[:int(n*.7)]; valid_pairs=data[int(n*.7):int(n*.85)]; test_pairs=data[int(n*.85):]
    weights=[0.0]*len(FEATURE_NAMES); bias=-2.0
    rng=random.Random(42)
    samples=[(vector(event),y) for event,y in train_pairs]
    for epoch in range(33):
        rng.shuffle(samples)
        lr = .052 / (1 + epoch*.075)
        for x,y in samples:
            z=bias+sum(w*a for w,a in zip(weights,x))
            diff=sigmoid(z)-y
            bias -= lr*diff
            for j,val in enumerate(x):
                weights[j]-=lr*(diff*val+ .000025*weights[j])
    valid=raw_scores(valid_pairs, weights,bias)
    candidates=[i/1000 for i in range(5, 951, 5)]
    threshold=max(candidates,key=lambda t:(metrics(valid,t)['f1'], -t))
    test=raw_scores(test_pairs,weights,bias)
    artifact={
        'version':'synthetic-baseline-1', 'trained_at':datetime.now(timezone.utc).isoformat(),
        'kind':'logistic regression (standard library SGD)', 'data_origin':'synthetic PaySim-like events ONLY',
        'features':FEATURE_NAMES,'weights':[round(w,8) for w in weights],
        'bias':round(bias,8),'threshold':threshold,
        'sample_counts':{'train':len(train_pairs),'validation':len(valid_pairs),'test':len(test_pairs)},
        'validation':metrics(valid, threshold),'test':{**metrics(test, threshold),'average_precision':average_precision(test)}
    }
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(artifact,indent=2)+'\n', encoding='utf8')
    return artifact
