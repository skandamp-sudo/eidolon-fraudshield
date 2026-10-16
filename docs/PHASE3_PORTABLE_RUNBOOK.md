# Portable inference and LinuxONE demonstration runbook

## Local export (optional scientific environment only)

Use the same pinned environment as Phase 2. The runner checks installed versions, the frozen Phase 2 files, canonical CSV and original artifact before work. It refits only the locked winner on the original training partition; thresholds are copied, never recomputed. It rejects an existing output directory.

```bash
LOKY_MAX_CPU_COUNT=2 OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 \
  .venv-training/bin/python -B -u -m experiments.export_portable \
  /path/to/paysim.csv /path/to/preserved-paysim.local.json \
  --output .experiments/phase3-export-v1
```

No pickle is read or written. Export reads scikit-learn's private numeric tree representation, audited against 1.7.2 only. Numeric `<=` branches, the initial raw margin and already-shrunk leaf contributions are preserved; sigmoid is applied once after summing the trees. The format deliberately excludes categorical and missing-value routing. The application input contract requires finite amount/type/step features, and the portable runtime rejects NaN/infinite raw vectors.

A successful run writes:

- `paysim.phase3.local.json`: portable numeric model, feature schema, provenance and six fixed operating thresholds.
- `parity-vectors.local.json`: generated computational feature vectors and scikit-learn reference scores. No actual transaction records are included.
- `export-report.json`: final success record, hashes, parity errors, zero-mismatch checks, dependency versions and timings. **Do not use an artifact from an incomplete/failed export without this successful report.**
- Training working arrays and a protocol snapshot, all under the ignored `.experiments/` directory. Keep these local and private; transfer neither the arrays nor the CSV to the demo VM.

The original artifacts, Phase 2 files and dashboard default are preserved. The exported model and golden vector files are deliberately not committed to Git. Aggregate evidence can be reviewed and committed.

## Trust and compatibility checks

Obtain the expected model and golden-vector SHA-256 values from the reviewed export report through a trusted channel. Do not compute a checksum from an untrusted downloaded artifact and treat that checksum as authentication. SHA-256 detects substitution relative to a trusted fingerprint; it is not a signature or evidence of data authenticity.

The runtime checks the artifact digest, training dataset digest, exact feature/format version, source fingerprints, required provenance, threshold structure and every tree. JSON is capped at 1 MB; duplicate keys, non-finite values, cycles, shared/unreachable nodes, invalid indices and excess trees/nodes are rejected. The golden fixture file is capped at 8 MB and 20,000 cases. Model limits are 100 trees and 13 nodes per tree. There are no imports or commands specified by the artifact.

The runtime pins the bytes of `fraudshield/portable.py` and `fraudshield/features.py` recorded by the exporter. Transfer the matching source archive without line-ending conversion. A source mismatch requires an audited re-export, not disabling the check. Thresholds are interpreted on the unrounded score; scores are uncalibrated, especially for the class-weighted estimator.

## LinuxONE transfer and execution — not yet tested on hardware

Use an organizer-authorized VM and the existing [IBM Z runbook](IBM_Z_DEPLOYMENT.md). Do not expose this unauthenticated demo publicly. From the reviewed Phase 3 commit, create a tracked-source archive and transfer only source plus the model and golden vectors:

```bash
git archive --format=tar.gz --output=/tmp/fraudshield-phase3-source.tgz HEAD
scp /tmp/fraudshield-phase3-source.tgz \
  .experiments/phase3-export-v1/paysim.phase3.local.json \
  .experiments/phase3-export-v1/parity-vectors.local.json \
  <username>@<VM_HOST>:~/
ssh <username>@<VM_HOST>
```

On the VM, replace the fingerprint placeholders with the trusted report values. This is the runtime path: **do not install scikit-learn, NumPy or SciPy**.

```bash
umask 077
mkdir -p ~/eidolon-fraudshield-phase3
tar -xzf ~/fraudshield-phase3-source.tgz -C ~/eidolon-fraudshield-phase3
cd ~/eidolon-fraudshield-phase3
uname -m
python3 --version
python3 -S -c 'import sqlite3; print(sqlite3.sqlite_version)'
python3 -S -B -m unittest discover -s tests -v

export FRAUDSHIELD_MODEL_SHA='<trusted artifact_sha256>'
export FRAUDSHIELD_VECTORS_SHA='<trusted golden_vectors_sha256>'
export FRAUDSHIELD_DATASET_SHA='16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b'

python3 -S -B -m fraudshield.portable_cli \
  --model ~/paysim.phase3.local.json --sha256 "$FRAUDSHIELD_MODEL_SHA" \
  --dataset-sha256 "$FRAUDSHIELD_DATASET_SHA" --output parity-s390x.json \
  verify --vectors ~/parity-vectors.local.json --vectors-sha256 "$FRAUDSHIELD_VECTORS_SHA"

python3 -S -B -m fraudshield.portable_cli \
  --model ~/paysim.phase3.local.json --sha256 "$FRAUDSHIELD_MODEL_SHA" \
  --dataset-sha256 "$FRAUDSHIELD_DATASET_SHA" --output score-s390x.json \
  score --event '{"step":24,"type":"TRANSFER","amount":200000}'

python3 -S -B -m fraudshield.portable_cli \
  --model ~/paysim.phase3.local.json --sha256 "$FRAUDSHIELD_MODEL_SHA" \
  --dataset-sha256 "$FRAUDSHIELD_DATASET_SHA" --output inference-s390x.json \
  benchmark --iterations 10000 --repeats 3

python3 -S run.py
```

Require `uname -m` = `s390x`, Python >=3.10, successful runtime tests and golden parity before claiming portable execution. Optional scientific tests are expected to skip with `-S`; skips are not scientific-stack verification. Stop and preserve evidence if any gate fails. Commands intentionally refuse to overwrite output files; use new filenames for another run.

For the smoke event above, the local reference score is `0.7483462817308377` (tolerance 1e-12), with `alert=false` and threshold `0.9833296104213592`. Verify this event-to-score result as well as the raw-vector golden checks.

Open the **synthetic** dashboard through the SSH tunnel described in the existing runbook. Score/replay/review transactions and verify SQLite persistence after restart. Present the portable score JSON alongside it as a separate locked-model inference demonstration. The dashboard has not been switched to PaySim and its metrics must not be attributed to the exported tree.

## Evidence to retain

Record source commit/archive SHA-256, model/vector hashes, architecture, OS, Python/SQLite versions, full test output, parity/score/benchmark JSON, timestamp, and the synthetic dashboard persistence checks. Redact VM identifiers and credentials before publishing. The benchmark reports three sequential runs, 10,000 timed calls each, one caller, 100 warm-up calls per mode, latency percentiles and throughput. It measures in-process feature-vector inference and event-validation-plus-inference separately; excludes model loading, HTTP and SQLite. Timings include instrumentation overhead and are not concurrent service capacity.

Do not infer IBM Z latency from a MacBook result. No container, paid API, dataset transfer or scientific runtime stack is required for this demonstration. A fresh accuracy dataset and actual s390x hardware execution remain separate gates.
