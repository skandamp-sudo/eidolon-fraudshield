# Scientific evaluation and honest claims

The included model is a **functional dependency-free starter baseline**, not a validated fraud detection solution for use in a bank.

## Current baseline

- Source: seeded, generated PaySim-like toy events, 12,000 rows
- Split: earlier 70% train / next 15% validation / last 15% untouched test (by generation order, time-step grouping approximated)
- Features: log amount, value bands, transaction type, simulated hour — **balance fields and fraud labels excluded**
- Learner: simple standard-library logistic SGD model
- Threshold: selected to maximize F1 on synthetic validation data
- Metrics: see `models/baseline.json`; reports F1, precision, recall, false-positive rate and average precision
- Scoring: 0–100 uncalibrated model score; contribution explanations, not causal attributions

## Next rigorous benchmark

1. Download and document PaySim dataset version and license/usage terms. It is **synthetic**, not live bank records.
2. Use an agreed chronological split in PaySim by time-step, keeping time steps entirely within one partition. Do not use the label, `isFlaggedFraud`, name ID leakage or **any PaySim balance fields** as predictive features (dataset author warning).
3. Train logistic regression and gradient boosted trees on training time steps only; tune threshold using validation steps only. Never report a resampled/downsampled evaluation set as if it represented natural fraud prevalence.
4. Evaluate once on the untouched future time window. Report PR-AUC, fraud-class precision and recall, confusion matrix, false-positive rate, alert volume at the natural base rate, and 95% bootstrap uncertainty where viable.
5. Compare models on identical splits, report decision latency percentiles p50/p95/p99 and throughput, and benchmark on actual IBM LinuxONE hardware.
6. If using the ULB Credit Card Fraud dataset, recognize its anonymized `Time`/`Amount` + PCA features are a **different input schema**. Train a separate adapter/model; do not feed it to the PaySim schema as though equivalent.
7. Observe possible concept drift and feature/schema evolution. Document drift measurements and how the alerts are evaluated by an analyst.

## Red flags to avoid in the judging pitch

- No claim of '99.9% detection', measured fraud savings, 'IBM Z acceleration' or production readiness unless independently measured.
- Do not mix synthetic generator labels into supposed real bank performance results.
- Do not interpret a logistic output as a calibrated fraud probability without calibration on representative data.
- Do not automatically block transactions, and do not store personal account identifiers in a public demo.
