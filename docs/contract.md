# Shared Contract (human-readable)

The **binding** version is the code in [`idlegrid/common/models.py`](../idlegrid/common/models.py), copied from **PRD Appendix A**. This page explains it in plain words. If the two ever disagree, the code wins. Then fix this page.

`SCHEMA_VERSION = "1.0"`: every heartbeat and usage batch carries it. A different **major** number is rejected (HTTP 426); minor differences are accepted.

## Conventions
| Thing | Rule |
|---|---|
| Durations | seconds, `float` |
| Sizes | MB unless the name says otherwise (`disk_free_gb`) |
| Percentages | 0–100 |
| Timestamps | epoch seconds UTC (`float`) in Python and the API; `DATETIME(3)` UTC in MySQL; ISO 8601 with `Z` in CSV files |
| IDs | `node-` + 12 hex (stable, made by the agent) · `job_` + 10 hex · `{job_id}-a{n}` per attempt · `cmd_` + 12 hex · `study_` + 8 hex · `run_` + 8 hex · `u_` + 8 hex |
| Unknown fields | ignored, so additive (minor) changes don't break older code |

## Status vocabularies
| Enum | Values | Set by |
|---|---|---|
| `HostState` | `ACTIVE` (recent input) · `BUSY` (owner's programs using CPU/RAM) · `IDLE` · `UNKNOWN` (input can't be read) | Agent |
| `NodeStatus` | `OFFLINE` · `HOST_ACTIVE` · `HOST_BUSY` · `IDLE_SAFE` · `IDLE_RISKY` · `RUNNING_JOB` · `DRAINING` · `UNSCHEDULABLE` | Dispatcher |
| `JobStatus` | `QUEUED` · `ASSIGNED` · `RUNNING` · `PAUSED` · `COMPLETED` · `FAILED` · `CANCELLED` · `TIMED_OUT` | Dispatcher |
| `AttemptStatus` | JobStatus values + `MIGRATED` · `LOST` | Dispatcher |
| `InputDetection` | `PRECISE` · `COARSE` · `NONE` | Agent |
| `JobKind` | `SCRIPT` · `HPO_TRIAL` | Dispatcher |
| `CommandType` | `START` · `ABORT` · `PAUSE` · `RESUME` | Dispatcher → agent |
| `StudyStatus` | `RUNNING` · `COMPLETED` · `FAILED` · `CANCELLED` | HPO controller |

**Renamed from the prototype:** Ronit's `NodeStatus.BUSY` is now `RUNNING_JOB`. `JobStatus.RESUMING` and `PREEMPTED_MIGRATING` are gone (migration is an attempt outcome now). `TIMED_OUT` is new. Arya's `USER_ACTIVE` becomes `HostState.ACTIVE`.

## Main models (who sends what)
| Model | From → to | Purpose |
|---|---|---|
| `Heartbeat` | Agent → Dispatcher, every 5 s | Host state, metrics, power, capabilities, current attempt, command results |
| `HeartbeatResponse` | Dispatcher → agent | Node status, pending `NodeCommand`s, runtime overrides |
| `UsageSample` / `UsageBatch` | Agent → Dispatcher | One row every 15 s (same columns as the usage CSV, PRD Appendix D); max 2,000 rows per batch |
| `JobManifest` | Packager → everyone | `manifest.json` inside every job bundle |
| `JobResult` / `ExecutionMetrics` | Executor → Dispatcher | Outcome, logs (last 64 KB), active vs wall-clock time |
| `StartJobPayload` | Dispatcher → agent | What to run, bundle hash, timeouts |
| `IdlePrediction` | Oracle → Dispatcher | q10 / q20 / q50 remaining idle seconds |
| `NodeView` / `JobView` / `AttemptView` / `StudyView` | Dispatcher → CLI and dashboard | Read models for the UI |
| `StudySpec` / `ParamSpec` | CLI → Dispatcher | An Optuna HPO study and its search space |
| `TelemetrySnapshot` | Dispatcher → dashboard (WebSocket) | Everything the live dashboard shows |

`idlegrid/common/legacy.py` holds prototype-only models (`NodeTelemetry` and others) that keep the old dashboard running until Phase 1. They are **not** part of the contract.

## Changing the contract (PRD section 15.4)
1. Open an issue titled "Contract change: …" with the reason and the exact change.
2. Get approval from Harith (custodian) and every member whose code is affected.
3. In **one PR**: update PRD Appendix A, this page and `models.py`; bump `SCHEMA_VERSION` (minor = additive, major = breaking); regenerate the lock file with
   `UPDATE_CONTRACT_SNAPSHOT=1 pytest tests/unit/common/test_contract.py`.
4. Contract PRs need **2 approvals**, one from Harith.

`tests/unit/common/test_contract.py` fails CI whenever `models.py` changes without that snapshot update, so accidental changes can't slip in.
