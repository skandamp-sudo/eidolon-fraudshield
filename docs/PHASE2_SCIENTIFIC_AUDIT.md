# Phase 2 scientific audit and frozen development protocol

## Baseline preservation

The original local PaySim JSON contains the model, source hash, splits and reported metrics. Its SHA-256 is `2017a5382d3795724023b1f137ecbf96cd8b60311c30e0d64af2cf85318402dd`; the user's baseline backup is identical. The canonical CSV hash is `16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b`. Both files were readable and the CSV hash matched. The versioned aggregate report is `benchmarks/paysim-baseline-v1.json`; no original model weights or dataset rows are committed. These are local MacBook results, not LinuxONE results.

The existing test window (steps 379 onward) is previously observed. Its precision 0.284906, recall 0.201198, F1 0.235845, approximate AP 0.097924 and confusion counts are retained as historical results. They are not objectives for Phase 2 selection, and are not re-evaluated by the experiment runner.

## Pipeline findings

- The fixed feature map uses only amount, transaction type and simulated hour. Labels enter the loss/metrics separately; account IDs, `isFlaggedFraud`, and all balance columns are excluded. No account-history or future aggregate feature is introduced.
- Splitting keeps complete time steps together. The baseline uses training through step 323 and validation through step 378. A single chronological SGD pass, constant learning rate, no feature scaling and no imbalance weighting can leave the model sensitive to optimizer convergence and within-training row order. These are hypotheses for comparison, not a demonstrated cause of low recall.
- The saved train prevalence is 3,643 / 4,463,587; validation is 564 / 980,416. The previously observed test prevalence is 4,006 / 918,617. Their difference limits the transferability of precision and alert-volume expectations. No further test-label inspection is needed to establish that historical difference.
- The baseline threshold was selected for validation F1 on a grid of 0.0001. That objective has no analyst-capacity constraint. Fine score differences are coalesced by 10,001-bin AP. Phase 2 computes exact tie-grouped AP on development windows and chooses thresholds among unique scores.
- The separate synthetic trainer's `average_precision` helper ranks tied scores by row order. It is not used for Phase 2 metrics; the historical synthetic artifact remains unchanged. Binned PaySim AP and exact Phase 2 AP must not be presented as interchangeable measurements.
- The old CLI can overwrite its chosen PaySim output. Phase 2 never calls it, requires a fresh experiment directory, checks source/artifact hashes before and after work, and writes no replacement application model.
- Optional scikit-learn transforms fit only on the fitting subset. Histogram trees disable automatic random early stopping. Class weighting uses training labels only; development assessment retains every row and its natural prevalence.

## Protocol frozen before measurement

The executable configuration is `experiments/phase2_protocol.json`.

| Window | Steps | Purpose |
| --- | --- | --- |
| Inner fitting | <=250 | Fit all seven predefined candidates and their scalers |
| Inner tuning | 251..323 | Select the best logistic and tree configurations by exact AP; select the overall candidate here |
| Refit | <=323 | Refit those family winners on all original training rows |
| Threshold calibration | 324..350 | Choose F1 and capacity thresholds; no model fitting |
| Development confirmation | 351..378 | Assess locked choices once; no further selection or tuning |
| Previously observed test | >=379 | Excluded from feature/label loading and all candidate predictions |

The fixed comparison includes baseline-feature logistic regression, three richer logistic variants (regularization and class weighting), and three histogram tree variants. Richer features add transaction-type/amount interactions, a squared log amount and cyclic simulated hour. No feature learns statistics from future rows. Model output is an uncalibrated ranking score, including for class-weighted fits.

The historical SGD model was already trained through 323, so it is compared only on later development windows. Its historical 0.008 threshold used the entire old validation window and is explicitly marked as such; it is not a fresh confirmation threshold. A recalibrated reference uses the same 324..350 threshold window as the new candidates.

Review capacities of 1, 5, 10, 25 and 50 alerts per 10,000 transactions are illustrative scenarios, not asserted staffing capacity. Thresholds preserve score ties and may select no alerts when a tied group exceeds the budget. The report measures realized confirmation alert counts, false alerts and simulated-step bursts: a calibration-rate target does not guarantee the same future workload.

## Interpretation limits

These are development comparisons on synthetic PaySim transactions. The baseline already used the original validation window, so the later development confirmation is not a new independent final test. A higher development metric does not establish real-bank improvement. The frozen selection rule cannot be changed after seeing confirmation results; disappointing results must be reported. Approval and a fresh, independently specified evaluation are required before any dashboard model replacement.
