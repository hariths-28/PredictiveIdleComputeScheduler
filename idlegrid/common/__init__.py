"""
Shared contracts used by every IdleGrid component (PRD Appendix A).
Import from idlegrid.common.models; see docs/contract.md before changing anything.
"""
from idlegrid.common.models import (
    SCHEMA_VERSION,
    AttemptStatus,
    CommandType,
    ExecutionMetrics,
    HostState,
    InputDetection,
    JobKind,
    JobManifest,
    JobResult,
    JobStatus,
    NodeStatus,
    StudyStatus,
)

__all__ = [
    "SCHEMA_VERSION",
    "AttemptStatus",
    "CommandType",
    "ExecutionMetrics",
    "HostState",
    "InputDetection",
    "JobKind",
    "JobManifest",
    "JobResult",
    "JobStatus",
    "NodeStatus",
    "StudyStatus",
]
