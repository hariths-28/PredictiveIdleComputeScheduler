import os
import time
import logging
from typing import Optional, List, Dict, Any, Callable
import psutil

logger = logging.getLogger("NodeAgent.KillSwitch")

class PreemptionEvent:
    def __init__(self, job_id: Optional[str], pid: int, action: str, reason: str, timestamp: float):
        self.job_id = job_id
        self.pid = pid
        self.action = action
        self.reason = reason
        self.timestamp = timestamp

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "pid": self.pid,
            "action": self.action,
            "reason": self.reason,
            "timestamp": self.timestamp
        }

class KillSwitch:
    """
    The Preemption Engine ("Kill Switch") for Role 1.
    Guarantees zero-lag for the machine owner: instantly suspends or terminates
    borrowed background compute jobs the millisecond user activity is detected.
    """
    def __init__(
        self,
        default_action: str = "terminate", # "terminate" or "suspend"
        preemption_callback: Optional[Callable[[PreemptionEvent], None]] = None
    ):
        self.default_action = default_action
        self.preemption_callback = preemption_callback
        # Dictionary of monitored jobs: pid -> {"job_id": str, "registered_at": float}
        self.monitored_jobs: Dict[int, Dict[str, Any]] = {}
        self.preemption_history: List[PreemptionEvent] = []

    def register_job(self, pid: int, job_id: Optional[str] = None) -> bool:
        """Registers a compute job PID to be guarded by the Kill Switch."""
        if not psutil.pid_exists(pid):
            logger.warning(f"Cannot register PID {pid}: Process does not exist.")
            return False

        self.monitored_jobs[pid] = {
            "job_id": job_id or f"job-{pid}",
            "registered_at": time.time()
        }
        logger.info(f"Registered compute job PID {pid} (Job ID: {job_id or pid}) under Kill Switch guard.")
        return True

    def unregister_job(self, pid: int):
        """Removes a job from the guard list (e.g., when completed naturally)."""
        if pid in self.monitored_jobs:
            del self.monitored_jobs[pid]
            logger.debug(f"Unregistered PID {pid} from Kill Switch.")

    def has_active_jobs(self) -> bool:
        """Returns True if there are currently running jobs being monitored."""
        # Clean up already exited PIDs
        alive_pids = [pid for pid in self.monitored_jobs if psutil.pid_exists(pid)]
        self.monitored_jobs = {pid: self.monitored_jobs[pid] for pid in alive_pids}
        return len(self.monitored_jobs) > 0

    def trigger_preemption(self, reason: str = "User presence detected", action: Optional[str] = None) -> List[PreemptionEvent]:
        """
        Executes immediate preemption on all registered compute jobs.
        Terminates or suspends the entire process tree to guarantee zero host lag.
        """
        action = action or self.default_action
        events = []
        start_time = time.time()

        for pid, meta in list(self.monitored_jobs.items()):
            if not psutil.pid_exists(pid):
                self.unregister_job(pid)
                continue

            try:
                parent = psutil.Process(pid)
                # Include all spawned children in process tree
                children = parent.children(recursive=True)
                targets = children + [parent]

                if action == "suspend":
                    for proc in targets:
                        try:
                            proc.suspend()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    logger.warning(f"[KILL SWITCH ACTIVATED] SUSPENDED process tree for PID {pid} ({reason})")

                else: # terminate
                    for proc in targets:
                        try:
                            proc.terminate()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    # Wait briefly for graceful exit, then kill if stubborn
                    _, alive = psutil.wait_procs(targets, timeout=0.2)
                    for proc in alive:
                        try:
                            proc.kill()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    logger.warning(f"[KILL SWITCH ACTIVATED] TERMINATED process tree for PID {pid} ({reason})")

                event = PreemptionEvent(
                    job_id=meta["job_id"],
                    pid=pid,
                    action=action,
                    reason=reason,
                    timestamp=time.time()
                )
                self.preemption_history.append(event)
                events.append(event)

                if self.preemption_callback:
                    self.preemption_callback(event)

            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                logger.error(f"Error preempting PID {pid}: {e}")
            finally:
                if action == "terminate":
                    self.unregister_job(pid)

        duration_ms = round((time.time() - start_time) * 1000, 2)
        if events:
            logger.info(f"Kill Switch executed across {len(events)} job(s) in {duration_ms}ms.")

        return events

    def on_state_update(self, current_state: str, inactivity_sec: float) -> List[PreemptionEvent]:
        """
        Called on every monitoring cycle.
        If user becomes active while jobs are running, instantly triggers preemption.
        """
        if current_state == "USER_ACTIVE" and self.has_active_jobs():
            reason = f"User input detected (inactivity {inactivity_sec}s < threshold)"
            return self.trigger_preemption(reason=reason)
        return []
