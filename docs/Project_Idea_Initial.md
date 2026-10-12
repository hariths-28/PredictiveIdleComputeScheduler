IDP PROJECT IDEAS

https\://share.gemini.google/UfliGgGeSUO7

# **Predictive Idle-Compute Scheduler for Distributed ML Workloads**

## **The core idea**

A coordinator watches all 5 laptops. Instead of reactively grabbing whichever machine looks idle *right now*, it uses a model trained on each machine's historical usage patterns to predict **how long a machine will likely stay idle** before someone sits back down and starts using it. It assigns task chunks sized to fit that predicted window, and — critically — the actual work being distributed is a real ML task: **distributed hyperparameter search** (training the same model with many different hyperparameter combinations in parallel across idle machines) or **distributed dataset preprocessing** for a training pipeline. That choice matters: it makes the demo "we sped up an actual ML workload using harvested idle compute," not an abstract systems exercise with no ML in the room.

## **Where ML integration actually happens — two distinct layers**

**Layer 1 — Predicting idle-window duration (the scheduling brain)** Each laptop's monitoring agent logs its own usage history: when it goes idle, how long that idle period lasts, time-of-day patterns, day-of-week patterns. You train a simple time-series/regression model (start with basic regression on time-of-day \+ rolling recent-activity features; Prophet or a small LSTM if you want to go further) per machine, predicting "given it's currently idle and it's 3pm on a Tuesday, how much idle time is left, probably." The scheduler uses this prediction to decide task chunk size and which machine to assign to, instead of just "it's idle now, send it work and hope."

**Layer 2 — The actual harvested workload is itself ML** The idle machines aren't just running arbitrary compute — they're running real hyperparameter search trials (using something like Optuna, distributed across workers) or batch preprocessing a real dataset. This gives you a genuine "before/after" story: hyperparameter search that takes N hours on one machine takes a fraction of that time across your harvested idle fleet — a real, measurable, demoable speedup on a real ML task.

## **How I'd build it**

**Architecture**

* **Agent** (runs on all 5 laptops): a lightweight Python process using `psutil` to monitor CPU/RAM/battery usage, reporting status to the coordinator every few seconds, and executing assigned task chunks when told to  
* **Coordinator** (runs on one machine, or a small server): maintains the list of machines and their current state (busy/idle/predicted-idle-duration), holds the task queue, assigns chunks, collects results, handles reassignment if a machine gets preempted mid-task  
* **Prediction service**: a small model (can literally run inside the coordinator process for this scale) that takes each machine's logged history and outputs a predicted idle-window estimate, feeding the scheduler's assignment decisions  
* **Communication layer**: REST API (Flask/FastAPI) is genuinely sufficient at 5-machine scale — you don't need gRPC's complexity for this  
* **Task queue/state**: Celery \+ Redis if you want a proper job queue, or just a simple database-backed queue (SQLite table of pending/running/done tasks) if you want to keep the stack lighter  
* **Example workload**: Optuna for distributed hyperparameter search (it has native support for parallel trials across workers) — this is a real, well-documented tool, so you're not building the ML orchestration from scratch, just the *scheduling layer* around it, which is your actual contribution

## **How I'd test it**

**Component-level first**

1. Single agent reporting resource stats correctly to the coordinator — just prove the monitoring pipeline works  
2. Manually simulate busy/idle transitions (run a CPU-stress script, then kill it) and confirm the coordinator correctly detects the state change

**Scheduling logic** 3\. Assign a dummy long-running task, then trigger a simulated "user returns" event mid-task, and confirm the coordinator detects the preemption and reassigns the remaining work to another idle machine without losing progress incorrectly

**The actual ML comparison — this is your real experiment** 4\. Collect a few weeks of real usage logs from your own team's laptops (this is your training data for the idle-prediction model — genuinely your own data, no permission issues) 5\. Run the same hyperparameter search workload three ways and compare: (a) single machine baseline, (b) your reactive/naive version (grab whatever's idle right now, no prediction), (c) your predictive version — measure total completion time, number of tasks that got preempted/reassigned, and total wasted compute (work redone due to a bad assignment) 6\. This comparison — naive reactive scheduling vs. your learned predictive scheduling — is the actual finding for your report: does prediction meaningfully reduce wasted/reassigned work compared to reacting blindly? That's a real, measurable claim, not just "it works."

## **Difficulty and realistic scope**

Base distributed scheduling (no ML): moderate, genuinely achievable early in your timeline. The prediction layer and the naive-vs-predictive comparison experiment is where your remaining months should go — that comparison is what turns this from "we built a task distributor" into a legitimate, defensible AI/ML systems project.

Not particularly difficult overall — it's a genuinely good fit for your time budget, mainly because you're building the scheduling/prediction layer on top of existing tools rather than everything from raw scratch. Here's the honest breakdown.

## **Difficulty by component**

**Easy-to-moderate parts**

* Resource monitoring (`psutil` reading CPU/RAM/idle time) — a few lines of code, well-documented  
* Basic REST API communication between agent and coordinator (Flask/FastAPI) — standard, plenty of tutorials  
* Running Optuna for distributed hyperparameter search — it has built-in support for exactly this, you're integrating an existing tool, not building distributed ML orchestration yourself

**Moderate — where real effort goes**

* Coordinator logic: tracking machine states, assigning task chunks, deciding chunk size — this is genuine design work, but it's conventional software engineering, nothing exotic  
* The idle-duration prediction model — a regression/time-series model on your own logged usage data; moderate because you need to think carefully about features (time of day, day of week, recent activity trend), not because the modeling technique itself is hard  
* Preemption handling: detecting a machine got reclaimed mid-task and reassigning work without corrupting results — this is the trickiest *logic* to get right, though not conceptually hard, just easy to get subtly wrong

**What you're explicitly NOT building from scratch (keeps difficulty down)**

* No custom networking protocol, no custom job queue engine, no custom ML training framework — you're wiring together existing, well-documented libraries (Optuna, Flask, psutil, scikit-learn) around your own coordination and prediction logic, which is the actually original part

## **Concepts you'll need**

**Distributed systems**

* Client-server architecture — one coordinator, multiple agents  
* Task partitioning — splitting a hyperparameter search into independent trials that can run in parallel with no dependency between them (this task type is "embarrassingly parallel," which is exactly why it's a good fit — you're not fighting dependency management)  
* State tracking across machines — knowing at any moment which machine is doing what  
* Fault tolerance / reassignment — handling a worker disappearing or getting reclaimed mid-task

**Networking (direct course tie-in)**

* REST API request/response basics  
* Polling vs. push for status updates (agents periodically reporting in vs. the coordinator asking) — worth deciding deliberately and explaining why in your report  
* Timeout handling — deciding how long to wait before declaring a machine "gone" and reassigning its work

**Machine learning**

* Regression / time-series forecasting — predicting a continuous value (idle-window duration) from historical patterns, a genuinely approachable ML task (not classification, not deep learning required)  
* Feature engineering on time-based data — time of day, day of week, recent activity trend as inputs  
* Basic hyperparameter search concepts — since your harvested workload *is* hyperparameter search, you'll naturally learn what it's actually doing (why you search over combinations, what you're optimizing for), which is useful, transferable ML knowledge on its own

**Systems/practical skills**

* Concurrent/async handling — the coordinator needs to deal with multiple agents talking to it at once, which is a good gentle introduction to concurrency concepts without needing to go deep into threading theory

## **Honest verdict on difficulty**

This sits comfortably in the "moderate" band across the board — nothing here is a genuine technical wall like RF signal processing or getting cryptographic correctness right were in earlier ideas we discussed. It's very achievable at your pace if you budget the middle months for the prediction model and the preemption-handling logic specifically, since those are where things will take longer than they look on paper.

## **2\. Predictive Idle-Compute Scheduler for ML Workloads**

Your own vague idea, refined with a real ML layer — and worth knowing: **this exact concept independently appears in your department's own project idea list** ("compute-sharing platform for university CS departments" — idle lab machines, students hitting Colab limits). That's a genuinely strong signal this isn't a made-up problem; it's one your own program considers legitimate.

* **Difficulty:** moderate — you're wiring together existing tools (Optuna, Flask, psutil), your original contribution is the coordination \+ prediction logic, not low-level infrastructure.  
* **Usefulness:** concrete and real — idle lab/personal machines wasted while people hit compute limits is a genuine, common problem.  
* **Testability:** this is the strongest of the three on this criterion specifically — you get a clean, quantifiable naive-vs-predictive comparison (completion time, wasted/reassigned work) using your own real usage logs as data.  
* **Resume:** distributed systems \+ ML is a rarer, more "systems engineer" combination than a typical single-model project — signals range.

## **Final Suggestion:**

**\#2, the idle-compute scheduler.** It's the best combination of "not everyone can casually build this" and "not so hard you'll stall" for your stated time budget, it has the cleanest built-in experiment (naive vs. predictive is a genuinely satisfying result to show), and the fact that your own department independently suggested the same core problem means you're not gambling on an idea nobody else has validated as reasonable.

