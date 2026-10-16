# EIDOLON // FRAUDSHIELD

**Explainable financial fraud intelligence — IBM Z Datathon 2026 proof of concept.**

> **Status: working local MVP, NOT a production fraud platform.** The dashboard's bundled classifier is trained and measured **only on our generated synthetic examples**. Its 0–100 output is a model risk score, not a calibrated probability. A separate, optional PaySim training pipeline exists, but its artifact is never loaded by the demo automatically. No money is moved, no accounts are blocked, and no real customer data is required. The dashboard displays monetary values as **SU (simulation units)**, not rupees or any asserted bank currency.

![Screenshot of the demo dashboard with simulated records](dashboard-preview.png)

## What's implemented

- Self-contained, polished responsive dashboard with risk chart, classifications and alerts
- Validated transaction scoring API; standardized, shared training and inference features
- Portable **standard-library logistic regression** baseline with chronological synthetic train/validation/test partitions
- 85-event synthetic replay worker and automatically updating dashboard
- Persistent SQLite transaction history, analyst review actions, review audit log
- Synthetic test precision/recall/F1/false-positive-rate metrics included in the model artifact
- PaySim CSV replay and streaming external-dataset evaluation utilities
- Separate, streaming PaySim training with whole-step chronological partitions and a future-step test
- Dependency-free runtime and tests: **Python 3.10+, no Docker, no Node, no API key, no pip install**

## Quick start

### macOS / Linux / IBM LinuxONE

```bash
cd eidolon-fraudshield
python3 run.py
```

### Windows PowerShell

```powershell
cd eidolon-fraudshield
py run.py
```

Open **http://127.0.0.1:8000**. Click **Start live replay** or **Score transaction**. Open an event to inspect the reasons and record analyst disposition. Data is saved to `data/fraudshield.sqlite3`.

To run tests and retrain the included synthetic model:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/train_model.py
```

Optional server port (macOS / Linux): `PORT=8080 python3 run.py`. On Windows PowerShell: `$env:PORT="8080"; py run.py`.

## PaySim dataset integration

The publicly available [PaySim dataset](https://www.kaggle.com/datasets/ealaxi/paysim1) is **itself synthetic financial data**, not actual banking records. Download it through the data provider and extract its CSV (the CSV is not bundled or auto-downloaded).

When the app is running, replay selected CSV records:

```bash
python3 scripts/replay_paysim.py /path/to/paysim.csv --limit 100 --delay 0.10 --min-step 300
```

To evaluate our *synthetic-trained* baseline on PaySim without saving data:

```bash
python3 scripts/evaluate_paysim.py /path/to/paysim.csv --min-step 600
```

**Interpretation warning:** This script is an out-of-domain check of the synthetic-trained model. The separate PaySim baseline and Phase 2 development experiments described below have different training provenance.

To train and evaluate a **separate** PaySim model after obtaining the canonical CSV:

```bash
python3 scripts/train_paysim.py /path/to/paysim.csv
```

The input must have the canonical PaySim columns and be sorted by nondecreasing `step`. The original pipeline uses whole steps for training, validation and a future test. It saves to ignored `models/paysim.local.json`; **do not rerun it over the preserved original artifact**. The dashboard still loads `models/baseline.json`. The completed local MacBook baseline on 6,362,620 rows is preserved in [the versioned benchmark report](benchmarks/paysim-baseline-v1.json), including dataset/artifact hashes and the previously observed future-test metrics. No dataset or local trained model is committed.

### Phase 2 development comparisons

The optional [Phase 2 runner](docs/PHASE2_REPRODUCIBILITY.md) compares batch logistic models and histogram trees using only steps through 378. Candidate selection, threshold calibration and later development confirmation use separate chronological windows. The previously observed future test is excluded. See the [scientific audit and frozen protocol](docs/PHASE2_SCIENTIFIC_AUDIT.md) and [measured results and limitations](docs/PHASE2_RESULTS.md). Training dependencies are isolated in `requirements-training.txt`; the application remains dependency free. Any validated replacement requires approval before changing the dashboard model.

### Phase 3 portable inference

The locked Phase 2 tree now has a separate [validated JSON export and standard-library inference workflow](docs/PHASE3_PORTABLE_RUNBOOK.md). Local parity and timing evidence is in [Phase 3 results](docs/PHASE3_RESULTS.md). The [new-source validation plan](docs/PHASE3_VALIDATION_PLAN.md) specifies a fresh simulation realization; that dataset is not yet available. The historical future window remains a previously exposed holdout. No new fraud-accuracy or LinuxONE deployment claim is made, and the synthetic dashboard model remains the default.

**Leakage warning:** [PaySim's dataset description](https://www.kaggle.com/ealaxi/paysim1) states that fraud is cancelled and cautions against using origin/destination balance columns as predictive inputs. The model feature map uses only `step`, `type` and `amount`; the offline pipeline reads `isFraud` separately as the target. Account identifiers, balance columns and `isFlaggedFraud` are never predictors. The demo API still accepts pre-transaction balances for display.

## System diagram

```text
Synthetic replay OR PaySim CSV event stream
                     │
                     ▼
            Input validation / API
                     │
                     ▼
             Shared feature map
                     │
                     ▼
          FS-01 risk-scoring model
                     │
            ┌────────┴─────────┐
            ▼                  ▼
     SQLite event store   Reasons + decision
            │                  │
            └────────┬─────────┘
                     ▼
         Live browser console
                     │
                     ▼
      Analyst review / audit trail
```

### REST API

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/api/health` | Health / model version |
| `GET` | `/api/state` | Dashboard state, model context, replay progress |
| `GET` | `/api/events?limit=60` | Recent transactions |
| `POST` | `/api/score` | Score and store a PaySim-like event |
| `POST` | `/api/demo/start` | Start synthetic event replay, `{"count":85}` |
| `POST` | `/api/demo/reset` | Delete local demo events, `{}` |
| `POST` | `/api/review` | Analyst disposition, `{"id":1,"disposition":"INVESTIGATING"}` |

Example manual score:

```bash
curl -X POST http://127.0.0.1:8000/api/score \
  -H 'Content-Type: application/json' \
  -d '{"step":36,"type":"TRANSFER","amount":68000,"oldbalanceOrg":72000,"oldbalanceDest":4000,"transactionId":"TEST-001"}'
```

### Model caveats

- Threshold is selected on the synthetic validation partition, not test.
- Metrics from `models/baseline.json` apply **only** to our generated synthetic distribution.
- Explanations list positive logistic feature contributions, not counterfactual or causal evidence.
- No data drift monitoring, calibrated probabilities, authentication, production throughput/latency SLOs or real banking integration yet.
- The unauthenticated development server now rejects non-loopback binding, unexpected Host/Origin values and non-JSON mutation requests. Local processes remain able to call its API. For any shared deployment, add authentication, access controls, transport security, retention policy and audit integrity. **Never expose this development server to the open Internet.**

## Event schedule (IST)

- **Oct 16, 2026, 7:30 PM** — mandatory LinuxONE setup session
- **Oct 17, 2026, 9–10 AM** — global Datathon kickoff; final-project submission opens at 10 AM
- **Oct 18, 2026, 10 AM** — team lead's final project submission deadline

See [IBM Z deployment instructions](docs/IBM_Z_DEPLOYMENT.md), [scientific validation plan](docs/VALIDATION.md) and [engineering audit](docs/AUDIT.md).

## Roadmap

1. **Built:** functional synthetic end-to-end demonstrator with recording and analyst review.
2. **Measured local baseline; Phase 2 development comparisons:** original PaySim results are preserved, with optional logistic/tree experiments and capacity thresholds. Independent future validation, uncertainty estimates and hardware benchmarking remain open.
3. **Next:** deploy and verify on actual IBM LinuxONE `s390x`, capture host diagnostics and demo evidence.
4. **Next:** final pitch, architecture, risk/limitations slides and recorded walkthrough.

Project name: **EIDOLON FRAUDSHIELD**. Challenge: **Real-Time AI for Critical Decisions**.
