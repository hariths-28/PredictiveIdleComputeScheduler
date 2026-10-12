"""
Process Controller for sandboxed execution of compute jobs.
Manages the process tree, log streaming, and instant preemption (suspend/resume) via psutil.
"""

import os
import sys
import time
import subprocess
import threading
import logging
from pathlib import Path
from typing import Optional, Callable, List, Dict
import psutil

from src.common.models import JobStatus, ExecutionMetrics

logger = logging.getLogger("GridExecutor.ProcessController")


class ProcessController:
    """
    Spawns, monitors, suspends, resumes, and terminates a job process tree.
    Captures realtime logs and resource utilization metrics.
    """

    def __init__(
        self,
        command: List[str],
        cwd: Path,
        env: Optional[Dict[str, str]] = None,
        log_callback: Optional[Callable[[str, str], None]] = None, # (stream_type, text)
        status_callback: Optional[Callable[[JobStatus], None]] = None
    ):
        self.command = command
        self.cwd = Path(cwd).resolve()
        self.env = os.environ.copy()
        self.env["PYTHONUNBUFFERED"] = "1"
        if env:
            self.env.update(env)

        self.log_callback = log_callback
        self.status_callback = status_callback

        self.process: Optional[subprocess.Popen] = None
        self.psutil_proc: Optional[psutil.Process] = None

        self.status = JobStatus.QUEUED
        self.metrics = ExecutionMetrics()

        self._stdout_lines: List[str] = []
        self._stderr_lines: List[str] = []

        self._pause_start_time: Optional[float] = None
        self._is_paused = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._metric_thread: Optional[threading.Thread] = None
        self._stop_requested = threading.Event()
        self._exit_code: Optional[int] = None

        self.stdout_log_path = self.cwd / "stdout.log"
        self.stderr_log_path = self.cwd / "stderr.log"

    def _update_status(self, new_status: JobStatus):
        self.status = new_status
        if self.status_callback:
            try:
                self.status_callback(new_status)
            except Exception as e:
                logger.error(f"Error in status callback: {e}")

    def start(self) -> bool:
        """Launches the process in the workspace directory."""
        try:
            self.metrics.start_time = time.time()
            self._update_status(JobStatus.RUNNING)

            # Ensure logs directory exists
            self.cwd.mkdir(parents=True, exist_ok=True)

            self.process = subprocess.Popen(
                self.command,
                cwd=str(self.cwd),
                env=self.env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            self.psutil_proc = psutil.Process(self.process.pid)

            # Start reader threads for stdout and stderr
            self._stdout_thread = threading.Thread(target=self._read_stream, args=(self.process.stdout, "stdout", self.stdout_log_path), daemon=True)
            self._stderr_thread = threading.Thread(target=self._read_stream, args=(self.process.stderr, "stderr", self.stderr_log_path), daemon=True)
            self._stdout_thread.start()
            self._stderr_thread.start()

            # Start resource metric sampler
            self._metric_thread = threading.Thread(target=self._sample_metrics_loop, daemon=True)
            self._metric_thread.start()

            return True
        except Exception as e:
            self._update_status(JobStatus.FAILED)
            self._stderr_lines.append(f"Failed to start process: {str(e)}")
            logger.error(f"Execution startup failed: {e}")
            return False

    def _read_stream(self, stream, stream_name: str, log_file: Path):
        """Reads stream line-by-line in real-time, logs to file and fires callback."""
        if not stream:
            return

        with open(log_file, "a", encoding="utf-8") as f:
            for line in iter(stream.readline, ''):
                if not line:
                    break
                f.write(line)
                f.flush()

                if stream_name == "stdout":
                    self._stdout_lines.append(line)
                else:
                    self._stderr_lines.append(line)

                if self.log_callback:
                    try:
                        self.log_callback(stream_name, line)
                    except Exception:
                        pass
        stream.close()

    def _sample_metrics_loop(self):
        """Periodically samples CPU & Memory usage of the running process tree."""
        while not self._stop_requested.is_set() and self.process and self.process.poll() is None:
            if not self._is_paused and self.psutil_proc and self.psutil_proc.is_running():
                try:
                    # Sample process tree
                    cpu = self.psutil_proc.cpu_percent(interval=0.2)
                    mem_info = self.psutil_proc.memory_info()
                    mem_mb = mem_info.rss / (1024 * 1024)

                    # Also accumulate children if any
                    for child in self.psutil_proc.children(recursive=True):
                        try:
                            mem_mb += child.memory_info().rss / (1024 * 1024)
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass

                    self.metrics.cpu_percent_samples.append(cpu)
                    self.metrics.ram_mb_samples.append(mem_mb)

                    if cpu > self.metrics.peak_cpu_percent:
                        self.metrics.peak_cpu_percent = cpu
                    if mem_mb > self.metrics.peak_ram_mb:
                        self.metrics.peak_ram_mb = mem_mb

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    break
                except Exception as e:
                    logger.debug(f"Metrics sampling error: {e}")
            time.sleep(0.8)

    def pause(self) -> bool:
        """
        Instant Preemption: Suspends the process tree using psutil.
        Called when the Node Agent detects the laptop owner has become active.
        """
        if self._is_paused or not self.psutil_proc or not self.psutil_proc.is_running():
            return False

        try:
            logger.info(f"Preempting/Pausing process tree PID={self.process.pid}")
            # Suspend children first, then parent
            for child in self.psutil_proc.children(recursive=True):
                try:
                    child.suspend()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            self.psutil_proc.suspend()

            self._is_paused = True
            self._pause_start_time = time.time()
            self.metrics.pause_count += 1
            self._update_status(JobStatus.PAUSED)
            
            if self.log_callback:
                self.log_callback("stdout", f"[SYSTEM PREEMPTION] Job paused because host activity was detected.\n")

            return True
        except Exception as e:
            logger.error(f"Failed to pause process: {e}")
            return False

    def resume(self) -> bool:
        """
        Resumes a previously suspended process tree when the node becomes idle again.
        """
        if not self._is_paused or not self.psutil_proc or not self.psutil_proc.is_running():
            return False

        try:
            logger.info(f"Resuming process tree PID={self.process.pid}")
            self.psutil_proc.resume()
            for child in self.psutil_proc.children(recursive=True):
                try:
                    child.resume()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            if self._pause_start_time:
                pause_duration = time.time() - self._pause_start_time
                self.metrics.total_pause_duration_sec += pause_duration
                self._pause_start_time = None

            self._is_paused = False
            self._update_status(JobStatus.RUNNING)

            if self.log_callback:
                self.log_callback("stdout", f"[SYSTEM RESUMED] Host is idle again. Resuming compute job execution.\n")

            return True
        except Exception as e:
            logger.error(f"Failed to resume process: {e}")
            return False

    def terminate(self, force: bool = False):
        """Terminates or kills the process tree."""
        self._stop_requested.set()
        if not self.psutil_proc:
            return

        try:
            # If paused, resume first so it can receive signals properly
            if self._is_paused:
                self.resume()

            children = []
            try:
                children = self.psutil_proc.children(recursive=True)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

            for child in children:
                try:
                    if force:
                        child.kill()
                    else:
                        child.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            if force:
                self.psutil_proc.kill()
            else:
                self.psutil_proc.terminate()

            self._update_status(JobStatus.CANCELLED)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        except Exception as e:
            logger.error(f"Error terminating process: {e}")

    def wait(self, timeout: Optional[float] = None) -> int:
        """Waits for process completion and updates final status and metrics."""
        if not self.process:
            return -1

        try:
            self._exit_code = self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.warning("Job timed out. Terminating...")
            self.terminate(force=True)
            self._exit_code = -9

        self._stop_requested.set()

        # Allow stream reader threads to finish reading final buffer and close file handles
        if hasattr(self, '_stdout_thread') and self._stdout_thread.is_alive():
            self._stdout_thread.join(timeout=1.0)
        if hasattr(self, '_stderr_thread') and self._stderr_thread.is_alive():
            self._stderr_thread.join(timeout=1.0)
        if hasattr(self, '_metric_thread') and self._metric_thread.is_alive():
            self._metric_thread.join(timeout=0.5)

        self.metrics.end_time = time.time()
        if self.metrics.start_time:
            self.metrics.duration_seconds = self.metrics.end_time - self.metrics.start_time

        if self._exit_code == 0:
            self._update_status(JobStatus.COMPLETED)
        elif self.status != JobStatus.CANCELLED:
            self._update_status(JobStatus.FAILED)

        return self._exit_code

    @property
    def stdout(self) -> str:
        return "".join(self._stdout_lines)

    @property
    def stderr(self) -> str:
        return "".join(self._stderr_lines)

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    @property
    def is_paused(self) -> bool:
        return self._is_paused
