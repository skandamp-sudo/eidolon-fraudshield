"""Scientific boundary tests. Optional estimator tests skip without training extras."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fraudshield.features import clean_event
from fraudshield.paysim import REQUIRED

ROOT = Path(__file__).resolve().parents[1]
AVAILABLE = all(importlib.util.find_spec(name) for name in ('numpy', 'scipy', 'sklearn'))


class FrozenBenchmarkTests(unittest.TestCase):
    def test_baseline_report_preserves_supplied_counts_without_model_weights(self):
        report = json.loads((ROOT / 'benchmarks/paysim-baseline-v1.json').read_text())
        measured = report['previously_observed_test']
        self.assertEqual([measured[k] for k in ('tp', 'fp', 'fn', 'tn')], [806, 2023, 3200, 912588])
        self.assertAlmostEqual(measured['precision'], 806 / 2829, places=6)
        self.assertEqual(report['provenance']['dataset_rows'], 6362620)
        self.assertNotIn('weights', report['model'])
        self.assertNotIn('bias', report['model'])


@unittest.skipUnless(AVAILABLE, 'optional training dependencies not installed')
class ExperimentTests(unittest.TestCase):
    def test_features_exclude_balances_labels_and_accounts(self):
        from experiments.paysim_models import static_features
        event = clean_event({'step': 30, 'type': 'TRANSFER', 'amount': 55000})
        altered = dict(event, isFraud=1, isFlaggedFraud=1, oldbalanceOrg=10**12,
                       oldbalanceDest=10**12, newbalanceOrig=999, newbalanceDest=999,
                       nameOrig='SECRET', nameDest='SECRET')
        self.assertEqual(static_features(event), static_features(altered))

    def test_capacity_never_splits_score_ties(self):
        import numpy as np
        from experiments.paysim_models import choose_thresholds, confusion
        y = np.array([1, 0, 1, 0])
        scores = np.array([.9, .9, .2, .1])
        thresholds = choose_thresholds(y, scores, [2500, 5000])
        self.assertIsNone(thresholds['capacity_2500_per_10000'])
        self.assertEqual(thresholds['capacity_5000_per_10000'], .9)
        measured = confusion(y, scores, thresholds['capacity_5000_per_10000'])
        self.assertEqual((measured['tp'], measured['fp'], measured['fn'], measured['tn']), (1, 1, 1, 1))
        # Capacity threshold is label independent, unlike F1 threshold.
        changed = choose_thresholds(1-y, scores, [5000])
        self.assertEqual(changed['capacity_5000_per_10000'], .9)

    def test_scaler_fitted_on_training_only_and_tree_has_no_random_holdout(self):
        import numpy as np
        from experiments.paysim_models import fit_candidate, model_for
        protocol = json.loads((ROOT / 'experiments/phase2_protocol.json').read_text())
        x = np.zeros((20, 18));x[:10, 0] = np.arange(10);x[10:, 0] = 100000
        y = np.tile([0, 1], 10)
        estimator, _ = fit_candidate(protocol['candidates'][0], protocol, x, y, slice(0, 10))
        self.assertEqual(estimator[0].mean_[0], 4.5)
        self.assertFalse(model_for(protocol['candidates'][-1], protocol).early_stopping)

    def test_end_to_end_never_parses_observed_test_features_or_labels(self):
        from experiments.paysim_models import run, sha256
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            csv_path = directory / 'fixture.csv'
            with csv_path.open('w', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=sorted(REQUIRED))
                writer.writeheader()
                for step in range(1, 10):
                    for index in range(20):
                        row = dict.fromkeys(REQUIRED, '0')
                        row.update(step=str(step), type='TRANSFER', amount=str(index * 100), isFraud=str(index % 2))
                        if step == 9:
                            row.update(type='MUST_NOT_READ', amount='MUST_NOT_READ', isFraud='MUST_NOT_READ')
                        writer.writerow(row)
            baseline = json.loads((ROOT / 'models/baseline.json').read_text())
            baseline.update(source_sha256=sha256(csv_path), split={'train_step_lte': 4, 'validation_step_lte': 8})
            baseline_path = directory / 'original.json'
            baseline_path.write_text(json.dumps(baseline))
            protocol = json.loads((ROOT / 'experiments/phase2_protocol.json').read_text())
            protocol.update(dataset_sha256=sha256(csv_path), baseline_artifact_sha256=sha256(baseline_path),
                            expected_development_rows=160,
                            split={'fit_end': 2, 'tune_end': 4, 'calibration_end': 6, 'confirmation_end': 8, 'observed_test_start': 9})
            protocol['candidates'] = [protocol['candidates'][0], protocol['candidates'][4]]
            protocol['tree_fixed'].update(max_iter=3, min_samples_leaf=2)
            protocol_path = directory / 'protocol.json';protocol_path.write_text(json.dumps(protocol))
            output = directory / 'run'
            report = run(csv_path, baseline_path, protocol_path, output)
            self.assertEqual(report['drift']['windows']['confirmation']['rows'], 40)
            self.assertIn('>=9', report['test_policy'])
            self.assertEqual(sha256(baseline_path), protocol['baseline_artifact_sha256'])
            self.assertEqual(sha256(csv_path), protocol['dataset_sha256'])
            with self.assertRaises(FileExistsError):
                run(csv_path, baseline_path, protocol_path, output)


if __name__ == '__main__':
    unittest.main()
