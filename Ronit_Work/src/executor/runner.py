"""
Top-level JobRunner executing packaged grid bundles, handling signals and packaging results.
"""

import sys
import time
import shutil
import logging
import threading
from pathlib import Path
from typing import Optional, Callable, Union, Dict

from src.common.models import JobManifest, JobResult, JobStatus, ExecutionMetrics
from src.packager.bundle import JobUnpackager, ResultPackager
from src.executor.process_controller import ProcessController

logger = logging.getLogger("GridExecutor.JobRunner")


class JobRunner:
    """
    Executes a job bundle on the local worker node.
    Provides methods to run, pause, resume, cancel, and retrieve results.
    """

    def __init__(
        self,
        base_workspace_dir: Union[str, Path] = "./workspaces/jobs",
        log_callback: Optional[Callable[[str, str], None]] = None,
        status_callback: Optional[Callable[[JobStatus], None]] = None
    ):
        self.base_workspace_dir = Path(base_workspace_dir).resolve()
        self.base_workspace_dir.mkdir(parents=True, exist_ok=True)
        self.log_callback = log_callback
        self.status_callback = status_callback

        self.manifest: Optional[JobManifest] = None
        self.workspace_dir: Optional[Path] = None
        self.controller: Optional[ProcessController] = None
        self.job_result: Optional[JobResult] = None
        self._thread: Optional[threading.Thread] = None

    def setup_workspace(self, bundle_source: Union[bytes, str, Path]) -> JobManifest:
        """Unpacks the job bundle into its unique workspace directory."""
        # Unpack to temporary first to extract manifest and get job_id
        temp_dir = self.base_workspace_dir / f"tmp_{int(time.time() * 1000)}"
        manifest = JobUnpackager.extract_bundle(bundle_source, temp_dir)

        # Move to permanent workspace named by job_id
        final_workspace = self.base_workspace_dir / manifest.job_id
        if final_workspace.exists():
            shutil.rmtree(final_workspace)
        temp_dir.rename(final_workspace)

        self.manifest = manifest
        self.workspace_dir = final_workspace
        return manifest

    def run_sync(
        self,
        bundle_source: Optional[Union[bytes, str, Path]] = None,
        manifest: Optional[JobManifest] = None,
        workspace_dir: Optional[Union[str, Path]] = None
    ) -> JobResult:
        """
        Executes the job synchronously and returns the JobResult.
        """
        if bundle_source is not None:
            self.setup_workspace(bundle_source)
        elif manifest is not None and workspace_dir is not None:
            self.manifest = manifest
            self.workspace_dir = Path(workspace_dir).resolve()

        if not self.manifest or not self.workspace_dir:
            raise ValueError("No valid job manifest or workspace available to run.")

        entrypoint_path = self.workspace_dir / self.manifest.entrypoint
        if not entrypoint_path.exists():
            result = JobResult(
                job_id=self.manifest.job_id,
                status=JobStatus.FAILED,
                exit_code=-1,
                error_message=f"Entrypoint script '{self.manifest.entrypoint}' not found in workspace."
            )
            self.job_result = result
            return result

        command = [sys.executable, str(entrypoint_path)] + self.manifest.args

        self.controller = ProcessController(
            command=command,
            cwd=self.workspace_dir,
            env=self.manifest.env_vars,
            log_callback=self.log_callback,
            status_callback=self.status_callback
        )

        started = self.controller.start()
        if not started:
            result = JobResult(
                job_id=self.manifest.job_id,
                status=JobStatus.FAILED,
                exit_code=-1,
                error_message="Process controller failed to spawn process."
            )
            self.job_result = result
            return result

        exit_code = self.controller.wait(timeout=self.manifest.timeout_seconds)

        status = JobStatus.COMPLETED if exit_code == 0 else (
            JobStatus.CANCELLED if self.controller.status == JobStatus.CANCELLED else JobStatus.FAILED
        )

        self.job_result = JobResult(
            job_id=self.manifest.job_id,
            status=status,
            exit_code=exit_code,
            stdout=self.controller.stdout,
            stderr=self.controller.stderr,
            metrics=self.controller.metrics,
            completed_at=time.time()
        )

        # Package results inside the workspace
        result_bundle_path = self.workspace_dir / "result_bundle.zip"
        ResultPackager.create_result_bundle(
            workspace_dir=self.workspace_dir,
            job_result=self.job_result,
            output_bundle_path=result_bundle_path
        )

        return self.job_result

    def run_async(
        self,
        bundle_source: Optional[Union[bytes, str, Path]] = None,
        on_complete: Optional[Callable[[JobResult], None]] = None
    ):
        """Runs the job asynchronously in a background worker thread."""
        def _target():
            res = self.run_sync(bundle_source=bundle_source)
            if on_complete:
                try:
                    on_complete(res)
                except Exception as e:
                    logger.error(f"Error in on_complete callback: {e}")

        self._thread = threading.Thread(target=_target, daemon=True)
        self._thread.start()

    def wait(self, timeout: Optional[float] = None) -> Optional[JobResult]:
        """Waits for the background execution thread to finish."""
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        return self.job_result

    def pause(self) -> bool:
        """Signal preemption: suspend the running job."""
        if self.controller:
            return self.controller.pause()
        return False

    def resume(self) -> bool:
        """Signal node idle: resume the suspended job."""
        if self.controller:
            return self.controller.resume()
        return False

    def cancel(self):
        """Cancel/terminate the running job."""
        if self.controller:
            self.controller.terminate(force=True)

    @property
    def current_status(self) -> JobStatus:
        if self.controller:
            return self.controller.status
        return JobStatus.QUEUED
