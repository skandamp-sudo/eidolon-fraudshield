"""Reconstruct only the locked Phase 2 tree and export validated numeric JSON.

Requires optional, pinned training dependencies. Never loads/saves pickle.
The original Phase 2 fitted estimator was not retained, so this is a recipe refit.
"""
from __future__ import annotations
import argparse
import csv
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import random
import time

import numpy as np
from threadpoolctl import threadpool_limits

from experiments.paysim_models import fit_candidate, static_features, write_json
from fraudshield.features import clean_event
from fraudshield.paysim import REQUIRED
from fraudshield.portable import FEATURES, FEATURE_SPEC, FORMAT, PortableModel, features, fingerprint

ROOT = Path(__file__).resolve().parents[1]


def export_estimator(estimator, provenance, thresholds):
    if importlib.metadata.version('scikit-learn') != '1.7.2':
        raise ValueError('Exporter audited only against scikit-learn 1.7.2')
    if (estimator.n_features_in_ != len(FEATURES) or list(estimator.classes_) != [0, 1] or
            estimator.n_trees_per_iteration_ != 1 or estimator.is_categorical_ is not None and
            np.any(estimator.is_categorical_)):
        raise ValueError('Only binary numeric static-v2 trees are supported')
    trees = []
    for iteration in estimator._predictors:
        if len(iteration) != 1:
            raise ValueError('Multiclass trees are not supported')
        tree = []
        for node in iteration[0].nodes:
            if node['is_categorical']:
                raise ValueError('Categorical splits are not supported')
            if node['is_leaf']:
                tree.append({'leaf': float(node['value'])})
            else:
                tree.append({'feature': int(node['feature_idx']), 'threshold': float(node['num_threshold']),
                             'left': int(node['left']), 'right': int(node['right'])})
        trees.append(tree)
    return {'format': FORMAT, 'version': 'paysim-phase2-locked-tree-v1',
            'feature_spec': FEATURE_SPEC, 'features': FEATURES, 'provenance': provenance,
            'thresholds': thresholds, 'default_threshold': 'max_f1',
            'bias': float(estimator._baseline_prediction[0, 0]), 'trees': trees}


def representative_events(count=2000, seed=20261015):
    events = []
    amounts = [0, 1e-12, 1, 4999.999999, 5000, 5000.000001, 19999.999999,
               20000, 20000.000001, 99999.999999, 100000, 100000.000001, 1e12]
    for kind in ('TRANSFER', 'CASH_OUT', 'CASH_IN', 'PAYMENT', 'DEBIT'):
        for step in (0, 1, 5, 6, 23, 24, 323, 10_000_000):
            for amount in amounts:
                events.append({'step': step, 'type': kind, 'amount': amount})
    rng = random.Random(seed)
    for _ in range(count):
        events.append({'step': rng.randrange(0, 744),
                       'type': rng.choice(('TRANSFER', 'CASH_OUT', 'CASH_IN', 'PAYMENT', 'DEBIT')),
                       'amount': 10 ** rng.uniform(-10, 12)})
    return events


def boundary_vectors(trees):
    """Reach every numeric split, then probe at/below/above its threshold.

    These are computational fixtures, not invented transactions or fraud data.
    """
    vectors = []
    for tree in trees:
        pending = [(0, [(-1e12, 1e12)] * len(FEATURES))]
        while pending:
            index, bounds = pending.pop()
            node = tree[index]
            if 'leaf' in node:
                continue
            feature, threshold = node['feature'], node['threshold']
            for value in (math.nextafter(threshold, -math.inf), threshold,
                          math.nextafter(threshold, math.inf)):
                row = [(low + high) / 2 for low, high in bounds]
                row[feature] = value
                if not all(low <= x <= high for x, (low, high) in zip(row, bounds)):
                    raise ValueError('Could not construct reachable split-boundary fixture')
                # Check the path really reaches this node before scoring the ensemble.
                cursor = 0
                while cursor != index and 'leaf' not in tree[cursor]:
                    parent = tree[cursor]
                    cursor = parent['left'] if row[parent['feature']] <= parent['threshold'] else parent['right']
                if cursor != index:
                    raise ValueError('Unreachable boundary fixture')
                vectors.append(row)
            left, right = list(bounds), list(bounds)
            low, high = bounds[feature]
            left[feature] = (low, min(high, threshold))
            right[feature] = (max(low, math.nextafter(threshold, math.inf)), high)
            pending.extend(((node['left'], left), (node['right'], right)))
    return vectors


def parity(estimator, portable, rows, thresholds, tolerance):
    reference = estimator.predict_proba(np.asarray(rows, dtype=np.float64))[:, 1]
    actual = np.asarray([portable.score_features(list(row)) for row in rows])
    error = float(np.max(np.abs(reference - actual)))
    mismatches = {name: int(np.sum((reference >= threshold) != (actual >= threshold)))
                  for name, threshold in thresholds.items() if threshold is not None}
    if error > tolerance or any(mismatches.values()):
        raise ValueError(f'Parity gate failed: max error={error}; decisions={mismatches}')
    return {'vectors': len(rows), 'max_absolute_error': error,
            'decision_mismatches': mismatches, 'absolute_tolerance': tolerance}, reference


def load_training(csv_path, protocol, directory):
    count = protocol['training_rows']
    x = np.memmap(directory / 'training-features.dat', mode='w+', dtype='float64', shape=(count, len(FEATURES)))
    y = np.memmap(directory / 'training-labels.dat', mode='w+', dtype='int8', shape=(count,))
    csv.field_size_limit(4096)
    previous, loaded = -1, 0
    with Path(csv_path).open(newline='', encoding='utf-8-sig') as source:
        reader = csv.DictReader(source, strict=True)
        names = reader.fieldnames or []
        if len(names) != len(set(names)) or not REQUIRED.issubset(names):
            raise ValueError('Invalid PaySim header')
        for row in reader:
            step = row['step']
            if step is None or len(step) > 8 or not step.isascii() or not step.isdecimal():
                raise ValueError('Invalid simulation step')
            step = int(step)
            if step < previous:
                raise ValueError('Training rows out of chronological order')
            previous = step
            if step > protocol['training_step_lte']:
                break  # no validation/confirmation/test labels or features parsed
            if loaded >= count or None in row or any(v is None for v in row.values()) or row['isFraud'] not in ('0', '1'):
                raise ValueError('Invalid training row or row count')
            event = clean_event({'step': step, 'type': row['type'], 'amount': row['amount']})
            x[loaded] = static_features(event)
            y[loaded] = int(row['isFraud'])
            loaded += 1
            if loaded % 1_000_000 == 0:
                print(f'Loaded {loaded:,} locked training rows', flush=True)
    if loaded != count or int(np.sum(y)) != protocol['training_positives']:
        raise ValueError('Locked training counts changed')
    x.flush(); y.flush()
    return x, y


def run(csv_path, baseline_path, output):
    protocol = json.loads((ROOT / 'experiments/phase3_protocol.json').read_text())
    frozen = {'experiments/phase2_protocol.json': protocol['phase2_protocol_sha256'],
              'benchmarks/paysim-phase2-v1.json': protocol['phase2_report_sha256'],
              'experiments/paysim_models.py': protocol['phase2_runner_sha256'],
              csv_path: protocol['dataset_sha256'], baseline_path: protocol['baseline_artifact_sha256']}
    for path, expected in frozen.items():
        if fingerprint(ROOT / path) != expected:
            raise ValueError(f'Frozen input fingerprint mismatch: {path}')
    expected_dependencies = {}
    for line in (ROOT / 'requirements-training.txt').read_text().splitlines():
        if '==' in line and not line.startswith('#'):
            package, version = line.split('==')
            if importlib.metadata.version(package) != version:
                raise ValueError(f'Pinned dependency mismatch: {package}')
            expected_dependencies[package] = version
    phase2 = json.loads((ROOT / 'experiments/phase2_protocol.json').read_text())
    candidate = next(c for c in phase2['candidates'] if c['id'] == protocol['selected_candidate'])
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'protocol.json', protocol)
    started = time.perf_counter()
    x, y = load_training(csv_path, protocol, output)
    with threadpool_limits(limits=protocol['threads']):
        estimator, fit_seconds = fit_candidate(candidate, phase2, x, y, slice(None))
        provenance = {key: protocol[key] for key in ('dataset_sha256', 'baseline_artifact_sha256',
                     'phase2_protocol_sha256', 'phase2_report_sha256', 'training_rows', 'training_step_lte', 'seed')}
        provenance.update(training_recipe=candidate['id'], sklearn_version='1.7.2',
                          exporter_sha256=fingerprint(__file__),
                          portable_source_sha256=fingerprint(ROOT / 'fraudshield/portable.py'),
                          base_features_sha256=fingerprint(ROOT / 'fraudshield/features.py'))
        artifact = export_estimator(estimator, provenance, protocol['locked_thresholds'])
        model_path = output / 'paysim.phase3.local.json'
        write_json(model_path, artifact)
        model_hash = fingerprint(model_path)
        portable = PortableModel(model_path, expected_sha256=model_hash,
                                 expected_dataset_sha256=protocol['dataset_sha256'])
        events = representative_events(protocol['parity_random_events'], protocol['parity_random_seed'])
        event_rows = [features(event) for event in events]
        if event_rows != [static_features(clean_event(event)) for event in events]:
            raise ValueError('Frozen and portable feature transforms differ')
        boundaries = boundary_vectors(artifact['trees'])
        golden_rows = event_rows + boundaries
        golden_result, reference = parity(estimator, portable, golden_rows, protocol['locked_thresholds'], protocol['parity_absolute_tolerance'])
        positions = np.linspace(0, len(x) - 1, min(protocol['parity_training_vectors'], len(x)), dtype=int)
        training_result, _ = parity(estimator, portable, x[positions].tolist(), protocol['locked_thresholds'], protocol['parity_absolute_tolerance'])
        golden = {'format': 'eidolon-portable-parity-v1', 'artifact_sha256': model_hash,
                  'absolute_tolerance': protocol['parity_absolute_tolerance'],
                  'cases': [{'features': row, 'score': float(score)} for row, score in zip(golden_rows, reference)]}
        golden_path = output / 'parity-vectors.local.json'
        write_json(golden_path, golden)
    for path, expected in frozen.items():
        if fingerprint(ROOT / path) != expected:
            raise ValueError('Frozen input changed during export; results invalid')
    report = {'version': protocol['version'], 'status': 'portable_parity_passed_not_independent_validation',
              'protocol_sha256': fingerprint(ROOT / 'experiments/phase3_protocol.json'),
              'artifact_sha256': model_hash, 'artifact_bytes': model_path.stat().st_size,
              'golden_vectors_sha256': fingerprint(golden_path), 'provenance': provenance,
              'locked_thresholds': protocol['locked_thresholds'], 'trees': len(artifact['trees']),
              'nodes': sum(map(len, artifact['trees'])), 'parity': {'synthetic_and_boundary': golden_result,
              'synthetic_events': len(events), 'split_boundary_vectors': len(boundaries), 'training_only': training_result},
              'fit_seconds': fit_seconds, 'elapsed_seconds': time.perf_counter() - started,
              'environment': {'python': platform.python_version(), 'platform': platform.platform(), 'dependencies': expected_dependencies},
              'limitations': ['Reconstructed locked recipe; original fitted Phase 2 estimator was not saved.',
                             'No independent fraud evaluation, confirmation rerun or previously exposed holdout evaluation.',
                             'No s390x hardware tested. Artifact and golden fixtures remain outside Git.']}
    write_json(output / 'export-report.json', report)
    print(json.dumps(report, indent=2), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv_path', type=Path)
    parser.add_argument('baseline_path', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.csv_path.resolve(), args.baseline_path.resolve(), args.output)
