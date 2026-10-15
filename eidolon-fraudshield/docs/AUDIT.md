# Engineering audit — 15 October 2026

## Scope and observed baseline

Inspected `fraudshield/`, `web/`, `scripts/`, `tests/`, `models/baseline.json`, `data/`, `README.md` and both existing runbooks. The checkout has a bundled synthetic model, static browser dashboard, Python HTTP server, SQLite event/review store, generator, PaySim replay and an out-of-domain baseline evaluator. No PaySim CSV is present. A local ignored SQLite file exists and was left intact.

Before changes, `python3 -B -m unittest discover -s tests -v` ran 8 tests: 7 passed and the HTTP test errored because this sandbox denied loopback bind (`PermissionError: [Errno 1] Operation not permitted`). This is an environment restriction, not evidence of an application failure. After changes, the full suite passed with loopback permission: 13 tests. No application throughput benchmark was run.

## Findings and disposition

| Area | Finding | Severity | Status |
| --- | --- | --- | --- |
| API exposure | `HOST` could bind an unauthenticated, state-changing demo service to a public interface; JSON requests had no Host/Origin or media-type check. | High | Loopback-only binding, Host/Origin checks, JSON media type and body timeout added. Shared deployment still needs authentication and access controls. |
| Model loading | Artifact weight count, finite values and threshold were unchecked; `zip` could silently ignore a truncated vector. | High | Reject malformed artifacts at load. No artifact signature/provenance verification exists. |
| PaySim science | Existing PaySim script evaluated only the synthetic-trained model. A PaySim-trained artifact and untouched temporal test did not exist. | High for claims | Added separate streaming trainer and future-step evaluation; no full dataset run or PaySim metric claimed. |
| Leakage | Shared feature map excludes label, flag and balances, but this was covered by one narrow test. Account IDs were not used. Synthetic baseline amount correlates with generator label by construction. | High for external-validity claims | Added fixture regression showing perturbing balance, ID and flag columns cannot change training/evaluation. No real-world accuracy claim is supported. |
| SQLite/API race | Reset checked replay state and released the lock before deleting rows; a replay could start in between. | Medium | Reset and replay start now share the lock through deletion. Local store architecture preserved. |
| Dashboard | Table/alerts could remain stale after a review from another browser because rendering keyed only on total row count; table rows lacked keyboard activation. | Medium | Rendering now observes event/review changes; rows support keyboard activation. Full accessibility audit remains open. |
| Model/dataset | PaySim CSV is not bundled. Existing baseline reports synthetic generator holdout numbers only. Chronological split of the generator is by generation order, not an independent real-time bank holdout. | Claim blocker | Documentation separates demo and PaySim artifacts, sources and limitations. |
| LinuxONE | Standard-library Python/SQLite is architecture-portable in source, but no actual s390x VM, distro package check, tests or latency measurements were available. | Deployment blocker | Added hardware verification and SSH-tunnel steps. Deployment remains not verified. |

## Remaining limitations

- The demo API is unauthenticated for local use; any local process or person with access to the SSH tunnel can mutate its data. Review records have no user identity or tamper-evident audit trail. Do not expose it as a shared service.
- SQLite history has no retention cap. Do not replay a full PaySim dataset into the demo database. Downloaded CSVs and local model artifacts are ignored by Git.
- The PaySim trainer uses one fixed SGD pass and binned average precision. It has no calibration, confidence interval, alternative model comparison or measured inference latency. The test fixture establishes mechanics and exclusion boundaries, not fraud efficacy.
- Real LinuxONE deployment, end-to-end UI automation, accessibility review and performance benchmarking are **NOT VERIFIED**.
