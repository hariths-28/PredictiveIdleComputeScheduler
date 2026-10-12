# IdleGrid: Product Requirements Document (PRD)

**Project:** Predictive Idle-Compute Scheduler for Distributed ML Workloads (working name **IdleGrid**, Python package `idlegrid`)
**Course:** BACSE291 Innovative Design Project, SCOPE, VIT (AY 2026–27)
**Team:** Arya (Node Agent) · Harith (Dispatcher & Integration Lead) · Amaan (State Manager / Database) · Rejish (ML Oracle & Simulator) · Ronit (Executor, CLI, Dashboard & HPO)
**PRD version:** 1.0, 8 October 2026
**Build window:** 12 October 2026 → 28 March 2027 (24 weeks)
**Baseline code:** branch `claude/nifty-ramanujan-mtwgp7` (commit `0459e07`). About 80% of the existing code is reused, and every change to it is listed in this document.

---

## 0. How to use this document

### 0.1 For the team
- Part I (§1–§9) is shared context that everyone reads once.
- Part II (§10) has one section per member: what to build, which existing code to keep or change, how it plugs into the others, and phase-by-phase tasks with acceptance criteria.
- Part III (§11–§19) covers experiments, the research paper, testing, process, security, risks and the final demo.
- The appendices (A–G) are the **binding contracts**: data models, REST API, database DDL, CSV format, configuration, state machines and CI. Code must match them. Changing them follows the process in §15.4.

### 0.2 For an LLM (using this PRD as a build prompt)
Each member section is written so it can be handed to an LLM coding assistant. Build the prompt like this:

```
[1] §0.3 "Global rules for any implementer" (below)
[2] Part I: §1 to §9 (shared context)
[3] Your member section from §10 (e.g. §10.1 Arya)
[4] Appendices A–G (contracts)
[5] The relevant existing source files from the repo
[6] The specific task, e.g. "Implement task A-P1-3 from §10.1"
```

Each member section begins with a **prompt preamble** (a ready-to-paste opening paragraph) and lists exactly which existing files to attach.

### 0.3 Global rules for any implementer (human or LLM)
1. **The contracts in Appendices A–G are law.** Never rename a field, enum value, endpoint, table or column on your own. If something must change, stop and raise a contract-change request (§15.4).
2. **Reuse before rewriting.** If existing code does the job, move it and adapt it; don't replace it. Every file has a planned destination in §6.2.
3. **One package, absolute imports.** Everything lives under the `idlegrid` package. Imports look like `from idlegrid.common.models import JobStatus`. No `sys.path.insert` hacks and no `from src.…`.
4. **Python 3.12** on every machine. Type hints on all public functions. Format and lint with `ruff`. Tests use `pytest`.
5. **Units:** durations in **seconds** (`float`), sizes in **MB** unless named otherwise, percentages from 0 to 100. Timestamps: epoch seconds (UTC, `float`) in the API and in Python, `DATETIME(3)` UTC in MySQL, ISO 8601 UTC with `Z` in CSV files.
6. **Cross-platform:** every agent and executor feature must work on **Windows 10/11, macOS 13+ and Ubuntu 22.04+**. Use `pathlib`, never hard-code `/` or `\`, and never assume `python3` is on PATH (use `sys.executable`).
7. **Privacy:** never record keystrokes, key identities, mouse coordinates, window titles, app names, URLs or screen contents. The only user-activity signal is *seconds since last input*.
8. **No silent failures.** Log errors with context, return explicit error responses, and never swallow exceptions without logging.
9. **Every pull request** includes tests, passes CI, updates the docs it affects, and is reviewed by at least one teammate (two for contract changes).

---

# PART I: SHARED CONTEXT

## 1. Product summary

### 1.1 Problem
Students' laptops sit idle for long stretches every day: during lectures, meals, overnight while charging. Meanwhile the same students run out of compute for ML work (Colab limits, slow single-laptop training). Existing systems (HTCondor, BOINC) harvest idle machines **reactively**: they grab a machine that looks idle *now* and evict the job when the owner returns. On personal laptops, owners return unpredictably, so reactive scheduling wastes work and keeps interrupting jobs.

### 1.2 Solution
IdleGrid turns a small fleet of personal laptops (Windows, macOS, Linux) into a shared compute pool that:
1. **Detects idleness** on each laptop: seconds since last keyboard/mouse input, owner CPU load, and power state.
2. **Runs jobs only while the owner is away**, at lowest OS priority, and **pauses them within one second** when the owner touches the laptop (the kill switch).
3. **Migrates** a paused job to another laptop if the owner stays active longer than a set limit (default 5 minutes).
4. **Predicts how long each idle laptop will stay idle**, using an ML model trained on the team's own recorded usage, and uses those predictions to place jobs where they're likely to finish uninterrupted.
5. Runs **real ML workloads**: any Python script, plus **distributed Optuna hyperparameter search** that splits trials across idle laptops.

### 1.3 Research question (the project's core contribution)
> Does a learned idle-window predictor reduce wasted computation, preemptions and job completion time compared with reactive idle-harvesting policies, on a real fleet of student laptops?

This is answered two ways:
- **Trace-driven simulation** over months of recorded laptop usage, which gives statistical power.
- **Live experiments** on the real fleet, which shows the effect is real.

### 1.4 Goals (what "complete" means in March 2027)
| ID | Goal | Measured by |
|---|---|---|
| G1 | A job submitted from any team laptop runs on another idle team laptop and its results come back | End-to-end test E2E-1 (§14) |
| G2 | The owner never notices: the job pauses within 1 s of input (p95) and runs at lowest priority | Pause-latency benchmark, per OS |
| G3 | No job is lost: pauses, migrations, laptop sleep, network loss and Dispatcher restarts are all survived | Chaos tests C1–C6 |
| G4 | The idle predictor beats reactive policies in simulation with statistical significance | Experiment EXP-SIM (§11) |
| G5 | The live fleet confirms the simulated benefit, and fleet HPO is faster than a single laptop | Experiment EXP-LIVE (§11) |
| G6 | One Scopus-indexed conference paper submitted by January and presented before the final review | Outcome Analysis (§12) |
| G7 | Installable by a new member in under 15 minutes on any of the 3 OSes, with a full runbook | Install test on a clean machine |

### 1.5 Non-goals (explicitly out of scope; list them as future work)
- GPU scheduling (jobs are CPU-only).
- Running untrusted code from outside the team (users are the 5 team members, see §16).
- Container or VM sandboxing (jobs run as an unprivileged OS process at low priority).
- Checkpoint-based migration (migration restarts the job, which is cheap for HPO trials).
- Multi-coordinator high availability.
- Optuna pruning and conditional (define-by-run) search spaces.
- Mobile apps or a system-tray UI (a CLI and web dashboard only).

### 1.6 Users
| User | Needs |
|---|---|
| **Submitter** (any team member) | Submit a script or HPO study from the CLI or dashboard, watch progress, download results |
| **Laptop owner** (every team member) | Zero noticeable slowdown; can switch sharing off at any time; battery protected |
| **Operator** (Harith; anyone in a demo) | See fleet status, predictions, queue and experiments; change policy; drain nodes |
| **Researcher** (Rejish and the team) | Export usage data, train and evaluate the predictor, run simulations, compare policies |

---

## 2. Decisions and assumptions

### 2.1 Decisions (agreed with the team lead on 8 October 2026)
| # | Decision | Consequence |
|---|---|---|
| D1 | The fleet is **Windows + macOS + Linux** | OS-specific idle detection, sleep prevention, priority and autostart (§5) |
| D2 | Networks: **campus Wi-Fi, home/hostel Wi-Fi, phone hotspot** | Overlay network (Tailscale) for campus. Agents only make outgoing connections (§5.6) |
| D3 | The coordinator is **one team laptop** (Dispatcher + MySQL, and it may also be a worker) | Agents keep working and buffering while the coordinator is off |
| D4 | Workload: **any Python script + distributed Optuna HPO** | Optuna's ask-and-tell runs inside the Dispatcher. Workers never touch the database |
| D5 | Preemption: **pause instantly, then migrate** after `migrate_after_sec` (default 300) | Attempts model, wasted-compute accounting |
| D6 | Dependencies: **one shared, pinned worker environment** on every laptop | `worker_env_hash` checked before a job is assigned |
| D7 | Repo layout: **one Python package organised by function** | Migration map in §6.2 |
| D8 | **Harith takes over Ronit's server code** (`app.py`, `mock_cluster.py`) to build the Dispatcher | Ronit keeps the executor, packager, CLI, dashboard front end and HPO |
| D9 | Users: **team only**, **one API token per member** (expandable later) | `users` table and per-user tokens from day one |
| D10 | Git: **feature branches + PR + 1 review + GitHub Actions CI** (3-OS test matrix) | §15 |
| D11 | Research outcome: **Scopus-indexed conference paper** | Paper track in §12 |
| D12 | **MySQL 8** stays (as the charter says), only on the coordinator | SQLAlchemy Core + PyMySQL. Optuna storage in the same server |

### 2.2 Assumptions (change only by team decision)
- All five laptops can install Python 3.12 and the pinned worker environment.
- Team members consent in writing to logging of CPU, RAM, power and *seconds since last input* on their laptops (§16.3).
- The coordinator laptop is switched on and plugged in during experiments and demos.
- Jobs are CPU-bound Python, take minutes to about an hour, and need under 4 GB of RAM.

---

## 3. Evaluation alignment (how the plan earns full marks)

| Assessment | Date | Marks | What we show | Ready by |
|---|---|---|---|---|
| 2nd Review: 60% implementation + complete design | Jan, 2nd/3rd week (W14–W15) | 30 | **Project plan** (§9), **analysis & requirements** (§1, §8), **system design** (§4, Appendices), **proposed methodology** (§11). Live demo of Phases 0–4: real remote execution, kill switch, migration, Oracle v1, Optuna HPO across laptops, first simulation results. About 70% implemented, ahead of the 60% bar. | End of W13 (Jan 10) |
| Project report: final report + rough draft of outcome | By 15 Mar 2027 | 5 | Full report built from this PRD, design docs, experiment results and paper | W22 (Mar 14) |
| Final review: complete presentation, code, demo, proof of outcome | Last week of March 2027 | 40 | Polished live demo (§18), complete code with CI, experiment results, **paper presented** (proof) | W23 rehearsal, W24 review |
| Outcome analysis | (proof at final review) | up to 10 | Scopus conference paper: **presented = 10**, communicated = 5 | Submit by Jan 10, present Feb–Mar |

**The design principle behind this plan:** each phase ends with a working, demonstrable system. If any later phase slips, the latest completed phase is still a coherent demo.

---

## 4. System architecture

### 4.1 Components

```
                        ┌──────────────────────── Coordinator laptop ────────────────────────┐
                        │                                                                     │
   gridctl (CLI) ──────▶│  Dispatcher  (FastAPI, uvicorn)                 [Harith]            │
   Web dashboard ──────▶│   ├─ REST API  /api/v1/*   + WebSocket /ws/v1/telemetry             │
     [Ronit]            │   ├─ NodeService      (heartbeats, status, fencing)                 │
                        │   ├─ JobService       (submit, cancel, logs, results)               │
                        │   ├─ Scheduler loop   (offline detection, migration, timeouts,      │
                        │   │                    HPO tick, assignment via Policy)             │
                        │   ├─ Policies         (pure functions, shared with simulator)       │
                        │   ├─ OracleClient ───▶ IdleOracle                     [Rejish]      │
                        │   ├─ HpoController (Optuna ask/tell)                  [Ronit]       │
                        │   ├─ BlobStore  data/bundles, data/results, data/logs               │
                        │   └─ Repositories ───▶ MySQL 8: idlegrid + idlegrid_optuna [Amaan]  │
                        │                                                                     │
                        │  (optional) Agent ── the coordinator can also be a worker           │
                        └──────────────────────────────────▲──────────────────────────────────┘
                                                           │ HTTPS/HTTP over LAN or Tailscale
                                                           │ (agents only make OUTGOING requests)
         ┌──────────────────────────── Each worker laptop (Win / macOS / Linux) ───────────────┐
         │  Agent  (one process, started at login)                       [Arya]               │
         │   ├─ IdleDetector (OS-specific: seconds since last input)                          │
         │   ├─ MetricsCollector (CPU, host CPU excluding our job, RAM, power)                │
         │   ├─ UsageLogger → ~/.idlegrid/usage/YYYY-MM-DD.csv  (+ batch upload)              │
         │   ├─ HeartbeatLoop (5 s) → receives commands (START / ABORT / PAUSE / RESUME)      │
         │   ├─ KillSwitch (polls every 0.25 s → pause/resume the job instantly, locally)     │
         │   ├─ PowerGuard (prevent sleep while a job runs, only on AC power)                 │
         │   └─ Worker → JobRunner / ProcessController / Packager            [Ronit]          │
         └────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Ownership map
| Area | Owner | Python package(s) |
|---|---|---|
| Shared contracts | Harith (custodian), all approve | `idlegrid.common` |
| Node Agent | Arya | `idlegrid.agent` |
| Executor + packager | Ronit | `idlegrid.executor`, `idlegrid.packager` |
| CLI + dashboard front end | Ronit | `idlegrid.cli`, `idlegrid.dashboard` |
| HPO (Optuna) | Ronit | `idlegrid.hpo` |
| Dispatcher, scheduler, policies | Harith | `idlegrid.dispatcher` |
| Dev tools (simulated agents) | Harith | `idlegrid.devtools` |
| Database, repositories, migrations, analytics | Amaan | `idlegrid.db` |
| Oracle (features, models, training) | Rejish | `idlegrid.oracle` |
| Simulator and experiments | Rejish (simulator), Harith (live runner) | `idlegrid.sim`, `experiments/` |

### 4.3 Key flows

**F1: Heartbeat (every 5 s, pull model)**
1. The agent sends `POST /api/v1/heartbeat` with its host state, metrics, power, capabilities, current attempt report and acknowledged command IDs.
2. The Dispatcher authenticates the token, upserts the node, records any status change, updates the attempt from the report, marks acknowledged commands, checks fencing (aborts stale attempts), and computes the node's status (with the cached prediction).
3. The response carries `node_status`, pending `commands[]`, `server_time` and runtime config.

The agent never accepts inbound connections. Commands ride on heartbeat responses, so worst-case command latency is one heartbeat interval (5 s). The kill switch doesn't depend on this latency because it acts locally.

**F2: Job lifecycle**
1. `gridctl submit train.py --data d.csv` → the packager builds a zip with `manifest.json` → `POST /api/v1/jobs`.
2. The Dispatcher validates the bundle, assigns its own `job_id`, stores it in `data/bundles/{job_id}.zip`, and inserts a `jobs` row as `QUEUED`.
3. The scheduler tick (every 2 s) calls `policy.assign(queue, free_nodes, predictor, now)`, which returns (job, node) pairs. For each pair it creates a `job_attempts` row as `ASSIGNED` and queues a `START` command.
4. On the next heartbeat the agent receives `START`, downloads the bundle, checks the SHA-256, and runs it through `JobRunner` at lowest priority. It reports `RUNNING`, and streams logs every 2 s.
5. On exit, the agent uploads `result_bundle.zip` and the `JobResult` JSON. The Dispatcher marks the attempt and job `COMPLETED`, `FAILED` or `TIMED_OUT`, stores the results, and frees the node.
6. `gridctl download <job>` fetches the result zip.

**F3: Preemption and migration**
1. The owner touches the keyboard. Within 0.25 s the KillSwitch sees `inactivity < pause_if_inactivity_below_sec` and calls `runner.pause()` (the whole process tree is suspended). The next heartbeat reports the attempt as `PAUSED` with `paused_since`.
2. The owner leaves. Once inactivity reaches `resume_after_idle_sec` (120 s) the KillSwitch calls `runner.resume()`, and the attempt returns to `RUNNING`. Paused time doesn't count towards the job timeout.
3. If the attempt stays paused for more than `migrate_after_sec` (300 s), the scheduler queues an `ABORT` command, marks the attempt `MIGRATED`, puts the job back to `QUEUED` with a priority boost, and adds the attempt's active compute time to wasted compute. The job then restarts on another node.
4. Local fail-safe: if the Dispatcher is unreachable and an attempt has been paused for more than `migrate_after_sec + 60`, the agent cancels it locally and reports it later.

**F4: Node loss**
1. No heartbeat for `offline_after_sec` (15 s) → node marked `OFFLINE`.
2. After `lost_grace_sec` (60 s) more, its attempt is marked `LOST`, the job is requeued, and the work counts as wasted.
3. If the node comes back still running an attempt the Dispatcher already marked `LOST` or `MIGRATED`, the heartbeat response sends `ABORT` (fencing). Results from stale attempts are rejected with HTTP 409.

**F5: Distributed HPO (Optuna ask-and-tell)**
1. `gridctl hpo create objective.py --space space.json --n-trials 40 --parallel 5` → `POST /api/v1/hpo/studies` (objective bundle + `StudySpec`).
2. The HpoController (inside the Dispatcher) creates an Optuna study in the `idlegrid_optuna` MySQL schema, using `TPESampler(constant_liar=True, seed=spec.seed)`.
3. On each scheduler tick, while fewer than `max_parallel` trials are in flight and fewer than `n_trials` have been asked for, it calls `study.ask(fixed_distributions)`. It then builds a trial bundle (objective bundle + `params.json` + the `__idlegrid_trial__.py` wrapper) and inserts an `HPO_TRIAL` job.
4. On the worker, the wrapper loads `params.json`, calls the user's `objective(params) -> float`, and writes `output/objective.json`.
5. When the trial job completes: `study.tell(trial_number, value)`. If the script failed: `study.tell(trial_number, state=FAIL)`. If it was migrated: the same trial number is requeued, with no `tell`.
6. The dashboard shows best value over time, trials per node and the speedup compared with sequential execution.

**F6: Data and ML pipeline**
1. Every agent writes one `UsageSample` every 15 s to a local daily CSV (source of truth), and uploads batches to `POST /api/v1/usage` whenever the Dispatcher is reachable. Inserts are idempotent.
2. `idlegrid.oracle` turns the samples into idle sessions using the single shared definition in `idlegrid.oracle.availability`, builds features, and trains quantile models (nightly or on demand).
3. The model file is saved to `data/models/` and registered in the `oracle_models` table. The Dispatcher reloads it on `POST /api/v1/admin/oracle/reload` or at startup.
4. `IdleOracle.predict(node_id, now)` returns q10/q20/q50 remaining idle seconds, cached for 30 s per node.
5. The simulator (`idlegrid.sim`) replays recorded availability with the *same* policy code to evaluate policies offline.

### 4.4 Status vocabularies (summary; full definitions in Appendix A and the state machines in Appendix F)
- **HostState** (reported by the agent): `ACTIVE` (recent input) · `BUSY` (no input, but the owner's processes use a lot of CPU) · `IDLE` · `UNKNOWN` (input can't be detected).
- **NodeStatus** (computed by the Dispatcher): `OFFLINE` · `HOST_ACTIVE` · `HOST_BUSY` · `IDLE_SAFE` · `IDLE_RISKY` · `RUNNING_JOB` · `DRAINING` · `UNSCHEDULABLE`.
- **JobStatus**: `QUEUED` · `ASSIGNED` · `RUNNING` · `PAUSED` · `COMPLETED` · `FAILED` · `CANCELLED` · `TIMED_OUT`.
- **AttemptStatus**: `ASSIGNED` · `RUNNING` · `PAUSED` · `COMPLETED` · `FAILED` · `CANCELLED` · `TIMED_OUT` · `MIGRATED` · `LOST`.

> **Changes to existing code:** Ronit's `NodeStatus.BUSY` becomes `RUNNING_JOB`. `HOST_BUSY`, `DRAINING` and `UNSCHEDULABLE` are added. `JobStatus.RESUMING` and `PREEMPTED_MIGRATING` are **removed** (migration is now an attempt outcome) and `TIMED_OUT` is added. Arya's `USER_ACTIVE` becomes `HostState.ACTIVE`, and Arya's `BUSY` becomes `HostState.BUSY`.

---

## 5. Operating systems and networks: how they affect the code and the outcome

The fleet mixes Windows, macOS and Linux. Each OS behaves differently in six areas that directly decide whether IdleGrid works. Every OS-specific piece of code sits behind one small interface, so the rest of the system stays OS-agnostic.

### 5.1 Detecting "seconds since last input" (the most important signal)
| OS | Method (priority order) | Permissions | Precision | Notes |
|---|---|---|---|---|
| **Windows** | `user32.GetLastInputInfo` + `kernel32.GetTickCount` via `ctypes` (already in Arya's code) | None | ~1 ms → **PRECISE** | Compute `(GetTickCount() - lii.dwTime) & 0xFFFFFFFF` with `GetTickCount.restype = c_uint32`. The current code relies on signed wraparound. **Only works in the logged-in user session**, so the agent must run as a user-logon task, not a Windows Service. |
| **macOS** | 1) Quartz `CGEventSourceSecondsSinceLastEventType(1, 0xFFFFFFFF)` via `ctypes` from `ApplicationServices.framework` (restype `c_double`). 2) Fallback: parse `HIDIdleTime` (nanoseconds) from `ioreg -c IOHIDSystem`. | None (no Accessibility or Input Monitoring prompt) | **PRECISE** | Avoid `pynput` on macOS: it needs Accessibility/Input Monitoring permission and adds nothing here. |
| **Linux (X11)** | `XScreenSaverQueryInfo` via `ctypes` (`libX11.so.6`, `libXss.so.1`), or the `xprintidle` binary | None (needs `DISPLAY`, package `libxss1`) | **PRECISE** | — |
| **Linux (Wayland, GNOME)** | D-Bus `org.gnome.Mutter.IdleMonitor.GetIdletime` (ms) via `gdbus call --session …` | None | **PRECISE** | Default on Ubuntu 22.04+ |
| **Linux (Wayland, KDE)** | D-Bus `org.freedesktop.ScreenSaver.GetSessionIdleTime` | None | **COARSE** (1 s) | — |
| **Linux (fallback)** | `loginctl show-session $XDG_SESSION_ID -p IdleHint -p IdleSinceHint` | None | **COARSE** (often only flips at screen lock) | — |
| Any | Nothing works | — | **NONE** | Node reported `UNSCHEDULABLE` unless the owner sets `dedicated_mode = true` |

**Effect on the outcome:**
- On PRECISE nodes, pause latency is about 0.25 s.
- COARSE nodes pause late, which risks owner annoyance, so the scheduler gives them lower priority (`input_detection` is part of the node's capabilities and a feature in the Oracle).
- The paper reports pause latency per OS (G2).

### 5.2 Pausing and resuming jobs
`psutil.Process.suspend()/resume()` (Ronit's `ProcessController`) maps to:
- **Linux/macOS:** `SIGSTOP`/`SIGCONT`, which is reliable and instant.
- **Windows:** `NtSuspendProcess`/`NtResumeProcess`, which suspends all threads and is reliable.

Children must be suspended before the parent, which the existing code already does.

**Caveat on every OS:** a suspended process **keeps its RAM**. That's why migration exists (D5), and why the scheduler doesn't place jobs that need more than `ram_available_mb − 1024`.

### 5.3 Making the job invisible to the owner (priority)
| OS | How | Who |
|---|---|---|
| Windows | `subprocess.Popen(..., creationflags=subprocess.IDLE_PRIORITY_CLASS)` | Ronit (ProcessController) |
| macOS | Prefix the command with `["taskpolicy", "-b"]` (background QoS: CPU and I/O throttled) **and** `os.nice(19)` | Ronit |
| Linux | `preexec_fn=lambda: os.nice(19)`, plus `ionice -c3` if available | Ronit |
| All | Optional `max_job_cores` via `psutil.Process.cpu_affinity()` (Windows and Linux only; **not supported on macOS**) | Ronit (API), Arya (config) |

### 5.4 Sleep and lid-close: the biggest hidden availability limit
An idle laptop **goes to sleep**, and a sleeping laptop can't compute. While (and only while) a job is running and the laptop is **on AC power**, the agent holds a "stay awake" assertion:

| OS | Mechanism | Lid closed? |
|---|---|---|
| Windows | `kernel32.SetThreadExecutionState(ES_CONTINUOUS \| ES_SYSTEM_REQUIRED)` from a dedicated thread; clear with `ES_CONTINUOUS` when done | Depends on the power setting "When I close the lid". Owners may set it to "Do nothing" while plugged in. |
| macOS | Spawn `caffeinate -i -w <job_pid>` (exits automatically with the job) | **Sleeps on lid close** (unless clamshell with an external display). macOS laptops only contribute while open. |
| Linux | Spawn `systemd-inhibit --what=sleep:idle --who=idlegrid --why="job running" --mode=block sleep infinity`; kill it when done | Depends on `HandleLidSwitch` in logind. Usually suspends. |

**Effect on the outcome:**
- The model learns availability **as it actually is** (sleep shows up as gaps in the logs, which end idle sessions).
- Practical tip for the team: leave laptops open and plugged in when not in use. This is documented in the runbook and is an honest limitation in the paper.

### 5.5 Autostart, power and other OS differences
| Topic | Windows | macOS | Linux |
|---|---|---|---|
| Autostart at login | Task Scheduler task "At log on", user context (`schtasks /Create /SC ONLOGON /RL LIMITED`) | `~/Library/LaunchAgents/in.idlegrid.agent.plist` (LaunchAgent, **not** LaunchDaemon) | `~/.config/systemd/user/idlegrid-agent.service` + `systemctl --user enable --now` |
| Battery / AC | `psutil.sensors_battery()` | same | same (`None` on desktops = treat as AC) |
| Required env vars for child processes | Must pass `SYSTEMROOT`, `TEMP`, `TMP`, `PATH`, `USERPROFILE` (Python breaks without `SYSTEMROOT`) | `PATH`, `HOME`, `TMPDIR`, `LANG` | `PATH`, `HOME`, `LANG` |
| Console encoding | UTF-8 reconfigure (already in `gridctl.py`) | UTF-8 | UTF-8 |
| Firewall | The coordinator gets a Defender prompt: allow on **Private** networks. Campus Wi-Fi is often "Public", so use Tailscale. | Usually no prompt for outbound; coordinator prompt on first bind | `ufw` usually inactive |
| CPU architecture | x86-64 | Apple Silicon (arm64) or x86-64 | x86-64 |
| Performance | Measured as `perf_score` by a benchmark at agent start (§10.1); the scheduler scales runtime estimates by it | Apple Silicon is often fastest per core | — |

**Numerical results** can differ in the last decimal places across OSes because of different BLAS libraries. This doesn't matter for HPO, and the paper mentions it as a reproducibility note.

### 5.6 Networks (campus, home/hostel, hotspot)

> **Correction to earlier advice:** in the design reviews we said the pull model fixes campus Wi-Fi. That's only half true. Pull removes the need for the *coordinator* to reach workers, but workers still have to reach the *coordinator laptop*, which is just another Wi-Fi client. Campus networks usually block client-to-client traffic (client isolation), so workers can't reach it there either.

| Network | Can workers reach the coordinator? | What we use |
|---|---|---|
| Home/hostel router | Usually yes | Direct LAN: `http://<coordinator-LAN-IP>:8000` |
| Phone hotspot | Yes (most phones allow client-to-client) | Direct LAN |
| Campus Wi-Fi | Usually **no** (client isolation) | **Overlay network: Tailscale** on all six machines (WireGuard, works through NAT and isolation by relaying over HTTPS port 443). Coordinator URL: `http://<coordinator-tailscale-IP>:8000` or its MagicDNS name. |

**Rules:**
- The agent and CLI read the Dispatcher URL from config (`dispatcher_url`), so switching networks is a config change, not a code change.
- Default to Tailscale everywhere for simplicity. Tailscale's free Personal plan limits users and devices, so **check the current limits**. If five separate accounts exceed them, put all devices under one shared team account, or use ZeroTier or Headscale.
- Tailscale traffic is end-to-end encrypted (WireGuard), so plain HTTP inside it is acceptable. Without Tailscale (home LAN), the per-user API token still protects every endpoint (§16).
- **Phase 0 network test (mandatory):** from every laptop, `curl http://<coordinator>:8000/healthz` on campus Wi-Fi, home Wi-Fi and the hotspot. Record the results in `docs/runbook/network.md`.

---

## 6. Repository layout and migration from the existing code

### 6.1 Target layout
```
PredictiveIdleComputeScheduler/
├── pyproject.toml                  # one package "idlegrid"; extras: agent, dispatcher, ml, dev
├── requirements/
│   ├── worker-env.txt              # PINNED shared worker environment (D6); hash → worker_env_hash
│   ├── dispatcher.txt              # pinned server deps
│   └── dev.txt                     # pytest, ruff, httpx, etc.
├── .gitignore  .github/workflows/ci.yml  .github/pull_request_template.md
├── README.md                       # quickstart for all three roles
├── docs/
│   ├── PRD.md (this file)  PROJECT_OVERVIEW.md  CODE_REVIEW.md
│   ├── contract.md                 # human-readable mirror of Appendices A–E
│   ├── design/                     # architecture, sequence diagrams, ADRs (2nd Review)
│   ├── runbook/                    # install per OS, network, coordinator setup, demo checklist
│   └── paper/                      # LaTeX/Word source, figures
├── idlegrid/
│   ├── __init__.py                 # __version__
│   ├── common/        [Harith]     models.py, enums.py, config.py, auth.py, timeutil.py, logging.py
│   ├── agent/         [Arya]       __main__.py, agent.py, config.py, client.py, metrics.py,
│   │                               idle/{__init__,base,windows,macos,linux}.py, usage_logger.py,
│   │                               killswitch.py, power.py, worker.py, perf.py, install/{windows,macos,linux}.py
│   ├── executor/      [Ronit]      process_controller.py, runner.py, platform.py
│   ├── packager/      [Ronit]      bundle.py
│   ├── cli/           [Ronit]      gridctl.py, config.py, __main__.py
│   ├── dashboard/     [Ronit]      templates/index.html, static/{css,js,vendor}/
│   ├── hpo/           [Ronit]      spec.py, controller.py, trial_entry.py, bundle.py
│   ├── dispatcher/    [Harith]     app.py, deps.py, api/{heartbeat,jobs,nodes,attempts,usage,hpo,admin,experiments,ws}.py,
│   │                               services/{node_service,job_service,command_queue,blob_store,oracle_client,event_bus}.py,
│   │                               scheduler.py, policies.py, status.py, __main__.py
│   ├── devtools/      [Harith]     fake_agents.py (from mock_cluster.py), trace_replay_agents.py
│   ├── db/            [Amaan]      engine.py, migrate.py, migrations/0001_initial.sql …, repositories/{users,nodes,
│   │                               usage,jobs,attempts,commands,studies,experiments,models}.py, analytics.py,
│   │                               export.py, admin.py, optuna_storage.py, backup.py
│   ├── oracle/        [Rejish]     availability.py, sessionize.py, features.py, dataset.py, models.py, train.py,
│   │                               evaluate.py, oracle.py, registry.py, synthetic.py
│   └── sim/           [Rejish]     traces.py, workload.py, engine.py, metrics.py, run.py, plots.py
├── examples/
│   ├── jobs/                       # monte_carlo_pi.py, matrix_stress.py, tabular_ml_train.py (from Ronit)
│   └── hpo/                        # objective.py + space.json + data/ (reference HPO workload, §11.4)
├── experiments/                    # notebooks, configs, results/ (gitignored raw data, committed summaries)
├── scripts/                        # install_*.ps1/.sh, coordinator_setup, backup cron, dev_cluster
└── tests/
    ├── unit/{common,agent,executor,packager,cli,hpo,dispatcher,db,oracle,sim}/
    ├── integration/                # dispatcher + MySQL + fake agents, in-process
    └── e2e/                        # real multi-laptop checklists and scripts
```

### 6.2 Migration map: every existing file
| Existing file | Destination | What changes (details in the owner's §10 section) |
|---|---|---|
| `Arya_Work/main.py` | `idlegrid/agent/__main__.py` | Subcommands `run`, `status`, `enable`, `disable`, `install`, `uninstall`, `log-only` |
| `Arya_Work/node_agent/agent.py` | `idlegrid/agent/agent.py` | Becomes a supervisor of 4 threads (heartbeat, kill switch, usage logger, worker). Keep its signal handling and sleep loop. |
| `Arya_Work/node_agent/config.py` | `idlegrid/agent/config.py` | Keep `NodeConfig` and the stable `node_id`. Move to TOML. Add the fields in Appendix E.2. Default URL `http://127.0.0.1:8000`. |
| `Arya_Work/node_agent/metrics_collector.py` | `idlegrid/agent/metrics.py` + `idlegrid/agent/idle/*.py` | Split OS idle detection into `idle/`. Add `host_cpu_percent`, power and HostState logic. Fix `GetTickCount` restype. |
| `Arya_Work/node_agent/heartbeat_sender.py` | `idlegrid/agent/client.py` | Becomes `DispatcherClient` (heartbeat, bundle download, logs, result, usage). Payload follows Appendix A `Heartbeat`. Add auth header. |
| `Arya_Work/config.json` | `idlegrid/agent/default_agent.toml` | Format change only |
| `Arya_Work/requirements.txt` | delete | Use `pyproject.toml` extras |
| `Arya_Work/tests/*` | `tests/unit/agent/` | Update imports and expected states |
| `Amaan_Work/DatabaseCreate.sql` | `idlegrid/db/migrations/0001_initial.sql` | Rewritten to Appendix C |
| `Amaan_Work/db_functions.py` | `idlegrid/db/repositories/*.py` | Keep the upsert pattern. Move to SQLAlchemy Core + `text()`. Credentials from env. Transactions. |
| `Amaan_Work/ReturnTables.sql` | delete | — |
| `Rejish_Work/generate_dataset.py` | `idlegrid/oracle/synthetic.py` | **Tests only.** Produce `UsageSample`-shaped rows. Fix future dates. Generate from a *process* (sessions), not from the label. |
| `Rejish_Work/train_oracle.py` | `idlegrid/oracle/train.py` (+ `dataset.py`, `features.py`, `models.py`) | Time-based split, sessionised labels, quantile models, registry |
| `Rejish_Work/ml_oracle.py` | `idlegrid/oracle/oracle.py` | `IdleOracle` (keep `MLOracle = IdleOracle` alias). Seconds. Contract-shaped input. Keep `evaluate_node_suitability()` and the fallback idea. |
| `Ronit_Work/src/common/models.py` | `idlegrid/common/models.py` | Extended to Appendix A (enum changes in §4.4) |
| `Ronit_Work/src/packager/bundle.py` | `idlegrid/packager/bundle.py` | `job_id` optional, `Path.is_relative_to` check, zip-bomb limits |
| `Ronit_Work/src/executor/process_controller.py` | `idlegrid/executor/process_controller.py` | Active-time timeout, `TIMED_OUT`, low priority, minimal env, log offsets |
| `Ronit_Work/src/executor/runner.py` | `idlegrid/executor/runner.py` | `setup_workspace(bundle, workspace_name)`, never delete an existing workspace, attempt-aware |
| `Ronit_Work/src/cli/gridctl.py` + `Ronit_Work/gridctl.py` | `idlegrid/cli/gridctl.py` (console script `gridctl`) | Auth, `/api/v1` paths, `status.value` fix, demo-run fix, new `hpo` commands |
| `Ronit_Work/src/dashboard/app.py` | `idlegrid/dispatcher/app.py` + `api/*.py` (**Harith**) | App factory, routers, auth, sync endpoints for DB work |
| `Ronit_Work/src/dashboard/mock_cluster.py` | **split:** lifecycle logic → `dispatcher/services/job_service.py` + `scheduler.py` (Harith); fake nodes → `devtools/fake_agents.py` (Harith) | Fake nodes now talk to the real HTTP API |
| `Ronit_Work/src/dashboard/templates`, `static/` | `idlegrid/dashboard/` (Ronit) | Real data, new pages, token login, escaping, vendored assets |
| `Ronit_Work/demo_jobs/*` | `examples/jobs/` | Unchanged |
| `Ronit_Work/tests/*` | `tests/unit/{executor,packager}`, `tests/integration/` | Imports, new behaviours |
| `Ronit_Work/README.md` | merged into `README.md` + `docs/` | Remove overclaims |
| `Ronit_Work/workspaces/`, `results/`, `demo_results/`, all `__pycache__/`, `*.pyc` | **delete** + `.gitignore` | — |
| `Project_Idea_Initial.md`, `Project_Outline_and_Division.md`, `PROJECT_OVERVIEW.md` | `docs/` | — |

The migration happens in **one PR** (Phase 0, task H-P0-2) that moves files with `git mv`, so history is kept. Behaviour changes come in later PRs.

---

## 7. Contracts overview (full text in the appendices)

| Contract | Where | Custodian |
|---|---|---|
| Enums and Pydantic models | Appendix A → `idlegrid/common/models.py` | Harith |
| REST and WebSocket API | Appendix B → `idlegrid/dispatcher/api/*` | Harith |
| MySQL schema | Appendix C → `idlegrid/db/migrations/*.sql` | Amaan |
| Usage CSV format | Appendix D → `idlegrid/agent/usage_logger.py` | Arya |
| Configuration files | Appendix E → `idlegrid/*/config.py` | each owner |
| State machines | Appendix F → `idlegrid/dispatcher/status.py`, `scheduler.py` | Harith |
| CI | Appendix G → `.github/workflows/ci.yml` | Harith |

`idlegrid.common.models.SCHEMA_VERSION = "1.0"`. Every heartbeat and usage batch carries it. The Dispatcher rejects a major-version mismatch with HTTP 426 and accepts minor differences.

---

## 8. Requirements

### 8.1 Functional requirements
| ID | Requirement | Owner | Phase |
|---|---|---|---|
| FR-01 | The agent measures seconds since last input on Windows, macOS and Linux (X11, GNOME Wayland, KDE Wayland, fallback) and reports which method it used and its precision | Arya | P0/P1 |
| FR-02 | The agent logs one `UsageSample` every 15 s to a local daily CSV, even with no Dispatcher | Arya | P0 |
| FR-03 | The agent uploads usage batches idempotently whenever the Dispatcher is reachable, and catches up after outages | Arya + Amaan | P1 |
| FR-04 | The agent sends a heartbeat every 5 s and executes the commands it receives | Arya | P1/P2 |
| FR-05 | The Dispatcher keeps a live node registry, computes `NodeStatus`, and records every status change | Harith + Amaan | P1 |
| FR-06 | Users submit script jobs (zip bundle) through the CLI and dashboard. Each gets a Dispatcher-assigned ID. | Ronit + Harith | P2 |
| FR-07 | The scheduler assigns queued jobs to free nodes using a pluggable `Policy` | Harith | P2 (reactive), P4 (predictive) |
| FR-08 | The agent downloads, verifies and runs the job at lowest priority, streams logs, and uploads results | Arya + Ronit | P2 |
| FR-09 | The kill switch pauses the job within 1 s (p95) of owner input on PRECISE nodes and resumes after `resume_after_idle_sec` | Arya + Ronit | P2 |
| FR-10 | The timeout counts only active (unpaused) time. Expiry gives `TIMED_OUT`. | Ronit | P2 |
| FR-11 | Paused for more than `migrate_after_sec` → the attempt is aborted and marked `MIGRATED`, and the job is requeued with a priority boost | Harith + Arya | P3 |
| FR-12 | Node offline detection (15 s), lost attempts after the grace period (60 s), fencing of stale attempts and results | Harith | P3 |
| FR-13 | The agent prevents system sleep only while a job runs on AC power. Configurable `require_ac_power` (default true). | Arya | P3 |
| FR-14 | Per-user API tokens on every endpoint. Admin-only endpoints. Owners can drain or undrain their own node. | Harith + Amaan | P3 |
| FR-15 | The Oracle predicts q10/q20/q50 remaining idle seconds per node, with a fallback heuristic | Rejish | P3 |
| FR-16 | The predictive policy uses the Oracle (best fit at a confidence quantile, starvation guard) | Harith + Rejish | P4 |
| FR-17 | Distributed Optuna HPO: create, monitor and cancel studies; trials run as jobs; best params reported | Ronit + Harith + Amaan | P4 |
| FR-18 | A trace-driven simulator evaluates policies offline using the same policy code | Rejish + Harith | P3/P4 |
| FR-19 | Experiment runs: tag jobs with `experiment_run_id`, switch policy, compute summary metrics | Harith + Amaan | P4/P5 |
| FR-20 | The dashboard shows nodes (with predictions), jobs, attempts, logs, studies and experiments, live | Ronit | P1→P6 |
| FR-21 | Nightly retraining and hot reload of the Oracle model | Rejish + Harith | P5 |
| FR-22 | One-command install and autostart on all 3 OSes; uninstall leaves no trace | Arya | P6 |
| FR-23 | Owner controls: `idlegrid-agent disable/enable`, plus a "dedicated mode" for unattended machines | Arya | P3/P6 |
| FR-24 | Database backup (nightly `mysqldump`) and restore procedure | Amaan | P5 |
| FR-25 | Usage export for research (CSV/Parquet), with node pseudonymisation | Amaan | P1/P5 |

### 8.2 Non-functional requirements
| ID | Requirement | Target | How verified |
|---|---|---|---|
| NFR-01 | Pause latency (owner input → job suspended) | p95 ≤ 1.0 s on PRECISE nodes, ≤ 3 s on COARSE | `tests/e2e/pause_latency.py` per OS |
| NFR-02 | Owner impact while a job runs | Job at lowest OS priority; 0% job CPU while paused | Manual check + `ProcessController` metrics |
| NFR-03 | Offline detection | ≤ 15 s | Integration test |
| NFR-04 | Dispatcher capacity | 20 nodes, 1,000 queued jobs, 10 heartbeats/s, p95 API latency < 200 ms | Load test with `fake_agents` |
| NFR-05 | Durability | Dispatcher restart loses no job and no result; running attempts continue | Chaos test C4 |
| NFR-06 | Data completeness | ≥ 95% of expected usage samples while the agent runs; no duplicates | Analytics query |
| NFR-07 | Portability | Windows 10/11, macOS 13+, Ubuntu 22.04+, Python 3.12 | CI matrix + install tests |
| NFR-08 | Security | Every endpoint authenticated; tokens stored hashed; no secrets in git | Tests + `gitleaks`-style check in CI |
| NFR-09 | Privacy | No keystrokes, content or app names recorded | Code review checklist |
| NFR-10 | Code quality | `ruff` clean; ≥ 70% line coverage on `common`, `dispatcher`, `db`, `executor`, `oracle`, `sim` | CI |
| NFR-11 | Install time | < 15 min on a clean machine following the runbook | Phase 6 install test |
| NFR-12 | Observability | Structured logs (JSON lines) on Dispatcher and agent; `/healthz`; log rotation | Review |

---

## 9. Phase plan

### 9.1 Overview
| Phase | Weeks | Dates | Theme | Exit demo |
|---|---|---|---|---|
| **P0** | W1–W2 | 12 Oct – 25 Oct 2026 | Foundations + **start data collection** | All 5 laptops logging usage. Restructured repo with CI green. Network test done. |
| **P1** | W3–W5 | 26 Oct – 15 Nov | Live cluster: real heartbeats, DB, Dispatcher v1, dashboard shows real laptops | Dashboard shows 5 real laptops changing status as owners use them |
| **P2** | W6–W8 | 16 Nov – 6 Dec | Remote execution MVP + kill switch | Job from laptop A runs on laptop B, pauses on touch, resumes, results return |
| **P3** | W9–W10 | 7 Dec – 20 Dec | Fault tolerance (migration, node loss, fencing, auth) + Oracle v1 + simulator v1 | Migration and laptop-unplug demos. Oracle v1 evaluated on real data. First simulation plots. |
| **P4** | W11–W13 | 21 Dec – 10 Jan 2027 | Predictive scheduling + Optuna HPO + **paper submission** | 40-trial HPO across the fleet with the predictive policy. Paper submitted. |
| **P5** | W14–W17 | 11 Jan – 7 Feb | **2nd Review** (W14–W15) + live experiments + nightly retraining | Review demo. Live A/B results. |
| **P6** | W18–W20 | 8 Feb – 28 Feb | Hardening, installers, UX polish. **Feature freeze 21 Feb.** | Clean-machine install on 3 OSes. All chaos tests pass. |
| **P7** | W21–W24 | 1 Mar – 28 Mar | **Code freeze 7 Mar**, report (due **15 Mar**), rehearsals, **final review** | Final demo + paper presented |

Holiday weeks (W11–W12) carry lighter, mostly asynchronous work (paper writing, Optuna integration, dashboard).

### 9.2 Phase 0: Foundations and data collection (W1–W2, 12–25 Oct)
**Why first:** the Oracle and the experiments need **months** of real usage data. Logging must start in week 1, before anything else is integrated.

| Task | Owner | Description | Acceptance |
|---|---|---|---|
| A-P0-1 | Arya | Standalone `usage_logger` with OS idle detection for all 3 OSes (§10.1.4). Writes the Appendix D CSV every 15 s. Runs with only `psutil`. | Running on all 5 laptops by **Wed 14 Oct**. CSV validated by `scripts/validate_usage_csv.py`. |
| A-P0-2 | Arya | Autostart the logger at login on each team laptop (manual steps from §5.5) | Survives reboot on all 5 laptops |
| H-P0-1 | Harith | Write `idlegrid/common/models.py` exactly as Appendix A. Write `docs/contract.md`. Get every member's sign-off. | PR merged with 5 approvals |
| H-P0-2 | Harith | Restructure PR: create the package and move every file per §6.2 with `git mv`, fix imports, add `pyproject.toml`, `.gitignore`, delete junk | `pytest` passes (old tests moved). No `sys.path` hacks remain. |
| H-P0-3 | Harith | CI (Appendix G): ruff + unit tests on a 3-OS matrix + MySQL service job | CI green on `main` |
| H-P0-4 | Harith | Network test from every laptop on campus, home and hotspot (§5.6). Set up Tailscale. | `docs/runbook/network.md` with results |
| M-P0-1 | Amaan | Install MySQL 8 on the coordinator laptop. Create the `idlegrid` DB user from an env var. **Rotate the password committed in `db_functions.py`.** | `IDLEGRID_DB_URL` works. Old password invalid. |
| M-P0-2 | Amaan | `0001_initial.sql` per Appendix C + `migrate.py` runner + `engine.py` | `python -m idlegrid.db.migrate` creates all tables on a clean DB, and is idempotent |
| R-P0-1 | Rejish | Move the Oracle code. Rewrite `synthetic.py` to emit Appendix D rows from a session-based process. Write `availability.py` (the single shared definition, §10.4.3). | Unit tests for the availability definition |
| R-P0-2 | Rejish | Literature notes for the paper's related work (HTCondor, BOINC, desktop-grid availability prediction, spot-instance interruption prediction) | `docs/paper/related_work.md` |
| N-P0-1 | Ronit | Fix the confirmed bugs in place after the move: R1 (demo-run runs twice), R5 (`status.value`), R3 (`TIMED_OUT`) | Regression tests added |
| N-P0-2 | Ronit | Update models usage to the new enums (CLI and JS colour maps) | CLI and dashboard render the new statuses |
| ALL | All | Sign the data-logging consent (§16.3) | Signed copies in the team drive |

**Exit criteria:** usage CSVs are growing on 5 laptops. CI is green. The package installs with `pip install -e .[dev]`. The contract is merged.

### 9.3 Phase 1: Live cluster (W3–W5, 26 Oct – 15 Nov)
| Task | Owner | Description | Acceptance |
|---|---|---|---|
| A-P1-1 | Arya | Agent supervisor + `DispatcherClient.heartbeat()` per Appendix B. HostState logic with `host_cpu_percent` (excluding job PIDs; empty for now). | Fake Dispatcher test + real Dispatcher shows the node |
| A-P1-2 | Arya | Usage batch upload with local cursor file (`~/.idlegrid/usage/.upload_cursor`) and catch-up | Unplug the network for 1 h → all rows arrive later, no duplicates |
| A-P1-3 | Arya | `perf.py` benchmark (§10.1.6) → `capabilities.perf_score` | Score between 0.3 and 3.0 on team laptops; stable within ±10% |
| A-P1-4 | Arya | Switch the logger into the agent without changing the CSV format (the standalone logger is retired) | Continuous CSV across the switchover |
| H-P1-1 | Harith | Dispatcher app factory, config, auth dependency, `/healthz`, `POST /api/v1/heartbeat`, `GET /api/v1/nodes`, `NodeService`, `status.py` (pure status function, Appendix F.1) | Unit tests for every status branch |
| H-P1-2 | Harith | `POST /api/v1/usage` → `usage_repo.insert_ignore` | 10k-row batch in < 2 s |
| H-P1-3 | Harith | `devtools/fake_agents.py` (from `mock_cluster.py`): N simulated agents using the real HTTP API with scripted activity | `idlegrid-dispatcher --sim-nodes 4` shows 4 nodes |
| H-P1-4 | Harith | WebSocket `/ws/v1/telemetry` snapshot every 1 s | Dashboard live |
| M-P1-1 | Amaan | Repositories: `users`, `nodes`, `node_status_events`, `usage`. `admin.py create-user` (prints the token once, stores SHA-256). | Repository tests against MySQL in CI |
| M-P1-2 | Amaan | `export.py usage --from --to --out` (CSV/Parquet, pseudonymised node IDs option) | Export reproduces the uploaded rows exactly |
| R-P1-1 | Rejish | `sessionize.py` + exploratory analysis notebook on the first 3 weeks of real data: session length distributions per node, hour and day of week | `experiments/notebooks/01_eda.ipynb` + summary figures |
| R-P1-2 | Rejish | `features.py` (online and offline from one function) + `dataset.py` (prediction points every 60 s inside sessions; label = remaining seconds) | Tests: features at t never use data after t |
| N-P1-1 | Ronit | Dashboard on real data: node cards (OS icon, input-detection badge, power, host state, `last_heartbeat` age), token login, HTML escaping, vendored assets (fonts, Chart.js) | Works offline. No `innerHTML` with unescaped data. |
| N-P1-2 | Ronit | CLI config (`gridctl login --url --token`, `~/.idlegrid/client.toml`), `/api/v1` paths, `gridctl nodes` | CLI tests with a mocked API |

**Exit demo:** the dashboard shows all real laptops. Touching a laptop turns its card to `HOST_ACTIVE` within one heartbeat. The DB has 3+ weeks of usage.

### 9.4 Phase 2: Remote execution MVP (W6–W8, 16 Nov – 6 Dec)
| Task | Owner | Description | Acceptance |
|---|---|---|---|
| N-P2-1 | Ronit | `ProcessController`: active-time timeout (FR-10), low priority per OS (§5.3), minimal env (§5.5), log offsets, `cpu_affinity` option | Unit tests on the CI 3-OS matrix incl. the pause-past-timeout case |
| N-P2-2 | Ronit | `JobRunner.setup_workspace(bundle, workspace_name)`. Never delete an existing workspace (raise). Attempt-aware result bundle. | Tests |
| N-P2-3 | Ronit | Packager: optional `job_id`, `Path.is_relative_to`, limits (bundle ≤ 200 MB, uncompressed ≤ 1 GB, ≤ 10,000 files) | Zip-bomb and path-traversal tests |
| N-P2-4 | Ronit | CLI `submit`, `jobs`, `status`, `logs --follow` (offset-based, stops on 404 or terminal state), `download`, `cancel` against the real API | E2E-1 |
| A-P2-1 | Arya | `worker.py`: handle `START` (download, SHA-256 check, `JobRunner.run_async`, low priority), log shipping every 2 s, result upload with retry, workspace cleanup (keep the last 5) | E2E-1 |
| A-P2-2 | Arya | `killswitch.py`: 0.25 s poll; pause on input; resume after `resume_after_idle_sec`; `pause_on_host_busy` | NFR-01 measured on own OS; later all 3 |
| A-P2-3 | Arya | Report `current_attempt` in heartbeats; acknowledge commands; handle `ABORT`, `PAUSE`, `RESUME` | Integration test with the Dispatcher |
| H-P2-1 | Harith | `JobService`: `POST /api/v1/jobs` (validate, assign ID, store bundle), list, get, logs, result download, cancel | API tests |
| H-P2-2 | Harith | `command_queue` (DB-backed, at-least-once, ack via heartbeat) + attempt endpoints (bundle, logs, result) | Duplicate deliveries are harmless (idempotent by `command_id`) |
| H-P2-3 | Harith | Scheduler loop v1 + policies `FifoAnyIdle` and `ReactiveLongestIdle` (pure functions, Appendix F.3) | Unit tests with synthetic `NodeView`s |
| M-P2-1 | Amaan | Repositories: `jobs`, `job_attempts`, `node_commands`. Atomic `assign_job_to_node()` transaction (§10.2.5). | Concurrency test: 2 schedulers never double-book |
| R-P2-1 | Rejish | Baselines B1/B2 + first quantile model on real data (offline) + evaluation script | `experiments/results/oracle/v0/report.md` |
| R-P2-2 | Rejish | `sim/traces.py` (availability intervals from usage) + `sim/workload.py` | Tests |

**Exit demo (MVP):** `gridctl submit examples/jobs/tabular_ml_train.py --follow` on laptop A runs on idle laptop B. Touching B's keyboard pauses it (Task Manager / Activity Monitor shows 0% CPU). Leaving B idle for 2 minutes resumes it. `gridctl download` brings the results back to A.

### 9.5 Phase 3: Fault tolerance + Oracle v1 + simulator v1 (W9–W10, 7–20 Dec)
| Task | Owner | Description | Acceptance |
|---|---|---|---|
| H-P3-1 | Harith | Migration (F3): paused > `migrate_after_sec` → `ABORT` + `MIGRATED` + requeue with priority boost | Chaos test C1 |
| H-P3-2 | Harith | Offline (15 s) and lost (60 s) handling, fencing (stale attempt → `ABORT`; stale result → 409) | Chaos tests C2, C3 |
| H-P3-3 | Harith | Auth everywhere (per-user tokens, admin flag), node ownership binding, drain/undrain, restricted CORS | Security tests |
| H-P3-4 | Harith | Experiment runs: `experiments` table, `experiment_run_id` tagging, active policy switch API | API tests |
| A-P3-1 | Arya | `power.py`: sleep prevention per OS while a job runs on AC; `require_ac_power`; local fail-safe abort | Laptop doesn't sleep during a 30-minute job with lid open on AC |
| A-P3-2 | Arya | Linux Wayland and KDE paths, COARSE fallback, `dedicated_mode` | Tested on at least one Linux laptop |
| R-P3-1 | Rejish | **Oracle v1**: HistGradientBoosting quantile models (q10, q20, q50), time-based split, calibration, registry, `IdleOracle.predict()`, fallback heuristic | q20 empirical coverage 0.75–0.85 on the test split. Beats B2 on pinball loss. |
| R-P3-2 | Rejish | **Simulator v1**: discrete-event engine using `idlegrid.dispatcher.policies` + Oracle; policies FifoAnyIdle, ReactiveLongestIdle, Predictive-q50, Predictive-q20, OraclePerfect | Unit tests + first plots |
| M-P3-1 | Amaan | `analytics.py`: `experiment_summary(run_id)`, `wasted_compute`, `goodput`, `queue_wait`, `availability_report`. `oracle_models` repo. | Verified by hand on a fixture dataset |
| N-P3-1 | Ronit | Dashboard: job detail page (attempt timeline: assigned, running, paused, migrated), logs viewer with offsets, cancel button, prediction bars on node cards | Visual QA |
| N-P3-2 | Ronit | HPO spec + `trial_entry.py` + `hpo/bundle.py` (unit-testable without the Dispatcher) | Trial wrapper tests on 3 OSes |

**Exit demo:** a job migrates when its owner stays active, and survives unplugging a laptop. The Oracle v1 evaluation report is ready, and the first simulator charts compare reactive and predictive policies.

### 9.6 Phase 4: Predictive scheduling + Optuna HPO + paper (W11–W13, 21 Dec – 10 Jan)
| Task | Owner | Description | Acceptance |
|---|---|---|---|
| H-P4-1 | Harith | `Predictive` policy (Appendix F.3), `OracleClient` with a 30 s cache, safety buffer, starvation guard, runtime estimate scaled by `perf_score` | Unit tests + simulator agreement test |
| H-P4-2 | Harith | Integrate the `HpoController.tick()` into the scheduler loop; `tell` on results | E2E-2 |
| N-P4-1 | Ronit | `HpoController` (ask/tell, `constant_liar` TPE, MySQL storage via Amaan), API handlers' service functions, CLI `gridctl hpo create/status/best/cancel` | E2E-2: 40 trials across ≥ 3 laptops |
| N-P4-2 | Ronit | Dashboard HPO page: best-so-far chart, trials table (node, duration, value, attempts), speedup vs sequential estimate | Visual QA |
| M-P4-1 | Amaan | `optuna_storage.py` (separate schema `idlegrid_optuna`, pool settings), `studies` repo, analytics for studies | Optuna study survives a Dispatcher restart |
| R-P4-1 | Rejish | **EXP-SIM full run** (§11.2): all policies × workloads × windows × seeds, 95% CIs, Wilcoxon tests, plots | `experiments/results/sim/v1/` + figures for the paper |
| A-P4-1 | Arya | Pause-latency benchmark script per OS (NFR-01) for the paper | Numbers for Windows, macOS, Linux |
| ALL | All | **Paper:** draft by 3 Jan, internal review 4–7 Jan, **submit by 10 Jan** (or the venue's earlier deadline; see §12) | Submission confirmation email (proof for the Outcome Analysis) |

**Exit demo:** a 40-trial HPO study runs across the fleet under the predictive policy, with the dashboard showing trials moving between laptops when owners return. The paper is submitted.

### 9.7 Phase 5: 2nd Review + live experiments (W14–W17, 11 Jan – 7 Feb)
| Task | Owner | Description | Acceptance |
|---|---|---|---|
| ALL-P5-1 | All (Harith leads) | **2nd Review pack:** design docs (`docs/design/`), plan (§9), requirements (§8), methodology (§11), live demo of P0–P4 | Rehearsed twice before the review |
| H-P5-1 | Harith | `experiments/run_live.py`: schedules interleaved A/B blocks, sets the policy, submits the reference HPO workload, collects summaries | Runs unattended for a 3-hour block |
| ALL-P5-2 | All | **EXP-LIVE** (§11.3): ≥ 5 blocks per policy, plus single-laptop baselines | `experiments/results/live/` |
| R-P5-1 | Rejish | Nightly retraining job + model registry + `/admin/oracle/reload`; drift monitoring (weekly coverage report) | Model updates without a Dispatcher restart |
| M-P5-1 | Amaan | Nightly backup + restore drill; DB indexes tuned using `EXPLAIN` | Restore test documented |
| R-P5-2 | Rejish | Sim-to-real validation: replay the live windows in the simulator and compare metrics | Gap table in the paper or report |
| N-P5-1 | Ronit | Experiments page in the dashboard (policy comparison charts) | Visual QA |
| A-P5-1 | Arya | Usage completeness report per laptop; fix gaps | NFR-06 |

### 9.8 Phase 6: Hardening, installers, polish (W18–W20, 8–28 Feb). Feature freeze 21 Feb.
| Task | Owner | Description | Acceptance |
|---|---|---|---|
| A-P6-1 | Arya | `idlegrid-agent install/uninstall` for all 3 OSes (Task Scheduler / LaunchAgent / systemd user) + `scripts/install_*.ps1/.sh` | NFR-11 clean-machine test |
| H-P6-1 | Harith | Chaos suite C1–C6 automated where possible (§14.4); load test NFR-04 | All pass |
| H-P6-2 | Harith | Structured logging, log rotation, `/api/v1/metrics/summary` | Review |
| N-P6-1 | Ronit | UX polish, empty and error states, accessibility (contrast, keyboard navigation), screenshots for the report | Visual QA checklist |
| M-P6-1 | Amaan | Data-quality report + final export for the paper and report (pseudonymised) | Export reproducible from one command |
| R-P6-1 | Rejish | Final model, ablations (feature groups, quantile choice), final figures | Figures in `docs/paper/figures/` |
| ALL | All | Bug bash: every member breaks someone else's component for one day | Issues triaged, P0/P1 fixed |

### 9.9 Phase 7: Code freeze, report, final review (W21–W24, 1–28 Mar)
| Week | Activity |
|---|---|
| W21 (1–7 Mar) | **Code freeze 7 Mar** (bug fixes only, each needs 2 approvals). Tag `v1.0.0`. Final results regenerated from tagged code. |
| W22 (8–14 Mar) | **Project report** finalised and submitted **by 14 Mar** (deadline 15 Mar). Report outline in §12.3. |
| W23 (15–21 Mar) | Final presentation deck. Two full demo rehearsals on campus Wi-Fi (via Tailscale) and on a hotspot (fallback). Backup demo video recorded. |
| W24 (22–28 Mar) | **Final review.** Bring proof of the paper presentation or acceptance (Outcome Analysis). |

**Task ID prefixes:** `A-` Arya · `H-` Harith · `M-` Amaan · `R-` Rejish · `N-` Ronit · `ALL-` whole team.

---

# PART II: MEMBER SECTIONS

Each section follows the same structure:
- Prompt preamble
- Mission
- Files to attach for an LLM
- Existing code: keep / change
- Module specifications
- Integration points
- Tests
- Tasks by phase

---

## 10.1 Arya: Node Agent (`idlegrid.agent`)

### 10.1.0 Prompt preamble (paste first when using an LLM)
> You are implementing the **Node Agent** of IdleGrid, a system that runs ML jobs on idle team laptops (Windows, macOS, Linux) and pauses them instantly when the laptop's owner returns. The agent is one Python 3.12 process that starts at user login on every laptop. It measures *seconds since last keyboard/mouse input* with OS-specific code, logs usage every 15 s to a local CSV, sends a heartbeat to the central Dispatcher every 5 s over HTTP (outgoing only), receives commands in the heartbeat response, runs assigned jobs using the existing `idlegrid.executor.JobRunner`, pauses them within 1 s of owner input (the kill switch), keeps the laptop awake while a job runs on AC power, and uploads logs and results. You must follow the contracts in Appendices A (models), B (API), D (CSV) and E.2 (agent config) exactly. Never record keystrokes or anything beyond the time since last input. Reuse the existing code listed below rather than rewriting it.

### 10.1.1 Mission
Own everything that runs on a worker laptop except the internals of process execution (which belong to Ronit). The agent is the system's eyes (idle detection, usage data), its hands (running jobs) and its safety guarantee (kill switch, power, owner controls).

### 10.1.2 Files to attach for an LLM
`idlegrid/agent/*` (after the move), `idlegrid/common/models.py`, `idlegrid/executor/runner.py`, `idlegrid/executor/process_controller.py`, `idlegrid/packager/bundle.py`, `tests/unit/agent/*`, plus Appendices A, B, D, E.2 and F.2.

### 10.1.3 Existing code: keep / change
| File (after move) | Keep | Change |
|---|---|---|
| `agent/config.py` (was `node_agent/config.py`) | `_generate_default_node_id()` (stable hash of hostname + MAC; **this is the project-wide node identity**), load-from-file + overrides pattern | Becomes `AgentConfig` (a Pydantic model) loaded from `~/.idlegrid/agent.toml` (Appendix E.2) with env overrides `IDLEGRID_URL`, `IDLEGRID_TOKEN`. Default URL `http://127.0.0.1:8000`. Persist the generated `node_id` into the config on first run so it never changes. |
| `agent/metrics.py` (was `metrics_collector.py`) | `psutil` sampling, CPU priming, overall structure | Move idle detection to `agent/idle/`. Add `host_cpu_percent` (excluding job PIDs), `PowerInfo`, HostState rules (§10.1.5). RAM threshold default 92%. Remove the `sys.platform == "win32"` gate in the state logic. |
| `agent/client.py` (was `heartbeat_sender.py`) | `requests.Session`, timeout handling, "never crash on network error" behaviour | Becomes `DispatcherClient` with `heartbeat()`, `download_bundle()`, `post_logs()`, `post_result()`, `post_usage()`. `Authorization: Bearer` header. Payloads are Appendix A models (`model_dump(mode="json")`). |
| `agent/agent.py` | Signal handling, responsive 0.5 s sleep loop, logging setup | Becomes a supervisor that starts and stops 4 threads (§10.1.4) and restarts any thread that crashes (with backoff). |
| `agent/__main__.py` (was `main.py`) | argparse CLI | Subcommands: `run`, `log-only`, `status`, `enable`, `disable`, `benchmark`, `idle-test`, `install`, `uninstall` |
| `tests/unit/agent/*` | All existing tests | Update imports, states (`ACTIVE`/`BUSY`/`IDLE`/`UNKNOWN`) and payload fields |

### 10.1.4 Agent architecture
```
AgentSupervisor (main thread)
 ├─ SharedState  (thread-safe: last metrics, host_state, current attempt, pending command results, config overrides)
 ├─ HeartbeatThread   every heartbeat_interval_sec (5 s): sample → Heartbeat → POST → handle response
 ├─ KillSwitchThread  every 0.25 s: read idle seconds → pause/resume the running job (never waits on network)
 ├─ UsageThread       every 15 s: append CSV row; every 60 s: upload pending rows in batches
 └─ WorkerThread      consumes START/ABORT/PAUSE/RESUME commands; runs one attempt at a time; ships logs; uploads results
```
- Only `SharedState` is shared, behind a `threading.Lock`. Commands go from HeartbeatThread to WorkerThread through a `queue.Queue`.
- **Startup:** load config → pick the idle detector → run the perf benchmark (median of 3 × 1.5 s) → **kill orphan jobs** (for each `~/.idlegrid/work/*/.pid` whose process is still alive, terminate its tree) → start the threads.
- **Shutdown** (SIGINT/SIGTERM, or the Windows console close event): stop accepting work, cancel the running attempt (the Dispatcher marks it LOST after the grace period), flush the CSV, exit within 5 s.

### 10.1.5 Idle detection (`agent/idle/`) and host state
**Interface** (`idle/base.py`):
```python
from typing import Protocol
from idlegrid.common.models import InputDetection

class IdleDetector(Protocol):
    method: str                 # e.g. "win32_getlastinputinfo", "macos_quartz", "macos_ioreg", "x11_xss", "gnome_mutter_dbus", "kde_screensaver_dbus", "logind", "none"
    precision: InputDetection   # PRECISE | COARSE | NONE
    def seconds_since_input(self) -> float | None: ...   # None = could not read this time

def get_idle_detector() -> IdleDetector: ...   # probe in priority order (§5.1); cache; on Linux re-probe every 10 min
```
**Implementations** (see §5.1 for the method table):
- `windows.py`: existing `LASTINPUTINFO` code. **Fix:** `kernel32.GetTickCount.restype = ctypes.c_uint32`, then `elapsed_ms = (GetTickCount() - lii.dwTime) & 0xFFFFFFFF`.
- `macos.py`: Quartz via `ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")`, function `CGEventSourceSecondsSinceLastEventType`, `argtypes=[c_uint32, c_uint32]`, `restype=c_double`, call `(1, 0xFFFFFFFF)`. Fallback: `subprocess.run(["ioreg", "-c", "IOHIDSystem"])`, regex `"HIDIdleTime" = (\d+)`, nanoseconds → seconds.
- `linux.py`: try in order:
  1. If `XDG_SESSION_TYPE == "x11"`: XScreenSaver via ctypes, else `xprintidle`.
  2. GNOME: `gdbus call --session --dest org.gnome.Mutter.IdleMonitor --object-path /org/gnome/Mutter/IdleMonitor/Core --method org.gnome.Mutter.IdleMonitor.GetIdletime` → parse `(uint64 N,)` ms.
  3. KDE: `qdbus org.freedesktop.ScreenSaver /ScreenSaver GetSessionIdleTime` (or the `gdbus` equivalent).
  4. `loginctl` IdleHint (COARSE).
  5. `none`.

  Each probe must time out within 1 s.
- `idle-test` subcommand: prints `method`, `precision` and the reading once per second, for manual verification on every laptop.

**Host state rules** (`metrics.py`, evaluated on every sample):
```
if precision == NONE and not cfg.dedicated_mode:            → UNKNOWN
if not cfg.dedicated_mode and inactivity < cfg.idle_threshold_sec (120):   → ACTIVE
if mean(host_cpu_percent over last 3 samples) > cfg.host_busy_cpu_percent (40)
   or ram_percent > cfg.host_busy_ram_percent (92):         → BUSY
otherwise                                                    → IDLE
```
`host_cpu_percent = max(0, psutil.cpu_percent() − Σ job_proc.cpu_percent() / cpu_count)`, where the job processes are the running attempt's process tree (PIDs come from the worker). Our own job must never make the laptop look busy (review issue A2).

### 10.1.6 Performance benchmark (`agent/perf.py`)
`measure_perf_score() -> float`: a pure-Python integer loop (`sum(i*i for i in range(10_000))`) repeated for 1.5 s, giving iterations/second; take the median of 3 runs. `perf_score = rate / REFERENCE_RATE`. Measure `REFERENCE_RATE` once on the coordinator laptop in P1 and hard-code it with a comment, so the reference laptop is about 1.0. Sent in `capabilities.perf_score`. The Dispatcher uses it to scale runtime estimates (`est_runtime_on_node = estimated_runtime_sec / perf_score`).

### 10.1.7 Usage logger (`agent/usage_logger.py`): **start in week 1**
- Every `usage_interval_sec` (15) append one row to `~/.idlegrid/usage/YYYY-MM-DD.csv` (UTC date) with the exact columns of **Appendix D**. Write the header when creating a file. `flush()` after every row.
- **Phase 0 standalone mode:** the same module must run alone with only `psutil` installed: `python -m idlegrid.agent log-only` (or, before the restructure PR merges, `python usage_logger.py`). The CSV format never changes after week 1. If a column must be added later, append it at the end; never rename or reorder.
- **Upload (P1):** every 60 s, read rows after the cursor stored in `~/.idlegrid/usage/.upload_cursor` (JSON `{"file": "...", "line": N}`), send batches of ≤ 2,000 rows to `POST /api/v1/usage`, and advance the cursor only after HTTP 2xx. On failure keep the cursor, so it retries naturally. The server ignores duplicates by primary key `(node_id, ts_utc)`.
- Disk use: about 2 MB per laptop per month. Never delete CSVs automatically.

### 10.1.8 Dispatcher client (`agent/client.py`)
```python
class DispatcherClient:
    def __init__(self, base_url: str, token: str, timeout_sec: float = 5.0): ...
    def heartbeat(self, hb: Heartbeat) -> HeartbeatResponse: ...          # POST /api/v1/heartbeat
    def download_bundle(self, url_path: str, dest: Path, expected_sha256: str) -> None: ...  # streams; raises BundleIntegrityError
    def post_logs(self, attempt_id: str, offset: int, text: str) -> int: ...   # returns server's next_offset
    def post_result(self, attempt_id: str, result: JobResult, result_zip: Path | None) -> None: ...  # raises StaleAttemptError on 409
    def post_usage(self, batch: UsageBatch) -> UsageBatchResponse: ...
```
Errors: network errors raise `DispatcherUnavailable`. The caller decides whether to retry. Never let an exception escape a thread loop: catch, log with context, and continue.

### 10.1.9 Heartbeat loop
Every `heartbeat_interval_sec`:
1. Take a metrics sample.
2. Build a `Heartbeat` (Appendix A) including `sharing`, `capabilities`, `current_attempt` (from the worker) and `command_results` (results of commands processed since the last successful heartbeat).
3. POST it. On success, clear the sent `command_results`, apply `config_overrides` (`migrate_after_sec`, `resume_after_idle_sec`, `heartbeat_interval_sec`), store `clock_offset = server_time − local_time`, and push each new command (dedupe by `command_id` using an LRU set of 500) to the worker queue.

On failure, keep everything and retry next interval. Log a warning at most once per minute while the Dispatcher is unreachable.

### 10.1.10 Worker (`agent/worker.py`)
One attempt at a time. The worker's state machine is in **Appendix F.2**.

- **`START`** (payload `StartJobPayload`):
  1. Reject (with `command_results` `ok=false`, `error="host_active"|"busy"|"not_accepting"`) if the host state isn't `IDLE` (unless `dedicated_mode`), sharing is disabled, or another attempt is running.
  2. Download to `~/.idlegrid/work/{attempt_id}.zip` and verify the SHA-256.
  3. `runner = JobRunner(base_workspace_dir=work_dir, low_priority=True, max_job_cores=cfg.max_job_cores)`, then `runner.setup_workspace(bundle_path, workspace_name=attempt_id, job_id_override=payload.job_id)` and `runner.run_async(active_timeout_sec=payload.active_timeout_sec, on_complete=self._on_complete)`.
  4. `PowerGuard.acquire(job_pid)` if on AC.
  5. Report `RUNNING`.
- **Log shipping:** every 2 s, read new bytes from `workspace/combined.log` starting at the last acknowledged offset, and `post_logs()`. On failure retry next tick (the offset makes it idempotent).
- **Completion:**
  1. `PowerGuard.release()`.
  2. Write the result upload into the outbox `~/.idlegrid/outbox/{attempt_id}/` (`result.json` + `result_bundle.zip`) and upload it, retrying with backoff (5 s → 5 min) for up to 24 h. The outbox survives agent restarts.
  3. On HTTP 409 (stale attempt), discard.
  4. After a successful upload, delete the workspace, keeping the newest `keep_workspaces` (5).
- **`ABORT`:** `runner.cancel()` (kills the process tree), release the PowerGuard, report `command_results ok=true`, set `current_attempt = None`. No result upload.
- **`PAUSE` / `RESUME`** (manual, from an admin or a demo): set a `manual_pause` flag. While it is set, the kill switch must not auto-resume.

### 10.1.11 Kill switch (`agent/killswitch.py`)
Every `killswitch_poll_sec` (0.25):
```
s = idle.seconds_since_input()
if job running and not paused:
    if (s is not None and s < cfg.pause_if_inactivity_below_sec (2.0))
       or (cfg.pause_on_host_busy and host_state == BUSY)
       or (cfg.require_ac_power and on_ac_power is False):
        t0 = monotonic(); runner.pause(); latency = (s or 0) + (monotonic() - t0)
        append (ts, latency, method) to ~/.idlegrid/metrics/pause_latency.csv
if job paused and not manual_pause:
    if s is not None and s >= cfg.resume_after_idle_sec (120) and host_state == IDLE and power ok:
        runner.resume()
local fail-safe: if paused for > migrate_after_sec + 60 and the Dispatcher has been unreachable for that whole time:
        runner.cancel(); mark the attempt locally "aborted_offline" (report it in the next successful heartbeat)
```
This loop must never block on the network or disk. It acts only on in-memory state, plus the latency CSV append, which is buffered.

### 10.1.12 Power guard (`agent/power.py`)
```python
class PowerGuard:
    def acquire(self, job_pid: int) -> None: ...   # no-op if not on AC or already held
    def release(self) -> None: ...
```
Per-OS implementation exactly as §5.4. On Windows, `SetThreadExecutionState` must be called from one dedicated long-lived thread (the state is per thread). `capabilities.can_prevent_sleep` reports whether it worked.

### 10.1.13 Owner controls and installers (P3/P6)
- `python -m idlegrid.agent disable|enable` toggles `accepting_jobs` in `agent.toml`. The running agent re-reads it every heartbeat. Disabling while a job runs pauses it immediately, and the Dispatcher migrates it after `migrate_after_sec` (or immediately if `--now`, which sends `sharing.accepting_jobs=false` plus a local cancel).
- `dedicated_mode = true`: for machines with no owner (e.g. the coordinator). Input is ignored, so the host is always `IDLE` unless busy.
- `install` / `uninstall` (§5.5): writes the Task Scheduler task, LaunchAgent plist or systemd user unit pointing at the current `sys.executable -m idlegrid.agent run`, and starts it. `uninstall` removes it and optionally `~/.idlegrid` (asks first).
- `status`: prints node ID, Dispatcher reachability, host state, idle method, current attempt, and the last 5 pause latencies.

### 10.1.14 Integration points
| Direction | With | Interface |
|---|---|---|
| Provides → Harith | Heartbeat, usage, logs, results | Appendix B agent endpoints, Appendix A models |
| Consumes ← Harith | Commands `START`/`ABORT`/`PAUSE`/`RESUME`, config overrides | `HeartbeatResponse` |
| Consumes ← Ronit | `JobRunner` (`setup_workspace`, `run_async`, `pause`, `resume`, `cancel`, `pid`, `job_pids()`), `combined.log`, `result_bundle.zip` | §10.5.4 |
| Provides → Rejish | Usage CSV (Appendix D), pause-latency CSV | Files + `POST /api/v1/usage` |
| Provides → Amaan | Rows for `usage_samples` | Same as above |

### 10.1.15 Tests
- **Unit:** HostState rules (table-driven), Windows tick wraparound arithmetic, each Linux probe's output parser (fixtures of real `gdbus`/`ioreg` output), CSV writer (header, column order, ISO timestamps), upload cursor (crash between batches → no loss, no duplicates), command dedupe, worker state machine with a fake `JobRunner`, kill-switch decisions with a fake clock and fake detector.
- **Integration** (`tests/integration/test_agent_dispatcher.py`): start the Dispatcher in-process on a free port with MySQL (CI), run the agent threads against it with a fake idle detector, and assert the node appears, a job runs, a pause is reported and the result is uploaded.
- **Manual per-OS checklist** (`docs/runbook/agent_os_checklist.md`): `idle-test` readings change when you touch the keyboard; pause latency ≤ 1 s for 20 trials; sleep prevention works; autostart survives reboot.

### 10.1.16 Your tasks
P0: A-P0-1, A-P0-2 · P1: A-P1-1…4 · P2: A-P2-1…3 · P3: A-P3-1, A-P3-2 · P4: A-P4-1 · P5: A-P5-1 · P6: A-P6-1 (details in §9).

---

## 10.2 Amaan: State Manager / Database (`idlegrid.db`)

### 10.2.0 Prompt preamble
> You are implementing the **database layer** of IdleGrid, a system that schedules ML jobs onto idle team laptops. The central Dispatcher (FastAPI) is the only process that talks to the database. Laptops never connect to MySQL. You own the MySQL 8 schema (Appendix C), the migration runner, repository functions used by the Dispatcher (plain SQL through SQLAlchemy Core 2.x `text()` with the PyMySQL driver), the atomic job-assignment transaction, the Optuna storage schema, analytics queries for experiments, data export for the ML team, an admin CLI for users and tokens, and backups. Follow Appendices A (models) and C (DDL) exactly. Credentials come only from the environment variable `IDLEGRID_DB_URL`, never from source code. All timestamps are UTC `DATETIME(3)`.

### 10.2.1 Mission
Make the system's memory **correct under concurrency, durable across restarts, and useful for research**. The charter's "historical logs of when laptops were idle vs. busy" become `usage_samples` and `node_status_events`, which are the training data for the whole ML part of the project.

### 10.2.2 Files to attach for an LLM
`idlegrid/db/**`, `idlegrid/common/models.py`, Appendices A and C, the old `Amaan_Work/db_functions.py` (for its upsert pattern), and the call sites in `idlegrid/dispatcher/services/*.py` once they exist.

### 10.2.3 Existing code: keep / change
| Existing | Keep | Change |
|---|---|---|
| `DatabaseCreate.sql` | The `nodes` + `jobs` idea, `last_heartbeat` auto-timestamp idea | Replaced by `migrations/0001_initial.sql` (Appendix C): `node_id` primary key, history tables, attempts, commands, studies, experiments, users, models |
| `db_functions.update_node()` | `INSERT … ON DUPLICATE KEY UPDATE` upsert | Becomes `nodes.upsert_from_heartbeat()` with all columns. Uses `text()` + bound params. Runs inside a caller-provided connection. |
| `db_functions.get_available_node()` | — | Replaced by Dispatcher-side status logic + `nodes.list_schedulable()` (filters freshness, status, `current_attempt_id IS NULL`) |
| `db_functions.assign_job()` | — | Replaced by the atomic `assign_job_to_node()` (§10.2.5) |
| `get_connection()` returning `None` on error | — | `engine.py` raises `DatabaseUnavailable` with context. Connections always closed through `with engine.begin() as conn:` |
| Hard-coded `'password': 'amaan'` | — | **Delete, and rotate the MySQL password (P0).** Use `IDLEGRID_DB_URL=mysql+pymysql://idlegrid:<pw>@127.0.0.1:3306/idlegrid`. |
| `ReturnTables.sql` | — | Delete |

### 10.2.4 Engine, migrations, conventions
- `engine.py`: `get_engine(url: str | None = None) -> Engine` (singleton; `pool_size=10`, `max_overflow=5`, `pool_pre_ping=True`, `pool_recycle=1800`, `isolation_level="READ COMMITTED"`). Session time zone forced to UTC on connect (`SET time_zone = '+00:00'`).
- `migrate.py`: applies `migrations/NNNN_*.sql` in order, recording each in `schema_migrations(version, applied_at)`. Idempotent. `python -m idlegrid.db.migrate [--db-url]`. Never edit an applied migration. Always add a new file.
- **Repository convention:** each function takes `conn: Connection` as its first argument (the caller owns the transaction), uses `text()` with named parameters, returns Pydantic models or small dataclasses (never raw tuples), and converts `DATETIME` ↔ epoch `float` in one helper (`common/timeutil.py`).
- The JSON columns (`manifest`, `search_space`, `payload`, `metrics`) use MySQL `JSON`.

### 10.2.5 Repository API (function signatures the Dispatcher relies on)
```python
# users.py
def create_user(conn, display_name: str, is_admin: bool = False) -> tuple[str, str]   # (user_id, plaintext token, shown once)
def get_user_by_token(conn, token: str) -> UserRow | None                              # lookup by sha256(token)
def rotate_token(conn, user_id: str) -> str
def list_users(conn) -> list[UserRow]

# nodes.py
def get(conn, node_id: str) -> NodeRow | None
def list_all(conn) -> list[NodeRow]
def upsert_from_heartbeat(conn, hb: Heartbeat, owner_user_id: str, last_ip: str, status: NodeStatus, now: float) -> NodeStatus | None  # returns previous status
def set_status(conn, node_id: str, status: NodeStatus, now: float) -> bool             # True if changed; writes node_status_events
def mark_stale_offline(conn, now: float, offline_after_sec: float) -> list[str]
def list_schedulable(conn, now: float, offline_after_sec: float) -> list[NodeRow]     # IDLE_SAFE/IDLE_RISKY, fresh, no attempt
def set_prediction(conn, node_id: str, pred: IdlePrediction) -> None
def set_accepting(conn, node_id: str, accepting: bool) -> None
def set_available_since(conn, node_id: str, ts: float | None) -> None

# usage.py
def insert_batch_ignore(conn, node_id: str, samples: list[UsageSample]) -> tuple[int, int]   # (accepted, duplicates); INSERT IGNORE, chunks of 1000
def recent(conn, node_id: str, since: float) -> list[UsageSample]
def iter_range(conn, start: float, end: float, node_ids: list[str] | None = None, chunk: int = 50_000) -> Iterator[list[UsageSample]]

# jobs.py
def create(conn, job: JobCreate) -> JobRow
def get(conn, job_id: str) -> JobRow | None
def list_jobs(conn, *, status: list[JobStatus] | None, user_id: str | None, study_id: str | None, limit: int, offset: int) -> list[JobRow]
def queued(conn, limit: int = 200) -> list[JobRow]                                    # ORDER BY priority DESC, queued_at ASC
def set_status(conn, job_id: str, status: JobStatus, now: float, **fields) -> None
def requeue(conn, job_id: str, now: float, priority_boost: int) -> None              # status=QUEUED, current_attempt_id=NULL, queued_at=now
def finish(conn, job_id: str, status: JobStatus, now: float, attempt_id: str, exit_code: int | None, error: str | None) -> None

# attempts.py
def get(conn, attempt_id: str) -> AttemptRow | None
def list_for_job(conn, job_id: str) -> list[AttemptRow]
def update_from_report(conn, rep: AttemptReport, now: float) -> None                  # RUNNING/PAUSED, paused_since, active_seconds, pause_count
def finish(conn, attempt_id: str, status: AttemptStatus, now: float, *, end_reason: str, exit_code: int | None = None,
           active_seconds: float | None = None, metrics: dict | None = None, result_path: str | None = None, result_sha256: str | None = None) -> None
def paused_longer_than(conn, now: float, seconds: float) -> list[AttemptRow]
def active_on_offline_nodes(conn, now: float, lost_grace_sec: float) -> list[AttemptRow]
def assigned_not_started(conn, now: float, start_timeout_sec: float) -> list[AttemptRow]

# commands.py
def enqueue(conn, node_id: str, type: CommandType, payload: dict, attempt_id: str | None, now: float) -> str
def pending_for_node(conn, node_id: str, now: float, redeliver_after_sec: float = 15) -> list[NodeCommand]  # marks delivered_at
def apply_results(conn, node_id: str, results: list[CommandResult], now: float) -> None

# scheduling.py  (the critical transaction)
def assign_job_to_node(conn, *, job_id: str, node_id: str, attempt_id: str, now: float,
                       prediction: IdlePrediction | None, policy_name: str, start_payload: dict) -> bool
# studies.py, experiments.py, models.py: CRUD per Appendix C (create/get/list/update_progress/set_status/set_best; create/finish/get_active; register/get_active/set_active)
```

**`assign_job_to_node`** runs as one transaction and returns `False` (rolled back) if anything changed underneath it:
```sql
SELECT status, current_attempt_id FROM jobs  WHERE job_id  = :job_id  FOR UPDATE;   -- must be QUEUED
SELECT status, current_attempt_id, accepting_jobs FROM nodes WHERE node_id = :node_id FOR UPDATE;  -- IDLE_* and NULL attempt and accepting
INSERT INTO job_attempts (attempt_id, job_id, node_id, attempt_no, status, assigned_at, policy_name,
                          predicted_q20_sec, predicted_q50_sec, experiment_run_id)
       VALUES (..., (SELECT attempts_count + 1 FROM jobs WHERE job_id=:job_id), 'ASSIGNED', :now, ...);
UPDATE jobs  SET status='ASSIGNED', current_attempt_id=:attempt_id, attempts_count=attempts_count+1 WHERE job_id=:job_id;
UPDATE nodes SET status='RUNNING_JOB', current_attempt_id=:attempt_id WHERE node_id=:node_id;
INSERT INTO node_commands (command_id, node_id, attempt_id, type, payload, created_at) VALUES (..., 'START', :payload, :now);
INSERT INTO node_status_events (...);
COMMIT;
```
Lock order is always **jobs, then nodes**, to avoid deadlocks. Every other multi-row update must follow the same order.

### 10.2.6 Optuna storage (`optuna_storage.py`), P4
- Separate schema `idlegrid_optuna` on the same server, with a user that has rights on it.
- `get_optuna_storage() -> optuna.storages.RDBStorage` built from `IDLEGRID_OPTUNA_DB_URL` with `engine_kwargs={"pool_pre_ping": True, "pool_recycle": 1800}`. Optuna creates its own tables. **Never** hand-edit them.
- Our `hpo_studies` table links our `study_id` to Optuna's `study_name` (`idlegrid-{study_id}`).

### 10.2.7 Analytics (`analytics.py`): the numbers in the paper
Definitions (Rejish's simulator must compute the *same* definitions; a cross-check test exists):
| Metric | Definition |
|---|---|
| `makespan_sec` | `max(jobs.finished_at) − min(jobs.created_at)` over the run's jobs |
| `useful_compute_sec` | Σ `active_seconds` of attempts with status `COMPLETED` |
| `wasted_compute_sec` | Σ `active_seconds` of attempts with status `MIGRATED` or `LOST` |
| `goodput` | `useful / (useful + wasted)` |
| `preemptions` | Σ `pause_count` over all attempts (each is an owner returning to a laptop running our job) |
| `migrations` / `node_losses` | count of attempts `MIGRATED` / `LOST` |
| `mean_queue_wait_sec` | mean over jobs of (first attempt `assigned_at` − `created_at`) |
| `mean_jct_sec` | mean over `COMPLETED` jobs of (`finished_at` − `created_at`) |
| `harvest_ratio` | Σ attempt `active_seconds` ÷ Σ node available-seconds in the window (from `usage_samples` via the shared availability definition) |

```python
def experiment_summary(conn, run_id: str) -> ExperimentSummary
def study_summary(conn, study_id: str) -> StudySummary            # trials done, failed, best, wall time, Σ compute, speedup estimate
def availability_report(conn, start: float, end: float) -> list[NodeAvailability]   # % of time logged, % available, sessions
def data_quality_report(conn, start: float, end: float) -> DataQuality              # expected vs received samples per node (NFR-06)
```

### 10.2.8 Export, admin and backup
- `python -m idlegrid.db.export usage --from 2026-10-12 --to 2026-12-20 --out data/exports/usage.parquet [--pseudonymise]`. Pseudonymised node IDs become `N1…N5`, with the mapping saved separately and never committed. Also `export attempts|jobs|events`.
- `python -m idlegrid.db.admin create-user --name Arya [--admin]` (prints the token once), `rotate-token`, `list-users`, `list-nodes`.
- `scripts/backup_db.(ps1|sh)`: `mysqldump --single-transaction idlegrid idlegrid_optuna | gzip > data/backups/idlegrid-YYYYMMDD.sql.gz`, keeping 14 days. Scheduled nightly on the coordinator. `docs/runbook/restore.md` documents a tested restore (P5).

### 10.2.9 Integration points
| Direction | With | Interface |
|---|---|---|
| Provides → Harith | All repositories, `assign_job_to_node`, `analytics` | §10.2.5, §10.2.7 |
| Provides → Ronit | Optuna storage, `studies` repo, `study_summary` | §10.2.6 |
| Provides → Rejish | `usage.iter_range`, `export`, `oracle_models` repo | §10.2.5, §10.2.8 |
| Consumes ← Arya | Usage rows (through the Dispatcher) | Appendix D / `UsageSample` |

### 10.2.10 Tests
- CI runs a `mysql:8.0` service container. Fixture: create a fresh database per test session, run migrations, and `TRUNCATE` all tables between tests.
- Required tests:
  - Migrations are idempotent.
  - Upsert then status change writes exactly one event.
  - `insert_batch_ignore` counts duplicates correctly.
  - **`assign_job_to_node` under concurrency:** 20 threads assigning 20 jobs to 5 nodes produce no double booking.
  - Lost/paused/start-timeout queries are correct at the boundaries.
  - Analytics on a hand-built fixture match hand-computed numbers.
  - Export round-trip.
  - Token hashing.
- `EXPLAIN` check (P5): heartbeat-path queries use indexes (no full scans on `usage_samples`).

### 10.2.11 Your tasks
P0: M-P0-1, M-P0-2 · P1: M-P1-1, M-P1-2 · P2: M-P2-1 · P3: M-P3-1 · P4: M-P4-1 · P5: M-P5-1 · P6: M-P6-1.

---

## 10.3 Harith: Dispatcher, Scheduler & Integration Lead (`idlegrid.dispatcher`, `idlegrid.devtools`, `idlegrid.common`)

### 10.3.0 Prompt preamble
> You are implementing the **Dispatcher** of IdleGrid: a FastAPI service on one coordinator laptop that is the single source of truth for a fleet of worker laptops. Agents on the laptops send a heartbeat every 5 s (`POST /api/v1/heartbeat`) and receive commands in the response. Laptops never accept inbound connections. Users submit jobs and Optuna HPO studies through a CLI and web dashboard. The Dispatcher stores state in MySQL through the repository functions in `idlegrid.db.repositories` (never raw SQL inside the Dispatcher). A background scheduler thread runs every 2 s to detect offline nodes, migrate long-paused jobs, requeue lost work, drive HPO studies, and assign queued jobs to idle laptops using a pluggable, **pure** `Policy` (also used by the offline simulator, so it must not import FastAPI or the DB). You are evolving the existing `app.py` and `mock_cluster.py` (originally written by Ronit), not starting from scratch. Follow Appendices A (models), B (API), C (DB), E.1 (config) and F (state machines) exactly.

### 10.3.1 Mission
Build the frame that every other part bolts into: the API, the scheduling brain, and the guarantees about failure (no job lost, no double booking, no stale results). As **integration lead**, Harith also custodies the shared contracts (`idlegrid.common`), owns CI, and runs the weekly integration session (§15.3).

### 10.3.2 Files to attach for an LLM
`idlegrid/dispatcher/**`, `idlegrid/devtools/**`, `idlegrid/common/**`, the original `Ronit_Work/src/dashboard/app.py` and `mock_cluster.py`, the repository signatures in §10.2.5, `idlegrid/hpo/controller.py` (interface only), `idlegrid/oracle/oracle.py` (interface only), and Appendices A, B, C, E.1, F, G.

### 10.3.3 Existing code: keep / change
| Existing (Ronit's) | Keep | Change |
|---|---|---|
| `app.py` FastAPI app, routes, `FileResponse` download, WebSocket loop, static mount, demo presets (`job_type` → bundle from `demo_jobs`) | Route ideas, response shapes (field names like `assigned_node_id`, `assigned_hostname`, `duration_seconds`, `pause_count`, `total_pause_duration_sec`, `peak_cpu_percent`, `peak_ram_mb`, `artifact_files` are **kept** in `JobView` so the CLI and JS need few changes), preset submission | App factory `create_app(cfg)`. Routers split into `api/*.py` under `/api/v1`. **Remove CORS middleware** (the dashboard is same-origin). Auth dependency on every route. Endpoints doing DB/disk work become **sync `def`** (FastAPI runs them in a threadpool). `bind_host`/`port` from config. Lifespan starts and stops the scheduler. Absolute paths from config. |
| `mock_cluster.ClusterOrchestrator.submit_job()` | Flow: unpack manifest → create record → log line → maybe start | Moves to `services/job_service.py`: validate bundle (§10.3.7), **Dispatcher-assigned `job_id`**, store the bundle with `BlobStore`, insert `QUEUED`. No immediate execution: the scheduler assigns. **Temporary unpack folders are always deleted** (review R9). |
| `_select_best_node()` | Candidate filtering idea | Becomes `policies.py` (pure; §10.3.9). Uses the runtime estimate (it was ignored before, R7). |
| `_start_job_on_node()` + `_on_done()` | Record fields, log lines | `assign_job_to_node` (Amaan) + START command. Completion handled in `POST /attempts/{id}/result`. |
| `pause_job` / `resume_job` / `cancel_job` | Endpoint semantics | Enqueue `PAUSE`/`RESUME`/`ABORT` commands to the node. Cancel marks the job `CANCELLED`. |
| `toggle_node_host_activity` | Demo value | Only exists when `dev.sim_nodes > 0`: `POST /api/v1/dev/nodes/{id}/simulate-activity` drives a fake agent's idle detector |
| `_init_default_nodes()` + `_telemetry_ticker()` | Node personas (gaming laptop, MacBook, ThinkPad, lab PC) | Move to `devtools/fake_agents.py`: each persona is a **fake agent thread using the real `DispatcherClient` over HTTP**, with a scripted idle pattern and either fake execution (sleep honouring pause) or real execution through `JobRunner` |
| In-memory dicts `nodes`, `jobs`, `runners`, `log_buffers` | — | Replaced by DB + `BlobStore` (logs in files). Only caches (predictions, WebSocket snapshot) stay in memory. |

### 10.3.4 Process model and configuration
- Run with **exactly one** uvicorn worker (`idlegrid-dispatcher` console script → `uvicorn.run(app, workers=1)`). The scheduler thread and caches live in-process, so `--workers > 1` is forbidden and checked at startup.
- `DispatcherConfig` (Appendix E.1) is loaded from `dispatcher.toml` + env (`IDLEGRID_DB_URL`, `IDLEGRID_OPTUNA_DB_URL`, `IDLEGRID_DATA_DIR`, `IDLEGRID_BIND`, `IDLEGRID_PORT`).
- Data dir layout: `data/bundles/`, `data/results/`, `data/logs/`, `data/models/`, `data/backups/`, `data/exports/`.
- `GET /healthz` → `{status, db: ok|down, scheduler_last_tick_age_sec, version}` (no auth).
- Logging: JSON lines to `data/logs/dispatcher.log` (rotating, 10 × 10 MB) + console. Every log line about a job or node includes `job_id` / `attempt_id` / `node_id`.

### 10.3.5 Authentication and authorisation (`deps.py`)
- `Authorization: Bearer <token>` on every `/api/v1/*` route. The WebSocket uses `?token=`. Look up the user by `sha256(token)` through `users.get_user_by_token` (cached 60 s).
- Roles: every user can submit, see all jobs and nodes, and cancel **their own** jobs. Node owner (the user whose token first registered the `node_id`) can drain/undrain that node. Admin (`is_admin`) can do everything, plus `/api/v1/admin/*` and `/api/v1/experiments/*`.
- **Node binding:** the first heartbeat for a `node_id` sets `owner_user_id`. Later heartbeats with another user's token get 403.
- Upload limits enforced while streaming: job bundle ≤ 200 MB, result bundle ≤ 500 MB, log chunk ≤ 1 MB.

### 10.3.6 Heartbeat handling (`services/node_service.py`)
```
handle_heartbeat(hb, user, client_ip, now):
  1. Reject if the major of hb.schema_version ≠ ours (426). Validate with the Pydantic model (422 on error).
  2. with engine.begin() as conn:
       node = nodes.get(conn, hb.node_id)
       if node and node.owner_user_id != user.user_id and not user.is_admin: 403
       commands.apply_results(conn, hb.node_id, hb.command_results, now)
       if hb.current_attempt:
           att = attempts.get(conn, rep.attempt_id)
           if att is None or att.node_id != hb.node_id or att.status in TERMINAL_ATTEMPT_STATES:
               enqueue ABORT(rep.attempt_id, reason="fenced") unless one is already pending   # fencing
           else:
               attempts.update_from_report(conn, rep, now); jobs.set_status(conn, att.job_id, RUNNING|PAUSED, now)
       prediction = oracle_client.cached(hb.node_id)              # never computes in the request path
       status = compute_node_status(hb, node, current_attempt, prediction, cfg, now)   # pure, Appendix F.1
       nodes.upsert_from_heartbeat(conn, hb, owner, client_ip, status, now)            # writes status event if changed
       maintain available_since (set when status enters IDLE_*, clear when it leaves)
       pending = commands.pending_for_node(conn, hb.node_id, now)
  3. event_bus.publish_node(hb.node_id)
  4. return HeartbeatResponse(server_time=now, node_status=status, commands=pending,
                              heartbeat_interval_sec=cfg.heartbeat_interval_sec,
                              config_overrides={migrate_after_sec, resume_after_idle_sec})
```
Target: p95 < 50 ms with 20 nodes. No Oracle inference and no file I/O in this path.

### 10.3.7 Jobs (`services/job_service.py`, `services/blob_store.py`)
- **Submit** `POST /api/v1/jobs` (multipart `bundle` **or** form `preset=pi|matrix|ml`):
  1. Open the zip, run `JobUnpackager`'s validation (path traversal, size and file-count limits) into a temp dir, and parse `manifest.json` as `JobManifest`.
  2. Check that the entrypoint exists, `1 ≤ estimated_runtime_sec ≤ 86400`, `timeout_seconds ≤ cfg.max_timeout_sec` (21600), and `ram_required_mb ≤ 8192`.
  3. Generate `job_id = "job_" + 10 hex chars`.
  4. `BlobStore.put_bundle(job_id, bytes)` (atomic write: temp → rename; returns SHA-256 and size).
  5. `jobs.create(...)` with `status=QUEUED`, `user_id` **from the token** (ignore the manifest's), `experiment_run_id` = the active run if any, `priority` = 0 (+ study priority for trials).
  6. Delete the temp dir.
  7. Return `201 JobView`.
- **Logs:** `data/logs/{job_id}.log` contains all attempts, separated by `===== attempt {n} on {hostname} ({node_id}) at {iso} =====`. Agents post `(offset, text)` per attempt (`attempt_log_offset` tracked in `job_attempts.log_bytes`). Duplicate or overlapping offsets are skipped. Clients read `GET /api/v1/jobs/{id}/logs?offset=N` → `{text, next_offset, complete}`.
- **Result** `POST /api/v1/attempts/{attempt_id}/result` (multipart `result_json` + optional `result_bundle`):
  1. Load the attempt. If it isn't the job's current attempt, or is already terminal → **409** (stale; the agent discards).
  2. Store the zip as `data/results/{attempt_id}.zip` and record its SHA-256.
  3. `attempts.finish(...)` with the status from `JobResult` (`COMPLETED`/`FAILED`/`TIMED_OUT`/`CANCELLED`), `active_seconds`, metrics.
  4. `jobs.finish(...)`, free the node (`current_attempt_id = NULL`).
  5. If `kind == HPO_TRIAL` → `hpo_controller.on_trial_job_finished(...)`.
  6. Publish an event.
- **Download** `GET /api/v1/jobs/{id}/result` streams the result zip of the job's final attempt (404 until it exists).
- **Cancel** `POST /api/v1/jobs/{id}/cancel`: if `QUEUED` → `CANCELLED`. If an attempt is active → enqueue `ABORT`, finish the attempt as `CANCELLED`, job `CANCELLED`.

### 10.3.8 Scheduler loop (`scheduler.py`)
A daemon thread, ticking every `scheduler_tick_sec` (2 s). It also wakes early on events (job submitted, node became idle, result arrived) through a `threading.Event`. Each step uses its own short transaction:
```
tick(now):
  1  offline sweep     nodes.mark_stale_offline(now, cfg.offline_after_sec=15)
  2  lost sweep        for att in attempts.active_on_offline_nodes(now, cfg.lost_grace_sec=60):
                           finish(att, LOST, end_reason="node_offline"); jobs.requeue(att.job_id, boost=+5); node.current_attempt_id=NULL
  3  start-timeout     for att in attempts.assigned_not_started(now, cfg.start_timeout_sec=60):
                           enqueue ABORT; finish(att, LOST, end_reason="start_timeout"); requeue(+5)
  4  migration sweep   for att in attempts.paused_longer_than(now, cfg.migrate_after_sec=300):
                           enqueue ABORT(att, reason="migrate"); finish(att, MIGRATED, end_reason="owner_active");
                           requeue(att.job_id, boost=+10); node.current_attempt_id=NULL
  5  timeout backstop  attempts RUNNING with active_seconds > job.timeout_seconds + 60 → ABORT; finish TIMED_OUT; job TIMED_OUT
  6  oracle refresh    every 30 s: oracle_client.refresh(schedulable + idle nodes) → nodes.set_prediction
  7  HPO               hpo_controller.tick(conn, now)                        # may create trial jobs
  8  assignment        queue = jobs.queued(200); free = nodes.list_schedulable(now)
                       if queue and free:
                           plan = policy.assign(to_sched_jobs(queue), to_sched_nodes(free), predictions, now)
                           for a in plan: assign_job_to_node(...start_payload...)   # False → skip (race)
  9  publish           event_bus.publish_snapshot()
```
- A tick taking longer than 1 s logs a warning. An exception in one step is logged and the remaining steps still run.
- **START payload** (`StartJobPayload`): `job_id`, `attempt_id`, `bundle_path="/api/v1/attempts/{attempt_id}/bundle"`, `bundle_sha256`, `manifest`, `active_timeout_sec`, `migrate_after_sec`, `kind`.

### 10.3.9 Policies (`policies.py`): pure, shared with the simulator
```python
@dataclass(frozen=True)
class SchedJob:  job_id: str; priority: int; queued_at: float; est_runtime_sec: float; ram_required_mb: int; kind: str
@dataclass(frozen=True)
class SchedNode: node_id: str; perf_score: float; elapsed_idle_sec: float; ram_available_mb: float; input_precision: str
@dataclass(frozen=True)
class Assignment: job_id: str; node_id: str; required_sec: float; q20_sec: float | None; q50_sec: float | None

class Policy(Protocol):
    name: str
    def assign(self, jobs: Sequence[SchedJob], nodes: Sequence[SchedNode],
               predictions: Mapping[str, IdlePrediction | None], now: float) -> list[Assignment]: ...

POLICIES: dict[str, Callable[..., Policy]] = {
    "fifo_any": FifoAnyIdle, "reactive_longest_idle": ReactiveLongestIdle,
    "predictive": Predictive, "random": RandomIdle,            # "oracle_perfect" lives in idlegrid.sim only
}
```
Common rules for all policies:
- Jobs are considered in order `(-priority, queued_at)`.
- A node can take at most one job per tick.
- Nodes need `ram_available_mb − 1024 ≥ job.ram_required_mb`.
- COARSE nodes are only used when no PRECISE node is available.
- `required_sec = est_runtime_sec / perf_score × safety_factor (1.1) + safety_buffer_sec (60)`.

| Policy | Node choice for each job |
|---|---|
| `FifoAnyIdle` (naive reactive baseline) | First free node by `node_id` |
| `RandomIdle` | Uniformly random free node (seeded) |
| `ReactiveLongestIdle` (strong reactive baseline: "idle longest, likely stays idle") | Free node with the largest `elapsed_idle_sec` |
| `Predictive(quantile="q20", starvation_after_sec=900)` | `fits = nodes where pred[quantile] ≥ required_sec` (if a node has no prediction, use `elapsed_idle_sec` as its estimate). If `fits` → **best fit**: the smallest `pred − required` (keeps long windows for long jobs; ties → higher `perf_score`). Else if the job has waited > `starvation_after_sec` → the node with the highest `pred.q50 / required`. Else leave the job queued and try the next job (backfilling). |

The policy is selected by `cfg.policy` and switchable at runtime via `POST /api/v1/admin/policy` (recorded in the active experiment run). **The policy module must import only `idlegrid.common` and the standard library.** CI enforces this with an import-linter test.

### 10.3.10 Oracle client (`services/oracle_client.py`)
Wraps Rejish's `IdleOracle`:
- `refresh(node_ids, now)` calls `oracle.predict_many()` in the scheduler thread (never in the request path) and caches results for 30 s.
- `cached(node_id)` returns the last prediction or `None`.
- `reload()` re-reads the active model (admin endpoint).
- If the Oracle raises, log it, keep the old predictions, and mark them `method="stale"`.

`elapsed_idle_sec` for a node = `now − available_since` (tracked from heartbeats, §10.3.6). The same quantity is computed offline by Rejish's `availability.elapsed_idle()`.

### 10.3.11 WebSocket and events (`api/ws.py`, `services/event_bus.py`)
`/ws/v1/telemetry?token=…` sends a `TelemetrySnapshot` (Appendix A) every 1 s, plus immediate pushes on events. The snapshot is built once per second by the scheduler thread and shared by all clients, so cost doesn't grow with client count.

### 10.3.12 Experiments and admin (`api/experiments.py`, `api/admin.py`)
- `POST /api/v1/experiments {name, policy, notes, config}` → creates the run, sets it **active**, and switches the policy. Jobs created while it's active get its `experiment_run_id`.
- `POST /api/v1/experiments/{id}/finish` → deactivates the run and stores the summary (Amaan's `experiment_summary`).
- `GET /api/v1/experiments` and `/{id}/summary`.
- `experiments/run_live.py` (H-P5-1): reads a TOML plan (blocks, policy order, workload), and for each block:
  1. Waits until the start time.
  2. Starts the run.
  3. Submits the reference HPO study (§11.4) through the API.
  4. Waits for the study to complete or the block to time out.
  5. Finishes the run.
  6. Exports the summary to `experiments/results/live/{run_id}.json`.

  Interleave policies A/B/A/B across comparable time slots (§11.3).

### 10.3.13 Dev tools (`devtools/fake_agents.py`)
`idlegrid-dispatcher --sim-nodes 4 [--sim-pattern office|random|replay:path.csv] [--sim-exec fake|real]` starts N fake agents in threads. Each uses the real `DispatcherClient` and agent worker logic with a `FakeIdleDetector` driven by:
- `office`: an idle schedule by local hour.
- `random`: random sessions from a lognormal distribution.
- `replay`: a recorded usage CSV, time-compressed ×60.

With `fake` execution, a job "runs" by sleeping `est_runtime/perf_score` seconds, honouring pause. This lets everyone develop and demo the full system on one laptop, and it powers integration and load tests (NFR-04: 20 fake nodes, 1,000 queued jobs).

### 10.3.14 Integration points
| Direction | With | Interface |
|---|---|---|
| Consumes | Amaan | Repositories, `assign_job_to_node`, analytics (§10.2) |
| Consumes | Rejish | `IdleOracle.predict_many/reload` (§10.4.8) |
| Consumes | Ronit | `JobUnpackager` validation, `HpoController` (§10.5.6), dashboard static files |
| Provides | Arya | Agent API (Appendix B.1) |
| Provides | Ronit | Client API (Appendix B.2) for the CLI and dashboard |
| Provides | Rejish | `policies.py` (pure) for the simulator |

### 10.3.15 Tests
- **Unit:** `compute_node_status` truth table (every branch of Appendix F.1), each policy against hand-built scenarios (including best-fit choice, starvation, COARSE deprioritisation, RAM filter), scheduler sweeps with a fake repository layer and fake clock, bundle validation (missing manifest, traversal, too big), auth (missing/invalid token, node binding, admin-only routes).
- **Integration** (MySQL service): the full job lifecycle with 2 fake agents (submit → assign → run → pause → resume → result), migration, lost node, fencing (stale result → 409), Dispatcher restart in the middle of a job (C4), HPO study end to end with fake execution.
- **Load:** 20 fake agents + 1,000 jobs, measuring p95 heartbeat latency (NFR-04).
- **Contract test:** `tests/unit/common/test_contract.py` snapshots the JSON schema of every Appendix A model. Any change fails CI until the snapshot is deliberately updated in a contract-change PR.

### 10.3.16 Your tasks
P0: H-P0-1…4 · P1: H-P1-1…4 · P2: H-P2-1…3 · P3: H-P3-1…4 · P4: H-P4-1, H-P4-2 · P5: H-P5-1 (+ leads ALL-P5-1) · P6: H-P6-1, H-P6-2 · P7: release tagging and demo lead.

---

## 10.4 Rejish: ML Oracle & Simulator (`idlegrid.oracle`, `idlegrid.sim`)

### 10.4.0 Prompt preamble
> You are implementing the **ML Oracle** and the **trace-driven simulator** of IdleGrid, a system that runs jobs on idle student laptops and pauses or migrates them when owners return. Each laptop logs a `UsageSample` every 15 s (Appendix D: CPU, owner CPU, RAM, seconds since last input, host state, power). Your Oracle predicts, for a currently idle laptop, the **remaining idle time** as quantiles (q10, q20, q50, in seconds), using only data available up to the prediction time. The Dispatcher calls `IdleOracle.predict_many()` every 30 s and its scheduling policies prefer laptops whose conservative prediction (q20) covers a job's runtime. Your simulator replays recorded availability traces with the **same policy code** (`idlegrid.dispatcher.policies`, which is pure) to compare reactive and predictive scheduling with statistical rigour. Use pandas, numpy, scikit-learn (`HistGradientBoostingRegressor` with `loss="quantile"`), scipy and joblib, all from the pinned worker environment. Follow Appendices A and D exactly. Avoid any leakage of future information into features.

### 10.4.1 Mission
Produce the project's scientific contribution:
1. A calibrated idle-window predictor trained on **real** fleet data.
2. Evidence, from simulation and live runs, that it reduces wasted compute and preemptions compared with strong reactive baselines.

You lead the results sections of the paper and the report.

### 10.4.2 Files to attach for an LLM
`idlegrid/oracle/**`, `idlegrid/sim/**`, `idlegrid/dispatcher/policies.py`, `idlegrid/common/models.py`, the old `Rejish_Work/*.py`, a sample of the real usage CSV (100 rows), and Appendices A and D.

### 10.4.3 Existing code: keep / change
| Existing | Keep | Change |
|---|---|---|
| `train_oracle.py`: cyclical hour encoding, feature list saved with the model, MAE/R²/importance report | All three ideas | Real sessionised data. **Time-based split** (not `train_test_split`). Quantile models. Registry. RandomForest kept as **ablation model M2**. |
| `ml_oracle.py`: `MLOracle`, `evaluate_node_suitability(..., safety_buffer)`, fallback when the model is missing | Class (renamed `IdleOracle`, alias `MLOracle`), method name, fallback concept | Units in **seconds**. Input is `node_id` + time (features are built internally from history), not a loose dict. **Missing features raise errors instead of silently using defaults** (review M3). Returns `IdlePrediction`. |
| `generate_dataset.py` | Behaviour bands (sleep/class/evening) as an *idea* | Becomes `synthetic.py` for **tests only**: simulates sessions per node, then derives Appendix D samples from them (inactivity grows inside sessions and resets at activity). No target leakage. Timestamps end at "now". |

### 10.4.4 The availability definition (`availability.py`): single source of truth
Used by the simulator, the dataset builder, Amaan's `harvest_ratio`, and (through the same constants) the agent's host state.
```python
IDLE_THRESHOLD_SEC = 120          # must equal agent idle_threshold_sec
SAMPLE_INTERVAL_SEC = 15
MAX_GAP_SEC = 45                  # > 3 missed samples = agent off / laptop asleep

def is_available(s: UsageSample, require_ac: bool = True) -> bool:
    return (s.host_state == "IDLE"
            and (not require_ac or s.on_ac_power is not False)      # None (no battery) counts as AC
            and s.input_precision != "NONE")

def sessionize(samples: list[UsageSample]) -> list[Session]:
    """Maximal runs of available samples with consecutive gaps ≤ MAX_GAP_SEC.
    start = first.ts − (first.user_inactivity_sec − IDLE_THRESHOLD_SEC), clipped to ≥ previous sample ts
    end:
      next sample exists within MAX_GAP_SEC and host_state == ACTIVE → end = next.ts − next.user_inactivity_sec (exact input moment)
      next sample exists and not available for another reason      → end = next.ts, end_reason = BUSY | UNPLUGGED
      gap > MAX_GAP_SEC or end of data                              → end = last.ts + SAMPLE_INTERVAL_SEC, end_reason = GAP | CENSORED
    Session(node_id, start, end, end_reason)"""

def elapsed_idle(available_since: float, now: float) -> float: return max(0.0, now - available_since)
```
`end_reason` matters: `ACTIVE`/`BUSY`/`UNPLUGGED` cause a **pause** in the simulator (as the kill switch does live). `GAP` causes a **node loss**. `CENSORED` sessions (cut off by the end of the data) are excluded from labels.

### 10.4.5 Dataset (`dataset.py`) and features (`features.py`)
- **Prediction points:** for each non-censored session, t = start, start+60, start+120, … < end. Label `remaining_sec = end − t`. Optional sample weight `1 / n_points(session)` (evaluate both weighted and unweighted).
- **One feature function for training and serving** (prevents training/serving skew):
```python
def compute_features(node: NodeMeta, history: NodeHistory, t: float) -> dict[str, float]:
    # history exposes only data with ts <= t (enforced by NodeHistory.until(t)); unit test asserts no future access
```
| Feature | Definition |
|---|---|
| `hour_sin`, `hour_cos` | Local hour (using `tz_offset_min`) as a cyclical encoding *(from the original code)* |
| `dow_sin`, `dow_cos`, `is_weekend` | Local day of week |
| `log_elapsed_idle` | `log1p(t − session.start)` (online: `now − available_since`) |
| `cpu_percent`, `host_cpu_percent`, `ram_percent` | Latest sample ≤ t |
| `on_ac` | 1 / 0 / −1 (unknown) |
| `battery_percent` | −1 if no battery |
| `idle_frac_1h`, `idle_frac_24h` | Fraction of available samples in the window before t |
| `log_mean_session_same_hour_7d` | log1p of the mean length of sessions that **ended before t**, started within ±1 h of the current local hour, over the previous 7 days |
| `hist_q50_remaining_given_elapsed` | Node-specific empirical median of remaining time given an elapsed-time bucket (0–5, 5–15, 15–30, 30–60, 60–120, 120+ min), from sessions ended before t; global value if fewer than 5 sessions |
| `sessions_7d` | Count of sessions ended in the previous 7 days |
| `log_last_session_len` | Length of the previous completed session |
| `os_windows`, `os_darwin`, `os_linux`, `input_coarse` | Node metadata |
| `node_id` (one-hot) | **Only in variant "with-node"**. Variant "no-node" omits it, for leave-one-node-out generalisation. |

- **Target:** `log1p(remaining_sec)`. Quantile loss on the log scale back-transforms exactly (quantiles are preserved by monotonic transforms).
- **Splits:**
  - **Time-based:** train = first ~70% of calendar days, validation = next ~15% (early stopping, hyperparameters), test = last ~15%. Never shuffle across time.
  - **Leave-one-node-out:** for generalisation to new laptops (no-node variant).

### 10.4.6 Models (`models.py`)
| ID | Model | Purpose |
|---|---|---|
| B1 | Global empirical quantiles of remaining time given an elapsed-time bucket ("Lindy" baseline) | Simple baseline |
| B2 | Per-node × hour-of-week × elapsed-bucket empirical quantiles (falls back to B1 with < 5 sessions in the cell) | Strong heuristic baseline + cold-start fallback |
| **M1** | `HistGradientBoostingRegressor(loss="quantile", quantile=q)` for q ∈ {0.1, 0.2, 0.5}; `max_iter ≤ 500` with early stopping on the validation split; `learning_rate` 0.05; `max_leaf_nodes` 31; `min_samples_leaf` 40 | **Production model** |
| M2 | `RandomForestRegressor` on log target (median only), *the original model* | Ablation |
| M3 (optional) | `HistGradientBoostingClassifier` for P(remaining ≥ d), d ∈ {10, 30, 60} min | Decision-quality comparison |

Post-processing: enforce `q10 ≤ q20 ≤ q50` per prediction (sort), and clip to [0, 24 h].

### 10.4.7 Training, evaluation, registry
- `python -m idlegrid.oracle.train --from 2026-10-14 --to 2026-12-12 --variant with-node --out data/models/` builds the dataset from the DB (`usage.iter_range`) or from an export file (`--input usage.parquet`), trains B1, B2, M1 (and optionally M2/M3), and writes `oracle-YYYYMMDD-HHMM.joblib` containing `{models, feature_names, variant, train_window, metrics, code_version}` plus a JSON sidecar. It registers the model in `oracle_models` (`is_active=false`).
- `python -m idlegrid.oracle.evaluate --model <path> --test-from … --test-to …` writes `experiments/results/oracle/<model>/report.md` with:
  - **Pinball loss** per quantile (M1 vs B1 vs B2).
  - **MAE** of q50 (minutes).
  - **Coverage:** fraction of cases where the true remaining time ≥ q20 (target 0.80 ± 0.05) and ≥ q10 (target 0.90 ± 0.05). Calibration plot.
  - **Decision quality** at d ∈ {10, 30, 60} min: precision and recall of "q20 ≥ d" against "true remaining ≥ d".
  - Breakdown by node, OS, hour of day and elapsed bucket.
  - Feature importance (permutation importance on the test split).
  - Leave-one-node-out table.
- **Acceptance for activation:** M1 beats B2 on pinball loss at q20 and q50 on the test split, and q20 coverage is within 0.75–0.85. Then `python -m idlegrid.oracle.registry activate <model_id>` followed by `POST /api/v1/admin/oracle/reload`.
- **Nightly retraining (P5):** a scheduled task on the coordinator trains on the trailing 6 weeks, evaluates on the last 7 days, and auto-activates only if the acceptance criteria hold. Otherwise it keeps the current model and logs why. A weekly drift report checks the coverage of the active model on the last 7 days.

### 10.4.8 Serving API (`oracle.py`): what Harith calls
```python
class IdleOracle:
    def __init__(self, engine: Engine, model_dir: Path, cfg: OracleConfig): ...   # loads the active model; builds HistoryCache
    def predict(self, node_id: str, now: float) -> IdlePrediction: ...
    def predict_many(self, node_ids: Sequence[str], now: float) -> dict[str, IdlePrediction]: ...
    def evaluate_node_suitability(self, node_id: str, required_sec: float, now: float,
                                  quantile: str = "q20", safety_buffer_sec: float = 60) -> SuitabilityResult: ...
    def reload(self) -> str: ...      # returns the active model_version
MLOracle = IdleOracle                  # backwards-compatible alias
```
- **History cache:** per node, keep the last 7 days of samples in memory (loaded once, then appended from `usage.recent()` every 60 s). Recompute history aggregates every 10 min. Current-state features come from the newest sample and `available_since` from `nodes`.
- **Fallbacks** (recorded in `IdlePrediction.method`): no active model → `"heuristic"` (B2); node has < 3 days of data → `"heuristic_global"` (B1); node not idle → `"none"` with all quantiles 0.
- **Performance:** `predict_many` for 20 nodes in < 200 ms.

### 10.4.9 Simulator (`idlegrid.sim`)
- `traces.py`: `build_traces(samples, require_ac=True) -> dict[node_id, list[Session]]`, using `sessionize`, plus node metadata (`perf_score`, OS).
- `workload.py`: generators with seeds:
  - `hpo_batch(n_trials, runtime_dist, max_parallel, submit_at)`, with the runtime distribution fitted (lognormal) to **real** trial runtimes from P4.
  - `poisson_jobs(rate_per_hour, runtime_dist, duration)`.
  - Runtime classes: short 2–5 min, medium 10–20 min, long 30–60 min (reference speed).
- `engine.py`: a discrete-event simulator (`heapq`). Events: `AVAIL_START`, `AVAIL_END(reason)`, `JOB_ARRIVAL`, `ATTEMPT_FINISH`, `MIGRATE_TIMER`, `LOST_TIMER`. Semantics mirror the live system:
  - On `AVAIL_END` with ACTIVE/BUSY/UNPLUGGED: the running attempt **pauses**. If the same node becomes available again within `migrate_after_sec`, it resumes and the remaining work continues. Otherwise at `migrate_after_sec` the attempt is `MIGRATED`: its active time counts as wasted, and the job is requeued with a priority boost.
  - On `AVAIL_END` with GAP: after `offline_after_sec + lost_grace_sec` the attempt is `LOST` (wasted) and the job is requeued.
  - A job's runtime on a node = `est_runtime / perf_score` (true runtime = estimate × lognormal noise σ=0.2, to model estimate error).
  - Scheduling runs on every state change, calling `policy.assign(...)` from **`idlegrid.dispatcher.policies`** (imported unchanged).
  - Predictions for each candidate node come from `IdleOracle` *offline mode* (`compute_features` on the trace history up to t, using a model trained strictly before the simulation window). For the upper bound, `OraclePerfect` uses the true remaining time.
- `metrics.py`: the **same definitions as Amaan's analytics** (§10.2.7). A cross-check test runs one small scenario both through fake agents + Dispatcher and through the simulator and compares the metrics.
- `run.py`: `python -m idlegrid.sim.run --config experiments/configs/sim_main.toml` runs the grid (policies × workloads × windows × seeds) in parallel processes and writes `results.parquet`, `summary.csv` and plots.

### 10.4.10 Integration points
| Direction | With | Interface |
|---|---|---|
| Provides → Harith | `IdleOracle` serving API; `elapsed_idle` definition | §10.4.8 |
| Consumes ← Harith | `policies.py` (pure) | §10.3.9 |
| Consumes ← Amaan | `usage.iter_range`, export files, `oracle_models` repo | §10.2.5 |
| Consumes ← Arya | Usage samples (Appendix D), pause-latency CSVs | — |
| Consumes ← Ronit | Real HPO trial runtimes (from `job_attempts`) to fit the workload distribution | — |

### 10.4.11 Tests
- Sessionizer edge cases: gaps, ACTIVE end with exact-moment correction, UNPLUGGED, censored last session, single-sample sessions.
- **No-leakage test:** `NodeHistory.until(t)` raises if code accesses later rows. Property test: features at t are unchanged when all data after t is deleted.
- Model I/O round trip. Quantile monotonicity. Fallback paths.
- Simulator: deterministic with a seed; hand-computed tiny scenarios (one node, one job, one interruption) for each event type; cross-check with analytics.
- Synthetic-data pipeline smoke test runs in CI in < 60 s.

### 10.4.12 Your tasks
P0: R-P0-1, R-P0-2 · P1: R-P1-1, R-P1-2 · P2: R-P2-1, R-P2-2 · P3: R-P3-1, R-P3-2 · P4: R-P4-1 (+ paper results) · P5: R-P5-1, R-P5-2 · P6: R-P6-1.

---

## 10.5 Ronit: Executor, Packager, CLI, Dashboard & HPO (`idlegrid.executor`, `idlegrid.packager`, `idlegrid.cli`, `idlegrid.dashboard`, `idlegrid.hpo`)

### 10.5.0 Prompt preamble
> You are implementing the **job execution and user-facing layers** of IdleGrid, a system that runs Python ML jobs on idle team laptops (Windows, macOS, Linux), pauses them instantly when owners return, and migrates them if owners stay. You own:
> 1. The **packager**: zips a script and data with a `manifest.json`.
> 2. The **executor**: `JobRunner`/`ProcessController`, which runs a bundle as a low-priority subprocess tree with live logs, suspend/resume and an active-time timeout. The Node Agent on each laptop calls it.
> 3. The **`gridctl` CLI**.
> 4. The **web dashboard** front end (vanilla JS served by the Dispatcher).
> 5. **Distributed Optuna HPO**: the study spec, the trial wrapper that runs on workers, and the `HpoController` (ask-and-tell) that runs inside the Dispatcher.
>
> Much of this code already exists and works. Extend it and fix the listed bugs; don't rewrite it. Follow Appendices A (models), B (API) and E.3 (client config) exactly.

### 10.5.1 Mission
Make jobs **portable, safe to run on someone else's laptop, and pleasant to submit and watch**, and make distributed HPO the system's headline workload.

### 10.5.2 Files to attach for an LLM
`idlegrid/executor/**`, `idlegrid/packager/**`, `idlegrid/cli/**`, `idlegrid/dashboard/**`, `idlegrid/hpo/**`, `idlegrid/common/models.py`, `examples/**`, `tests/unit/{executor,packager,cli,hpo}/**`, and Appendices A, B, E.3.

### 10.5.3 Existing code: keep / change (by file)
| File | Keep | Change |
|---|---|---|
| `common/models.py` (moves to Harith's custody) | Everything as the base of Appendix A | Enum changes per §4.4. New fields per Appendix A. |
| `packager/bundle.py` | `JobPackager.create_bundle`, `JobUnpackager.extract_bundle`, `ResultPackager`, `ResultUnpackager`, traversal check | `job_id` optional in the manifest (the Dispatcher assigns it). Traversal check uses `Path.is_relative_to(dest)` instead of `str.startswith`. Add limits: bundle ≤ 200 MB, total uncompressed ≤ 1 GB, ≤ 10,000 entries, no absolute paths or symlinks (`BundleRejected` errors). `create_bundle(..., ram_required_mb=1024, kind="SCRIPT")`. |
| `executor/process_controller.py` | Popen + reader threads, metrics sampler, suspend/resume of the tree (children first), terminate logic | (1) **Active-time timeout** (§10.5.4). Fixes review R2. (2) `TIMED_OUT` status (R3). (3) Low priority + minimal env through `executor/platform.py` (§5.3, §5.5). (4) Writes `workspace/.pid` and `workspace/combined.log` (stderr lines prefixed `[stderr] `). (5) `job_pids()` returns the current PIDs of the tree. (6) `ExecutionMetrics.active_seconds`. (7) `max_job_cores` → `cpu_affinity` (Windows/Linux) + `OMP_NUM_THREADS`/`MKL_NUM_THREADS`/`OPENBLAS_NUM_THREADS`. |
| `executor/runner.py` | `JobRunner` API (`setup_workspace`, `run_sync`, `run_async`, `pause`, `resume`, `cancel`, `wait`) | `setup_workspace(bundle, workspace_name: str, job_id_override: str \| None)`, which **raises if the workspace exists** (never `rmtree`, R8). `run_sync/run_async(active_timeout_sec=…)`. `JobResult` includes `attempt_id` (the workspace name). Constructor options `low_priority=True`, `max_job_cores=None`. |
| `cli/gridctl.py` | Rich UI, all commands, `--local` mode, Windows UTF-8 fix | `/api/v1` paths. Bearer token from `~/.idlegrid/client.toml` or `IDLEGRID_TOKEN`. Use `status.value` in `format_status` (R5). Fix `demo-run` (R1): don't call `run_sync()` after `run_async()`; use `runner.wait()` and `runner.job_result`; use job sizes long enough that the pause is visible. `follow_logs` uses `?offset=` and stops on 404 or a terminal status. Exit codes (§10.5.5). New commands. |
| `dashboard/templates/index.html`, `static/js/app.js`, `static/css/styles.css` | The visual design (glass cards, meters, terminal pane), WebSocket client with reconnect | Real data from `/ws/v1/telemetry` + REST. Hash routing for pages (§10.5.7). Token login. **Escape all dynamic text** (`textContent` or an `esc()` helper; fixes S4). Vendor Chart.js and fonts into `static/vendor/` so the demo works offline. "Simulate activity" shown only in sim mode. |
| `demo_jobs/*.py` → `examples/jobs/` | As they are | Default sizes raised so each runs ≥ 60 s on the reference laptop (visible pause demo) |
| `tests/*` | All | Move and extend (§10.5.9) |
| `README.md` | Feature list, quickstart style | Remove the overclaims ("sandbox", "ML-guided routing" before it exists). Merge into the root README. |

### 10.5.4 Executor specification
**Active-time timeout** (replaces `process.wait(timeout=…)`):
```python
def active_seconds(self) -> float:
    now = time.monotonic()
    paused_now = (now - self._pause_started) if self._is_paused else 0.0
    return (now - self._started) - self._paused_total - paused_now

def wait(self, active_timeout_sec: float | None) -> int:
    while (rc := self.process.poll()) is None:
        if active_timeout_sec is not None and self.active_seconds() > active_timeout_sec:
            self._timed_out = True
            self.terminate(force=True)
            rc = self.process.wait()
            break
        time.sleep(0.2)
    ...  # join reader threads (existing code), finalise metrics, active_seconds
    status = COMPLETED if rc == 0 else TIMED_OUT if self._timed_out else CANCELLED if self._cancel_requested else FAILED
```
Use `time.monotonic()` for all durations (wall-clock jumps on laptops waking from sleep must not break timeouts).

**`executor/platform.py`:**
```python
def popen_kwargs(low_priority: bool) -> dict          # Windows: creationflags=IDLE_PRIORITY_CLASS | CREATE_NEW_PROCESS_GROUP
                                                       # POSIX: preexec_fn → os.nice(19) (+ start_new_session=True)
def command_prefix(low_priority: bool) -> list[str]    # macOS: ["taskpolicy", "-b"] if available, else []
def minimal_env(manifest_env: dict[str, str], max_job_cores: int | None) -> dict[str, str]
```
The `minimal_env` allowlist copied from the agent's environment: `PATH, SYSTEMROOT, WINDIR, COMSPEC, TEMP, TMP, TMPDIR, HOME, USERPROFILE, LOCALAPPDATA, APPDATA, LANG, LC_ALL`. It then sets `PYTHONUNBUFFERED=1`, `PYTHONIOENCODING=utf-8`, `IDLEGRID_JOB=1`, adds the manifest's `env_vars` (keys must match `^[A-Z_][A-Z0-9_]*$` and must not override the allowlist), and adds thread-count variables if `max_job_cores` is set. **Never** pass tokens or `IDLEGRID_DB_URL`.

**Interface the agent uses** (contract with Arya):
```python
runner = JobRunner(base_workspace_dir: Path, log_callback=None, status_callback=None, low_priority=True, max_job_cores=None)
manifest = runner.setup_workspace(bundle_path_or_bytes, workspace_name=attempt_id, job_id_override=job_id)
runner.run_async(active_timeout_sec: float, on_complete: Callable[[JobResult], None])
runner.pause() -> bool ; runner.resume() -> bool ; runner.cancel() -> None
runner.pid -> int | None ; runner.job_pids() -> set[int] ; runner.is_paused -> bool
runner.workspace_dir / "combined.log" ; runner.workspace_dir / "result_bundle.zip"
```

### 10.5.5 CLI specification (`gridctl`)
Global options: `--url`, `--token` (override the config), `--json` (machine-readable output). Exit codes: `0` ok, `1` usage error, `2` API error (4xx/5xx), `3` connection error.
| Command | Behaviour |
|---|---|
| `gridctl login --url URL --token TOKEN` | Verifies with `GET /api/v1/me`, writes `~/.idlegrid/client.toml` (permissions 0600 on POSIX) |
| `gridctl submit SCRIPT [--name] [--data F…] [--job-args A…] [--timeout 3600] [--estimated-runtime 300] [--ram 1024] [--follow] [--local]` | Packages and POSTs to `/api/v1/jobs`. Prints the job panel. `--follow` tails logs. `--local` runs with `JobRunner` (no server). |
| `gridctl jobs [--status …] [--mine] [--study ID] [--limit 20]` | Table of jobs |
| `gridctl status JOB` | Job panel + attempts table (node, status, active time, pauses, end reason) |
| `gridctl logs JOB [--follow]` | Offset-based tail |
| `gridctl download JOB [-o DIR]` | Downloads and extracts the result |
| `gridctl cancel JOB` | Cancels the job |
| `gridctl nodes` (alias `cluster`) | Nodes with OS, status, host state, power, perf, q20/q50 prediction, current job |
| `gridctl hpo create OBJECTIVE.py --space SPACE.json [--data F…] --n-trials N --parallel P --direction maximize\|minimize [--name] [--trial-timeout 1800] [--estimated-trial-runtime 240] [--seed 42]` | Creates a study (§10.5.6) |
| `gridctl hpo list` / `status STUDY` / `best STUDY` / `cancel STUDY` | Study views |
| `gridctl admin policy [NAME]` / `drain NODE` / `undrain NODE` / `oracle-reload` | Admin helpers |
| `gridctl experiment start NAME --policy P` / `finish RUN` / `summary RUN` | Experiment control |
| `gridctl demo-run --type pi\|matrix\|ml` | Local preemption demo (fixed) |

### 10.5.6 Distributed HPO (`idlegrid.hpo`)
**User contract:** the user writes `objective.py` with `def objective(params: dict) -> float`, and a `space.json` like:
```json
{"learning_rate": {"type": "float", "low": 0.001, "high": 0.3, "log": true},
 "max_iter":      {"type": "int",   "low": 50,    "high": 500},
 "max_leaf_nodes":{"type": "int",   "low": 15,    "high": 255, "log": true},
 "l2_regularization": {"type": "float", "low": 1e-6, "high": 1.0, "log": true},
 "loss_variant":  {"type": "categorical", "choices": ["log_loss"]}}
```
Static search spaces only (no conditional parameters); this is a documented limitation.

- `spec.py`: `StudySpec` and `ParamSpec` (Appendix A), plus `to_distributions(spec) -> dict[str, optuna.distributions.BaseDistribution]` (`IntDistribution`, `FloatDistribution`, `CategoricalDistribution`).
- `trial_entry.py` (copied into every trial bundle as `__idlegrid_trial__.py`, the trial's entrypoint):
```python
import importlib, json, math, os, sys, time
from pathlib import Path
sys.path.insert(0, os.getcwd())                  # the user's module sits in the job workspace
params = json.loads(Path("params.json").read_text())
mod = importlib.import_module(os.environ.get("IDLEGRID_OBJECTIVE_MODULE", "objective"))
t0 = time.time(); value = float(mod.objective(params))
if not math.isfinite(value): raise ValueError(f"objective returned non-finite value {value}")
Path("output").mkdir(exist_ok=True)
Path("output/objective.json").write_text(json.dumps({"value": value, "params": params, "duration_sec": time.time() - t0}))
print(f"[idlegrid-trial] value={value}")
```
- `bundle.py`: `build_trial_bundle(objective_bundle: bytes, params: dict, study_id: str, trial_number: int, spec: StudySpec) -> bytes` copies the user's files, adds `params.json` and `__idlegrid_trial__.py`, and writes a manifest with `entrypoint="__idlegrid_trial__.py"`, `kind="HPO_TRIAL"`, `hpo={study_id, trial_number}`, `timeout_seconds=spec.trial_timeout_sec` and `estimated_runtime_sec` = the current estimate.
- `controller.py`: runs inside the Dispatcher process (Harith calls `tick` and `on_trial_job_finished`):
```python
class HpoController:
    def __init__(self, storage_factory, repos, job_service, blob_store, cfg): ...
    def create_study(self, conn, spec: StudySpec, objective_bundle: bytes, user_id: str) -> StudyView
    def tick(self, conn, now: float) -> int                      # returns the number of trial jobs created
    def on_trial_job_finished(self, conn, job: JobRow, result: JobResult, result_zip: Path | None) -> None
    def cancel_study(self, conn, study_id: str) -> None
    def get_study(self, conn, study_id: str) -> StudyView         # includes trials, best so far, speedup estimate
```
  - Study creation: `optuna.create_study(study_name=f"idlegrid-{study_id}", storage=storage, direction=spec.direction, sampler=optuna.samplers.TPESampler(seed=spec.seed, constant_liar=True, multivariate=True), load_if_exists=True)`. Stores the objective bundle via `BlobStore` and inserts an `hpo_studies` row.
  - `tick`: for each `RUNNING` study, `in_flight` = its trial jobs in `QUEUED/ASSIGNED/RUNNING/PAUSED`. While `in_flight < max_parallel` and `asked < n_trials`: `trial = study.ask(fixed_distributions=dists)`, build the trial bundle, create the job (priority = study priority, `estimated_runtime_sec` = the median of completed trials' `active_seconds × perf_score`, else `spec.estimated_trial_runtime_sec`), and increment `asked`.
  - On finish:
    - `COMPLETED`: read `output/objective.json` from the result zip, then `study.tell(trial_number, value)` and update the best.
    - `FAILED`/`TIMED_OUT`: `study.tell(trial_number, state=TrialState.FAIL)`. If failures > max(3, 20% of `n_trials`), the study becomes `FAILED` (no more asks).
    - `CANCELLED`: tell `FAIL`.
    - Migrations and losses are attempt-level only: the same trial job requeues, with **no tell**.
  - Done when `asked == n_trials` and nothing is in flight: the study becomes `COMPLETED`, with `best_value`/`best_params` stored.
  - **Speedup estimate** = Σ trial `active_seconds × perf_score` (the sequential time on the reference laptop) ÷ study wall time.
- **Reference workload** (`examples/hpo/`, built with Rejish): `objective.py` trains `HistGradientBoostingClassifier` on a bundled real tabular dataset (for example a 50,000-row Covertype or Adult subset as CSV, ≤ 10 MB) with 3-fold CV accuracy. Sized so one trial takes 2–6 minutes on the reference laptop. Used by EXP-LIVE (§11.3) and the final demo.

### 10.5.7 Dashboard specification
Pages (hash routing in `app.js`, no framework):
| Route | Content |
|---|---|
| `#/nodes` (home) | Node cards: hostname, owner, OS icon, status badge (colour per NodeStatus), host state, idle method/precision, AC/battery, CPU/RAM meters, perf score, **prediction bar** (q20 and q50 minutes, with the fallback method shown), current job with paused overlay, last heartbeat age. Summary tiles: nodes online, idle capacity, jobs running/queued, wasted compute today. |
| `#/jobs` | Filterable job table (status, user, study). Columns as the existing table + attempts + wasted time. |
| `#/jobs/:id` | Job header, **attempt timeline** (horizontal bars per attempt: assigned → running → paused segments → end reason, coloured), live log terminal (offset polling or WebSocket), Download / Cancel buttons |
| `#/hpo` | Studies list with progress (asked / done / failed), best value |
| `#/hpo/:id` | Best-so-far line chart, trial scatter (trial # vs value), trials table (node, duration, attempts, value), parallelism over time, speedup estimate |
| `#/experiments` | Runs table + comparison bar charts (makespan, wasted compute, preemptions, goodput) by policy, with error bars |
| `#/settings` | Dispatcher URL (read-only), token entry (stored in `localStorage`), active policy (admin can change) |

Rules:
- Every dynamic string is escaped.
- All times are shown in local time with relative ages ("12 s ago").
- Colours are colour-blind-safe and meet WCAG AA contrast.
- It works at 1280×720 (projector).
- No external network requests (everything vendored).

### 10.5.8 Integration points
| Direction | With | Interface |
|---|---|---|
| Provides → Arya | `JobRunner` / `ProcessController` | §10.5.4 |
| Provides → Harith | `JobUnpackager` validation, `HpoController`, dashboard static files | §10.5.6 |
| Consumes ← Harith | Client API + WebSocket | Appendix B.2 |
| Consumes ← Amaan | Optuna storage factory, `studies` repo | §10.2.6 |
| Provides → Rejish | Real trial runtimes (via the DB) for the simulator workload | — |

### 10.5.9 Tests
- **Executor (CI 3-OS matrix):**
  - Existing tests.
  - A pause longer than the timeout does **not** time out (regression for R2).
  - A real timeout → `TIMED_OUT`.
  - Pause actually stops CPU (sample `cpu_percent` of the tree ≈ 0 while paused).
  - Children are suspended.
  - Low priority applied (`psutil.Process.nice()` check per OS).
  - Minimal env (no `IDLEGRID_TOKEN` visible to the job; `SYSTEMROOT` present on Windows).
  - `combined.log` written; `.pid` written.
- **Packager:** traversal, absolute paths, symlinks, zip bomb, file-count limit, optional `job_id`.
- **CLI:** each command against a mocked API (`respx`/`responses`); exit codes; `demo-run` runs the job exactly once (regression for R1).
- **HPO:** `to_distributions`; trial wrapper success, non-finite and exception cases; controller against an in-memory SQLite Optuna storage (unit) and MySQL (integration); a study completes with fake execution; FAIL accounting; migration doesn't tell.
- **Dashboard:** a smoke test that pages load and `app.js` has no console errors (Playwright in CI using the pre-installed Chromium, against the Dispatcher with `--sim-nodes 3`).

### 10.5.10 Your tasks
P0: N-P0-1, N-P0-2 · P1: N-P1-1, N-P1-2 · P2: N-P2-1…4 · P3: N-P3-1, N-P3-2 · P4: N-P4-1, N-P4-2 · P5: N-P5-1 · P6: N-P6-1.

---

# PART III: RESEARCH, QUALITY AND DELIVERY

## 11. Research methodology and experiments

### 11.1 Hypotheses
| ID | Hypothesis (Predictive-q20 vs the strongest reactive baseline, ReactiveLongestIdle) |
|---|---|
| H1 | Predictive scheduling reduces **wasted compute** (active seconds lost to migrations and node losses) |
| H2 | It reduces **preemptions** (owner returns to a laptop running our job) and **migrations** |
| H3 | It does **not increase makespan** for HPO batches, and reduces it for medium and long jobs |
| H4 | The benefit **grows with job length** (short jobs rarely get interrupted under any policy) |

### 11.2 EXP-SIM: trace-driven simulation (P3–P4; main paper results)
- **Data:** real `usage_samples` from all laptops, 12 Oct → 12 Dec 2026 (about 8 weeks).
  - Oracle trained on 12 Oct → 21 Nov.
  - Validation 22 → 28 Nov.
  - **Simulation/test window 29 Nov → 12 Dec.** The model never sees it.
- **Scenarios:** the test window is split into 6-hour windows (00/06/12/18 local), and each window is one scenario × 5 seeds.
- **Workloads:** HPO batch of 40 trials with `max_parallel = #nodes`, in three runtime classes (short/medium/long, §10.4.9), plus Poisson arrivals at low and high load.
- **Policies:** `fifo_any`, `random`, `reactive_longest_idle`, `predictive(q50)`, `predictive(q20)`, `oracle_perfect` (upper bound).
- **Metrics:** §10.2.7, plus owner disruptions (= preemptions).
- **Statistics:** results are paired by (window, seed, workload). Use the Wilcoxon signed-rank test (`scipy.stats.wilcoxon`) for Predictive-q20 vs ReactiveLongestIdle on each metric, with Holm–Bonferroni correction across metrics. Report median relative improvement with a bootstrap 95% CI (10,000 resamples), and how much of the gap to `oracle_perfect` is closed.
- **Sensitivity:** `migrate_after_sec` ∈ {60, 300, 900}; quantile ∈ {q10, q20, q50}; safety buffer ∈ {0, 60, 300} s; runtime-estimate noise σ ∈ {0, 0.2, 0.5}.
- **Ablations:** features (no history group, no time group, no current-state group); models (B1, B2, M1, M2).
- **Output:** `experiments/results/sim/v1/` (parquet + summary CSV + figures). Figures are regenerated from the tagged code for the final report (W21).

### 11.3 EXP-LIVE: live A/B on the real fleet (P5, W15–W17)
- **Workload:** the reference HPO study (§10.5.6), 40 trials of 2–6 min each, `max_parallel = 5`.
- **Blocks:** 3-hour blocks on weekday afternoons and evenings when the team **uses their laptops normally**. Interruptions must be natural, never staged; the team agrees not to change behaviour for the experiment. Policies alternate A/B/A/B. At least **5 blocks per policy** (`reactive_longest_idle` vs `predictive(q20)`).
- **Baseline for speedup:** the same 40 trials run sequentially on the reference laptop in `dedicated_mode` (twice). Speedup = sequential wall time ÷ fleet makespan.
- **Also measured:**
  - Pause latency per OS (from the agents' `pause_latency.csv`).
  - Owner disruption survey after each block: "Did IdleGrid slow your laptop down?" on a 1–5 Likert scale.
  - Battery and thermal notes.
- **Analysis:** Mann–Whitney U (small n, unpaired blocks) plus effect sizes, reported honestly even if not significant. The simulation provides the statistical power and the live runs provide realism.
- **Sim-to-real check (R-P5-2):** replay each live block's actual availability trace in the simulator with the same workload and policy, then compare simulated and observed metrics (a table of the gap).

### 11.4 Predictor evaluation (EXP-ORACLE)
As in §10.4.7: pinball loss, MAE, coverage/calibration, decision quality at 10/30/60 min, and breakdowns by node, OS and hour. Leave-one-node-out results show how a brand-new laptop would be served (cold start).

### 11.5 System benchmarks (EXP-SYS)
- Pause latency distribution per OS (p50/p95/max).
- Heartbeat p95 latency vs number of fake nodes (5, 10, 20, 50).
- Scheduler tick time vs queue size.
- Overhead of the agent itself (its own CPU % and RSS while idle; target < 1% CPU and < 80 MB).

---

## 12. Research paper and project report

### 12.1 Paper plan (Outcome Analysis: presented = 10 marks; communicated = 5)
**Working title:** *"Predicting Idle Windows: Preemption-Aware Scheduling of ML Workloads on Student Laptop Fleets"*.

**Claimed contributions** (keep them honest and specific):
1. An open-source, cross-platform (Windows/macOS/Linux) idle-harvesting system with sub-second owner preemption and pause-then-migrate semantics.
2. A dataset of real student-laptop availability (N laptops × ~8–12 weeks, pseudonymised).
3. A quantile idle-window predictor and a best-fit predictive placement policy.
4. A trace-driven and live evaluation against strong reactive baselines, plus a distributed HPO speedup study.

| Milestone | Date | Owner |
|---|---|---|
| Shortlist 3 Scopus-indexed conferences: submission deadline mid-Dec to mid-Jan, **conference held between mid-Feb and ~20 Mar 2027**, proceedings indexed in Scopus (check the publisher (IEEE Xplore, Springer) and the indexing of past editions); confirm with the guide | 8 Nov (W4) | Harith + Rejish |
| Pick the venue; note page limit, template, deadline and fees | 15 Nov (W5) | Team + guide |
| Outline + figure list | 22 Nov (W6) | Rejish |
| Related work section | 6 Dec (W8) | Rejish (from R-P0-2) |
| System design section | 13 Dec (W9) | Harith, Arya, Ronit |
| Predictor + methodology sections | 20 Dec (W10) | Rejish, Amaan |
| Simulation results + figures | 27 Dec (W11) | Rejish |
| Full draft | 3 Jan (W12) | All |
| Internal review + guide review | 4–7 Jan (W13) | Guide + all |
| **Submit** (earlier if the venue's deadline is earlier: then freeze sim results one week before it) | **≤ 10 Jan 2027** | Harith |
| Camera-ready (add live results if ready), registration | Per venue (Feb) | All |
| Presentation | Feb–Mar 2027 (before the final review) | Presenter + backup presenter |

Keep as proof for the final review: submission confirmation, acceptance email, registration receipt, presentation certificate and the published proceedings link.

**Paper outline:**
1. Introduction
2. Related work (cycle scavenging: HTCondor; volunteer computing: BOINC; availability prediction in desktop grids; spot/preemptible instance interruption; distributed HPO)
3. System design
4. Idle-window prediction
5. Scheduling policies
6. Evaluation (dataset, simulation, live, latency, HPO speedup)
7. Limitations (small fleet, single institution, lid-close sleep, trust model)
8. Conclusion

### 12.2 Authorship and honesty
All five members plus the guide (per department norms). All numbers are generated by committed scripts from tagged code. No result is reported that the team can't reproduce in front of examiners.

### 12.3 Project report (due 15 Mar 2027; target 14 Mar)
Follow the department template if one is issued. Otherwise:
1. Abstract
2. Introduction (problem, motivation, objectives)
3. Literature survey (+ research gaps)
4. Requirements analysis (§1, §8)
5. System design (§4, Appendices A–C, F)
6. Methodology (§10.4, §11)
7. Implementation (per component; OS specifics §5)
8. Testing (§14)
9. Results and discussion (EXP-ORACLE, SIM, LIVE, SYS)
10. Conclusion and future work (§1.5 non-goals)
11. References
12. Appendices (user manual, API reference, install runbook)

Each member writes their component's chapters, and Harith edits for consistency.

---

## 13. Data management
| Data | Where | Retention | In git? |
|---|---|---|---|
| Usage CSVs (source of truth) | Each laptop `~/.idlegrid/usage/` | Until the project ends | No |
| `usage_samples`, events, jobs, attempts | MySQL on the coordinator | Project end + paper | No |
| DB backups | `data/backups/` on the coordinator + one teammate's copy weekly | 14 daily + weekly copies | No |
| Bundles, results, logs | `data/` on the coordinator | 30 days (except experiment runs) | No |
| Models | `data/models/` + `oracle_models` table | All (small) | No (metadata JSON yes) |
| Pseudonymised exports for the paper | `data/exports/` | Permanent | Summary CSVs and figures only |
| Experiment summaries and figures | `experiments/results/**/summary.*`, `docs/paper/figures/` | Permanent | **Yes** |

---

## 14. Testing strategy

### 14.1 Levels
| Level | Scope | Where it runs |
|---|---|---|
| Unit | Pure logic per module (§10.x.tests) | CI on every PR; 3-OS matrix for `common`, `agent` (with mocks), `executor`, `packager`, `cli`, `hpo` |
| Integration | Dispatcher + MySQL + fake agents in-process | CI (Ubuntu + MySQL service) |
| Contract | JSON-schema snapshot of Appendix A models; policy import-purity | CI |
| E2E (real laptops) | Scripted checklists, run at every Thursday integration session | Team |
| Chaos | Failure injection on real or fake nodes | Phase 3 onwards; full suite in P6 |
| UI smoke | Playwright loads every dashboard page against `--sim-nodes 3` | CI |

### 14.2 End-to-end scenarios
- **E2E-1 (script job):** submit `examples/jobs/tabular_ml_train.py` from laptop A. It runs on idle laptop B. Logs stream. The result downloads on A and matches a local `--local` run's metrics keys.
- **E2E-2 (HPO):** `gridctl hpo create examples/hpo/objective.py --n-trials 40 --parallel 5` completes on ≥ 3 laptops. The best value is within the expected range. The dashboard shows trials per node.
- **E2E-3 (kill switch):** during a running job, touch B's keyboard. The job is paused within 1 s (Task Manager / Activity Monitor / `top` shows ~0% CPU for the job). Two minutes of idleness resumes it.
- **E2E-4 (cross-OS):** E2E-1 with every OS combination as worker at least once.

### 14.3 Pause-latency benchmark (NFR-01)
`tests/e2e/pause_latency.py` runs a CPU-bound job on the local agent. The tester presses a key 30 times, at least 20 s apart, waiting for resume in between. The agent's `pause_latency.csv` provides the measurements, and the script prints p50/p95/max. Run it on every OS. The results go in the paper.

### 14.4 Chaos suite
| ID | Inject | Expected |
|---|---|---|
| C1 | The owner stays active for longer than `migrate_after_sec` | Attempt `MIGRATED`, job finishes on another node, wasted compute recorded |
| C2 | Laptop lid closed / Wi-Fi off mid-job for 5 min | Node `OFFLINE` ≤ 15 s; attempt `LOST` after 60 s more; job finishes elsewhere; when the laptop returns, its stale job gets `ABORT` |
| C3 | Stale attempt uploads its result late | HTTP 409, ignored; job state unchanged |
| C4 | Kill and restart the Dispatcher mid-run | No job lost; agents reconnect; running attempts continue; results accepted |
| C5 | Kill the agent process mid-job | On agent restart the orphan job is killed; attempt `LOST` after the grace period; job requeued |
| C6 | Stop MySQL for 2 minutes | API returns 503; agents keep running jobs and buffering usage; everything recovers automatically |

---

## 15. Engineering process

### 15.1 Git
- `main` is protected (no direct pushes; CI must pass; ≥ 1 approval).
- Branch names: `<member>/<task-id>-<short-desc>` (e.g. `arya/A-P1-2-usage-upload`).
- Squash-merge PRs. Keep PRs small (< 400 changed lines where possible). The restructure PR (H-P0-2) is the one exception.
- Tags: `v0.1` (P1), `v0.2` (P2 MVP), `v0.3` (P3), `v0.4` (P4 / 2nd Review), `v1.0.0` (code freeze, 7 Mar).

### 15.2 Pull requests
The template (`.github/pull_request_template.md`, Appendix G) asks for: task ID, what and why, how it was tested (including OS), screenshots for UI, **contract impact** (none / additive / breaking), and docs updated.
- Contract changes and DB migrations need **2 approvals**, including Harith (contracts) or Amaan (DB).

### 15.3 Cadence
- **Monday sync (30 min):** last week's demo, this week's task IDs, blockers.
- **Thursday integration session (60–90 min, in person, all laptops):** merge, run E2E-1…4 on real laptops, file issues.
- **Daily async update** in the team chat: done, doing, blocked.
- **End of each phase:** a recorded 5-minute demo video (also a backup for reviews) and a short retrospective.
- GitHub Projects board: one issue per task ID, labelled by phase and owner, with columns Backlog → In progress → Review → Done.

### 15.4 Contract change process
1. Open an issue titled "Contract change: …" with the motivation, the exact diff to the appendix, and the affected owners.
2. Get approval from Harith and every affected owner.
3. In one PR: update the appendix in this PRD, `docs/contract.md`, `idlegrid/common/models.py` (or the migration), and the contract snapshot test. Bump `SCHEMA_VERSION`: minor for additive changes, major for breaking ones (avoid breaking changes after P2).

### 15.5 Definition of done (every task)
- Code merged to `main` with CI green on all matrix jobs.
- Tests cover the acceptance criteria in §9.
- Docs and runbook updated. Configuration documented in Appendix E if it changed.
- Demonstrated at the Thursday session on real laptops (for anything user-visible).
- The owner can explain every line in a review (examiners will ask).

### 15.6 Coding standards
- `ruff` (lint + format; line length 110).
- Type hints on public APIs; docstrings on public functions.
- `logging.getLogger(__name__)`; no `print` outside the CLI.
- No bare `except:`; every network call has a timeout.
- `pathlib` everywhere; `time.monotonic()` for durations; UTC epoch for timestamps.
- Never import FastAPI/DB modules from `common`, `policies`, `executor`, `packager` or `oracle.features`.

### 15.7 Using LLM assistants responsibly
- Always build the prompt from §0.2. Never let an assistant change contracts, delete tests or weaken acceptance criteria.
- Run the tests locally before opening a PR. Review generated code line by line.
- Say in the PR description when substantial code was generated. You must understand it well enough to defend it in a review.

---

## 16. Security and privacy

### 16.1 Threat model
| Threat | In scope? | Control |
|---|---|---|
| Someone else on campus Wi-Fi calls the API | Yes | Tailscale (only team devices can reach the coordinator) + Bearer tokens on every endpoint |
| A malicious web page in a team member's browser POSTs to the Dispatcher | Yes | No CORS; token required (browsers can't read it); the dashboard keeps the token in `localStorage` for the Dispatcher's origin only |
| Token leak via git | Yes | Tokens never in the repo; secret scanning in CI; tokens hashed (SHA-256) in the DB and shown once |
| A job reading secrets from the worker's environment | Yes | Minimal env allowlist (§10.5.4) |
| A buggy job hogging the laptop | Yes | Lowest priority, kill switch, `max_job_cores`, timeouts, RAM check |
| A malicious team member submitting harmful code | **Out of scope** (trusted team; D9) | Documented assumption. Jobs run as the laptop owner's OS user and **can read that user's files**. Expanding beyond the team requires sandboxing (containers or a dedicated low-privilege OS user) first. |
| Zip-slip / zip bomb | Yes | Packager validation (§10.5.3) on both the Dispatcher and the agent |

### 16.2 Expanding beyond the team later (not in this plan)
Prerequisites before outside users:
1. Run jobs under a dedicated unprivileged OS account or in containers.
2. Per-user quotas and fair-share scheduling.
3. HTTPS with real certificates.
4. Registration and approval flow.
5. Abuse monitoring.

The `users` table and per-user tokens already make this an extension rather than a redesign.

### 16.3 Privacy and consent
- **Collected:** timestamps, CPU %, owner CPU %, RAM %, seconds since last input, host state, AC/battery, idle-detection method, agent version.
- **Never collected:** keystrokes or which keys, mouse positions, window titles, app or process names of the owner, URLs, file names, screen contents.
- **Consent:** each member signs a one-paragraph consent (template in `docs/runbook/consent.md`) covering what is collected, why (this project and its paper), where it's stored (the coordinator and their own laptop), retention (until the paper is published, then pseudonymised summaries only), and the right to pause (`disable`) or withdraw (data deleted on request).
- Publications use pseudonymised node IDs (`N1…N5`) and aggregate statistics only.

---

## 17. Risks and mitigations
| # | Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|---|
| K1 | Usage logging starts late or has gaps | Med | **High** (no ML or paper) | A-P0-1 by 14 Oct; weekly completeness report; autostart; local CSV buffer | Arya |
| K2 | Campus Wi-Fi blocks the coordinator | High | High | Tailscale from P0; hotspot fallback; network test documented | Harith |
| K3 | Laptops sleep or are closed most of the time → little availability | Med | Med | Team habit (open + plugged when away); `dedicated_mode` for a spare machine; honest reporting | All |
| K4 | Linux Wayland idle detection unreliable | Med | Low | Multiple probes; COARSE handling; scheduler deprioritises | Arya |
| K5 | Coordinator laptop failure | Low | High | Nightly backups + weekly off-machine copy; documented restore on another laptop (< 1 h) | Amaan |
| K6 | Predictor doesn't beat the reactive baselines | Med | Med | Still publishable: honest results + system + dataset; analyse why (sensitivity, ablations); `oracle_perfect` shows the headroom | Rejish |
| K7 | Paper rejected or no suitable venue in time | Med | Med (5 vs 10 marks) | Shortlist 3 venues early; submit by the deadline (communicated = 5); revise and resubmit immediately | Harith |
| K8 | A member is unavailable for weeks | Med | High | Pair owners (Arya↔Ronit, Harith↔Amaan, Rejish↔Harith) who review each other's PRs and can take over; this PRD makes handover possible | Harith |
| K9 | Scope creep | Med | Med | Feature freeze 21 Feb; non-goals list; Monday triage | Harith |
| K10 | Demo-day network or hardware failure | Med | **High** | Hotspot + Tailscale; `--sim-nodes` single-laptop demo mode; recorded backup video; two rehearsals | Harith |
| K11 | Library version drift (Optuna, scikit-learn) | Low | Med | Pinned `requirements/*.txt`; `worker_env_hash` check | Ronit |
| K12 | Owners complain about heat or battery | Med | Med | `require_ac_power`; lowest priority; `max_job_cores`; easy `disable`; survey | Arya |

---

## 18. Final review demo script (40 marks): 10 minutes + Q&A
**T−60 min checklist:**
- Coordinator plugged in; Dispatcher + MySQL running; `gridctl nodes` shows ≥ 4 laptops `IDLE_*`.
- Tailscale up (or hotspot).
- Dashboard on the projector at 1280×720.
- The reference HPO bundle is ready.
- Backup video on a USB drive.
- `migrate_after_sec = 60` and `resume_after_idle_sec = 20` for demo pacing (`gridctl admin`).

| Time | Step | What the examiners see |
|---|---|---|
| 0:00 | The problem in one slide; architecture in one slide | Idle laptops vs Colab limits; the 5 components and who built them |
| 1:30 | Dashboard `#/nodes` | Real laptops (Win/macOS/Linux), live CPU, idle predictions (q20/q50) |
| 2:30 | `gridctl hpo create examples/hpo/objective.py --n-trials 20 --parallel 4` from a laptop | Trials appear and spread across laptops |
| 3:30 | An examiner touches a worker's keyboard | Card turns red ≤ 1 s, job paused, Task Manager shows 0% CPU for it |
| 4:30 | The examiner keeps using it for 60 s | Attempt `MIGRATED`; the trial restarts on another laptop (timeline view) |
| 5:30 | Close a worker's lid / turn off Wi-Fi | Node `OFFLINE`, then `LOST`, trial requeued; nothing breaks |
| 6:30 | `#/hpo/:id` | Best-so-far curve, speedup vs sequential |
| 7:30 | Results slides | EXP-ORACLE calibration, EXP-SIM bar charts with CIs, EXP-LIVE table, pause latency per OS |
| 9:00 | Outcome proof | Paper acceptance / presentation certificate |
| 9:30 | Limitations and future work | Trust model, sandboxing, GPUs, checkpointing |

**Fallbacks:** network fails → switch to the hotspot; still failing → run `idlegrid-dispatcher --sim-nodes 4 --sim-exec real` on one laptop (the full UI and flow, with simulated owners); everything fails → the recorded video.

---

## 19. Glossary
| Term | Meaning |
|---|---|
| Agent | The IdleGrid process on each worker laptop (§10.1) |
| Attempt | One try at running a job on one node. A job may have several (after migration or loss). |
| Availability / idle session | A maximal period where a laptop is idle, on AC (if required) and observable (§10.4.4) |
| Coordinator | The laptop running the Dispatcher + MySQL |
| Dispatcher | The central FastAPI service (§10.3) |
| Fencing | Rejecting or aborting work from an attempt that is no longer current |
| Goodput | Useful compute ÷ (useful + wasted) |
| HostState | The agent's view of the owner: ACTIVE / BUSY / IDLE / UNKNOWN |
| Kill switch | Local, sub-second pausing of the job when the owner returns |
| Migration | Aborting a long-paused attempt and requeuing the job elsewhere |
| Node | One laptop running the agent, identified by `node_id` |
| NodeStatus | The Dispatcher's derived status (Appendix F.1) |
| Oracle | The idle-window predictor (§10.4) |
| perf_score | Relative CPU speed of a node (≈ 1.0 on the reference laptop) |
| q20 / q50 | The 20th / 50th percentile of predicted remaining idle time. "80% sure it stays idle at least q20." |
| Wasted compute | Active seconds of attempts that ended MIGRATED or LOST |

---

# APPENDICES (binding contracts)

## Appendix A: Shared models (`idlegrid/common/models.py`)
Pydantic v2. Unknown fields are **ignored** (the default), so additive minor-version changes don't break older readers. IDs: `user_id = "u_" + 8 hex`, `job_id = "job_" + 10 hex`, `attempt_id = f"{job_id}-a{attempt_no}"`, `command_id = "cmd_" + 12 hex`, `study_id = "study_" + 8 hex`, `run_id = "run_" + 8 hex`, `node_id = "node-" + 12 hex` (agent-generated, stable).

```python
"""IdleGrid shared contracts. Changes follow PRD §15.4. Never edit casually."""
from __future__ import annotations

import time
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


# ───────────────────────── Enums ─────────────────────────
class JobStatus(str, Enum):
    QUEUED = "QUEUED"; ASSIGNED = "ASSIGNED"; RUNNING = "RUNNING"; PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"; FAILED = "FAILED"; CANCELLED = "CANCELLED"; TIMED_OUT = "TIMED_OUT"

TERMINAL_JOB_STATUSES = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.TIMED_OUT}


class AttemptStatus(str, Enum):
    ASSIGNED = "ASSIGNED"; RUNNING = "RUNNING"; PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"; FAILED = "FAILED"; CANCELLED = "CANCELLED"; TIMED_OUT = "TIMED_OUT"
    MIGRATED = "MIGRATED"; LOST = "LOST"

TERMINAL_ATTEMPT_STATUSES = {AttemptStatus.COMPLETED, AttemptStatus.FAILED, AttemptStatus.CANCELLED,
                             AttemptStatus.TIMED_OUT, AttemptStatus.MIGRATED, AttemptStatus.LOST}


class NodeStatus(str, Enum):
    OFFLINE = "OFFLINE"; HOST_ACTIVE = "HOST_ACTIVE"; HOST_BUSY = "HOST_BUSY"
    IDLE_SAFE = "IDLE_SAFE"; IDLE_RISKY = "IDLE_RISKY"; RUNNING_JOB = "RUNNING_JOB"
    DRAINING = "DRAINING"; UNSCHEDULABLE = "UNSCHEDULABLE"


class HostState(str, Enum):
    ACTIVE = "ACTIVE"; BUSY = "BUSY"; IDLE = "IDLE"; UNKNOWN = "UNKNOWN"


class InputDetection(str, Enum):
    PRECISE = "PRECISE"; COARSE = "COARSE"; NONE = "NONE"


class JobKind(str, Enum):
    SCRIPT = "SCRIPT"; HPO_TRIAL = "HPO_TRIAL"


class CommandType(str, Enum):
    START = "START"; ABORT = "ABORT"; PAUSE = "PAUSE"; RESUME = "RESUME"


class StudyStatus(str, Enum):
    RUNNING = "RUNNING"; COMPLETED = "COMPLETED"; FAILED = "FAILED"; CANCELLED = "CANCELLED"


# ───────────────────────── Job bundles & execution ─────────────────────────
class HpoTrialRef(BaseModel):
    study_id: str
    trial_number: int


class JobManifest(BaseModel):
    """manifest.json inside every job bundle (created by the packager)."""
    job_id: str | None = None                  # assigned by the Dispatcher; ignored on submit
    job_name: str
    kind: JobKind = JobKind.SCRIPT
    entrypoint: str                            # relative path of the .py file inside the bundle
    args: list[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    timeout_seconds: int = 3600                # ACTIVE (unpaused) seconds
    estimated_runtime_sec: int = 60            # on the reference laptop (perf_score = 1.0)
    ram_required_mb: int = 1024
    requirements: list[str] | None = None      # informational; must be satisfied by the shared worker env
    env_vars: dict[str, str] = Field(default_factory=dict)
    files: list[str] = Field(default_factory=list)
    user_id: str | None = None                 # ignored; the Dispatcher uses the token's user
    hpo: HpoTrialRef | None = None


class ExecutionMetrics(BaseModel):
    start_time: float | None = None
    end_time: float | None = None
    duration_seconds: float = 0.0              # wall clock incl. pauses
    active_seconds: float = 0.0                # wall clock excl. pauses (used for timeouts & wasted compute)
    cpu_percent_samples: list[float] = Field(default_factory=list)
    ram_mb_samples: list[float] = Field(default_factory=list)
    peak_cpu_percent: float = 0.0
    peak_ram_mb: float = 0.0
    pause_count: int = 0
    total_pause_duration_sec: float = 0.0


class JobResult(BaseModel):
    job_id: str
    attempt_id: str | None = None
    status: JobStatus                          # COMPLETED | FAILED | CANCELLED | TIMED_OUT
    exit_code: int | None = None
    stdout: str = ""                           # last 64 KB only
    stderr: str = ""                           # last 64 KB only
    metrics: ExecutionMetrics = Field(default_factory=ExecutionMetrics)
    artifact_files: list[str] = Field(default_factory=list)
    error_message: str | None = None
    completed_at: float = Field(default_factory=time.time)
    objective_value: float | None = None       # HPO trials only


# ───────────────────────── Agent → Dispatcher ─────────────────────────
class NodeMetrics(BaseModel):
    cpu_percent: float                         # whole system, 0–100
    host_cpu_percent: float                    # system minus our job's processes, 0–100
    cpu_count: int
    ram_percent: float
    ram_available_mb: float
    ram_total_mb: float
    disk_free_gb: float
    user_inactivity_sec: float | None          # None = could not be read


class PowerInfo(BaseModel):
    on_ac_power: bool | None = None            # None = no battery (desktop) or unknown
    battery_percent: float | None = None


class NodeCapabilities(BaseModel):
    os: Literal["Windows", "Darwin", "Linux"]
    os_release: str
    arch: str
    python_version: str
    agent_version: str
    cpu_count: int
    ram_total_mb: float
    perf_score: float
    input_method: str
    input_precision: InputDetection
    can_prevent_sleep: bool
    worker_env_hash: str
    max_job_cores: int | None = None


class SharingPrefs(BaseModel):
    accepting_jobs: bool = True
    require_ac_power: bool = True
    dedicated_mode: bool = False


class AttemptReport(BaseModel):
    attempt_id: str
    job_id: str
    status: Literal["STARTING", "RUNNING", "PAUSED", "UPLOADING"]
    paused_since: float | None = None          # epoch seconds, already corrected to server clock
    active_seconds: float = 0.0
    pause_count: int = 0
    manual_pause: bool = False


class CommandResult(BaseModel):
    command_id: str
    ok: bool
    error: str | None = None                   # e.g. "host_active", "busy", "not_accepting", "bundle_integrity"


class Heartbeat(BaseModel):
    schema_version: str = SCHEMA_VERSION
    node_id: str
    hostname: str
    sent_at: float
    host_state: HostState
    metrics: NodeMetrics
    power: PowerInfo
    capabilities: NodeCapabilities
    sharing: SharingPrefs
    current_attempt: AttemptReport | None = None
    command_results: list[CommandResult] = Field(default_factory=list)


# ───────────────────────── Dispatcher → Agent ─────────────────────────
class StartJobPayload(BaseModel):
    job_id: str
    attempt_id: str
    kind: JobKind
    bundle_path: str                           # e.g. "/api/v1/attempts/{attempt_id}/bundle"
    bundle_sha256: str
    bundle_size: int
    manifest: JobManifest
    active_timeout_sec: float
    migrate_after_sec: float


class NodeCommand(BaseModel):
    command_id: str
    type: CommandType
    attempt_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)   # START → StartJobPayload; ABORT → {"reason": str}
    created_at: float


class AgentRuntimeOverrides(BaseModel):
    migrate_after_sec: float | None = None
    resume_after_idle_sec: float | None = None
    heartbeat_interval_sec: float | None = None


class HeartbeatResponse(BaseModel):
    schema_version: str = SCHEMA_VERSION
    server_time: float
    node_status: NodeStatus
    commands: list[NodeCommand] = Field(default_factory=list)
    heartbeat_interval_sec: float = 5.0
    config_overrides: AgentRuntimeOverrides = Field(default_factory=AgentRuntimeOverrides)


# ───────────────────────── Usage data ─────────────────────────
class UsageSample(BaseModel):
    ts_utc: float
    tz_offset_min: int
    node_id: str
    cpu_percent: float
    host_cpu_percent: float
    ram_percent: float
    user_inactivity_sec: float | None
    input_method: str
    input_precision: InputDetection
    host_state: HostState
    on_ac_power: bool | None
    battery_percent: float | None
    job_running: bool
    agent_version: str


class UsageBatch(BaseModel):
    schema_version: str = SCHEMA_VERSION
    node_id: str
    samples: list[UsageSample] = Field(max_length=2000)


class UsageBatchResponse(BaseModel):
    accepted: int
    duplicates: int


# ───────────────────────── Predictions ─────────────────────────
class IdlePrediction(BaseModel):
    node_id: str
    made_at: float
    elapsed_idle_sec: float
    q10_sec: float
    q20_sec: float
    q50_sec: float
    method: Literal["model", "heuristic", "heuristic_global", "none", "stale"]
    model_version: str | None = None


class SuitabilityResult(BaseModel):
    is_suitable: bool
    required_sec: float
    predicted_sec: float
    quantile: Literal["q10", "q20", "q50"]
    reason: str


# ───────────────────────── API views (CLI & dashboard) ─────────────────────────
class UserView(BaseModel):
    user_id: str
    display_name: str
    is_admin: bool


class NodeView(BaseModel):
    node_id: str
    owner_user_id: str
    owner_name: str
    hostname: str
    os: str
    os_release: str | None = None
    arch: str | None = None
    status: NodeStatus
    host_state: HostState | None = None
    metrics: NodeMetrics | None = None
    power: PowerInfo | None = None
    perf_score: float | None = None
    input_method: str | None = None
    input_precision: InputDetection | None = None
    accepting_jobs: bool = True
    current_job_id: str | None = None
    current_attempt_id: str | None = None
    current_attempt_status: AttemptStatus | None = None
    prediction: IdlePrediction | None = None
    available_since: float | None = None
    last_heartbeat_at: float | None = None
    first_seen_at: float | None = None


class AttemptView(BaseModel):
    attempt_id: str
    job_id: str
    attempt_no: int
    node_id: str
    hostname: str | None = None
    status: AttemptStatus
    assigned_at: float
    started_at: float | None = None
    ended_at: float | None = None
    end_reason: str | None = None
    active_seconds: float = 0.0
    pause_count: int = 0
    total_pause_duration_sec: float = 0.0
    predicted_q20_sec: float | None = None
    predicted_q50_sec: float | None = None
    required_sec: float | None = None
    policy_name: str | None = None
    exit_code: int | None = None


class JobView(BaseModel):
    # Field names kept compatible with Ronit's original dashboard/CLI where possible.
    job_id: str
    job_name: str
    kind: JobKind
    user_id: str
    status: JobStatus
    priority: int = 0
    entrypoint: str
    args: list[str] = Field(default_factory=list)
    created_at: float
    queued_at: float | None = None
    started_at: float | None = None
    completed_at: float | None = None
    estimated_runtime_sec: int
    timeout_seconds: int
    ram_required_mb: int
    assigned_node_id: str | None = None        # node of current/final attempt
    assigned_hostname: str | None = None
    attempts_count: int = 0
    duration_seconds: float = 0.0              # created_at → completed_at (or now)
    active_seconds: float = 0.0                # of the final/current attempt
    wasted_seconds: float = 0.0                # Σ active_seconds of MIGRATED/LOST attempts
    pause_count: int = 0                       # over all attempts
    total_pause_duration_sec: float = 0.0
    peak_cpu_percent: float = 0.0
    peak_ram_mb: float = 0.0
    exit_code: int | None = None
    error_message: str | None = None
    artifact_files: list[str] = Field(default_factory=list)
    study_id: str | None = None
    trial_number: int | None = None
    objective_value: float | None = None
    experiment_run_id: str | None = None
    attempts: list[AttemptView] | None = None  # only on GET /jobs/{id}


class LogChunk(BaseModel):
    job_id: str
    offset: int
    next_offset: int
    text: str
    complete: bool


class ParamSpec(BaseModel):
    type: Literal["int", "float", "categorical"]
    low: float | None = None
    high: float | None = None
    log: bool = False
    step: float | None = None
    choices: list[Any] | None = None           # required for categorical; JSON scalars only


class StudySpec(BaseModel):
    name: str
    direction: Literal["minimize", "maximize"] = "maximize"
    search_space: dict[str, ParamSpec]
    n_trials: int = Field(ge=1, le=1000)
    max_parallel: int = Field(ge=1, le=50)
    trial_timeout_sec: int = 1800
    estimated_trial_runtime_sec: int = 240
    seed: int | None = 42
    objective_module: str = "objective"
    priority: int = 0


class TrialView(BaseModel):
    trial_number: int
    job_id: str
    status: JobStatus
    node_id: str | None = None
    value: float | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    active_seconds: float = 0.0
    attempts: int = 0


class StudyView(BaseModel):
    study_id: str
    name: str
    user_id: str
    status: StudyStatus
    direction: str
    n_trials: int
    max_parallel: int
    asked: int
    completed: int
    failed: int
    in_flight: int
    best_value: float | None = None
    best_params: dict[str, Any] | None = None
    best_trial_number: int | None = None
    created_at: float
    finished_at: float | None = None
    wall_time_sec: float = 0.0
    sequential_estimate_sec: float = 0.0
    speedup_estimate: float | None = None
    trials: list[TrialView] | None = None      # only on GET /hpo/studies/{id}


class ExperimentSummary(BaseModel):
    run_id: str
    jobs_total: int
    jobs_completed: int
    makespan_sec: float | None
    useful_compute_sec: float
    wasted_compute_sec: float
    goodput: float | None
    preemptions: int
    migrations: int
    node_losses: int
    mean_queue_wait_sec: float | None
    mean_jct_sec: float | None
    harvest_ratio: float | None


class ExperimentRunView(BaseModel):
    run_id: str
    name: str
    policy: str
    notes: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    is_active: bool
    started_at: float
    finished_at: float | None = None
    summary: ExperimentSummary | None = None


class TelemetrySnapshot(BaseModel):
    server_time: float
    nodes: list[NodeView]
    jobs: list[JobView]                        # all active + 50 most recent
    studies: list[StudyView]                   # without trials
    active_policy: str
    active_experiment_run_id: str | None = None


class ErrorResponse(BaseModel):
    error: str                                 # machine code, e.g. "stale_attempt", "bundle_invalid"
    message: str
    details: dict[str, Any] | None = None
```

## Appendix B: REST and WebSocket API (`/api/v1`)
All endpoints except `/healthz` require `Authorization: Bearer <token>` (the WebSocket uses `?token=`). Request and response bodies are the Appendix A models. Errors use `ErrorResponse` with these status codes: 400 bad input · 401 missing/invalid token · 403 forbidden · 404 not found · 409 conflict/stale · 413 too large · 422 validation · 426 schema-version mismatch · 503 DB unavailable.

### B.1 Agent endpoints (called by Arya's agent)
| Method & path | Body → Response | Notes |
|---|---|---|
| `POST /api/v1/heartbeat` | `Heartbeat` → `HeartbeatResponse` | Every 5 s. Node binding on the first call. |
| `POST /api/v1/usage` | `UsageBatch` → `UsageBatchResponse` | Idempotent on `(node_id, ts_utc)` |
| `GET /api/v1/attempts/{attempt_id}/bundle` | → `application/zip` stream | Only to the node that owns the attempt, while it's ASSIGNED/RUNNING/PAUSED |
| `POST /api/v1/attempts/{attempt_id}/logs` | `{"offset": int, "text": str}` → `{"next_offset": int}` | Idempotent by offset; ≤ 1 MB per call |
| `POST /api/v1/attempts/{attempt_id}/result` | multipart: `result_json` (`JobResult`), `result_bundle` (zip, optional) → `{"accepted": true}` | **409** if the attempt is stale or terminal |

### B.2 Client endpoints (CLI & dashboard; Ronit's clients)
| Method & path | Body → Response | Notes |
|---|---|---|
| `GET /api/v1/me` | → `UserView` | Used by `gridctl login` |
| `POST /api/v1/jobs` | multipart `bundle` (zip) **or** form `preset=pi\|matrix\|ml` → `201 JobView` | Dispatcher assigns `job_id` |
| `GET /api/v1/jobs?status=&user=&study=&limit=&offset=` | → `list[JobView]` | Newest first |
| `GET /api/v1/jobs/{job_id}` | → `JobView` (with `attempts`) | — |
| `GET /api/v1/jobs/{job_id}/logs?offset=0` | → `LogChunk` | — |
| `GET /api/v1/jobs/{job_id}/result` | → zip | 404 until available |
| `POST /api/v1/jobs/{job_id}/cancel` | → `JobView` | Owner or admin |
| `POST /api/v1/jobs/{job_id}/pause` · `/resume` | → `{"queued": true}` | Admin/owner; sends a manual PAUSE/RESUME command |
| `GET /api/v1/nodes` | → `list[NodeView]` | — |
| `GET /api/v1/nodes/{node_id}` | → `NodeView` | — |
| `POST /api/v1/nodes/{node_id}/drain` · `/undrain` | → `NodeView` | Node owner or admin |
| `POST /api/v1/hpo/studies` | multipart: `spec` (`StudySpec` JSON), `bundle` (zip with `objective.py` + data) → `201 StudyView` | — |
| `GET /api/v1/hpo/studies` | → `list[StudyView]` | — |
| `GET /api/v1/hpo/studies/{study_id}` | → `StudyView` (with `trials`) | — |
| `POST /api/v1/hpo/studies/{study_id}/cancel` | → `StudyView` | Cancels queued and running trials |
| `GET /api/v1/metrics/summary?from=&to=` | → `ExperimentSummary`-shaped totals | Dashboard tiles |

### B.3 Admin and experiment endpoints (admin token)
| Method & path | Body → Response |
|---|---|
| `GET /api/v1/admin/config` | → effective `DispatcherConfig` (secrets redacted) + `sim_nodes` |
| `POST /api/v1/admin/policy` | `{"policy": "predictive"}` → `{"policy": ...}` |
| `POST /api/v1/admin/oracle/reload` | → `{"model_version": ...}` |
| `POST /api/v1/admin/runtime` | `{"migrate_after_sec": 60, "resume_after_idle_sec": 20}` → effective values (demo pacing) |
| `POST /api/v1/experiments` | `{"name", "policy", "notes", "config"}` → `ExperimentRunView` (becomes active) |
| `POST /api/v1/experiments/{run_id}/finish` | → `ExperimentRunView` (with summary) |
| `GET /api/v1/experiments` · `GET /api/v1/experiments/{run_id}` | → views |

### B.4 Dev endpoints (only when `dev.sim_nodes > 0`)
| `POST /api/v1/dev/nodes/{node_id}/simulate-activity` | `{"active": true \| false}` → `NodeView` |
|---|---|

### B.5 WebSocket and health
- `GET /ws/v1/telemetry?token=…` sends a `TelemetrySnapshot` every 1 s plus immediately after significant events.
- `GET /healthz` (no auth) → `{"status": "ok"|"degraded", "db": "ok"|"down", "scheduler_last_tick_age_sec": float, "version": str}`.
- `GET /` serves the dashboard.

## Appendix C: Database DDL (`idlegrid/db/migrations/0001_initial.sql`)
MySQL 8.0, InnoDB, `utf8mb4`, all `DATETIME(3)` values in UTC. A second database `idlegrid_optuna` is created empty for Optuna (Optuna creates its own tables).
```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
  version     VARCHAR(64) PRIMARY KEY,
  applied_at  DATETIME(3) NOT NULL
);

CREATE TABLE users (
  user_id       VARCHAR(16)  PRIMARY KEY,
  display_name  VARCHAR(64)  NOT NULL UNIQUE,
  token_sha256  CHAR(64)     NOT NULL UNIQUE,
  is_admin      BOOLEAN      NOT NULL DEFAULT FALSE,
  created_at    DATETIME(3)  NOT NULL
);

CREATE TABLE nodes (
  node_id             VARCHAR(64)  PRIMARY KEY,
  owner_user_id       VARCHAR(16)  NOT NULL,
  hostname            VARCHAR(255) NOT NULL,
  os                  VARCHAR(16)  NOT NULL,
  os_release          VARCHAR(64),
  arch                VARCHAR(16),
  python_version      VARCHAR(16),
  agent_version       VARCHAR(16),
  cpu_count           INT,
  ram_total_mb        INT,
  perf_score          FLOAT,
  input_method        VARCHAR(32),
  input_precision     VARCHAR(8),
  can_prevent_sleep   BOOLEAN,
  worker_env_hash     VARCHAR(64),
  accepting_jobs      BOOLEAN      NOT NULL DEFAULT TRUE,
  require_ac_power    BOOLEAN      NOT NULL DEFAULT TRUE,
  dedicated_mode      BOOLEAN      NOT NULL DEFAULT FALSE,
  status              VARCHAR(16)  NOT NULL,
  host_state          VARCHAR(8),
  cpu_percent         FLOAT,
  host_cpu_percent    FLOAT,
  ram_percent         FLOAT,
  ram_available_mb    INT,
  user_inactivity_sec FLOAT NULL,
  on_ac_power         BOOLEAN NULL,
  battery_percent     FLOAT NULL,
  current_attempt_id  VARCHAR(40) NULL,
  available_since     DATETIME(3) NULL,
  predicted_q10_sec   FLOAT NULL,
  predicted_q20_sec   FLOAT NULL,
  predicted_q50_sec   FLOAT NULL,
  prediction_method   VARCHAR(20) NULL,
  prediction_model    VARCHAR(64) NULL,
  prediction_at       DATETIME(3) NULL,
  last_ip             VARCHAR(45),
  last_heartbeat_at   DATETIME(3) NOT NULL,
  first_seen_at       DATETIME(3) NOT NULL,
  CONSTRAINT fk_nodes_owner FOREIGN KEY (owner_user_id) REFERENCES users(user_id),
  INDEX ix_nodes_status (status),
  INDEX ix_nodes_last_hb (last_heartbeat_at)
);

CREATE TABLE node_status_events (
  event_id     BIGINT AUTO_INCREMENT PRIMARY KEY,
  node_id      VARCHAR(64) NOT NULL,
  from_status  VARCHAR(16) NULL,
  to_status    VARCHAR(16) NOT NULL,
  at           DATETIME(3) NOT NULL,
  INDEX ix_nse_node_at (node_id, at)
);

-- No FK on node_id: rows logged before a node's first heartbeat (Phase 0 CSVs) must still be insertable.
CREATE TABLE usage_samples (
  node_id             VARCHAR(64) NOT NULL,
  ts_utc              DATETIME(3) NOT NULL,
  tz_offset_min       SMALLINT    NOT NULL,
  cpu_percent         FLOAT       NOT NULL,
  host_cpu_percent    FLOAT       NOT NULL,
  ram_percent         FLOAT       NOT NULL,
  user_inactivity_sec FLOAT       NULL,
  input_method        VARCHAR(32) NOT NULL,
  input_precision     VARCHAR(8)  NOT NULL,
  host_state          VARCHAR(8)  NOT NULL,
  on_ac_power         BOOLEAN     NULL,
  battery_percent     FLOAT       NULL,
  job_running         BOOLEAN     NOT NULL DEFAULT FALSE,
  agent_version       VARCHAR(16) NOT NULL,
  received_at         DATETIME(3) NOT NULL,
  PRIMARY KEY (node_id, ts_utc),
  INDEX ix_usage_ts (ts_utc)
);

CREATE TABLE experiment_runs (
  run_id       VARCHAR(16) PRIMARY KEY,
  name         VARCHAR(128) NOT NULL,
  policy       VARCHAR(32)  NOT NULL,
  notes        TEXT,
  config       JSON,
  is_active    BOOLEAN      NOT NULL DEFAULT FALSE,
  started_at   DATETIME(3)  NOT NULL,
  finished_at  DATETIME(3)  NULL,
  summary      JSON         NULL
);

CREATE TABLE hpo_studies (
  study_id                VARCHAR(16)  PRIMARY KEY,
  optuna_study_name       VARCHAR(128) NOT NULL UNIQUE,
  user_id                 VARCHAR(16)  NOT NULL,
  name                    VARCHAR(128) NOT NULL,
  direction               VARCHAR(8)   NOT NULL,
  spec                    JSON         NOT NULL,
  status                  VARCHAR(12)  NOT NULL,
  n_trials                INT          NOT NULL,
  max_parallel            INT          NOT NULL,
  asked                   INT          NOT NULL DEFAULT 0,
  completed               INT          NOT NULL DEFAULT 0,
  failed                  INT          NOT NULL DEFAULT 0,
  best_value              DOUBLE       NULL,
  best_params             JSON         NULL,
  best_trial_number       INT          NULL,
  objective_bundle_path   VARCHAR(255) NOT NULL,
  objective_bundle_sha256 CHAR(64)     NOT NULL,
  priority                INT          NOT NULL DEFAULT 0,
  experiment_run_id       VARCHAR(16)  NULL,
  created_at              DATETIME(3)  NOT NULL,
  finished_at             DATETIME(3)  NULL,
  CONSTRAINT fk_studies_user FOREIGN KEY (user_id) REFERENCES users(user_id),
  CONSTRAINT fk_studies_run  FOREIGN KEY (experiment_run_id) REFERENCES experiment_runs(run_id)
);

CREATE TABLE jobs (
  job_id                VARCHAR(16)  PRIMARY KEY,
  user_id               VARCHAR(16)  NOT NULL,
  job_name              VARCHAR(128) NOT NULL,
  kind                  VARCHAR(12)  NOT NULL,
  status                VARCHAR(12)  NOT NULL,
  priority              INT          NOT NULL DEFAULT 0,
  entrypoint            VARCHAR(255) NOT NULL,
  args                  JSON,
  manifest              JSON         NOT NULL,
  bundle_path           VARCHAR(255) NOT NULL,
  bundle_sha256         CHAR(64)     NOT NULL,
  bundle_size           BIGINT       NOT NULL,
  estimated_runtime_sec INT          NOT NULL,
  timeout_seconds       INT          NOT NULL,
  ram_required_mb       INT          NOT NULL,
  study_id              VARCHAR(16)  NULL,
  trial_number          INT          NULL,
  experiment_run_id     VARCHAR(16)  NULL,
  current_attempt_id    VARCHAR(40)  NULL,
  final_attempt_id      VARCHAR(40)  NULL,
  attempts_count        INT          NOT NULL DEFAULT 0,
  created_at            DATETIME(3)  NOT NULL,
  queued_at             DATETIME(3)  NOT NULL,
  started_at            DATETIME(3)  NULL,
  completed_at          DATETIME(3)  NULL,
  exit_code             INT          NULL,
  error_message         TEXT         NULL,
  objective_value       DOUBLE       NULL,
  CONSTRAINT fk_jobs_user  FOREIGN KEY (user_id) REFERENCES users(user_id),
  CONSTRAINT fk_jobs_study FOREIGN KEY (study_id) REFERENCES hpo_studies(study_id),
  CONSTRAINT fk_jobs_run   FOREIGN KEY (experiment_run_id) REFERENCES experiment_runs(run_id),
  UNIQUE KEY uq_jobs_trial (study_id, trial_number),
  INDEX ix_jobs_queue (status, priority, queued_at),
  INDEX ix_jobs_user (user_id, created_at),
  INDEX ix_jobs_run (experiment_run_id)
);

CREATE TABLE job_attempts (
  attempt_id         VARCHAR(40)  PRIMARY KEY,
  job_id             VARCHAR(16)  NOT NULL,
  attempt_no         INT          NOT NULL,
  node_id            VARCHAR(64)  NOT NULL,
  status             VARCHAR(12)  NOT NULL,
  policy_name        VARCHAR(32)  NOT NULL,
  experiment_run_id  VARCHAR(16)  NULL,
  assigned_at        DATETIME(3)  NOT NULL,
  started_at         DATETIME(3)  NULL,
  ended_at           DATETIME(3)  NULL,
  end_reason         VARCHAR(32)  NULL,
  paused_since       DATETIME(3)  NULL,
  active_seconds     DOUBLE       NOT NULL DEFAULT 0,
  pause_count        INT          NOT NULL DEFAULT 0,
  total_pause_sec    DOUBLE       NOT NULL DEFAULT 0,
  predicted_q20_sec  FLOAT        NULL,
  predicted_q50_sec  FLOAT        NULL,
  required_sec       FLOAT        NULL,
  exit_code          INT          NULL,
  peak_cpu_percent   FLOAT        NULL,
  peak_ram_mb        FLOAT        NULL,
  log_bytes          BIGINT       NOT NULL DEFAULT 0,
  result_path        VARCHAR(255) NULL,
  result_sha256      CHAR(64)     NULL,
  metrics            JSON         NULL,
  CONSTRAINT fk_att_job  FOREIGN KEY (job_id)  REFERENCES jobs(job_id),
  CONSTRAINT fk_att_node FOREIGN KEY (node_id) REFERENCES nodes(node_id),
  UNIQUE KEY uq_att_job_no (job_id, attempt_no),
  INDEX ix_att_node_status (node_id, status),
  INDEX ix_att_status_paused (status, paused_since),
  INDEX ix_att_run (experiment_run_id)
);

CREATE TABLE node_commands (
  command_id      VARCHAR(16)  PRIMARY KEY,
  node_id         VARCHAR(64)  NOT NULL,
  attempt_id      VARCHAR(40)  NULL,
  type            VARCHAR(8)   NOT NULL,
  payload         JSON         NOT NULL,
  created_at      DATETIME(3)  NOT NULL,
  delivered_at    DATETIME(3)  NULL,
  delivery_count  INT          NOT NULL DEFAULT 0,
  acked_at        DATETIME(3)  NULL,
  ok              BOOLEAN      NULL,
  error           VARCHAR(255) NULL,
  CONSTRAINT fk_cmd_node FOREIGN KEY (node_id) REFERENCES nodes(node_id),
  INDEX ix_cmd_pending (node_id, acked_at)
);

CREATE TABLE oracle_models (
  model_id     VARCHAR(64)  PRIMARY KEY,
  path         VARCHAR(255) NOT NULL,
  variant      VARCHAR(16)  NOT NULL,
  trained_at   DATETIME(3)  NOT NULL,
  train_from   DATETIME(3)  NOT NULL,
  train_to     DATETIME(3)  NOT NULL,
  metrics      JSON         NOT NULL,
  is_active    BOOLEAN      NOT NULL DEFAULT FALSE,
  notes        TEXT
);
```
Notes:
- `jobs.current_attempt_id` and `nodes.current_attempt_id` deliberately have **no foreign key**, to avoid circular dependencies. Consistency comes from `assign_job_to_node` and the finish functions.
- Only one experiment run may be active at a time. The repository enforces this inside a transaction.
- `user_id` is `u_` + 8 hex (10 chars), `job_id` is `job_` + 10 hex (14 chars), `command_id` is `cmd_` + 12 hex (16 chars), and `study_id`/`run_id` are 14/12 chars. The column sizes above fit all of them.

## Appendix D: Usage CSV format (agent → disk → upload)
File: `~/.idlegrid/usage/YYYY-MM-DD.csv` (date = UTC). UTF-8, comma-separated, `.` decimal separator, `\n` line endings, header row, append-only. **Column order is frozen.** New columns may only be appended at the end.

| # | Column | Type | Example | Notes |
|---|---|---|---|---|
| 1 | `ts_utc` | ISO 8601 UTC with ms and `Z` | `2026-10-14T09:30:15.123Z` | Sampling time |
| 2 | `tz_offset_min` | int | `330` | Local offset from UTC (IST = 330) |
| 3 | `node_id` | str | `node-3f2a9c1b7d4e` | Stable agent ID |
| 4 | `cpu_percent` | float | `7.5` | Whole system |
| 5 | `host_cpu_percent` | float | `7.5` | Minus our job (equals col 4 when no job) |
| 6 | `ram_percent` | float | `61.2` | — |
| 7 | `user_inactivity_sec` | float or empty | `845.3` | Empty = unreadable |
| 8 | `input_method` | str | `win32_getlastinputinfo` | See §10.1.5 |
| 9 | `input_precision` | `PRECISE`/`COARSE`/`NONE` | `PRECISE` | — |
| 10 | `host_state` | `ACTIVE`/`BUSY`/`IDLE`/`UNKNOWN` | `IDLE` | Rules in §10.1.5 |
| 11 | `on_ac_power` | `1`/`0`/empty | `1` | Empty = no battery / unknown |
| 12 | `battery_percent` | float or empty | `88` | — |
| 13 | `job_running` | `1`/`0` | `0` | Always 0 in Phase 0 |
| 14 | `agent_version` | str | `0.1.0` | — |

Example:
```
ts_utc,tz_offset_min,node_id,cpu_percent,host_cpu_percent,ram_percent,user_inactivity_sec,input_method,input_precision,host_state,on_ac_power,battery_percent,job_running,agent_version
2026-10-14T09:30:15.123Z,330,node-3f2a9c1b7d4e,7.5,7.5,61.2,845.3,win32_getlastinputinfo,PRECISE,IDLE,1,88,0,0.1.0
```
`scripts/validate_usage_csv.py <file>` checks the header, types, monotonic timestamps and allowed enum values.

## Appendix E: Configuration reference
### E.1 Dispatcher (`dispatcher.toml`; env overrides in brackets)
```toml
[server]
bind_host = "0.0.0.0"            # [IDLEGRID_BIND]; reachable on LAN/Tailscale, protected by tokens
port = 8000                      # [IDLEGRID_PORT]
data_dir = "./data"              # [IDLEGRID_DATA_DIR]
max_bundle_mb = 200
max_result_mb = 500
max_timeout_sec = 21600

[database]                       # URLs come ONLY from env: IDLEGRID_DB_URL, IDLEGRID_OPTUNA_DB_URL
pool_size = 10

[scheduler]
tick_sec = 2.0
policy = "reactive_longest_idle" # "predictive" from Phase 4
heartbeat_interval_sec = 5
offline_after_sec = 15
lost_grace_sec = 60
start_timeout_sec = 60
migrate_after_sec = 300
resume_after_idle_sec = 120
command_redeliver_after_sec = 15
safe_window_sec = 1200           # q20 ≥ this → IDLE_SAFE, else IDLE_RISKY
expected_worker_env_hash = ""    # empty = don't enforce
requeue_boost_lost = 5
requeue_boost_migrated = 10

[policy.predictive]
quantile = "q20"
safety_factor = 1.1
safety_buffer_sec = 60
starvation_after_sec = 900
prefer_precise = true

[oracle]
enabled = true
model_dir = "./data/models"
refresh_sec = 30
history_days = 7

[dev]
sim_nodes = 0
sim_pattern = "office"           # office | random | replay:<path.csv>
sim_exec = "fake"                # fake | real
```

### E.2 Agent (`~/.idlegrid/agent.toml`; env `IDLEGRID_URL`, `IDLEGRID_TOKEN`)
```toml
dispatcher_url = "http://127.0.0.1:8000"   # set to the coordinator's LAN or Tailscale address
# token = "…"                               # prefer IDLEGRID_TOKEN; if stored here the file must be private (0600)
node_id = ""                                # generated on first run and written back; never edit
heartbeat_interval_sec = 5
usage_interval_sec = 15
usage_upload_interval_sec = 60
idle_threshold_sec = 120                    # must equal idlegrid.oracle.availability.IDLE_THRESHOLD_SEC
pause_if_inactivity_below_sec = 2.0
resume_after_idle_sec = 120
migrate_after_sec = 300                     # server may override
killswitch_poll_sec = 0.25
host_busy_cpu_percent = 40
host_busy_ram_percent = 92
pause_on_host_busy = true
require_ac_power = true
accepting_jobs = true
dedicated_mode = false
max_job_cores = 0                           # 0 = no limit
data_dir = "~/.idlegrid"
keep_workspaces = 5
log_level = "INFO"
```

### E.3 Client (`~/.idlegrid/client.toml`; env `IDLEGRID_URL`, `IDLEGRID_TOKEN`)
```toml
url = "http://100.101.102.103:8000"
token = "…"                 # file permissions 0600 on POSIX
default_output_dir = "./results"
```

## Appendix F: State machines
### F.1 `compute_node_status()` (pure function in `idlegrid/dispatcher/status.py`; rules applied in order)
```
1. no heartbeat within offline_after_sec                                   → OFFLINE
2. sharing.accepting_jobs == false                                         → DRAINING
3. expected_worker_env_hash set and capabilities.worker_env_hash differs   → UNSCHEDULABLE
4. node has a current attempt (ASSIGNED/RUNNING/PAUSED)                    → RUNNING_JOB
5. host_state == ACTIVE                                                    → HOST_ACTIVE
6. host_state == BUSY                                                      → HOST_BUSY
7. host_state == UNKNOWN                                                   → UNSCHEDULABLE
8. sharing.require_ac_power and power.on_ac_power is False                 → UNSCHEDULABLE
9. prediction exists and prediction.q20_sec ≥ safe_window_sec              → IDLE_SAFE
10. otherwise                                                              → IDLE_RISKY
```
(The dashboard shows a paused overlay on RUNNING_JOB nodes when the attempt is PAUSED.)

### F.2 Agent worker states
```
IDLE ──START(accepted)──▶ PREPARING (download, verify, setup_workspace)
PREPARING ──ok──▶ RUNNING            PREPARING ──error──▶ IDLE   (command_results ok=false)
RUNNING ──kill switch / PAUSE──▶ PAUSED ──resume rule / RESUME──▶ RUNNING
RUNNING|PAUSED ──process exit──▶ UPLOADING ──uploaded / 409──▶ IDLE
any ──ABORT──▶ ABORTING (cancel tree, release power) ──▶ IDLE
PAUSED ──offline fail-safe (> migrate_after_sec + 60)──▶ ABORTING
```

### F.3 Job and attempt transitions (Dispatcher)
| Event | Attempt | Job |
|---|---|---|
| Submit | — | → QUEUED |
| Policy assigns (transaction) | create ASSIGNED | QUEUED → ASSIGNED |
| Heartbeat reports RUNNING | ASSIGNED/PAUSED → RUNNING | → RUNNING |
| Heartbeat reports PAUSED | RUNNING → PAUSED (`paused_since`) | → PAUSED |
| Result COMPLETED / FAILED / TIMED_OUT | → same | → same (terminal) |
| Paused > `migrate_after_sec` | → MIGRATED | → QUEUED (+10 priority) |
| Node offline > `lost_grace_sec` | → LOST | → QUEUED (+5) |
| START not confirmed within `start_timeout_sec` | → LOST (`start_timeout`) | → QUEUED (+5) |
| User cancels | → CANCELLED (ABORT sent) | → CANCELLED |
| Stale attempt reports in / uploads | unchanged; ABORT sent / HTTP 409 | unchanged |

### F.4 Predictive policy (pseudocode)
```
free = [n for n in nodes]; plan = []
for job in sorted(jobs, key=(-priority, queued_at)):
    cands = [n for n in free if n.ram_available_mb - 1024 >= job.ram_required_mb]
    if prefer_precise and any(n.input_precision == "PRECISE" for n in cands):
        cands = [n for n in cands if n.input_precision == "PRECISE"]
    if not cands: continue
    def window(n): p = predictions.get(n.node_id); return getattr(p, quantile + "_sec") if p and p.method != "none" else n.elapsed_idle_sec
    def required(n): return job.est_runtime_sec / max(n.perf_score, 0.1) * safety_factor + safety_buffer_sec
    fits = [n for n in cands if window(n) >= required(n)]
    if fits:   chosen = min(fits, key=lambda n: (window(n) - required(n), -n.perf_score))
    elif now - job.queued_at > starvation_after_sec:
               chosen = max(cands, key=lambda n: q50(n) / required(n))
    else:      continue                          # leave queued; backfill smaller jobs
    plan.append(Assignment(job.job_id, chosen.node_id, required(chosen), q20(chosen), q50(chosen)))
    free.remove(chosen)
return plan
```

## Appendix G: CI and PR template
### G.1 `.github/workflows/ci.yml`
```yaml
name: ci
on: [push, pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install ruff
      - run: ruff check . && ruff format --check .

  unit:
    strategy:
      fail-fast: false
      matrix: { os: [ubuntu-latest, windows-latest, macos-latest] }
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12", cache: pip }
      - run: pip install -r requirements/worker-env.txt -e ".[agent,ml,dev]"
      - run: pytest tests/unit -m "not mysql" -q --cov=idlegrid --cov-report=term-missing

  integration:
    runs-on: ubuntu-latest
    services:
      mysql:
        image: mysql:8.0
        env: { MYSQL_ROOT_PASSWORD: root, MYSQL_DATABASE: idlegrid_test }
        ports: ["3306:3306"]
        options: >-
          --health-cmd="mysqladmin ping -proot" --health-interval=5s --health-timeout=5s --health-retries=20
    env:
      IDLEGRID_DB_URL: mysql+pymysql://root:root@127.0.0.1:3306/idlegrid_test
      IDLEGRID_OPTUNA_DB_URL: mysql+pymysql://root:root@127.0.0.1:3306/idlegrid_optuna_test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12", cache: pip }
      - run: mysql -h 127.0.0.1 -uroot -proot -e "CREATE DATABASE IF NOT EXISTS idlegrid_optuna_test"
      - run: pip install -r requirements/worker-env.txt -r requirements/dispatcher.txt -e ".[agent,dispatcher,ml,dev]"
      - run: python -m idlegrid.db.migrate
      - run: pytest tests/unit -m mysql -q && pytest tests/integration -q

  ui-smoke:
    runs-on: ubuntu-latest
    needs: integration
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12", cache: pip }
      - run: pip install -r requirements/worker-env.txt -r requirements/dispatcher.txt -e ".[agent,dispatcher,dev]" playwright
      - run: python -m playwright install --with-deps chromium
      - run: pytest tests/e2e/test_dashboard_smoke.py -q   # starts Dispatcher with an in-memory test DB fixture + --sim-nodes 3

  secrets:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: gitleaks/gitleaks-action@v2
        env: { GITHUB_TOKEN: "${{ secrets.GITHUB_TOKEN }}" }
```
> The `ui-smoke` job needs a database. Either reuse a MySQL service as in `integration`, or skip it until Phase 3. Decide in H-P0-3.

### G.2 `.github/pull_request_template.md`
```markdown
## Task ID(s)
<!-- e.g. A-P1-2 -->

## What & why

## How it was tested
- [ ] Unit tests  - [ ] Integration tests  - [ ] Real laptops (OS: ___ )

## Contract impact
- [ ] None  - [ ] Additive (minor bump)  - [ ] Breaking (major bump, 2 approvals incl. Harith)

## Screenshots (UI changes)

## Checklist
- [ ] Docs/runbook updated  - [ ] No secrets committed  - [ ] I can explain every line of this PR
```

### G.3 `pyproject.toml` (sketch)
```toml
[project]
name = "idlegrid"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = ["pydantic>=2.6,<3", "psutil>=5.9", "requests>=2.31", "rich>=13.7"]

[project.optional-dependencies]
agent      = []                                            # worker-env.txt supplies job libraries
dispatcher = ["fastapi>=0.110", "uvicorn[standard]>=0.29", "sqlalchemy>=2.0", "pymysql>=1.1",
              "python-multipart>=0.0.9", "optuna>=4.0,<6"]
ml         = ["pandas>=2.2", "numpy>=1.26", "scikit-learn>=1.4", "scipy>=1.12", "joblib>=1.3", "pyarrow>=15"]
dev        = ["pytest>=8", "pytest-cov", "ruff", "httpx", "responses", "respx"]

[project.scripts]
gridctl             = "idlegrid.cli.gridctl:cli_main"
idlegrid-agent      = "idlegrid.agent.__main__:main"
idlegrid-dispatcher = "idlegrid.dispatcher.__main__:main"

[tool.ruff]
line-length = 110
target-version = "py312"

[tool.pytest.ini_options]
markers = ["mysql: needs a MySQL server (IDLEGRID_DB_URL)"]
```
`requirements/worker-env.txt` pins **exact** versions (`==`) of `numpy`, `pandas`, `scikit-learn`, `scipy`, `joblib`, `optuna`, `psutil`, `requests` and `pydantic`. Record the versions actually installed in Phase 0 (for example, Optuna 5.x was current in October 2026). `worker_env_hash` = the first 16 hex characters of SHA-256 of the sorted, normalised pinned lines. The agent computes it from `importlib.metadata` versions of those packages.

---
*End of PRD v1.0. Changes are tracked through the contract-change process (§15.4) and recorded in a changelog at the top of `docs/PRD.md`.*
