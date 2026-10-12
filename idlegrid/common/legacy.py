"""
Core data models and schemas for the Predictive Idle-Compute Scheduler.
Defines contracts used by Packager, Executor, Dispatcher, Agent, and CLI/UI.
"""

from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
import time
import uuid


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    ASSIGNED = "ASSIGNED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"          # Preempted because host became active
    RESUMING = "RESUMING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PREEMPTED_MIGRATING = "PREEMPTED_MIGRATING"


class NodeStatus(str, Enum):
    IDLE_SAFE = "IDLE_SAFE"         # Idle with high ML confidence for long window
    IDLE_RISKY = "IDLE_RISKY"       # Idle but short predicted window (only small micro-jobs)
    HOST_ACTIVE = "HOST_ACTIVE"     # Host is using the laptop (mouse/keyboard/high CPU)
    BUSY = "BUSY"                   # Currently running a grid job
    OFFLINE = "OFFLINE"


class JobManifest(BaseModel):
    """Metadata describing a packaged compute job."""
    job_id: str = Field(default_factory=lambda: f"job_{uuid.uuid4().hex[:10]}")
    job_name: str
    entrypoint: str                 # e.g. "main.py" or "train.py"
    args: List[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    timeout_seconds: int = 3600
    estimated_runtime_sec: Optional[int] = 60
    requirements: Optional[List[str]] = None
    env_vars: Dict[str, str] = Field(default_factory=dict)
    files: List[str] = Field(default_factory=list)
    user_id: Optional[str] = "user_default"


class ExecutionMetrics(BaseModel):
    """Runtime statistics captured during job execution."""
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    duration_seconds: float = 0.0
    cpu_percent_samples: List[float] = Field(default_factory=list)
    ram_mb_samples: List[float] = Field(default_factory=list)
    peak_cpu_percent: float = 0.0
    peak_ram_mb: float = 0.0
    pause_count: int = 0
    total_pause_duration_sec: float = 0.0


class JobResult(BaseModel):
    """Final outcome returned by the executor to the dispatcher/client."""
    job_id: str
    status: JobStatus
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    metrics: ExecutionMetrics = Field(default_factory=ExecutionMetrics)
    artifact_files: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    completed_at: float = Field(default_factory=time.time)


class NodeTelemetry(BaseModel):
    """Heartbeat telemetry sent by Node Agent (Role 1) and tracked by State Manager (Role 3)."""
    node_id: str
    hostname: str
    ip_address: str
    cpu_percent: float
    ram_percent: float
    ram_used_mb: float
    ram_total_mb: float
    idle_time_seconds: float
    is_user_active: bool
    predicted_idle_window_seconds: float = 0.0
    status: NodeStatus = NodeStatus.IDLE_SAFE
    current_job_id: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)


class NodeInfo(BaseModel):
    """Node registration details."""
    node_id: str
    hostname: str
    ip_address: str
    cpu_cores: int
    total_ram_gb: float
    gpu_name: Optional[str] = None
    os_name: str
    status: NodeStatus = NodeStatus.IDLE_SAFE


class JobSubmissionRequest(BaseModel):
    """Client request payload when submitting a job."""
    job_name: str
    entrypoint: str
    args: List[str] = Field(default_factory=list)
    timeout_seconds: int = 1800
    estimated_runtime_sec: Optional[int] = 60
    env_vars: Dict[str, str] = Field(default_factory=dict)
    preferred_node_id: Optional[str] = None
