"""
Prototype-only models from the original Role 5 dashboard (mock cluster).

These are NOT part of the shared contract (idlegrid.common.models, PRD Appendix A).
They keep the existing dashboard and CLI working until Phase 1 replaces the mock
cluster with real heartbeats (NodeView). Do not use them in new code.
"""

import time
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from idlegrid.common.models import NodeStatus


class NodeTelemetry(BaseModel):
    """Node state as tracked by the prototype dashboard's mock cluster."""
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
    """Node registration details (prototype)."""
    node_id: str
    hostname: str
    ip_address: str
    cpu_cores: int
    total_ram_gb: float
    gpu_name: Optional[str] = None
    os_name: str
    status: NodeStatus = NodeStatus.IDLE_SAFE


class JobSubmissionRequest(BaseModel):
    """Client request payload when submitting a job (prototype)."""
    job_name: str
    entrypoint: str
    args: List[str] = Field(default_factory=list)
    timeout_seconds: int = 1800
    estimated_runtime_sec: Optional[int] = 60
    env_vars: Dict[str, str] = Field(default_factory=dict)
    preferred_node_id: Optional[str] = None
