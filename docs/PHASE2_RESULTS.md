# Phase 2 measured development results

Protocol and runner committed before the full-data comparison at `ceabc9914c3a98379c8dbc2d37e61e2702665ef0`. Full numeric output, score-threshold curves, timing and platform versions are in [the aggregate report](../benchmarks/paysim-phase2-v1.json). The original result is preserved separately in [baseline v1](../benchmarks/paysim-baseline-v1.json).

**Scope:** local MacBook, Python 3.14.7, x86_64, two compute threads. All 5,444,003 original training/validation rows were used; no resampling. No candidate predictions or new metrics were computed for the previously observed test window, steps 379 onward. The dashboard model and original PaySim artifacts were not modified.

## Development windows

| Window | Rows | Fraud labels | Prevalence |
| --- | ---: | ---: | ---: |
| fit | 3,248,292 | 2,841 | 0.087461% |
| tune | 1,215,295 | 802 | 0.065992% |
| refit | 4,463,587 | 3,643 | 0.081616% |
| calibration | 480,328 | 258 | 0.053713% |
| confirmation | 500,088 | 306 | 0.061189% |

## Frozen candidate comparison

All candidates were fitted on steps <=250 and ranked by exact AP on 251..323. There was no change to the candidate grid after these measurements.

| Candidate | Inner-tuning exact AP | Fit seconds |
| --- | ---: | ---: |
| logistic_base_c1 | 0.017202 | 8.170 |
| logistic_static_c01 | 0.085042 | 24.765 |
| logistic_static_c1 | 0.059053 | 26.578 |
| logistic_static_balanced | 0.022715 | 54.455 |
| hist_tree_leaf7 | 0.350299 | 17.881 |
| hist_tree_leaf15 | 0.343360 | 21.556 |
| hist_tree_leaf7_balanced | 0.358707 | 19.049 |

Selected before confirmation: **hist_tree_leaf7_balanced**. The best logistic configuration was `logistic_static_c01`. Both family winners were refitted on steps <=323. F1 and review-capacity thresholds were fixed using steps 324..350.

## Locked confirmation: steps 351..378

The following rows use each model's calibration-selected F1 threshold. All models are evaluated on the same 500,088 rows with 306 fraud labels. This development comparison is not a new independent final test.

| Model | Exact AP | Precision | Recall | F1 | TP | FP | FN | TN |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| original_single_pass_sgd | 0.035342 | 0.120553 | 0.199346 | 0.150246 | 61 | 445 | 245 | 499337 |
| logistic_static_c01 | 0.227609 | 0.252101 | 0.294118 | 0.271493 | 90 | 267 | 216 | 499515 |
| hist_tree_leaf7_balanced | 0.373955 | 0.674556 | 0.372549 | 0.480000 | 114 | 55 | 192 | 499727 |

The tree found 114 of 306 frauds and missed 192. Its class-weighted score threshold (0.9833296104213592) is not a calibrated 98.3% fraud probability. No confirmation result was used to pick a different model or threshold.

The original SGD historical threshold of 0.008, previously chosen using all old validation rows, produced TP=61, FP=466, FN=245, TN=499316 on this window. That reference is labeled historical in the machine-readable report and is not treated as a fresh threshold-selection result.

## Review-capacity sensitivity for the preselected tree

Capacity targets are illustrative calibration rates. All table entries use thresholds fixed before confirmation, preserve tied score groups and include every confirmation row.

| Calibration target alerts / 10,000 | Actual confirmation alerts / 10,000 | Precision | Recall | TP | False alerts | Total alerts | Max alerts / simulated step |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1.600 | 0.900000 | 0.235294 | 72 | 8 | 80 | 14 |
| 5 | 7.459 | 0.329759 | 0.401961 | 123 | 250 | 373 | 113 |
| 10 | 9.718 | 0.265432 | 0.421569 | 129 | 357 | 486 | 136 |
| 25 | 24.336 | 0.118324 | 0.470588 | 144 | 1073 | 1217 | 327 |
| 50 | 39.913 | 0.075150 | 0.490196 | 150 | 1846 | 1996 | 327 |

For example, the 5-per-10,000 calibration target became 7.46 per 10,000 in confirmation. Increasing the target from 5 to 50 improved recall from 40.20% to 49.02%, while false alerts rose from 250 to 1,846. These are workload scenarios for human review, not a recommendation to change the locked operating threshold.

## Findings and limitations

- Amount/type interactions and cyclic time improved the logistic development ranking in this finite comparison; stronger regularization (C=0.1) beat C=1. Balanced logistic class weights reduced inner-tuning AP. Weighting is not automatically beneficial.
- Tree class weighting improved inner-tuning AP only modestly (0.358707 versus 0.350299 for seven-leaf unweighted trees). No uncertainty interval supports a strong superiority claim for that difference.
- Development temporal structure is pronounced: steps 49..72 contain only 1,070 rows but 310 fraud labels (28.97%); steps 25..48 contain 455,238 rows with 309 fraud labels (0.0679%). These are measured properties of the simulation. Calendar features and changing background volume may exploit simulator patterns that do not transfer to banks. No causal explanation is asserted.
- Confirmation prevalence rose from calibration 0.053713% to 0.061189%. Precision and alert volume changed as well; the data does not establish prevalence alone as the cause.
- This is one predeclared temporal comparison, with 306 confirmation frauds. No confidence intervals, repeated full runs, cross-hardware replication, calibrated probabilities or independent new test results were produced.
- The original model already used the broader validation window, so this later development confirmation is not a pristine final holdout. The new candidate was selected before confirmation and was not retuned afterwards.
- Do not compare this confirmation F1 or exact AP directly with the original future-test F1=0.235845 or binned AP=0.097924: the populations and AP methods differ.
- No deployed replacement artifact was exported. The committed recipe reproduces candidate training; a separately approved export, validation and runtime integration are still required.
- LinuxONE s390x execution is not verified. Pinned native scientific packages lack s390x PyPI wheels; see the reproduction guide for the separately versioned distribution-package path.

## Verification

- Five new scientific tests passed on fixtures: feature exclusion, tie-preserving capacities, training-only preprocessing/no random tree holdout, future-label/predictor exclusion and preserved baseline-report counts.
- Full optional-dependency regression suite: 18 tests passed in 2.084 seconds before the measured run. Existing scoring, replay, HTTP security and SQLite tests remained included.
- Dependency-free regression suite: 18 discovered, 14 passed and 4 optional estimator tests skipped in 0.624 seconds; no failures.
- Focused optional scientific tests: 5 passed in 87.966 seconds, including initial scientific-library import.
- `pip check`, `python3 -m compileall -q fraudshield experiments tests scripts run.py` and `git diff --check` passed. No separate static typechecker or frontend build is configured or claimed.
- Report runner/protocol hashes match the committed sources. The published aggregate report is byte-identical to the measured output. Original PaySim artifact, backup and synthetic model hashes are unchanged; the application/runtime/model diff is empty.
- The complete experiment succeeded with input hashes rechecked. No original artifact was overwritten.
- Measured experiment time from development loading through final integrity checks: 318.674 seconds. Candidate fit times are recorded above; they are local observations, not standardized throughput or LinuxONE benchmarks.

**Next step:** review the frozen candidate and capacity trade-offs, then approve a separately specified independent validation and artifact-export plan. Keep the synthetic dashboard model until that approval.


## Change inventory and security boundaries

| File | Reason |
| --- | --- |
| `.gitignore` | Keep private experiment arrays and the optional virtual environment out of Git. |
| `README.md` | Replace obsolete dataset-unavailable claims with measured baseline and Phase 2 links. |
| `benchmarks/paysim-baseline-v1.json` | Preserve original aggregate results, split metadata and hashes without weights or transactions. |
| `benchmarks/paysim-phase2-v1.json` | Publish the exact aggregate output from the frozen full-development experiment. |
| `benchmarks/phase2-platform-evidence.json` | Record inspected release wheel availability and s390x limitations. |
| `docs/PHASE2_SCIENTIFIC_AUDIT.md` | Record pipeline findings, leakage boundaries and the predeclared comparison design. |
| `docs/PHASE2_REPRODUCIBILITY.md` | Provide isolated setup/run commands, input checks and hardware replication constraints. |
| `docs/PHASE2_RESULTS.md` | Report measured comparisons, workload sensitivity, checks and remaining limitations. |
| `docs/VALIDATION.md` | Distinguish historical test evidence from development-only Phase 2 work. |
| `experiments/__init__.py` | Define a separate offline experiment package. |
| `experiments/paysim_models.py` | Implement chronological comparisons, training-only preprocessing and calibration-only thresholds. |
| `experiments/phase2_protocol.json` | Freeze hashes, seed, windows, candidates and selection rules before measurements. |
| `requirements-training.txt` | Pin optional scientific dependencies without changing application requirements. |
| `tests/test_experiments.py` | Add five regression tests for the scientific and artifact-preservation boundaries. |

The audit found methodological and operational risks, not a newly demonstrated application exploit. The new pipeline addresses accidental artifact overwrite with fresh exclusive output directories; source/model substitution with hash checks; preprocessing leakage with training-only fitting; accidental random holdout with disabled tree early stopping; and future-label access with an explicit development cutoff. Feature tests exclude balances, account IDs, fraud labels and flags. There is no pickle loading, new network service, application dependency or dashboard inference change.

Two existing issues remain outside this experiment: the historical PaySim CLI can overwrite its chosen output, and the separate synthetic trainer's AP helper is sensitive to tied-score ordering. Neither is invoked for Phase 2 scientific measurements. Source integrity checks do not establish dataset authenticity or real-bank validity. Temporary development arrays contain amounts/types/timing and labels, must remain local, and require operator cleanup when no longer needed.

Regression coverage executed with optional dependencies comprises the ten existing core tests (replay, decisions/reasons, demo reproducibility, feature leakage, HTTP API, malformed models, metrics, loopback restriction, SQLite review audit and untrusted inputs), three existing PaySim tests (baseline preservation, temporal/leakage boundaries and unsorted rejection), and all five new experiment tests. All 18 passed; no valid test was removed or weakened.
