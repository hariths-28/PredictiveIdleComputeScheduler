"""IdleGrid shared contracts. Changes follow PRD §15.4. Never edit casually."""
from __future__ import annotations

import time
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


# ───────────────────────── Enums ─────────────────────────
class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    ASSIGNED = "ASSIGNED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


TERMINAL_JOB_STATUSES = {
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
    JobStatus.TIMED_OUT,
}


class AttemptStatus(str, Enum):
    ASSIGNED = "ASSIGNED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    MIGRATED = "MIGRATED"
    LOST = "LOST"


TERMINAL_ATTEMPT_STATUSES = {
    AttemptStatus.COMPLETED,
    AttemptStatus.FAILED,
    AttemptStatus.CANCELLED,
    AttemptStatus.TIMED_OUT,
    AttemptStatus.MIGRATED,
    AttemptStatus.LOST,
}


class NodeStatus(str, Enum):
    OFFLINE = "OFFLINE"
    HOST_ACTIVE = "HOST_ACTIVE"
    HOST_BUSY = "HOST_BUSY"
    IDLE_SAFE = "IDLE_SAFE"
    IDLE_RISKY = "IDLE_RISKY"
    RUNNING_JOB = "RUNNING_JOB"
    DRAINING = "DRAINING"
    UNSCHEDULABLE = "UNSCHEDULABLE"


class HostState(str, Enum):
    ACTIVE = "ACTIVE"
    BUSY = "BUSY"
    IDLE = "IDLE"
    UNKNOWN = "UNKNOWN"


class InputDetection(str, Enum):
    PRECISE = "PRECISE"
    COARSE = "COARSE"
    NONE = "NONE"


class JobKind(str, Enum):
    SCRIPT = "SCRIPT"
    HPO_TRIAL = "HPO_TRIAL"


class CommandType(str, Enum):
    START = "START"
    ABORT = "ABORT"
    PAUSE = "PAUSE"
    RESUME = "RESUME"


class StudyStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# ───────────────────────── Job bundles & execution ─────────────────────────
class HpoTrialRef(BaseModel):
    study_id: str
    trial_number: int


class JobManifest(BaseModel):
    """manifest.json inside every job bundle (created by the packager)."""

    job_id: str | None = None  # assigned by the Dispatcher; ignored on submit
    job_name: str
    kind: JobKind = JobKind.SCRIPT
    entrypoint: str  # relative path of the .py file inside the bundle
    args: list[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    timeout_seconds: int = 3600  # ACTIVE (unpaused) seconds
    estimated_runtime_sec: int = 60  # on the reference laptop (perf_score = 1.0)
    ram_required_mb: int = 1024
    requirements: list[str] | None = None  # informational; must be satisfied by shared worker env
    env_vars: dict[str, str] = Field(default_factory=dict)
    files: list[str] = Field(default_factory=list)
    user_id: str | None = None  # ignored; Dispatcher uses the token's user
    hpo: HpoTrialRef | None = None


class ExecutionMetrics(BaseModel):
    start_time: float | None = None
    end_time: float | None = None
    duration_seconds: float = 0.0  # wall clock incl. pauses
    active_seconds: float = 0.0  # wall clock excl. pauses (used for timeouts & wasted compute)
    cpu_percent_samples: list[float] = Field(default_factory=list)
    ram_mb_samples: list[float] = Field(default_factory=list)
    peak_cpu_percent: float = 0.0
    peak_ram_mb: float = 0.0
    pause_count: int = 0
    total_pause_duration_sec: float = 0.0


class JobResult(BaseModel):
    job_id: str
    attempt_id: str | None = None
    status: JobStatus  # COMPLETED | FAILED | CANCELLED | TIMED_OUT
    exit_code: int | None = None
    stdout: str = ""  # last 64 KB only
    stderr: str = ""  # last 64 KB only
    metrics: ExecutionMetrics = Field(default_factory=ExecutionMetrics)
    artifact_files: list[str] = Field(default_factory=list)
    error_message: str | None = None
    completed_at: float = Field(default_factory=time.time)
    objective_value: float | None = None  # HPO trials only


# ───────────────────────── Agent → Dispatcher ─────────────────────────
class NodeMetrics(BaseModel):
    cpu_percent: float  # whole system, 0–100
    host_cpu_percent: float  # system minus our job's processes, 0–100
    cpu_count: int
    ram_percent: float
    ram_available_mb: float
    ram_total_mb: float
    disk_free_gb: float
    user_inactivity_sec: float | None  # None = could not be read


class PowerInfo(BaseModel):
    on_ac_power: bool | None = None  # None = no battery (desktop) or unknown
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
    paused_since: float | None = None  # epoch seconds, already corrected to server clock
    active_seconds: float = 0.0
    pause_count: int = 0
    manual_pause: bool = False


class CommandResult(BaseModel):
    command_id: str
    ok: bool
    error: str | None = None  # e.g. "host_active", "busy", "not_accepting", "bundle_integrity"


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
    bundle_path: str  # e.g. "/api/v1/attempts/{attempt_id}/bundle"
    bundle_sha256: str
    bundle_size: int
    manifest: JobManifest
    active_timeout_sec: float
    migrate_after_sec: float


class NodeCommand(BaseModel):
    command_id: str
    type: CommandType
    attempt_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)  # START → StartJobPayload; ABORT → {"reason": str}
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


# ───────────────────────── Sessions & Availability ─────────────────────────
class Session(BaseModel):
    node_id: str
    start: float
    end: float
    end_reason: Literal["ACTIVE", "BUSY", "UNPLUGGED", "GAP", "CENSORED"]

    @property
    def duration_sec(self) -> float:
        return max(0.0, self.end - self.start)


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
    assigned_node_id: str | None = None
    assigned_hostname: str | None = None
    attempts_count: int = 0
    duration_seconds: float = 0.0
    active_seconds: float = 0.0
    wasted_seconds: float = 0.0
    pause_count: int = 0
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
    attempts: list[AttemptView] | None = None


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
    choices: list[Any] | None = None


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
