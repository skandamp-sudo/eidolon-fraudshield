"""Bounded JSON histogram-tree inference; Python standard library only.

The trusted expected SHA-256 must be obtained independently of the artifact.
Scores are uncalibrated; this module does not replace the dashboard model.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re

from .features import FEATURE_NAMES, clean_event, vector

FORMAT = 'eidolon-hist-tree-v1'
FEATURE_SPEC = 'paysim-static-v2-1'
FEATURES = FEATURE_NAMES + [f'log_amount_x_{name}' for name in
                           ('transfer', 'cash_out', 'cash_in', 'payment', 'debit')]
FEATURES += ['hour_sin', 'hour_cos', 'log_amount_squared']
MAX_ARTIFACT_BYTES = 1_000_000


def fingerprint(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1_048_576), b''):
            digest.update(chunk)
    return digest.hexdigest()


def require_digest(value):
    if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('Expected a lowercase SHA-256 fingerprint')
    return value


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def _constant(value):
    raise ValueError('Non-finite JSON constant')


def checked_json(path, expected_sha256, max_bytes=MAX_ARTIFACT_BYTES):
    require_digest(expected_sha256)
    with Path(path).open('rb') as source:
        data = source.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError('JSON exceeds byte limit')
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError('JSON fingerprint mismatch')
    try:
        return json.loads(data, object_pairs_hook=_object, parse_constant=_constant)
    except (UnicodeError, RecursionError, ValueError) as exc:
        raise ValueError('Invalid bounded JSON') from exc


def _keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError('Unexpected artifact fields')


def _number(value, limit=1e12):
    if type(value) not in (int, float) or abs(value) > limit or not math.isfinite(value):
        raise ValueError('Invalid finite numeric value')
    return value


def features(payload):
    # Only these fields cross the prediction boundary. Balances/IDs/labels do not.
    if not isinstance(payload, dict) or not {'step', 'type', 'amount'} <= payload.keys():
        raise ValueError('step, type and amount are required')
    event = clean_event({name: payload[name] for name in ('step', 'type', 'amount')})
    base = vector(event)
    angle = 2 * math.pi * (event['step'] % 24) / 24
    return base + [base[0] * value for value in base[4:9]] + [
        math.sin(angle), math.cos(angle), base[0] ** 2]


class PortableModel:
    """Version 1: binary numeric trees, finite inputs, <=100 trees/13 nodes each."""

    def __init__(self, path, *, expected_sha256, expected_dataset_sha256):
        require_digest(expected_dataset_sha256)
        data = checked_json(path, expected_sha256)
        _keys(data, ('format', 'version', 'feature_spec', 'features', 'provenance',
                     'thresholds', 'default_threshold', 'bias', 'trees'))
        if data['format'] != FORMAT or data['feature_spec'] != FEATURE_SPEC or data['features'] != FEATURES:
            raise ValueError('Unsupported model format or feature schema')
        if data['version'] != 'paysim-phase2-locked-tree-v1':
            raise ValueError('Unsupported model version')
        provenance = data['provenance']
        _keys(provenance, ('dataset_sha256', 'baseline_artifact_sha256', 'phase2_protocol_sha256',
                          'phase2_report_sha256', 'training_recipe', 'training_rows', 'training_step_lte',
                          'seed', 'sklearn_version', 'exporter_sha256', 'portable_source_sha256', 'base_features_sha256'))
        for key in provenance:
            if key.endswith('_sha256'):
                require_digest(provenance[key])
        if (provenance['portable_source_sha256'] != fingerprint(__file__) or
                provenance['base_features_sha256'] != fingerprint(Path(__file__).with_name('features.py'))):
            raise ValueError('Portable inference source fingerprint mismatch')
        if provenance['dataset_sha256'] != expected_dataset_sha256:
            raise ValueError('Training dataset fingerprint mismatch')
        if (provenance['training_recipe'] != 'hist_tree_leaf7_balanced' or
                provenance['sklearn_version'] != '1.7.2' or type(provenance['seed']) is not int or
                provenance['seed'] != 74 or type(provenance['training_rows']) is not int or
                not 1 <= provenance['training_rows'] <= 10_000_000 or
                type(provenance['training_step_lte']) is not int or not 0 <= provenance['training_step_lte'] <= 323):
            raise ValueError('Unsupported training provenance')
        thresholds = data['thresholds']
        _keys(thresholds, ('max_f1', 'capacity_1_per_10000', 'capacity_5_per_10000',
                           'capacity_10_per_10000', 'capacity_25_per_10000', 'capacity_50_per_10000'))
        for value in thresholds.values():
            if value is not None and not 0 <= _number(value) <= 1:
                raise ValueError('Invalid threshold')
        if thresholds['max_f1'] is None or data['default_threshold'] != 'max_f1':
            raise ValueError('Missing locked default threshold')
        _number(data['bias'])
        trees = data['trees']
        if not isinstance(trees, list) or not 1 <= len(trees) <= 100:
            raise ValueError('Invalid tree count')
        for tree in trees:
            self._validate_tree(tree)
        self._trees = trees
        self._bias = data['bias']
        self.thresholds = dict(thresholds)
        self.provenance = dict(provenance)
        self.version = data['version']
        self.sha256 = expected_sha256

    @staticmethod
    def _validate_tree(tree):
        if not isinstance(tree, list) or not 1 <= len(tree) <= 13:
            raise ValueError('Invalid node count')
        seen = set()
        pending = [(0, 0)]
        while pending:
            index, depth = pending.pop()
            if type(index) is not int or not 0 <= index < len(tree) or index in seen or depth > 12:
                raise ValueError('Invalid tree graph, depth or child index')
            seen.add(index)
            node = tree[index]
            if isinstance(node, dict) and 'leaf' in node:
                _keys(node, ('leaf',))
                _number(node['leaf'])
            else:
                _keys(node, ('feature', 'threshold', 'left', 'right'))
                if type(node['feature']) is not int or not 0 <= node['feature'] < len(FEATURES):
                    raise ValueError('Invalid feature index')
                _number(node['threshold'])
                pending.extend(((node['left'], depth + 1), (node['right'], depth + 1)))
        if len(seen) != len(tree):
            raise ValueError('Unreachable tree nodes')

    def score_features(self, values):
        if not isinstance(values, (list, tuple)) or len(values) != len(FEATURES):
            raise ValueError('Feature vector length/type mismatch')
        for value in values:
            _number(value)
        raw = self._bias
        for tree in self._trees:
            index = 0
            while 'leaf' not in tree[index]:
                node = tree[index]
                index = node['left'] if values[node['feature']] <= node['threshold'] else node['right']
            # Exported leaf values already include learning-rate shrinkage.
            raw += tree[index]['leaf']
        if raw >= 0:
            return 1 / (1 + math.exp(-raw))
        exponential = math.exp(raw)
        return exponential / (1 + exponential)

    def predict(self, payload, *, operating_point='max_f1'):
        if operating_point not in self.thresholds:
            raise ValueError('Unknown locked operating point')
        score = self.score_features(features(payload))
        threshold = self.thresholds[operating_point]
        return {'risk_score': score, 'score_semantics': 'uncalibrated ranking score',
                'alert': threshold is not None and score >= threshold,
                'threshold': threshold, 'operating_point': operating_point,
                'model_version': self.version, 'artifact_sha256': self.sha256}
