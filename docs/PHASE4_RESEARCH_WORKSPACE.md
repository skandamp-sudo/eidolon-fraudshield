# Phase 4 — Optional research scoring workspace

**Status:** experimental branch; do not claim verified tests or deployment until run.

The main dashboard and `POST /api/score` keep using the existing synthetic FS-01 model, its risk tiers, replay and persistent review workflow. The separate Phase 3 PaySim histogram-tree scorer is **not** the default and must never be interpreted as calibrated fraud probability or independently validated real-bank accuracy.

## Configuration

Without configuration, `GET /api/research/status` returns `available: false` and `POST /api/research/score` returns HTTP 503. To enable the separate scorer from the project root, supply the existing locally exported (ignored) artifact and its independently trusted fingerprints:

```bash
export FRAUDSHIELD_RESEARCH_MODEL="$PWD/models/paysim.phase3.local.json"
export FRAUDSHIELD_RESEARCH_SHA256="4278a146ef1bd77039173e5083d6609e5b8fa8c417988cdfd905fecb0de06363"
export FRAUDSHIELD_RESEARCH_DATASET_SHA256="16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b"
python3 -S run.py
```

The model validates its artifact digest, provenance dataset digest, feature schema and source fingerprints at startup. **If validation fails, startup fails closed.** Do not copy the model JSON into tracked source or commit any datasets.

## Explicit research API

```bash
curl -s http://127.0.0.1:8000/api/research/status
curl -s -X POST http://127.0.0.1:8000/api/research/score \
  -H 'Content-Type: application/json' \
  -d '{"step":24,"type":"TRANSFER","amount":200000,"operating_point":"max_f1"}'
```

Accepted fields: `step`, `type`, `amount`, optionally `operating_point` from the artifact's six locked choices. Balances, IDs, labels, flags, and arbitrary operating points are rejected. The output is a **research-only, uncalibrated score** and alert decision with model version and SHA-256.

**No research result is inserted in the synthetic SQLite transaction table.** It is not eligible for the demo's reviews, metrics, dashboard risk distribution or replay. No real funds are transferred or blocked.

## Verification

```bash
python3 -S -B -m unittest discover -s tests -v
```

Also run a real artifact smoke test with the canonical JSON file, confirm `/api/research/score` returns the locally recorded reference score, then verify `/api/state` event counts remain unchanged. Run parity and hardware tests from [the Phase 3 runbook](PHASE3_PORTABLE_RUNBOOK.md) before making LinuxONE claims.

## Limits

No new user-facing research dashboard is added in this backend-first change. The API is a local development research sandbox; it remains unauthenticated and loopback-only. Never expose it on the public Internet or conflate its results with independently validated production fraud detection.
