# ⚡ Predictive Idle-Compute Scheduler
## Role 5: The Executor & Integration UI (CLI + Web Dashboard)

> **Turns a network of everyday student laptops into a single, shared supercomputer with ML-guided job routing and instant preemption.**

---

## 🌟 What Role 5 Delivers

As **Role 5 (Executor & Integration UI)**, this codebase provides the core execution engine and user interfaces for the entire project:

1. **📦 Job Bundle Packager (`src/packager/bundle.py`)**:
   - Packages Python user scripts (`train.py`), datasets, dependency manifests (`requirements.txt`), arguments, and generates `manifest.json`.
   - Safely extracts workspaces on worker nodes and harvests output files (`output/`, CSVs, model weights, logs) into `result_bundle.zip`.

2. **⚡ Worker Job Executor & Preemption Engine (`src/executor/runner.py`, `src/executor/process_controller.py`)**:
   - Spawns user workloads in an isolated execution sandbox.
   - **Instant Preemption**: Uses `psutil.Process.suspend()` to freeze the compute process tree instantly the moment the laptop owner moves their mouse or launches heavy software, freeing 100% CPU with zero lag to the host.
   - **Instant Resume**: Resumes the process tree via `psutil.Process.resume()` when the machine is idle again, preserving execution state and avoiding redundant recomputation.
   - Real-time non-blocking stream reader for `stdout` and `stderr`.

3. **💻 Rich Command-Line Interface (`gridctl.py`)**:
   - `python gridctl.py submit <script.py> [--data <files>] [--follow] [--local]`: Submit and monitor jobs.
   - `python gridctl.py status <job_id>`: Check job execution state and resource telemetry.
   - `python gridctl.py logs <job_id> [--follow]`: Live log tailing.
   - `python gridctl.py cluster`: View connected laptops and ML Oracle predicted idle durations.
   - `python gridctl.py download <job_id>`: Fetch and extract resulting artifacts.
   - `python gridctl.py demo-run --type [pi|matrix|ml]`: Self-contained interactive preemption demo.

4. **🌐 Live Web Dashboard (`src/dashboard/`)**:
   - Glassmorphic dark-mode interface with live WebSocket telemetry.
   - Visual cluster node cards with animated CPU/RAM meters and ML Oracle safe-window badges.
   - Interactive **"Simulate Host Active"** button for live judge demonstrations.
   - 1-Click demo workload dispatchers and drag-and-drop file upload.
   - Live stdout/stderr terminal window with auto-scrolling.

5. **🎯 Ready-to-Run Demo Jobs (`demo_jobs/`)**:
   - `monte_carlo_pi.py`: Distributed random dart-throwing estimation of $\pi$.
   - `matrix_stress.py`: Large $1500 \times 1500$ matrix multiplication benchmarking GFLOPS.
   - `tabular_ml_train.py`: Scikit-learn Random Forest model training with metrics and prediction outputs.

---

## 🚀 Quickstart Guide

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Start the Live Dashboard Server
```bash
python -m uvicorn src.dashboard.app:app --host 127.0.0.1 --port 8000 --reload
```
Open your browser at: **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

## 🛠️ CLI Usage Examples (`gridctl`)

### Submit a Job
```bash
# Submit to the central grid and follow logs
python gridctl.py submit demo_jobs/monte_carlo_pi.py --follow

# Submit a heavy machine learning training job
python gridctl.py submit demo_jobs/tabular_ml_train.py --name "RF_Model_Training"

# Execute locally inside standalone runner
python gridctl.py submit demo_jobs/matrix_stress.py --local --follow
```

### Inspect the Cluster
```bash
python gridctl.py cluster
```

### Check Job Status
```bash
python gridctl.py status <JOB_ID>
```

### Download Artifacts
```bash
python gridctl.py download <JOB_ID> --output ./my_results
```

### Run an Interactive Preemption Demo
```bash
python gridctl.py demo-run --type pi
```

---

## 🧪 Running the Test Suite

```bash
pytest -v
```

---

## 🤝 Integration Contracts for Teammates

| Role | Interface / Endpoint | Data Contract |
| :--- | :--- | :--- |
| **Role 1 (Node Agent)** | `JobRunner.pause()` / `JobRunner.resume()` | Called when `psutil` input activity detector flags host active/idle. |
| **Role 2 (Dispatcher)** | `POST /api/jobs/submit` | Accepts multipart `.zip` bundle produced by `JobPackager.create_bundle()`. |
| **Role 3 (State Manager)** | `src/common/models.py` | Imports `JobManifest`, `JobResult`, `NodeTelemetry`, `JobStatus`. |
| **Role 4 (ML Oracle)** | `node.predicted_idle_window_seconds` | Populates predicted safe idle window for node selection. |
