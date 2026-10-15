#!/usr/bin/env python3
"""Train a separate PaySim artifact and evaluate once on future steps."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fraudshield.paysim import train_and_evaluate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv_path', type=Path, help='Local canonical PaySim CSV, sorted by step')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'models' / 'paysim.local.json')
    args = parser.parse_args()
    artifact = train_and_evaluate(args.csv_path, args.output)
    print(json.dumps({key: artifact[key] for key in ('source_sha256', 'split', 'validation', 'test', 'metric_note')}, indent=2))
    print(f'Saved separate model: {args.output}')
    print('PaySim is simulated data. These metrics do not measure real-bank fraud accuracy.')


if __name__ == '__main__':
    main()
