"""
Cluster Orchestrator & State Engine.
Manages connected nodes, ML Oracle predictions, job scheduling, and live executions with JobRunner.
"""

import time
import uuid
import random
import threading
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable

from src.common.models import (
    NodeTelemetry,
    NodeStatus,
    JobManifest,
    JobResult,
    JobStatus,
    ExecutionMetrics
)
from src.executor.runner import JobRunner
from src.packager.bundle import JobUnpackager, ResultPackager, ResultUnpackager


class ClusterOrchestrator:
    """
    Central coordinator that maintains cluster node state, runs the ML Oracle predictor,
    and executes jobs across available worker nodes.
    """

    def __init__(self, workspace_root: str = "./workspaces"):
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)

        self.nodes: Dict[str, NodeTelemetry] = {}
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.runners: Dict[str, JobRunner] = {}
        self.log_buffers: Dict[str, List[str]] = {}

        self.ws_subscribers: List[Any] = []
        self._lock = threading.Lock()
        self._running = True

        # Initialize realistic initial peer laptops for the demo cluster
        self._init_default_nodes()

        # Start telemetry & ML Oracle ticker thread
        self._ticker_thread = threading.Thread(target=self._telemetry_ticker, daemon=True)
        self._ticker_thread.start()

    def _init_default_nodes(self):
        nodes_init = [
            {
                "node_id": "node-gaming-b",
                "hostname": "Laptop-B (RTX 4070 / i7)",
                "ip_address": "192.168.1.102",
                "cpu_percent": 3.2,
                "ram_percent": 22.0,
                "ram_used_mb": 3584,
                "ram_total_mb": 16384,
                "idle_time_seconds": 900,
                "is_user_active": False,
                "predicted_idle_window_seconds": 5400, # 90 mins (in lecture)
                "status": NodeStatus.IDLE_SAFE
            },
            {
                "node_id": "node-macbook-c",
                "hostname": "Laptop-C (M2 Pro / 16GB)",
                "ip_address": "192.168.1.105",
                "cpu_percent": 4.5,
                "ram_percent": 35.0,
                "ram_used_mb": 5734,
                "ram_total_mb": 16384,
                "idle_time_seconds": 240,
                "is_user_active": False,
                "predicted_idle_window_seconds": 3600, # 60 mins
                "status": NodeStatus.IDLE_SAFE
            },
            {
                "node_id": "node-thinkpad-d",
                "hostname": "Laptop-D (ThinkPad X1)",
                "ip_address": "192.168.1.118",
                "cpu_percent": 18.0,
                "ram_percent": 68.0,
                "ram_used_mb": 11141,
                "ram_total_mb": 16384,
                "idle_time_seconds": 30,
                "is_user_active": True,
                "predicted_idle_window_seconds": 120, # Risky, discord browsing
                "status": NodeStatus.HOST_ACTIVE
            },
            {
                "node_id": "node-lab-01",
                "hostname": "Lab-Station-CS01",
                "ip_address": "192.168.1.201",
                "cpu_percent": 1.5,
                "ram_percent": 18.0,
                "ram_used_mb": 2949,
                "ram_total_mb": 32768,
                "idle_time_seconds": 7200,
                "is_user_active": False,
                "predicted_idle_window_seconds": 14400, # 4 hours
                "status": NodeStatus.IDLE_SAFE
            }
        ]

        for n in nodes_init:
            self.nodes[n["node_id"]] = NodeTelemetry(**n)

    def _telemetry_ticker(self):
        """Simulates background heartbeat fluctuations and ML Oracle updates."""
        while self._running:
            with self._lock:
                for node_id, node in self.nodes.items():
                    if node.status == NodeStatus.HOST_ACTIVE:
                        node.cpu_percent = round(random.uniform(25.0, 75.0), 1)
                        node.idle_time_seconds = 0
                        node.is_user_active = True
                        node.predicted_idle_window_seconds = 0
                    elif node.status == NodeStatus.BUSY:
                        node.cpu_percent = round(random.uniform(60.0, 95.0), 1)
                        node.idle_time_seconds += 2
                        node.is_user_active = False
                    else: # IDLE_SAFE / IDLE_RISKY
                        node.cpu_percent = round(random.uniform(1.0, 6.0), 1)
                        node.idle_time_seconds += 2
                        node.is_user_active = False
                        # Slight drift in ML Oracle estimate
                        if node.predicted_idle_window_seconds > 0:
                            node.predicted_idle_window_seconds = max(0, node.predicted_idle_window_seconds - 2)

            time.sleep(2.0)

    def get_nodes(self) -> List[NodeTelemetry]:
        with self._lock:
            return list(self.nodes.values())

    def toggle_node_host_activity(self, node_id: str) -> Optional[NodeTelemetry]:
        """Simulates the host laptop owner moving mouse / launching a game."""
        with self._lock:
            if node_id not in self.nodes:
                return None
            node = self.nodes[node_id]
            
            if node.status == NodeStatus.HOST_ACTIVE:
                # Host went idle -> Safe
                node.status = NodeStatus.IDLE_SAFE
                node.is_user_active = False
                node.idle_time_seconds = 10
                node.predicted_idle_window_seconds = 3600
                
                # If there's an assigned running job, resume it
                if node.current_job_id and node.current_job_id in self.runners:
                    self.resume_job(node.current_job_id)
            else:
                # Host became active -> Preempt
                node.status = NodeStatus.HOST_ACTIVE
                node.is_user_active = True
                node.idle_time_seconds = 0
                node.predicted_idle_window_seconds = 0
                
                # If there's an assigned running job, trigger instant preemption pause
                if node.current_job_id and node.current_job_id in self.runners:
                    self.pause_job(node.current_job_id)

            return node

    def submit_job(self, bundle_bytes: bytes) -> Dict[str, Any]:
        """Processes an incoming job bundle, selects the best node via ML Oracle, and starts execution."""
        # Unpack to get manifest
        temp_dir = self.workspace_root / f"temp_{uuid.uuid4().hex[:8]}"
        manifest = JobUnpackager.extract_bundle(bundle_bytes, temp_dir)

        job_id = manifest.job_id
        job_name = manifest.job_name

        # Query ML Oracle to find best safe idle node
        best_node = self._select_best_node(manifest.estimated_runtime_sec or 60)

        job_record = {
            "job_id": job_id,
            "job_name": job_name,
            "entrypoint": manifest.entrypoint,
            "args": manifest.args,
            "status": JobStatus.ASSIGNED if best_node else JobStatus.QUEUED,
            "assigned_node_id": best_node.node_id if best_node else None,
            "assigned_hostname": best_node.hostname if best_node else None,
            "created_at": manifest.created_at,
            "started_at": None,
            "completed_at": None,
            "duration_seconds": 0.0,
            "exit_code": None,
            "pause_count": 0,
            "total_pause_duration_sec": 0.0,
            "peak_cpu_percent": 0.0,
            "peak_ram_mb": 0.0,
            "artifact_files": [],
            "error_message": None,
            "manifest": manifest.model_dump()
        }

        self.jobs[job_id] = job_record
        self.log_buffers[job_id] = [f"[DISPATCHER] Job {job_id} ({job_name}) received at {time.strftime('%X')}.\n"]

        if best_node:
            self._start_job_on_node(job_id, bundle_bytes, best_node.node_id)

        return job_record

    def _select_best_node(self, estimated_runtime: int) -> Optional[NodeTelemetry]:
        """ML Oracle Selection: picks the node with the highest confidence and safest idle window."""
        with self._lock:
            candidates = [
                n for n in self.nodes.values()
                if n.status == NodeStatus.IDLE_SAFE and not n.is_user_active and n.current_job_id is None
            ]
            if not candidates:
                return None
            
            # Sort by highest predicted idle window
            candidates.sort(key=lambda n: n.predicted_idle_window_seconds, reverse=True)
            return candidates[0]

    def _start_job_on_node(self, job_id: str, bundle_bytes: bytes, node_id: str):
        """Dispatches job to target node runner."""
        node = self.nodes[node_id]
        node.status = NodeStatus.BUSY
        node.current_job_id = job_id

        self.jobs[job_id]["status"] = JobStatus.RUNNING
        self.jobs[job_id]["started_at"] = time.time()
        self.jobs[job_id]["assigned_node_id"] = node_id
        self.jobs[job_id]["assigned_hostname"] = node.hostname

        self.log_buffers[job_id].append(
            f"[ORACLE] ML Oracle selected node '{node.hostname}' (Predicted idle: {node.predicted_idle_window_seconds//60:.0f} min).\n"
            f"[EXECUTOR] Dispatched to sandbox on {node_id}. Starting execution...\n"
        )

        # Instantiate JobRunner for this job
        def _log_cb(stream, text):
            if job_id in self.log_buffers:
                self.log_buffers[job_id].append(text)

        def _status_cb(new_status: JobStatus):
            if job_id in self.jobs:
                self.jobs[job_id]["status"] = new_status
                if self.runners.get(job_id) and self.runners[job_id].controller:
                    m = self.runners[job_id].controller.metrics
                    self.jobs[job_id]["pause_count"] = m.pause_count
                    self.jobs[job_id]["peak_cpu_percent"] = m.peak_cpu_percent
                    self.jobs[job_id]["peak_ram_mb"] = m.peak_ram_mb

        runner = JobRunner(
            base_workspace_dir=self.workspace_root / "jobs",
            log_callback=_log_cb,
            status_callback=_status_cb
        )
        self.runners[job_id] = runner

        def _on_done(result: JobResult):
            with self._lock:
                if job_id in self.jobs:
                    self.jobs[job_id]["status"] = result.status
                    self.jobs[job_id]["exit_code"] = result.exit_code
                    self.jobs[job_id]["completed_at"] = result.completed_at
                    self.jobs[job_id]["duration_seconds"] = result.metrics.duration_seconds
                    self.jobs[job_id]["pause_count"] = result.metrics.pause_count
                    self.jobs[job_id]["total_pause_duration_sec"] = result.metrics.total_pause_duration_sec
                    self.jobs[job_id]["peak_cpu_percent"] = result.metrics.peak_cpu_percent
                    self.jobs[job_id]["peak_ram_mb"] = result.metrics.peak_ram_mb
                    self.jobs[job_id]["artifact_files"] = result.artifact_files
                    self.jobs[job_id]["error_message"] = result.error_message

                # Free up the node
                if node_id in self.nodes and self.nodes[node_id].current_job_id == job_id:
                    self.nodes[node_id].current_job_id = None
                    if not self.nodes[node_id].is_user_active:
                        self.nodes[node_id].status = NodeStatus.IDLE_SAFE

                self.log_buffers[job_id].append(
                    f"\n[EXECUTOR] Job completed with status {result.status.value} (exit code {result.exit_code}). "
                    f"Artifacts packaged: {len(result.artifact_files)} files.\n"
                )

        runner.run_async(bundle_source=bundle_bytes, on_complete=_on_done)

    def pause_job(self, job_id: str) -> bool:
        """Pauses a running job on its worker node."""
        if job_id in self.runners:
            ok = self.runners[job_id].pause()
            if ok and job_id in self.jobs:
                self.jobs[job_id]["status"] = JobStatus.PAUSED
                self.log_buffers[job_id].append(f"[PREEMPTION] Host activity triggered preemption. Job {job_id} paused.\n")
            return ok
        return False

    def resume_job(self, job_id: str) -> bool:
        """Resumes a paused job."""
        if job_id in self.runners:
            ok = self.runners[job_id].resume()
            if ok and job_id in self.jobs:
                self.jobs[job_id]["status"] = JobStatus.RUNNING
                self.log_buffers[job_id].append(f"[RESUMED] Node is idle again. Job {job_id} resumed.\n")
            return ok
        return False

    def cancel_job(self, job_id: str):
        """Cancels a job."""
        if job_id in self.runners:
            self.runners[job_id].cancel()
        if job_id in self.jobs:
            self.jobs[job_id]["status"] = JobStatus.CANCELLED
            node_id = self.jobs[job_id].get("assigned_node_id")
            if node_id and node_id in self.nodes:
                self.nodes[node_id].current_job_id = None
                if not self.nodes[node_id].is_user_active:
                    self.nodes[node_id].status = NodeStatus.IDLE_SAFE

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        return self.jobs.get(job_id)

    def get_all_jobs(self) -> List[Dict[str, Any]]:
        return list(self.jobs.values())

    def get_job_logs(self, job_id: str) -> str:
        return "".join(self.log_buffers.get(job_id, []))

    def get_result_bundle_path(self, job_id: str) -> Optional[Path]:
        if job_id in self.runners and self.runners[job_id].workspace_dir:
            bundle_path = self.runners[job_id].workspace_dir / "result_bundle.zip"
            if bundle_path.exists():
                return bundle_path
        return None
