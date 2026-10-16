# Reproduce the Phase 2 development comparison

## Inputs and isolation

Read `PHASE2_SCIENTIFIC_AUDIT.md` and the committed protocol before running. The user supplied the canonical 6,362,620-row CSV and original trained JSON. Both remain outside Git and are read only. `benchmarks/paysim-baseline-v1.json` preserves aggregate historical results and hashes without model weights. Neither the synthetic dashboard artifact nor the original PaySim model is a runner output.

The protocol was committed before measuring full-data candidates. Every run checks the exact source and baseline hashes, creates a fresh output directory, records the protocol and runner hashes, then rechecks input hashes before declaring completion. Do not modify the protocol to improve confirmation results. Report scientific defects and stop the affected evaluation rather than silently repairing a running benchmark.

## Optional training environment

The application still needs only Python 3.10+ and the standard library. These offline experiments need Python 3.11+ because of the pinned NumPy/SciPy versions. Use a separate environment:

```bash
python3 -m venv .venv-training
.venv-training/bin/python -m pip install --only-binary=:all: -r requirements-training.txt
.venv-training/bin/python -m pip check
LOKY_MAX_CPU_COUNT=2 OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 \
  .venv-training/bin/python -B -m unittest discover -s tests -v
LOKY_MAX_CPU_COUNT=2 OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 \
  .venv-training/bin/python -B -u -m experiments.paysim_models \
  /path/to/paysim.csv /path/to/original-paysim.local.json \
  --output .experiments/phase2-v1-run1
```

The output directory must not already exist. It contains private working arrays and aggregate reports. Do not commit its contents wholesale. The report has no account identifiers or transaction rows; manually review aggregate reports before publishing them. No fitted scikit-learn pickle is created or deserialized. A model selected for a later deployment would need a separately approved export/inference integration.

The runner uses all 5,444,003 development rows and no resampling. Its on-disk feature array is approximately 784 MB plus labels and steps; estimator fitting needs additional RAM and temporary copies. Candidates run sequentially with two compute threads. Dataset size is capped at 10 million development rows; CSV fields at 4,096 characters. Execution time and process memory must be measured on the actual host rather than inferred from these allocation sizes.

Without optional dependencies, `python3 -B -m unittest discover -s tests -v` still runs the runtime suite and reports optional estimator tests as skipped. Skipped tests are not evidence that the scientific pipeline passed on that environment.

## LinuxONE s390x assessment

`benchmarks/phase2-platform-evidence.json` records the official PyPI file inventories checked on 2026-10-15. The pinned NumPy 2.3.4, SciPy 1.16.2 and scikit-learn 1.7.2 releases had no s390x wheels. Joblib and threadpoolctl have portable Python wheels. Thus the binary-only installation command is expected to fail for the native pinned stack on s390x; it must not silently fall back to a source build or an x86 binary.

The [scikit-learn installation guide](https://scikit-learn.org/1.7/install.html) documents isolated environments and distribution packages. On an actual authorized LinuxONE VM, first record `uname -m`, Python and SQLite versions and run the standard-library application tests. For experiments, obtain an organizer-supported s390x build of the pinned scientific stack or establish a separately documented distribution-package environment. Record exact versions, BLAS/OpenMP libraries and all test outputs. A different stack needs an explicitly versioned replication result and cannot be called bit-for-bit reproduction of the MacBook run.

No compiler toolchain or alternate binary distribution was installed for LinuxONE. No s390x execution, accelerator use, or hardware performance claim is made. Consult the [PyPI scikit-learn release](https://pypi.org/project/scikit-learn/1.7.2/) and recorded inventory when checking availability again.

An inspected alternative is Ubuntu 24.04's [s390x scikit-learn package](https://packages.ubuntu.com/noble/s390x/python3-sklearn-lib), version 1.4.1.post1, with its distribution NumPy/SciPy dependencies. This establishes package availability, not compatibility or matching results for the pinned 1.7.2 experiment. It has not been installed or tested here.

## Interpreting the output

`candidate_tuning` contains inner-tuning exact AP for every predefined candidate. `selected_before_confirmation` records the model choice made before confirmation. `comparisons` contains refitted family winners and the original SGD reference on the same later windows. Every operating point transfers a fixed calibration threshold; the confirmation report includes actual false-alert counts and simulated-step burst statistics.

Do not choose a new winner or threshold from the confirmation table. Capacities are hypothetical review-rate scenarios and are not guaranteed future service levels. Repeated development use and already observed baseline validation results mean these comparisons are not a fresh independent final benchmark.
