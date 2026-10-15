"""Portable, dependency-free baseline classifier. Scores are NOT calibrated probabilities."""
from __future__ import annotations
import json
import math
from pathlib import Path
from .features import FEATURE_NAMES, FEATURE_DESCRIPTIONS, vector

class RiskModel:
    def __init__(self, artifact_path: Path):
        with open(artifact_path, encoding='utf8') as f:
            self.artifact = json.load(f)
        if self.artifact['features'] != FEATURE_NAMES:
            raise ValueError('Model feature schema mismatch')
        self.weights = self.artifact['weights']
        self.bias = self.artifact['bias']
        self.threshold = self.artifact['threshold']
        if (not isinstance(self.weights, list) or len(self.weights) != len(FEATURE_NAMES)
                or any(isinstance(w, bool) or not isinstance(w, (int, float)) or not math.isfinite(w)
                       for w in self.weights)
                or isinstance(self.bias, bool) or not isinstance(self.bias, (int, float))
                or not math.isfinite(self.bias)
                or isinstance(self.threshold, bool) or not isinstance(self.threshold, (int, float))
                or not math.isfinite(self.threshold) or not 0 < self.threshold < 1
                or not isinstance(self.artifact.get('version'), str)
                or not self.artifact['version']):
            raise ValueError('Invalid model artifact parameters')

    def predict(self, event: dict) -> dict:
        feats = vector(event)
        z = self.bias + sum(w * x for w, x in zip(self.weights, feats))
        score = 1.0 / (1.0 + math.exp(-max(-45.0, min(45.0, z))))
        contributions = sorted(((w*x, FEATURE_DESCRIPTIONS[k]) for k, w, x in zip(FEATURE_NAMES, self.weights, feats) if x > 0 and w*x > .08), reverse=True)
        reasons = [label for _,label in contributions[:3]]
        if not reasons:
            reasons = ['No significant positive model contributions']
        if score >= self.threshold:
            decision, tier = 'ESCALATE', 'HIGH'
        elif score >= self.threshold * .45:
            decision, tier = 'REVIEW', 'MEDIUM'
        else:
            decision, tier = 'ALLOW', 'LOW'
        return dict(score=round(score * 100, 2), tier=tier, decision=decision,
                    reasons=reasons, model_version=self.artifact['version'])
