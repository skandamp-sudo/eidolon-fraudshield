"""Portable inference integrity, parser boundaries and numerical parity."""
import copy
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from fraudshield.portable import (FEATURES, FEATURE_SPEC, FORMAT, PortableModel,
                                 features, fingerprint)
from fraudshield.portable_cli import verify

ROOT = Path(__file__).resolve().parents[1]
AVAILABLE = all(importlib.util.find_spec(name) for name in ('numpy', 'scipy', 'sklearn'))


def fixture_artifact():
    protocol = json.loads((ROOT / 'experiments/phase3_protocol.json').read_text())
    provenance = {key: protocol[key] for key in ('dataset_sha256', 'baseline_artifact_sha256',
                 'phase2_protocol_sha256', 'phase2_report_sha256', 'training_rows', 'training_step_lte', 'seed')}
    provenance.update(training_recipe='hist_tree_leaf7_balanced', sklearn_version='1.7.2',
                      exporter_sha256=fingerprint(ROOT / 'experiments/export_portable.py'),
                      portable_source_sha256=fingerprint(ROOT / 'fraudshield/portable.py'),
                      base_features_sha256=fingerprint(ROOT / 'fraudshield/features.py'))
    return {'format': FORMAT, 'version': 'paysim-phase2-locked-tree-v1', 'feature_spec': FEATURE_SPEC,
            'features': list(FEATURES), 'provenance': provenance,
            'thresholds': dict(protocol['locked_thresholds']), 'default_threshold': 'max_f1', 'bias': 0.0,
            'trees': [[{'feature': 0, 'threshold': .5, 'left': 1, 'right': 2}, {'leaf': -2.0}, {'leaf': 2.0}]]}


class PortableTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'model.json'
        self.artifact = fixture_artifact()

    def load(self, value=None):
        value = self.artifact if value is None else value
        self.path.write_text(json.dumps(value))
        return PortableModel(self.path, expected_sha256=fingerprint(self.path),
                             expected_dataset_sha256=self.artifact['provenance']['dataset_sha256'])

    def test_numeric_branch_equality_and_sigmoid(self):
        model = self.load()
        row = [0.] * len(FEATURES)
        for x, raw in ((.5, -2), (math.nextafter(.5, -math.inf), -2), (math.nextafter(.5, math.inf), 2)):
            row[0] = x
            self.assertAlmostEqual(model.score_features(row), 1/(1+math.exp(-raw)), places=15)

    def test_artifact_and_dataset_fingerprints_required(self):
        self.load()
        for artifact_hash, dataset_hash in [('0'*64, self.artifact['provenance']['dataset_sha256']),
                                           (fingerprint(self.path), '0'*64), ('', '0'*64)]:
            with self.assertRaises(ValueError):
                PortableModel(self.path, expected_sha256=artifact_hash, expected_dataset_sha256=dataset_hash)

    def test_schema_provenance_and_threshold_validation(self):
        for target, key, value in [(None, 'format', 'pickle'), (None, 'features', ['isFraud']),
                (None, 'feature_spec', 'unknown'), (None, 'default_threshold', 'invented'),
                ('provenance', 'seed', True), ('provenance', 'sklearn_version', 'future'),
                ('provenance', 'portable_source_sha256', '0'*64), ('provenance', 'base_features_sha256', '0'*64),
                ('thresholds', 'max_f1', None), ('thresholds', 'max_f1', True),
                ('thresholds', 'max_f1', 1.1), (None, 'bias', 10**1000)]:
            with self.subTest(key=key, value=str(value)[:40]):
                data = copy.deepcopy(self.artifact)
                (data if target is None else data[target])[key] = value
                with self.assertRaises(ValueError): self.load(data)

    def test_invalid_tree_graphs_and_resource_bounds(self):
        invalid = [[], [[{'leaf': 0}]]*101, [[{'leaf': 0}]*14],
            [[{'feature': 0, 'threshold': 0, 'left': 0, 'right': 1}, {'leaf': 1}]],
            [[{'feature': 0, 'threshold': 0, 'left': 1, 'right': 1}, {'leaf': 1}]],
            [[{'feature': 0, 'threshold': 0, 'left': 1, 'right': 99}, {'leaf': 1}]],
            [[{'feature': 18, 'threshold': 0, 'left': 1, 'right': 2}, {'leaf': 1}, {'leaf': 2}]],
            [[{'leaf': 0}, {'leaf': 1}]], [[{'leaf': float('nan')}]],
            [[{'leaf': 0, 'command': 'do not execute'}]],
            [[{'feature': 0, 'threshold': 0, 'left': True, 'right': 2}, {'leaf': 1}, {'leaf': 2}]]]
        for trees in invalid:
            with self.subTest(trees=str(trees)[:100]):
                data = copy.deepcopy(self.artifact); data['trees'] = trees
                with self.assertRaises(ValueError): self.load(data)

    def test_bounded_duplicate_and_deep_json_rejected(self):
        for raw in ('{"format":1,"format":2}', '['*2000+']'*2000, ' '*1_000_001, '{"x":NaN}', '{'):
            self.path.write_text(raw)
            with self.assertRaises(ValueError):
                PortableModel(self.path, expected_sha256=fingerprint(self.path),
                              expected_dataset_sha256=self.artifact['provenance']['dataset_sha256'])

    def test_missing_and_nonfinite_inputs_rejected(self):
        model = self.load()
        for bad in (float('nan'), float('inf'), -float('inf'), True, '0', 10**1000):
            row = [0.]*18; row[0] = bad
            with self.subTest(bad=str(bad)[:30]), self.assertRaises(ValueError): model.score_features(row)
        for payload in ({'amount': 1, 'type': 'TRANSFER'}, {'step': 1, 'type': 'INVALID', 'amount': 1},
                        {'step': 1, 'type': 'TRANSFER', 'amount': float('nan')},
                        {'step': -1, 'type': 'TRANSFER', 'amount': 1}):
            with self.assertRaises(ValueError): model.predict(payload)
        with self.assertRaises(ValueError): model.score_features([0.]*17)
        with self.assertRaises(ValueError): model.predict({'step': 1, 'type': 'TRANSFER', 'amount': 1}, operating_point='new')

    def test_prediction_ignores_labels_ids_balances(self):
        model = self.load()
        event = {'step': 24, 'type': 'TRANSFER', 'amount': 1e12}
        poisoned = dict(event, isFraud=1, isFlaggedFraud=1, nameOrig='private', nameDest='private',
                        oldbalanceOrg='invalid', oldbalanceDest='invalid', newbalanceOrig=0, newbalanceDest=1e12)
        self.assertEqual(model.predict(event), model.predict(poisoned))
        self.assertEqual(len(features(event)), 18)
        self.assertEqual(model.predict(event)['threshold'], self.artifact['thresholds']['max_f1'])

    def test_golden_parity_pass_and_corruption_failure(self):
        model = self.load()
        path = Path(self.temp.name) / 'vectors.json'
        row = [0.]*18
        bundle = {'format': 'eidolon-portable-parity-v1', 'artifact_sha256': model.sha256,
                  'absolute_tolerance': 1e-12, 'cases': [{'features': row, 'score': model.score_features(row)}]}
        path.write_text(json.dumps(bundle))
        self.assertEqual(verify(model, path, fingerprint(path))['vectors'], 1)
        bundle['cases'][0]['score'] = .999
        path.write_text(json.dumps(bundle))
        with self.assertRaises(ValueError): verify(model, path, fingerprint(path))
        bundle['absolute_tolerance'] = 1.0
        path.write_text(json.dumps(bundle))
        with self.assertRaises(ValueError): verify(model, path, fingerprint(path))

    def test_cli_without_site_packages_and_output_preservation(self):
        model = self.load()
        output = Path(self.temp.name) / 'score.json'
        command = [sys.executable, '-S', '-B', '-m', 'fraudshield.portable_cli', '--model', str(self.path),
                   '--sha256', model.sha256, '--dataset-sha256', model.provenance['dataset_sha256'],
                   '--output', str(output), 'score', '--event', '{"step":1,"type":"TRANSFER","amount":10000}']
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        original = output.read_bytes()
        self.assertEqual(json.loads(original)['artifact_sha256'], model.sha256)
        self.assertNotEqual(subprocess.run(command, cwd=ROOT, capture_output=True).returncode, 0)
        self.assertEqual(output.read_bytes(), original)

    def test_frozen_phase2_inputs_and_thresholds(self):
        protocol = json.loads((ROOT / 'experiments/phase3_protocol.json').read_text())
        for name, path in [('phase2_protocol_sha256', 'experiments/phase2_protocol.json'),
                           ('phase2_runner_sha256', 'experiments/paysim_models.py'),
                           ('phase2_report_sha256', 'benchmarks/paysim-phase2-v1.json')]:
            self.assertEqual(protocol[name], fingerprint(ROOT / path))
        report = json.loads((ROOT / 'benchmarks/paysim-phase2-v1.json').read_text())
        self.assertEqual(protocol['selected_candidate'], report['selected_before_confirmation'])
        self.assertEqual(protocol['locked_thresholds'], report['comparisons'][protocol['selected_candidate']]['thresholds_from_calibration'])


@unittest.skipUnless(AVAILABLE, 'optional training dependencies not installed')
class ExportTests(unittest.TestCase):
    def test_export_matches_sklearn_on_events_and_every_split_boundary(self):
        import numpy as np
        from threadpoolctl import threadpool_limits
        from experiments.paysim_models import model_for, static_features
        from experiments.export_portable import export_estimator, representative_events, boundary_vectors, parity
        from fraudshield.features import clean_event
        protocol = json.loads((ROOT / 'experiments/phase2_protocol.json').read_text())
        estimator = model_for(protocol['candidates'][-1], protocol)
        events = representative_events(100)
        rows = [features(event) for event in events]
        self.assertEqual(rows, [static_features(clean_event(event)) for event in events])
        labels = np.asarray([int(event['type'] == 'TRANSFER' and event['amount'] > 5000) for event in events])
        with threadpool_limits(limits=2):
            estimator.fit(np.asarray(rows), labels)
            fixture = fixture_artifact()
            artifact = export_estimator(estimator, fixture['provenance'], fixture['thresholds'])
            with TemporaryDirectory() as temp:
                path = Path(temp) / 'fixture.json'; path.write_text(json.dumps(artifact))
                portable = PortableModel(path, expected_sha256=fingerprint(path),
                                         expected_dataset_sha256=fixture['provenance']['dataset_sha256'])
                boundaries = boundary_vectors(artifact['trees'])
                result, _ = parity(estimator, portable, rows+boundaries, fixture['thresholds'], 1e-12)
                self.assertLessEqual(result['max_absolute_error'], 1e-12)
                self.assertGreater(len(boundaries), 0)

    def test_export_training_loader_never_reads_later_labels_or_features(self):
        from experiments.export_portable import load_training
        from fraudshield.paysim import REQUIRED
        with TemporaryDirectory() as temp:
            directory = Path(temp); source = directory / 'fixture.csv'
            with source.open('w', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=sorted(REQUIRED)); writer.writeheader()
                for step in (1, 2, 3):
                    row = dict.fromkeys(REQUIRED, '0')
                    row.update(step=str(step), type='TRANSFER', amount='100', isFraud=str(step % 2))
                    if step == 3: row.update(type='DO_NOT_READ', amount='DO_NOT_READ', isFraud='DO_NOT_READ')
                    writer.writerow(row)
            digest = fingerprint(source)
            x, y = load_training(source, {'training_rows': 2, 'training_step_lte': 2, 'training_positives': 1}, directory)
            self.assertEqual(list(y), [1, 0]); self.assertEqual(len(x), 2)
            self.assertEqual(fingerprint(source), digest)


if __name__ == '__main__':
    unittest.main()
