"""Offline portable scoring, parity verification and local timing. No third-party imports."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import platform
import statistics
import time

from .portable import PortableModel, checked_json, features


def demo_events():
    """Deterministic computational fixture; not a fraud-accuracy dataset."""
    kinds = ('TRANSFER', 'CASH_OUT', 'CASH_IN', 'PAYMENT', 'DEBIT')
    amounts = (0, 1, 5000, 5000.000001, 20000, 100000, 100000.000001, 1e12)
    return [{'step': i % 744, 'type': kinds[i % len(kinds)], 'amount': amounts[i % len(amounts)]}
            for i in range(256)]


def verify(model, path, digest):
    bundle = checked_json(path, digest, max_bytes=8_000_000)
    if (not isinstance(bundle, dict) or set(bundle) != {'format', 'artifact_sha256', 'absolute_tolerance', 'cases'} or
            bundle['format'] != 'eidolon-portable-parity-v1' or bundle['artifact_sha256'] != model.sha256 or
            type(bundle['absolute_tolerance']) is not float or bundle['absolute_tolerance'] != 1e-12 or
            not isinstance(bundle['cases'], list) or not 1 <= len(bundle['cases']) <= 20_000):
        raise ValueError('Invalid parity bundle')
    max_error = 0.0
    mismatches = {name: 0 for name in model.thresholds}
    for case in bundle['cases']:
        if not isinstance(case, dict) or set(case) != {'features', 'score'}:
            raise ValueError('Invalid parity case')
        expected = case['score']
        if type(expected) not in (int, float) or not 0 <= expected <= 1 or not math.isfinite(expected):
            raise ValueError('Invalid reference score')
        actual = model.score_features(case['features'])
        max_error = max(max_error, abs(actual - expected))
        for name, threshold in model.thresholds.items():
            if threshold is not None:
                mismatches[name] += int((actual >= threshold) != (expected >= threshold))
    if max_error > 1e-12 or any(mismatches.values()):
        raise ValueError('Portable score or decision parity failed; do not deploy')
    return {'status': 'parity_passed', 'vectors': len(bundle['cases']),
            'max_absolute_error': max_error, 'absolute_tolerance': 1e-12, 'decision_mismatches': mismatches}


def benchmark(model, iterations=10_000, repeats=3):
    if type(iterations) is not int or not 100 <= iterations <= 100_000 or type(repeats) is not int or not 1 <= repeats <= 5:
        raise ValueError('Benchmark requires 100..100000 iterations and 1..5 repeats')
    events = demo_events()
    vectors = [features(event) for event in events]
    measured = {}
    for name, function, inputs in [('feature_vector_inference', model.score_features, vectors),
                                   ('event_validation_features_and_inference', model.predict, events)]:
        for i in range(100):
            function(inputs[i % len(inputs)])
        latencies, runs = [], []
        for _ in range(repeats):
            start = time.perf_counter_ns()
            for i in range(iterations):
                sample_start = time.perf_counter_ns()
                function(inputs[i % len(inputs)])
                latencies.append(time.perf_counter_ns() - sample_start)
            elapsed = (time.perf_counter_ns() - start) / 1e9
            runs.append({'seconds': elapsed, 'inferences_per_second': iterations / elapsed})
        ordered = sorted(latencies)
        percentile = lambda value: ordered[math.ceil(value * len(ordered)) - 1] / 1000
        measured[name] = {'runs': runs, 'samples': len(ordered), 'latency_microseconds': {
            'mean': statistics.mean(ordered) / 1000, 'p50': percentile(.50),
            'p95': percentile(.95), 'p99': percentile(.99)},
            'median_inferences_per_second': statistics.median(run['inferences_per_second'] for run in runs)}
    return {'status': 'measured_local_inference_only', 'artifact_sha256': model.sha256,
            'dataset_sha256': model.provenance['dataset_sha256'],
            'measured_at_utc': datetime.now(timezone.utc).isoformat(),
            'environment': {'platform': platform.platform(), 'machine': platform.machine(),
                            'python': platform.python_version(), 'implementation': platform.python_implementation()},
            'method': {'fixture': '256 deterministic amount/type/step edge events, no labels',
                       'concurrency': 1, 'warmup_per_mode': 100, 'iterations_per_repeat': iterations,
                       'repeats': repeats, 'clock': 'perf_counter_ns',
                       'scope': 'in-process inference, includes timing overhead; excludes model load, HTTP and SQLite'},
            'measurements': measured}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--sha256', required=True, help='Expected artifact digest from trusted export report')
    parser.add_argument('--dataset-sha256', required=True)
    parser.add_argument('--output', type=Path, help='Fresh JSON output file, never overwritten')
    sub = parser.add_subparsers(dest='command', required=True)
    score = sub.add_parser('score')
    score.add_argument('--event', required=True, help='JSON transaction with step, type and amount')
    score.add_argument('--operating-point', default='max_f1')
    check = sub.add_parser('verify')
    check.add_argument('--vectors', type=Path, required=True)
    check.add_argument('--vectors-sha256', required=True)
    timing = sub.add_parser('benchmark')
    timing.add_argument('--iterations', type=int, default=10000)
    timing.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    # Fail before doing expensive work if the chosen output already exists.
    if args.output and args.output.exists():
        parser.error('Output already exists; use a fresh path')
    try:
        model = PortableModel(args.model, expected_sha256=args.sha256, expected_dataset_sha256=args.dataset_sha256)
        if args.command == 'score':
            if len(args.event) > 65536:
                raise ValueError('Event exceeds size limit')
            result = model.predict(json.loads(args.event), operating_point=args.operating_point)
        elif args.command == 'verify':
            result = verify(model, args.vectors, args.vectors_sha256)
        else:
            result = benchmark(model, args.iterations, args.repeats)
        encoded = json.dumps(result, indent=2, allow_nan=False) + '\n'
        if args.output:
            with args.output.open('x') as output:
                output.write(encoded)
        print(encoded, end='')
    except (OSError, ValueError, RecursionError) as exc:
        parser.exit(1, f'Portable operation failed: {exc}\n')


if __name__ == '__main__':
    main()
