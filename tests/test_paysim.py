import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fraudshield.paysim import REQUIRED, train_and_evaluate
from fraudshield.model import RiskModel
from fraudshield.server import ROOT


class PaySimTests(unittest.TestCase):
    def write_fixture(self, path, reverse=False, changed_balances=False):
        names = sorted(REQUIRED)
        with path.open('w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=names)
            writer.writeheader()
            steps = list(range(1, 11))
            if reverse:
                steps.reverse()
            for step in steps:
                for index in range(20):
                    fraud = int(index in (1, 2))
                    row = {name: '0' for name in names}
                    row.update(step=str(step), type='TRANSFER' if fraud else 'PAYMENT',
                               amount='70000' if fraud else '120', isFraud=str(fraud),
                               nameOrig=f'ORIGIN-{step}-{index}', nameDest='DESTINATION')
                    if changed_balances:
                        row.update(oldbalanceOrg='999999', newbalanceOrig='3333',
                                   oldbalanceDest='4444', newbalanceDest='5555',
                                   isFlaggedFraud='1', nameOrig='REPLACED')
                    writer.writerow(row)

    def test_temporal_split_and_no_balance_or_flag_features(self):
        with TemporaryDirectory() as temp:
            path = Path(temp)/'paysim.csv'
            output = Path(temp)/'paysim.local.json'
            self.write_fixture(path)
            first = train_and_evaluate(path, output)
            self.assertEqual(first['split']['train_step_lte'], 7)
            self.assertEqual(first['split']['validation_step_lte'], 9)
            self.assertEqual(first['split']['partitions']['test']['rows'], 20)
            self.assertEqual(first['test']['tp'] + first['test']['fn'], 2)
            self.assertEqual(json.loads(output.read_text())['source_sha256'], first['source_sha256'])
            loaded = RiskModel(output)
            self.assertEqual(loaded.artifact['version'], 'paysim-chronological-1')
            self.write_fixture(path, changed_balances=True)
            second = train_and_evaluate(path, output)
            for key in ('weights', 'bias', 'threshold', 'validation', 'test'):
                self.assertEqual(first[key], second[key])
            self.assertNotEqual(first['source_sha256'], second['source_sha256'])

    def test_unsorted_csv_rejected_and_no_artifact_written(self):
        with TemporaryDirectory() as temp:
            path = Path(temp)/'paysim.csv';output = Path(temp)/'model.json'
            self.write_fixture(path, reverse=True)
            with self.assertRaisesRegex(ValueError, 'not sorted'):
                train_and_evaluate(path, output)
            self.assertFalse(output.exists())

    def test_baseline_artifact_cannot_be_replaced(self):
        with TemporaryDirectory() as temp:
            path = Path(temp)/'paysim.csv'
            self.write_fixture(path)
            with self.assertRaisesRegex(ValueError, 'must not replace'):
                train_and_evaluate(path, ROOT/'models'/'baseline.json')


if __name__ == '__main__':
    unittest.main()
