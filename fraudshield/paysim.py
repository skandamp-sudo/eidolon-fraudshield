"""Separate, bounded-memory PaySim training and future-step evaluation.

Only step, type and amount enter the feature map. Labels are read separately.
Balance and account columns are deliberately never parsed as predictors.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

from .features import FEATURE_NAMES, clean_event, vector
from .train import sigmoid

REQUIRED = {'step', 'type', 'amount', 'isFraud', 'isFlaggedFraud',
            'oldbalanceOrg', 'newbalanceOrig', 'oldbalanceDest', 'newbalanceDest',
            'nameOrig', 'nameDest'}
BINS = 10_000


def rows(path: Path):
    """Read a sorted, canonical PaySim CSV without retaining account IDs or balances."""
    with path.open(newline='', encoding='utf-8-sig') as source:
        reader = csv.DictReader(source)
        names = reader.fieldnames or []
        if len(names) != len(set(names)) or not REQUIRED.issubset(names):
            raise ValueError('PaySim CSV has missing or duplicate required columns')
        previous = -1
        for line, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f'Malformed CSV row at line {line}')
            raw_step = row['step']
            if not raw_step.isascii() or not raw_step.isdecimal():
                raise ValueError(f'Invalid step at line {line}')
            step = int(raw_step)
            if step < previous:
                raise ValueError(f'PaySim rows are not sorted by step at line {line}')
            previous = step
            if row['isFraud'] not in ('0', '1'):
                raise ValueError(f'Invalid isFraud label at line {line}')
            try:
                event = clean_event({'step': step, 'type': row['type'], 'amount': row['amount']})
            except ValueError as exc:
                raise ValueError(f'Invalid feature at line {line}: {exc}') from exc
            yield step, vector(event), int(row['isFraud'])


def inspect(path: Path):
    counts = {}
    positives = {}
    for step, _features, label in rows(path):
        counts[step] = counts.get(step, 0) + 1
        positives[step] = positives.get(step, 0) + label
    total = sum(counts.values())
    if len(counts) < 3:
        raise ValueError('At least three distinct time steps are required')
    steps = list(counts)
    cumulative = 0
    train_end = valid_end = None
    for step in steps:
        cumulative += counts[step]
        if train_end is None and cumulative >= total * .70:
            train_end = step
        elif train_end is not None and valid_end is None and cumulative >= total * .85:
            valid_end = step
    if valid_end is None or valid_end == steps[-1]:
        raise ValueError('Chronological split leaves no validation or test time steps')
    parts = {'train': {'rows': 0, 'positives': 0},
             'validation': {'rows': 0, 'positives': 0},
             'test': {'rows': 0, 'positives': 0}}
    for step in steps:
        part = 'train' if step <= train_end else 'validation' if step <= valid_end else 'test'
        parts[part]['rows'] += counts[step]
        parts[part]['positives'] += positives[step]
    if any(not part['rows'] or not part['positives'] for part in parts.values()):
        raise ValueError('Every chronological partition needs rows and positive labels')
    return train_end, valid_end, parts


def histogram(path, lower, upper, weights, bias):
    positive = [0] * (BINS + 1)
    negative = [0] * (BINS + 1)
    count = 0
    for step, features, label in rows(path):
        if lower < step <= upper:
            score = sigmoid(bias + sum(w * x for w, x in zip(weights, features)))
            bucket = min(BINS, int(score * BINS))
            (positive if label else negative)[bucket] += 1
            count += 1
    return positive, negative, count


def evaluate(positive, negative, threshold_bin):
    tp = sum(positive[threshold_bin:])
    fp = sum(negative[threshold_bin:])
    fn = sum(positive[:threshold_bin])
    tn = sum(negative[:threshold_bin])
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
            'precision': round(precision, 6), 'recall': round(recall, 6),
            'f1': round(f1, 6),
            'false_positive_rate': round(fp / (fp + tn), 6) if fp + tn else None,
            'alert_count': tp + fp, 'base_rate': round((tp + fn) / (tp + fp + fn + tn), 8)}


def binned_average_precision(positive, negative):
    total = sum(positive)
    if not total:
        return None
    tp = fp = 0
    area = 0.0
    for bucket in range(BINS, -1, -1):
        tp += positive[bucket]
        fp += negative[bucket]
        if positive[bucket]:
            area += (positive[bucket] / total) * (tp / (tp + fp))
    return round(area, 6)


def train_and_evaluate(source: Path, output: Path):
    source = Path(source)
    output = Path(output)
    if output.resolve() == (Path(__file__).resolve().parents[1] / 'models' / 'baseline.json').resolve():
        raise ValueError('PaySim model must not replace the bundled demo baseline')
    before = source.stat()
    train_end, valid_end, parts = inspect(source)
    weights = [0.0] * len(FEATURE_NAMES)
    bias = -4.0
    seen = 0
    for step, features, label in rows(source):
        if step > train_end:
            continue
        diff = sigmoid(bias + sum(w * x for w, x in zip(weights, features))) - label
        bias -= .015 * diff
        for index, value in enumerate(features):
            weights[index] -= .015 * (diff * value + .000025 * weights[index])
        seen += 1
    if seen != parts['train']['rows']:
        raise ValueError('PaySim source changed during training')
    valid_pos, valid_neg, count = histogram(source, train_end, valid_end, weights, bias)
    if count != parts['validation']['rows']:
        raise ValueError('PaySim source changed during validation')
    threshold_bin = max(range(1, BINS + 1),
                        key=lambda index: (evaluate(valid_pos, valid_neg, index)['f1'], index))
    test_pos, test_neg, count = histogram(source, valid_end, math.inf, weights, bias)
    if count != parts['test']['rows'] or (source.stat().st_size, source.stat().st_mtime_ns) != (before.st_size, before.st_mtime_ns):
        raise ValueError('PaySim source changed during evaluation')
    digest = hashlib.sha256()
    with source.open('rb') as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            digest.update(chunk)
    artifact = {'version': 'paysim-chronological-1', 'kind': 'logistic regression (single-pass standard-library SGD)',
                'data_origin': 'user-supplied PaySim synthetic CSV', 'source_sha256': digest.hexdigest(),
                'features': FEATURE_NAMES, 'weights': [round(w, 8) for w in weights],
                'bias': round(bias, 8), 'threshold': threshold_bin / BINS,
                'split': {'train_step_lte': train_end, 'validation_step_lte': valid_end, 'partitions': parts},
                'validation': evaluate(valid_pos, valid_neg, threshold_bin),
                'test': {**evaluate(test_pos, test_neg, threshold_bin),
                         'binned_average_precision': binned_average_precision(test_pos, test_neg)},
                'metric_note': 'AP uses 10,001 score bins; no calibration or real-world accuracy claim.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=output.parent, prefix='.paysim-', suffix='.tmp',
                                     encoding='utf-8', delete=False) as temporary:
        name = temporary.name
        try:
            json.dump(artifact, temporary, indent=2, allow_nan=False)
            temporary.write('\n')
        except BaseException:
            os.unlink(name)
            raise
    os.replace(name, output)
    return artifact
