# Predictive Idle-Compute Scheduler: Project Overview & Scope Review

> **Sources reviewed:** `Project_Idea_Initial.md`, `Project_Outline_and_Division.md`, `Ronit_Work/README.md`, and every member folder's code (`Arya_Work/`, `Amaan_Work/`, `Rejish_Work/`, `Ronit_Work/`).
> **Repo state reviewed:** branch `claude/nifty-ramanujan-mtwgp7` (commit `e1e5d59`), October 2026.

This document has two parts:

- **Part 1** is a plain-language explanation for anyone, with no programming background needed.
- **Part 2** is the technical explanation: architecture, who owns what, what exists in the code, the gaps, and a scope and feasibility assessment.

---

# Part 1: Plain-Language Explanation

## What is this project?

Think about the laptops owned by a group of five students. For most of the day, each one is doing very little. It sits closed in a bag, idles during a lecture, or stays switched on overnight. Meanwhile, the same students are often stuck waiting for slow programs to finish, especially machine learning programs that need a lot of computing power. Free services like Google Colab cut them off after a while.

This project builds a system that **borrows the spare computing power of idle laptops** and uses it to run other people's heavy programs, **without getting in the owner's way**.

A good comparison is a shared kitchen. If your oven is busy, you look around for a neighbour's oven that nobody is using, put your dish in it, and take it out when it's done. The rule is that the moment the neighbour comes home and wants their oven back, your dish has to come out immediately.

## How will it work, step by step?

1. **Every laptop runs a small background watcher.** It checks how hard the laptop is working and whether anyone has touched the mouse or keyboard recently. Every few seconds it reports "I'm idle" or "I'm busy" to a central coordinator.
2. **A central coordinator keeps track of everyone.** It knows which laptops are free right now.
3. **A user submits a job.** For example, typing `submit my_training_script.py`.
4. **The coordinator picks a free laptop** and sends the program there.
5. **The borrowed laptop runs the program** in the background and sends the results (files, logs) back to the person who asked.
6. **If the owner comes back,** the job is frozen instantly so the owner's laptop doesn't slow down. It can be resumed later or moved to another laptop.

## What makes it "smart"? (The prediction part)

A simple version would just grab any laptop that looks idle at this moment. The problem is that someone might sit down at that laptop 30 seconds later, and the job gets interrupted and wasted.

The **smart version** learns from history. If Laptop A is usually untouched every Tuesday from 2pm to 4pm because its owner is in a lecture, then at 2:05pm on a Tuesday the system can predict that Laptop A will probably stay free for about two hours. It then sends long jobs to laptops expected to stay free for a long time, and short jobs to laptops that might be needed again soon.

The main question the project wants to answer is: **does predicting idle time lead to fewer interrupted, wasted jobs than just grabbing whatever is free right now?**

## Who does what?

| Person | Nickname | Plain-language job |
|---|---|---|
| **Arya** | The Spy | Builds the background watcher on each laptop that reports "idle" or "busy," and the emergency stop when the owner returns. |
| **Harith** | The Traffic Cop | Builds the central coordinator that receives reports and decides which laptop gets which job. |
| **Amaan** | The Record Keeper | Builds the database that remembers which laptops exist, which jobs are waiting or running, and the history of when each laptop was idle. |
| **Rejish** | The Fortune Teller | Builds the prediction model that guesses how long each laptop will stay free. |
| **Ronit** | The Delivery Driver | Builds the tool people use to submit jobs, plus the code that packages a program, runs it on the borrowed laptop, and brings back the results. Also built a web dashboard. |

## Is it doable?

**Yes, with an important caveat.** Each individual piece is a normal, well-understood programming task, and four of the five pieces already have working code. The hard part isn't any single piece. It's **making the five pieces talk to each other**, because each person built theirs separately and they don't yet fit together. The coordinator, which is the piece that connects everything, hasn't been built yet.

## Is it too complex?

**No, provided the team sticks to the "10-day MVP" in the charter** and doesn't try to build everything in the original idea document at once. The MVP needs a working end-to-end demo plus a prediction notebook, and that's a reasonable target. The bigger goals (week-long real usage data collection, fair comparison experiments, distributed hyperparameter tuning) belong after the MVP.

## Does it matter in the real world?

**Yes. The problem is real, and real systems already address it.** Universities, scientific projects (like Folding@home, which used idle home computers to study proteins), and cloud companies have used idle computers for decades. That's good news: it shows the problem is genuine and the approach works. It also means the team isn't inventing the basic idea. The team's own contribution is the **prediction** layer, and testing whether it actually beats the simple approach on real student laptops. That is a fair, measurable question, and it's a good fit for a student project.

## Where do things stand today?

- ✅ The laptop watcher exists (Arya).
- ✅ A basic database exists (Amaan).
- ✅ A prediction model exists, but it's trained on **made-up data**, not real usage (Rejish).
- ✅ The job tool, executor and a polished dashboard exist (Ronit). The dashboard currently shows **pretend laptops** and runs all jobs on the same computer.
- ❌ The central coordinator that connects everything **doesn't exist yet** (Harith).
- ❌ Nobody has written the code that **receives a job on a borrowed laptop and runs it there**.
- ❌ No real laptop usage history is being recorded yet, so there's nothing real to train the model on.

---

# Part 2: Technical Explanation

## 1. Goals and success criteria

The two planning documents describe two different scopes, and they need to be kept apart.

| | **Charter MVP** (`Project_Outline_and_Division.md`) | **Full vision** (`Project_Idea_Initial.md`) |
|---|---|---|
| Timeline | 10 days | Several months ("remaining months") |
| Workload | Dummy payload ("a heavy math script") | Distributed hyperparameter search with Optuna, or dataset preprocessing |
| Routing | Detect an idle laptop, send, execute, return the result | Chunk sizing based on predicted idle window, plus preemption and reassignment |
| ML | Jupyter notebook PoC: a scikit-learn model that predicts idle duration from time of day and day of week, trained on the team's actual usage data | Per-machine idle-duration model inside the scheduling loop |
| Evaluation | Live demo | Three-way experiment (single machine vs. reactive vs. predictive), measuring completion time, preemptions and wasted compute |
| Data | "Run the Node Agent for a few days" | "A few weeks of real usage logs" |

**Recommendation:** treat the Charter MVP as the actual deliverable, and treat the full vision as a stretch goal or a follow-on phase. The three-way experiment is the thing that turns this into a defensible ML systems project, so it should be the first item after the MVP.

## 2. Target architecture

```
                         ┌───────────────────────────┐
  user ── gridctl ──────▶│  Dispatcher (Role 2)      │◀──── heartbeats ────┐
   (Role 5 CLI/UI)       │  FastAPI / Flask          │                     │
                         │   • node registry         │                     │
                         │   • job queue             │      ┌──────────────┴─────────┐
                         │   • scheduling policy ────┼──┐   │  Node Agent (Role 1)   │
                         └───┬───────────────────┬───┘  │   │  psutil + input idle   │
                             │ SQL               │      │   │  kill switch           │
                             ▼                   │      │   ├────────────────────────┤
                    ┌─────────────────┐          │      │   │  Worker / Executor     │
                    │ MySQL (Role 3)  │          │      └──▶│  (Role 5 runner)       │
                    │ nodes, jobs,    │          │  job     │  unzip → run → zip     │
                    │ idle history    │          │  bundle  │  results back          │
                    └────────┬────────┘          │          └────────────────────────┘
                             │ history           │ predict_idle_minutes()
                             ▼                   │
                    ┌─────────────────┐          │
                    │ ML Oracle       │◀─────────┘
                    │ (Role 4)        │
                    │ RandomForest    │
                    └─────────────────┘
```

**Data flow:**
1. The agent sends `POST /api/v1/heartbeat` every 5 s.
2. The Dispatcher upserts the node in MySQL and appends an idle/busy history row.
3. `gridctl submit` sends `POST /api/jobs/submit` with a zip bundle.
4. The Dispatcher asks the Oracle about each idle candidate, picks a node and pushes the bundle to that node's worker.
5. The worker runs the job and streams logs and status back.
6. When the agent detects the user, it tells the worker to suspend the job and tells the Dispatcher the node is `USER_ACTIVE`.
7. The finished `result_bundle.zip` goes back to the Dispatcher and on to the user.

## 3. Components: responsibility vs. what exists

### Role 1: Node Agent (Arya), `Arya_Work/`

| Charter says | Code has | Status |
|---|---|---|
| CPU/RAM monitoring with `psutil` | `metrics_collector.py` collects CPU %, RAM %, hostname and OS | ✅ |
| Mouse/keyboard presence via `pynput` | Uses Windows `GetLastInputInfo` through `ctypes`. **On macOS/Linux it always returns 0 s**, and the `USER_ACTIVE` check is skipped. `pynput` isn't used. | ⚠️ Windows-only |
| Report to Dispatcher | `heartbeat_sender.py` POSTs JSON to `http://localhost:5000/api/v1/heartbeat` | ✅ (but the endpoint doesn't exist yet) |
| Kill switch | Not implemented in the agent. Suspend/resume exists in Ronit's executor, but nothing connects agent state changes to it. | ❌ |
| Usage logs for ML | No local CSV logging. History only exists if the Dispatcher stores it. | ❌ |

States emitted: `IDLE`, `BUSY` (CPU > 20% or RAM > 80%), `USER_ACTIVE` (input within the last 180 s, Windows only). Tests: `tests/test_config.py`, `test_heartbeat.py`, `test_metrics.py`.

### Role 2: Dispatcher (Harith), not yet in repo

Nothing has been committed. This is the **integration hub**, so it's the critical path for the MVP. It must:
- Serve `POST /api/v1/heartbeat` (Arya's payload) and the job API that Ronit's CLI already calls (`/api/jobs/submit`, `/api/jobs/{id}`, `/logs`, `/download`, `/api/cluster/nodes`, and so on).
- Persist state through Amaan's functions.
- Call `MLOracle.evaluate_node_suitability()` to choose nodes.
- Detect stale nodes (no heartbeat within N × interval means `OFFLINE`) and requeue their jobs.

**Overlap to resolve:** `Ronit_Work/src/dashboard/mock_cluster.py` already contains a `ClusterOrchestrator` with node selection (`_select_best_node`) and a job lifecycle. That's essentially a Dispatcher. The team should decide whether Harith's Dispatcher **replaces** it or Ronit's dashboard becomes a **client** of Harith's Dispatcher. The second option is cleaner and matches the charter.

### Role 3: State Manager (Amaan), `Amaan_Work/`

| Charter says | Code has | Status |
|---|---|---|
| Online laptops and load | `nodes(ip_address PK, current_status, cpu_usage, last_heartbeat)` | ✅ minimal |
| Job queue | `jobs(job_id, assigned_to_ip, status, created_at)` | ✅ minimal (no script path, owner, runtime estimate, result location or timestamps per state) |
| **Historical idle/busy logs** | Not present | ❌ (and this is what the ML Oracle needs) |
| Python connector | `db_functions.py`: `update_node`, `get_available_node` (`LIMIT 1`, no ordering), `assign_job` | ✅ |

Issues:
- The database password is hard-coded in `db_functions.py`. It should move to an environment variable or config file that isn't committed.
- `get_connection()` returns `None` on failure, and the callers silently do nothing.
- Nodes are keyed by IP address, but the agent identifies itself by `node_id`. IPs change on DHCP Wi-Fi, so `node_id` is the better key.

### Role 4: ML Oracle (Rejish), `Rejish_Work/`

| File | Purpose |
|---|---|
| `generate_dataset.py` | Generates 5,000 **synthetic** rows at 5-min spacing with hour-of-day behaviour bands (sleep, class, evening use) |
| `train_oracle.py` | Feature engineering (cyclical hour, day of week, weekend flag, CPU, RAM, input counts, charging) followed by `RandomForestRegressor(n_estimators=100, max_depth=12)`. Reports MAE, R² and feature importances, and saves `oracle_rf_model.joblib`. |
| `ml_oracle.py` | `MLOracle.predict_idle_minutes(node_stats)` and `evaluate_node_suitability(node_stats, required_job_minutes, safety_buffer=2.0)`. If no model file exists, it falls back to a fixed rule. |

Technical concerns (more detail in §7):
- Trained on synthetic data, so the reported R² measures how well the model recovers the generator's own rules, not real behaviour.
- The input features (`mouse_events_last_min`, `key_events_last_min`, `battery_charging`, `cpu_pct`, `ram_pct`) **don't match** what the agent sends (`cpu_usage_percent`, `ram_usage_percent`, `user_inactivity_sec`).
- The model artifact isn't committed, so you have to run generate and then train first.

### Role 5: Executor & UI (Ronit), `Ronit_Work/`

The most complete component, at about 2,200 lines.

| Module | What it does |
|---|---|
| `src/packager/bundle.py` | Zips the entrypoint, data and requirements with a `manifest.json`. Safely extracts the bundle and harvests `output/` into `result_bundle.zip`. |
| `src/executor/process_controller.py` | `subprocess.Popen` in the job workspace with live stdout/stderr threads and CPU/RAM sampling. **Suspend/resume of the whole process tree** via `psutil`, plus terminate. |
| `src/executor/runner.py` | `JobRunner`: sets up the workspace, runs the job sync or async, and handles pause, resume, cancel and results. |
| `src/cli/gridctl.py`, `gridctl.py` | `submit`, `status`, `logs --follow`, `cluster`, `download`, `demo-run` using `rich`. Talks HTTP to `localhost:8000`. |
| `src/dashboard/` | FastAPI and WebSocket dashboard (HTML/JS/CSS) with job submission and a "simulate host active" button |
| `src/dashboard/mock_cluster.py` | **Four hard-coded fake nodes** with fake telemetry and fake "predicted idle" values. Every job actually runs **on the local machine** through `JobRunner`. |
| `demo_jobs/` | Monte Carlo π, a 1500×1500 matrix benchmark, and a scikit-learn random forest training job |
| `tests/` | Bundle, executor and API tests |

So the executor works, but **there's no remote worker process**: nothing on the target laptop listens for a job bundle, runs `JobRunner` and uploads results. The charter assigns "unzips it on the target idle machine" to Role 5, but there's no agreement yet on whether this lives inside Arya's agent or in a separate worker daemon.

## 4. Interface contracts: current mismatches

These need to be fixed in a shared spec (for example a `contracts.md` file or shared Pydantic models) **before** integration.

| Concern | Agent (Arya) | DB (Amaan) | Oracle (Rejish) | Executor/UI (Ronit) |
|---|---|---|---|---|
| Node identity | `node_id` (hostname-derived) | `ip_address` | n/a | `node_id` + `ip_address` |
| Node states | `IDLE`, `BUSY`, `USER_ACTIVE` | `IDLE`, `BUSY`, `OFFLINE` | n/a | `IDLE_SAFE`, `IDLE_RISKY`, `BUSY`, `HOST_ACTIVE`, … |
| CPU field | `cpu_usage_percent` | `cpu_usage` | `cpu_pct` | `cpu_percent` |
| RAM field | `ram_usage_percent` | not stored | `ram_pct` | `ram_percent` |
| User activity | `user_inactivity_sec` (seconds since last input) | not stored | `mouse_events_last_min`, `key_events_last_min` (counts) | `is_user_active`, `idle_time_seconds` |
| Job states | n/a | `PENDING`, `RUNNING`, `COMPLETED` | n/a | `JobStatus` enum (includes paused, failed, cancelled) |
| Dispatcher port | `:5000` | n/a | n/a | `:8000` |
| Idle prediction unit | n/a | n/a | minutes | seconds |

**Recommendation:** adopt Ronit's `src/common/models.py` (Pydantic) as the canonical schema, since it's the richest, and have every other component import or mirror it.

## 5. Scope analysis

### In scope for the 10-day MVP (realistic)
- Agent → Dispatcher heartbeats, with nodes and state persisted in MySQL.
- `gridctl submit` → Dispatcher → **one real remote laptop** → result returned.
- Kill switch: the agent detects user input and the job is suspended on that laptop.
- Oracle notebook: a model trained on whatever real data has been logged, compared against the synthetic baseline.

### Out of scope for the MVP (defer)
- Optuna distributed hyperparameter search.
- Chunking work to fit predicted windows.
- Migrating or reassigning a preempted job to another node with checkpointing (suspend/resume on the same node is enough for the MVP).
- The full three-way experiment.
- Security sandboxing beyond "trusted teammates only."
- GPU scheduling.

### Scope risk
The initial idea document mixes MVP and multi-month goals. The biggest single risk is **data collection lead time**. The charter wants the model trained on "the team's actual usage data," but no component is currently recording usage history. Every day without logging is a day of training data lost. **Logging should start immediately**, even before the Dispatcher exists, by having the agent append to a local CSV.

## 6. Feasibility by component

| Component | Inherent difficulty | Current progress | Risk to MVP |
|---|---|---|---|
| Node Agent | Low | ~80% (Windows only, no kill switch, no logging) | Medium: cross-platform input detection |
| Dispatcher | Moderate | 0% | **High: critical path, blocks integration** |
| State Manager | Low | ~50% (no history table, no node_id key) | Low |
| ML Oracle | Moderate (features and data, not algorithm) | ~60% code, 0% real data | **High: needs real data now** |
| Executor & UI | Moderate | ~85% locally, 0% remote worker | Medium: remote delivery not built |
| Integration | Moderate | 0% | **High: incompatible contracts** |

**Verdict: doable.** No piece needs exotic technology. The stack (Python, FastAPI, psutil, MySQL, scikit-learn) is mainstream and well documented. The risk is coordination, not technical difficulty.

## 7. Complexity hot spots

1. **Preemption semantics.** `psutil.suspend()` freezes the process but **keeps its RAM allocated**, so the owner still loses memory. A real kill switch needs a policy: suspend for short interruptions, kill and requeue for long ones. Reassigning a job to another node needs either restarting from scratch (acceptable for short jobs) or application-level checkpointing (out of MVP scope).
2. **Liveness and timeouts.** Laptops sleep, close their lids and change networks. The Dispatcher needs a heartbeat timeout (for example 3 × 5 s = 15 s) to mark a node `OFFLINE`, and must handle a job whose node disappeared.
3. **Concurrency in the Dispatcher.** Several agents and CLI clients hit it at once. FastAPI with a DB connection per request handles this fine at 5-node scale, but job assignment must be atomic, so two jobs can't be given to the same node. A MySQL transaction or `SELECT … FOR UPDATE` is enough.
4. **Cross-platform input detection.** The team's laptops likely run a mix of Windows, macOS and Linux. `pynput` (as the charter suggests) works everywhere but needs Accessibility permission on macOS. On Linux it depends on X11 or Wayland.
5. **Networking on campus Wi-Fi.** Many university and eduroam networks use **client isolation**, which stops laptops from connecting to each other directly. Test this on day 1. Fallbacks are a phone hotspot, a shared LAN, or making workers *pull* jobs from the Dispatcher (outbound-only connections) instead of the Dispatcher *pushing* jobs to them. **Pull is strongly recommended**: it avoids firewall and NAT issues and simplifies the design.
6. **Dependencies on the remote side.** A job's `requirements.txt` has to be installed on someone else's laptop. For the MVP, limit jobs to a pre-agreed environment (for example numpy, pandas and scikit-learn preinstalled everywhere).

### ML-specific concerns
- **Synthetic-data leakage.** In `generate_dataset.py`, CPU, RAM and input counts are generated *from* the target (`is_idle and idle_duration > 5`). The model can read the answer straight from those features, so R² will look excellent and say nothing about real behaviour. Use synthetic data only to test the pipeline, and **report metrics on real data only**.
- **Target definition.** Each synthetic row draws an independent idle duration, with no continuity between consecutive 5-minute rows. In real logs, the target should be *remaining* idle time from a point in an actual idle period. Building that means grouping the history into sessions (idle start to idle end).
- **The most predictive real feature is missing:** *how long the machine has already been idle*. This is classic survival-analysis territory. Add `current_idle_elapsed_min` as a feature.
- **Framing.** The scheduler really asks "will it stay idle for at least the job length plus a buffer?" That is a **classification** or quantile problem, and the charter itself mentions logistic regression and decision trees. A conservative quantile (for example the 20th percentile of predicted idle time) costs fewer preemptions than a mean prediction. Worth comparing both.
- **Data volume.** 5 laptops × a few days gives perhaps a few dozen to a few hundred idle sessions. Per-machine models will be thin, so start with one shared model that includes `node_id` as a feature.
- **Minor bug:** the synthetic timestamps start 7 days ago but cover about 17 days (5,000 × 5 min), so about 10 days of rows are dated in the future.

## 8. Real-world significance and prior art

**The problem is real.** Personal machines spend most of their powered-on time underused. That's why idle-cycle harvesting has a long history:

- **HTCondor** (University of Wisconsin–Madison, since the late 1980s) does exactly this for workstations: it runs jobs on idle desktops and evicts them when the owner returns. It's still widely used in research computing.
- **Volunteer computing** (BOINC, SETI@home, Folding@home) harvests idle home PCs on a global scale.
- **Cloud spot and preemptible instances** (AWS Spot, Google Cloud preemptible VMs) have the same core problem of capacity that can be reclaimed at any moment, and schedulers there also try to anticipate interruptions.
- Academic work on **availability prediction in desktop grids** studies the same question this project asks.

**What this means for the project:**
- The basic premise is validated by industry and academia, which is a strong signal.
- The project won't compete with these systems as a product, and it doesn't need to. Its value is (a) as a hands-on distributed systems and ML learning vehicle, and (b) as a **small empirical study**: does a learned idle predictor reduce wasted work versus reactive scheduling on real student laptops? That claim can be measured and stands on its own.
- When writing the report, **cite HTCondor and BOINC as prior art** and position the prediction layer as the contribution. Reviewers will know these systems.
- A limitation to acknowledge: students hitting Colab limits usually need **GPUs**, while this system shares mainly **CPU**. CPU-bound work (classical ML, scikit-learn, data preprocessing, hyperparameter search on small models) is a legitimate fit, and that's the right workload to target.

## 9. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Dispatcher not built in time | Medium | Blocks the demo | Start with Ronit's `ClusterOrchestrator` logic as a reference. Build heartbeat and submit endpoints first. |
| Campus Wi-Fi blocks laptop-to-laptop traffic | High | Blocks the live demo | Use a pull-based worker. Test on day 1. Keep a phone hotspot as backup. |
| No real usage data | High (nothing is logging yet) | ML PoC must rely on synthetic data | Add CSV logging to the agent **today** and run it on all 5 laptops continuously. |
| Contract mismatches surface late | High | Integration slips | Freeze a shared schema (`src/common/models.py`) before writing more code. |
| Kill switch only works on Windows | Medium | Demo fails on Mac/Linux | Use `pynput`, or run the demo on Windows laptops. |
| Running teammates' code is a security risk | Low within the team | High in general | State "trusted users only" as an explicit assumption. Mention containers as future work. |
| Battery drain on borrowed laptops | Medium | Owner annoyance | Only accept jobs when the laptop is charging (`psutil.sensors_battery()`). |

## 10. Recommended next steps (in order)

1. **Today:** add local CSV logging to the agent (timestamp, CPU, RAM, inactivity seconds, charging, state) and run it on all five laptops.
2. **Agree the contracts:** one schema for node identity (`node_id`), states, field names, units and endpoints.
3. **Dispatcher skeleton (Harith):** `POST /api/v1/heartbeat`, `GET /api/cluster/nodes`, `POST /api/jobs/submit`, `GET /api/jobs/{id}`, plus a heartbeat timeout. Persist through Amaan's DB.
4. **DB additions (Amaan):** key `nodes` on `node_id`, add a `node_history` table, add job fields (owner, entrypoint, estimated runtime, assigned node, timestamps, result path), and move credentials out of the code.
5. **Remote worker (Ronit + Arya):** a small loop on each laptop that polls the Dispatcher for assigned jobs, runs `JobRunner`, uploads `result_bundle.zip`, and suspends the job when the agent reports user activity.
6. **Make the dashboard real:** point Ronit's dashboard and CLI at the Dispatcher instead of `mock_cluster.py`.
7. **Oracle on real data (Rejish):** sessionise the logs, add an elapsed-idle feature, compare a regressor with a classifier or quantile model, and plug it into the Dispatcher's node selection.
8. **Stretch:** a simulated three-way comparison (single machine vs. reactive vs. predictive) replaying the recorded idle traces, then Optuna as the real workload.

---

## Appendix: repository map

```
Project_Idea_Initial.md          Original brainstorm and full vision
Project_Outline_and_Division.md  Charter: 10-day MVP and role assignments
Arya_Work/                       Role 1: Node Agent (psutil, heartbeats, tests)
Amaan_Work/                      Role 3: MySQL schema and db_functions.py
Rejish_Work/                     Role 4: synthetic data generator, RF training, MLOracle
Ronit_Work/                      Role 5: packager, executor (suspend/resume), gridctl CLI,
                                 FastAPI dashboard (mock cluster), demo jobs, tests
(Dispatcher: Role 2, Harith)     Not yet committed
```
