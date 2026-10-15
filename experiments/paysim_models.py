"""Reproducible development-only comparisons. Optional training dependencies.

No model pickle is read or written. No application artifact is replaced.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import platform
import time
import warnings
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from fraudshield.features import FEATURE_NAMES, clean_event, vector
from fraudshield.model import RiskModel
from fraudshield.paysim import REQUIRED

STATIC_NAMES = FEATURE_NAMES + [f'log_amount_x_{name}' for name in
                               ('transfer', 'cash_out', 'cash_in', 'payment', 'debit')]
STATIC_NAMES += ['hour_sin', 'hour_cos', 'log_amount_squared']


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    """Exclusive output: a repeat run must use a new directory."""
    with Path(path).open('x', encoding='utf-8') as output:
        json.dump(value, output, indent=2, allow_nan=False)
        output.write('\n')


def static_features(event):
    base = vector(event)
    angle = 2 * math.pi * (event['step'] % 24) / 24
    return base + [base[0] * value for value in base[4:9]] + [
        math.sin(angle), math.cos(angle), base[0] ** 2]


def validate_protocol(protocol):
    split = protocol['split']
    edges = [split[name] for name in ('fit_end', 'tune_end', 'calibration_end', 'confirmation_end')]
    if any(type(edge) is not int for edge in edges) or not 0 <= edges[0] < edges[1] < edges[2] < edges[3]:
        raise ValueError('Development windows must be disjoint and chronological')
    if split['observed_test_start'] != edges[-1] + 1:
        raise ValueError('Confirmation must end before the observed test window')
    count = protocol['expected_development_rows']
    if type(count) is not int or not 1 <= count <= 10_000_000:
        raise ValueError('Development row allocation must be 1..10,000,000')
    if protocol['tree_fixed']['early_stopping'] is not False:
        raise ValueError('Automatic random validation/early stopping is prohibited')
    if not 1 <= protocol['threads'] <= 8:
        raise ValueError('Experiment threads must be 1..8')


def load_development(csv_path, protocol, directory):
    """Read only development labels/features into bounded on-disk arrays.

    The first post-cutoff step is read to detect the boundary; its features and
    label are never parsed. Dataset hashing is separate from label access.
    """
    validate_protocol(protocol)
    size = protocol['expected_development_rows']
    x = np.memmap(directory / 'features.dat', mode='w+', dtype='float64', shape=(size, len(STATIC_NAMES)))
    y = np.memmap(directory / 'labels.dat', mode='w+', dtype='int8', shape=(size,))
    steps = np.memmap(directory / 'steps.dat', mode='w+', dtype='int32', shape=(size,))
    csv.field_size_limit(4096)
    count = 0
    previous = -1
    with Path(csv_path).open(newline='', encoding='utf-8-sig') as source:
        reader = csv.DictReader(source, strict=True)
        names = reader.fieldnames or []
        if len(names) != len(set(names)) or not REQUIRED.issubset(names):
            raise ValueError('Missing or duplicate PaySim columns')
        for row in reader:
            raw_step = row['step']
            if raw_step is None or len(raw_step) > 8 or not raw_step.isascii() or not raw_step.isdecimal():
                raise ValueError('Invalid simulation step')
            step = int(raw_step)
            if step < previous:
                raise ValueError('CSV is not chronologically ordered')
            previous = step
            if step > protocol['split']['confirmation_end']:
                break
            if count >= size or None in row or any(value is None for value in row.values()):
                raise ValueError('Unexpected development row count or malformed CSV')
            if row['isFraud'] not in ('0', '1'):
                raise ValueError('Invalid development label')
            event = clean_event({'step': step, 'type': row['type'], 'amount': row['amount']})
            x[count] = static_features(event)
            y[count] = int(row['isFraud'])
            steps[count] = step
            count += 1
            if count % 1_000_000 == 0:
                print(f'Loaded {count:,} development rows', flush=True)
    if count != size:
        raise ValueError(f'Development row count mismatch: {count} != {size}')
    for array in (x, y, steps):
        array.flush()
    return x, y, steps


def windows(steps, protocol):
    boundaries = [int(np.searchsorted(steps, protocol['split'][key], side='right'))
                  for key in ('fit_end', 'tune_end', 'calibration_end', 'confirmation_end')]
    a, b, c, d = boundaries
    if not 0 < a < b < c < d == len(steps):
        raise ValueError('Each development window must contain rows')
    return {'fit': slice(0, a), 'tune': slice(a, b), 'calibration': slice(b, c),
            'confirmation': slice(c, d), 'refit': slice(0, b)}


def score_groups(labels, scores):
    if len(labels) == 0 or len(labels) != len(scores) or not np.all(np.isfinite(scores)):
        raise ValueError('Scores must be finite, nonempty and aligned with labels')
    order = np.argsort(-scores, kind='stable')
    ordered = scores[order]
    ends = np.r_[np.flatnonzero(ordered[:-1] != ordered[1:]), len(ordered) - 1]
    counts = ends + 1
    tp = np.cumsum(labels[order], dtype=np.int64)[ends]
    return ordered[ends], counts, tp


def choose_thresholds(labels, scores, rates):
    thresholds, counts, tp = score_groups(labels, scores)
    positives = int(np.sum(labels))
    if not 0 < positives < len(labels):
        raise ValueError('Threshold calibration requires both classes')
    f1 = 2 * tp / (positives + counts)
    # Groups are descending: equal F1 favors the higher threshold/fewer alerts.
    result = {'max_f1': float(thresholds[int(np.argmax(f1))])}
    for rate in rates:
        if not 0 < rate <= 10_000:
            raise ValueError('Invalid review capacity')
        eligible = np.flatnonzero(counts <= math.floor(len(labels) * rate / 10_000))
        result[f'capacity_{rate}_per_10000'] = float(thresholds[eligible[-1]]) if len(eligible) else None
    return result


def confusion(labels, scores, threshold, steps=None):
    alerted = np.zeros(len(labels), dtype=bool) if threshold is None else scores >= threshold
    tp = int(np.sum(alerted & (labels == 1)))
    fp = int(np.sum(alerted & (labels == 0)))
    fn = int(np.sum(labels == 1)) - tp
    tn = len(labels) - tp - fp - fn
    result = {'threshold': threshold, 'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
              'precision': tp / (tp + fp) if tp + fp else 0.0,
              'recall': tp / (tp + fn) if tp + fn else None,
              'f1': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0,
              'false_positive_rate': fp / (fp + tn) if fp + tn else None,
              'alerts': tp + fp, 'alerts_per_10000': (tp + fp) / len(labels) * 10000,
              'false_alerts_per_10000': fp / len(labels) * 10000}
    if steps is not None:
        unique = np.unique(steps)
        per_step = np.bincount(steps[alerted], minlength=int(unique[-1]) + 1)[unique]
        result['alerts_per_simulated_step'] = {'mean': float(np.mean(per_step)),
                                             'p95': float(np.quantile(per_step, .95)),
                                             'max': int(np.max(per_step))}
    return result


def assessment(labels, scores, thresholds, steps):
    values, counts, tp = score_groups(labels, scores)
    positives = int(np.sum(labels))
    selected = np.unique(np.linspace(0, len(values) - 1, min(100, len(values)), dtype=int))
    curve = [{'threshold': float(values[i]), 'precision': float(tp[i] / counts[i]),
              'recall': float(tp[i] / positives), 'alerts': int(counts[i])} for i in selected]
    return {'rows': len(labels), 'positives': positives, 'prevalence': positives / len(labels),
            'exact_average_precision': float(average_precision_score(labels, scores)),
            'operating_points': {name: confusion(labels, scores, threshold, steps)
                                 for name, threshold in thresholds.items()},
            'pr_curve_sample': curve}


def model_for(candidate, protocol):
    if candidate['family'] == 'logistic':
        return make_pipeline(StandardScaler(), LogisticRegression(
            C=candidate['C'], class_weight=candidate['class_weight'], random_state=protocol['seed'],
            **protocol['logistic_fixed']))
    if candidate['family'] == 'hist_tree':
        return HistGradientBoostingClassifier(max_leaf_nodes=candidate['max_leaf_nodes'],
            class_weight=candidate['class_weight'], random_state=protocol['seed'], **protocol['tree_fixed'])
    raise ValueError('Unknown model family')


def columns(candidate):
    if candidate['features'] not in ('baseline', 'static_v2'):
        raise ValueError('Unknown feature schema')
    return slice(0, len(FEATURE_NAMES) if candidate['features'] == 'baseline' else len(STATIC_NAMES))


def fit_candidate(candidate, protocol, x, y, section):
    estimator = model_for(candidate, protocol)
    started = time.monotonic()
    with warnings.catch_warnings():
        warnings.simplefilter('error', ConvergenceWarning)
        estimator.fit(x[section, columns(candidate)], y[section])
    return estimator, time.monotonic() - started


def drift_summary(x, y, steps, parts):
    output = {}
    for name, section in parts.items():
        data, truth = x[section], y[section]
        output[name] = {'rows': len(truth), 'positives': int(np.sum(truth)),
                        'prevalence': float(np.mean(truth)), 'mean_log_amount_feature': float(np.mean(data[:, 0])),
                        'transaction_types': {FEATURE_NAMES[4+i]: {'rows': int(np.sum(data[:, 4+i])),
                            'positives': int(np.sum(truth[data[:, 4+i] == 1]))} for i in range(5)}}
    days = []
    for day in np.unique((steps - 1) // 24):
        start = int(np.searchsorted(steps, day * 24 + 1))
        end = int(np.searchsorted(steps, (day + 1) * 24, side='right'))
        days.append({'step_from': int(steps[start]), 'step_to': int(steps[end-1]),
                     'rows': end-start, 'positives': int(np.sum(y[start:end])),
                     'prevalence': float(np.mean(y[start:end])),
                     'mean_log_amount_feature': float(np.mean(x[start:end, 0]))})
    return {'windows': output, 'development_24_step_blocks': days}


def run(csv_path, baseline_path, protocol_path, output):
    protocol = json.loads(Path(protocol_path).read_text())
    validate_protocol(protocol)
    if sha256(csv_path) != protocol['dataset_sha256']:
        raise ValueError('Dataset SHA-256 differs from the frozen protocol')
    if sha256(baseline_path) != protocol['baseline_artifact_sha256']:
        raise ValueError('Baseline artifact differs from the frozen protocol')
    baseline = RiskModel(Path(baseline_path))
    if baseline.artifact['source_sha256'] != protocol['dataset_sha256']:
        raise ValueError('Baseline and dataset provenance mismatch')
    if (baseline.artifact['split']['train_step_lte'] != protocol['split']['tune_end'] or
            baseline.artifact['split']['validation_step_lte'] != protocol['split']['confirmation_end']):
        raise ValueError('Protocol cannot extend into the previously observed test partition')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'protocol.json', protocol)
    started = time.monotonic()
    x, y, steps = load_development(csv_path, protocol, output)
    parts = windows(steps, protocol)
    for name, section in parts.items():
        if not 0 < int(np.sum(y[section])) < len(y[section]):
            raise ValueError(f'{name} requires both classes; stop rather than change the split')
    report = {'protocol': protocol, 'protocol_sha256': sha256(protocol_path), 'runner_sha256': sha256(__file__),
              'environment': {'python': platform.python_version(), 'platform': platform.platform(),
                'dependencies': {name: importlib.metadata.version(name) for name in
                                 ('numpy', 'scipy', 'scikit-learn', 'joblib', 'threadpoolctl')}},
              'feature_schema': STATIC_NAMES, 'drift': drift_summary(x, y, steps, parts),
              'candidate_tuning': [], 'comparisons': {},
              'test_policy': f"No candidate predictions or metrics computed for steps >={protocol['split']['observed_test_start']}"}
    with threadpool_limits(limits=protocol['threads']):
        for candidate in protocol['candidates']:
            print(f"Fitting {candidate['id']} on inner training", flush=True)
            estimator, elapsed = fit_candidate(candidate, protocol, x, y, parts['fit'])
            scores = estimator.predict_proba(x[parts['tune'], columns(candidate)])[:, 1]
            measured = {'candidate': candidate, 'fit_seconds': elapsed,
                        'inner_tune_exact_ap': float(average_precision_score(y[parts['tune']], scores))}
            report['candidate_tuning'].append(measured)
            write_json(output / (candidate['id'] + '.tuning.json'), measured)
            print(json.dumps(measured), flush=True)
            del estimator, scores
        ranked = sorted(report['candidate_tuning'], key=lambda item: (-item['inner_tune_exact_ap'], item['candidate']['id']))
        report['selected_before_confirmation'] = ranked[0]['candidate']['id']
        winners = [next(item['candidate'] for item in ranked if item['candidate']['family'] == family)
                   for family in ('logistic', 'hist_tree')]
        report['family_winners'] = winners
        for candidate in winners + [None]:
            if candidate is not None:
                print(f"Refitting {candidate['id']} on original full training window", flush=True)
                estimator, elapsed = fit_candidate(candidate, protocol, x, y, parts['refit'])
                score = lambda section: estimator.predict_proba(x[section, columns(candidate)])[:, 1]
                name = candidate['id']
            else:
                elapsed = None
                def score(section):
                    z = x[section, :len(FEATURE_NAMES)] @ np.asarray(baseline.weights) + baseline.bias
                    return 1 / (1 + np.exp(-np.clip(z, -45, 45)))
                name = 'original_single_pass_sgd'
            calibration_scores = score(parts['calibration'])
            thresholds = choose_thresholds(y[parts['calibration']], calibration_scores,
                                           protocol['review_rates_per_10000'])
            if candidate is None:
                thresholds['historical_threshold_previously_selected_on_all_validation'] = baseline.threshold
            measured = {'refit_seconds': elapsed, 'thresholds_from_calibration': thresholds,
                'calibration': assessment(y[parts['calibration']], calibration_scores, thresholds, steps[parts['calibration']]),
                'confirmation': assessment(y[parts['confirmation']], score(parts['confirmation']), thresholds, steps[parts['confirmation']])}
            report['comparisons'][name] = measured
            write_json(output / (name + '.comparison.json'), measured)
            print(f"Completed locked development comparison: {name}", flush=True)
            if candidate is not None:
                del estimator
    if sha256(csv_path) != protocol['dataset_sha256'] or sha256(baseline_path) != protocol['baseline_artifact_sha256']:
        raise ValueError('Input integrity changed during the experiment; results invalid')
    report['elapsed_seconds'] = time.monotonic() - started
    report['status'] = 'complete_development_experiment_not_independent_test_validation'
    write_json(output / 'report.json', report)
    print(f'Completed report: {output / "report.json"}', flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv_path', type=Path)
    parser.add_argument('baseline_path', type=Path)
    parser.add_argument('--protocol', type=Path, default=Path(__file__).with_name('phase2_protocol.json'))
    parser.add_argument('--output', type=Path, required=True, help='New local directory; existing directories are rejected')
    args = parser.parse_args()
    run(args.csv_path, args.baseline_path, args.protocol, args.output)


if __name__ == '__main__':
    main()
