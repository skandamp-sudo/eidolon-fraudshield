# Phase 3 measured export and portable inference results

Implementation and new-source validation plan frozen at `085193c` before the full export. Phase 2 protocol, ranking report, candidate and thresholds are byte-preserved. No confirmation or previously exposed future-test evaluation was performed.

## Portable export

The locked recipe was reconstructed on all 4,463,587 original training rows through step 323. The original fitted Phase 2 estimator was not retained, so identity with its original bytes cannot be established. Parity here is between the reconstructed scikit-learn estimator and its export; it is not a new fraud-accuracy measurement.

- Format: `eidolon-hist-tree-v1`; 100 trees, 1,300 nodes, 108,717 bytes.
- Model SHA-256: `4278a146ef1bd77039173e5083d6609e5b8fa8c417988cdfd905fecb0de06363`.
- Golden-vector SHA-256: `44486332bb86c7acda7e566e2feaf5608843ed80c21e0e33453fac2404bbf166`.
- Default threshold: `0.9833296104213592`; all five capacity thresholds are copied exactly from Phase 2. Scores are uncalibrated.
- Refit: 25.193 seconds; export from training loading through completion: 89.749 seconds, locally.
- Portable model, golden vectors and a copy of the export report were saved as new ignored local `models/paysim.phase3.local.json`, `models/paysim.phase3.parity.local.json` and `models/paysim.phase3.export-report.local.json` files in the user's original checkout. No original file was overwritten and no fitted model/transaction rows were committed.

## Parity evidence

| Cases | Count | Maximum absolute score error | Threshold decision mismatches |
| --- | ---: | ---: | ---: |
| Synthetic events and split-boundary vectors | 4,320 | 1.1102230246251565e-16 | 0 across all six thresholds |
| Deterministically sampled training-only feature vectors | 4,096 | 1.1102230246251565e-16 | 0 across all six thresholds |

The 4,320 generated cases include 2,520 representative/edge transactions and 1,800 raw-vector probes immediately below, at and above all 600 internal numeric split thresholds. Every boundary fixture is checked to reach its intended node. Edge transactions cover all five types, hour boundaries, amount bands, zero, tiny values and the supported 1e12 amount limit. These are computational fixtures, not synthetic evidence of fraud accuracy. Training-only feature vectors remain local and are not in the golden bundle.

Portable feature construction matched the frozen Phase 2 transform on all 2,520 generated transactions. Standalone `python3 -S` verified the 4,320 golden raw-feature cases with the same error and no decision mismatches. Golden verification on another platform exercises tree inference; the runbook also requires an event-to-score smoke check because platform math libraries can differ. These cases do not prove equivalence for every possible input.

The local smoke transaction `(step=24, type=TRANSFER, amount=200000)` produced score `0.7483462817308377`, threshold `0.9833296104213592`, and `alert=false`. This is a functional demonstration; there is no ground-truth fraud label for it.

## Local performance only

Measured on macOS 26.7.1, x86_64, CPython 3.14.7 with site packages disabled. Three sequential repeats of 10,000 calls per mode, 100 warm-up calls, 256 fixed edge events, one caller. Timings include instrumentation; exclude model loading, HTTP and SQLite. No cross-platform speedup or service-capacity claim is supported.

| Mode | Median throughput / second | p50 latency (µs) | p95 (µs) | p99 (µs) |
| --- | ---: | ---: | ---: | ---: |
| feature_vector_inference | 23,416.7 | 41.259 | 65.290 | 109.612 |
| event_validation_features_and_inference | 21,065.2 | 46.434 | 65.056 | 115.608 |

No LinuxONE/s390x, Linux, ARM or Python 3.10 execution was performed. LinuxONE performance remains **NOT VERIFIED**.

## Tests and integrity checks

| Execution | Result |
| --- | --- |
| Focused new portable/export tests | 12 passed in 2.245 s |
| Full suite with pinned optional training dependencies | 30 passed in 2.541 s; 0 failures |
| Full suite with `python3 -S -B` | 24 passed, 6 optional scientific tests skipped in 0.906 s; 0 failures |
| Actual full locked export | Passed 8,416 score/decision parity cases |
| Exported golden fixtures using standard library only | 4,320 passed |
| Portable CLI event smoke | Passed, recorded score above |
| `python3 -m compileall -q fraudshield experiments tests scripts run.py` | Passed |
| Optional environment `pip check` | No broken requirements; cache unavailable warning only |
| `git diff --check` | Passed |

The 12 added tests cover: exact numeric branch boundaries/sigmoid; artifact and dataset fingerprints; schema/provenance/threshold checks; graph/node bounds; duplicate/deep/oversized JSON; missing/non-finite input rejection; exclusion of labels/IDs/balances; golden-case failure detection; CLI operation without site packages and output preservation; frozen Phase 2 inputs/thresholds; scikit-learn export parity; and stopping training parsing before later labels/features. Existing 18 tests remain intact. No separate typechecker/frontend build is configured or claimed.

## Security and remaining limitations

- New model loading is bounded JSON with independently supplied expected SHA-256, dataset fingerprint and source/schema checks. Numeric trees cannot instruct code execution. Cycles, shared/unreachable nodes, invalid children, non-finite parameters and excessive tree sizes are rejected. No pickle or runtime scientific dependency is introduced.
- Checksums depend on a trusted expected fingerprint and source channel; they are not cryptographic signatures or proof of dataset independence. The offline CLI creates no new remote surface.
- The exporter intentionally depends on scikit-learn 1.7.2 private tree fields. Upgrades require a separately reviewed exporter and parity run; categorical/missing-value models are unsupported.
- No new evaluation source was supplied or generated. The specified new PaySim realization is a pending source, with lineage and custody checks required before scoring. It would test simulator generalization, not real-bank effectiveness.
- The historical future window is a previously exposed holdout, never independent validation. No result from that window or confirmation was used to reselect the model or thresholds.
- No probability calibration, confidence interval for new fraud metrics, s390x deployment or dashboard replacement was performed. The synthetic default, HTTP API, frontend, SQLite and original model artifacts remain unchanged.
- Real LinuxONE access remains the demonstration blocker. The runbook requires actual s390x tests, golden parity, event scoring, local inference timings, synthetic replay and persistence readback before deployment claims.
- The previously documented historical PaySim CLI overwrite behavior and synthetic-trainer tied-score AP issue are unchanged and not invoked by this phase.

## Changed files

| File | Purpose |
| --- | --- |
| `fraudshield/portable.py` | Standard-library feature construction, bounded validated tree loading and inference. |
| `fraudshield/portable_cli.py` | Offline score, golden-parity verification and reproducible local timing commands. |
| `experiments/export_portable.py` | Reconstruct only the locked recipe, export numeric JSON, enforce parity and write provenance. |
| `experiments/phase3_protocol.json` | Pin Phase 2 hashes, selected recipe, thresholds, training counts and parity rules. |
| `tests/test_portable.py` | Twelve behavioral, adversarial, preservation and parity regressions. |
| `benchmarks/paysim-phase3-export-v1.json` | Exact aggregate export/parity report, no model parameters. |
| `benchmarks/paysim-phase3-stdlib-parity-v1.json` | Actual standalone standard-library golden verification result. |
| `benchmarks/paysim-phase3-inference-macos-v1.json` | Actual local latency/throughput measurements and methodology. |
| `docs/PHASE3_VALIDATION_PLAN.md` | Preregistered new-source proposal and explicit previously exposed holdout policy. |
| `docs/PHASE3_PORTABLE_RUNBOOK.md` | Export, trust, transfer and LinuxONE verification commands. |
| `docs/PHASE3_RESULTS.md` | This measured evidence, file inventory and limitations. |
| `docs/IBM_Z_DEPLOYMENT.md` | Link the existing synthetic demonstration to the separate portable verification runbook. |
| `README.md` | Surface the portable workflow and keep its validation/hardware status explicit. |

**Next bounded step:** run the reviewed portable verification package on an authorized LinuxONE s390x VM, preserving actual evidence. New-source accuracy assessment awaits a registered unseen dataset. Do not merge or change the default dashboard model automatically.
