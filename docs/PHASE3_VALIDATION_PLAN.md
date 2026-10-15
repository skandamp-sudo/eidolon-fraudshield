# Phase 3 locked export and new-source validation plan

## Frozen decisions

Phase 2 commit `d4fb349ab394b033b0298c23f7334e1ccadf1538`, its protocol, ranking report, selected `hist_tree_leaf7_balanced` recipe and all six calibrated thresholds remain unchanged. `experiments/phase3_protocol.json` pins their hashes. There is no grid search, threshold selection, calibration refit or confirmation/future-test evaluation in the exporter.

The Phase 2 fitted estimator was not retained. Phase 3 reconstructs that recipe on exactly 4,463,587 training rows through step 323 (3,643 fraud labels), seed 74 and the same pinned dependency versions. This is a deterministic recipe reconstruction, not recovery of the original estimator's bytes. The later rows are excluded from training-feature/label parsing; the whole CSV is hashed only for identity. Numerical parity compares the reconstructed scikit-learn estimator with its portable export, not with an unavailable original estimator.

## New evaluation source: specified, not yet available

The preferred feasible new source is a **new PaySim simulation realization produced after this plan is frozen**, by a separate custodian using the [upstream PaySim simulator](https://github.com/EdgarLopezPhD/PaySim). The existing Kaggle file, its renamed copies, different row orderings, or subsets are not new sources. No newly generated source is currently available or claimed.

Before generation, the custodian must freeze and record:

- Simulator Git commit, Java/runtime versions, complete configuration and input-parameter file hashes, and the source/licensing provenance of those parameters.
- One new seed, `2026101503`, and 744 simulation steps. Use all emitted transactions, with no fraud enrichment, background downsampling or seed retries based on outcomes. Do not tune generator parameters to match desirable model metrics.
- A generation timestamp after plan freeze, confirmation that this realization has not been inspected for model development, and a separate evaluator/custodian. If the simulator cannot support this protocol or its schema differs, stop and revise the plan before generating/scoring data.
- A semantic mapping for simulated step (hour), transaction type and amount units. Schema compatibility must be demonstrated; do not fabricate missing features or relabel incompatible transactions.

After generation and **before scoring**, register the exact CSV SHA-256, row count, complete step range, simulator/configuration/parameter hashes, custodian attestation and immutable source location. Reject the known canonical SHA-256 `16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b`. Hash inequality alone is not evidence of independence: establish lineage and confirm it is not a transformed copy. Keep labels sealed from model selection.

The generated realization would be unseen to this model-development process, but shares simulator assumptions and possibly parameter sources. Describe it as **new-realization validation within PaySim**, not independent real-bank validation. A separately governed, later real financial dataset would provide stronger external evidence, but none has been offered or claimed available.

## One-shot assessment contract

1. Freeze the portable artifact hash and parity evidence before receiving the new data; use the existing `max_f1` threshold as the primary operating point. Report all five previously locked capacity thresholds as prespecified secondary analyses.
2. Validate the source manifest, chronology, schema, finite values and complete row counts; fail explicitly on malformed/incompatible data. No repairs, row filtering or replacement seed after seeing outcomes. A scientific defect stops the affected evaluation for review.
3. Score the complete realization once using only amount, type and simulated hour. No fitting, sampling, probability recalibration or threshold optimization. Keep IDs, balances, flags and labels out of prediction features.
4. Report TP, FP, FN, TN, precision, recall, F1, exact tie-grouped AP, prevalence, false-positive rate, alert count/rate and maximum alerts per simulated step. Report each transaction type and consecutive 24-step block to expose distribution shifts. A class with no positives has undefined recall, not fabricated zero evidence.
5. For uncertainty, use 1,000 whole-24-step-block bootstrap replicates with fixed seed `2026101504`, preserving within-block dependence; identify undefined replicates and limits from few/unequal blocks. These intervals do not establish real-bank generalization.
6. Publish all prespecified operating points, including negative results. Accuracy results must not trigger an automatic model replacement. A new performance-driven choice requires a new model version and another untouched evaluation source.

No numerical accuracy acceptance target is invented after seeing data. Export acceptance is a computational gate: maximum absolute score error <=1e-12 and zero threshold-decision mismatches on the registered parity cases. Deployment readiness additionally requires the actual hardware checks below and a review of measured accuracy/workload against operator-provided review capacity.

## Previously exposed holdout fallback

Canonical PaySim steps 379 onward are a **previously exposed holdout**. If a later authorized assessment uses them, label every report accordingly. They cannot supply independent validation, and their results cannot change this locked model or thresholds. Phase 3 does not run that fallback or use the observed confirmation window.

## Portable demonstration gate

Keep the synthetic dashboard model as the default. The separate portable CLI accepts a trusted artifact hash, training dataset fingerprint and a transaction, then returns an explicitly uncalibrated score and the locked alert decision. It introduces no HTTP endpoint, database migration or runtime scientific dependency.

Run the standard-library suite, exported golden parity vectors, a scoring smoke test and an instrumented benchmark on actual LinuxONE s390x. Record exact source/model hashes, architecture, OS and Python. Until that happens, local MacBook timings and parity are local evidence only. See `PHASE3_PORTABLE_RUNBOOK.md` for commands and `PHASE3_RESULTS.md` for actual evidence and outstanding blockers.
