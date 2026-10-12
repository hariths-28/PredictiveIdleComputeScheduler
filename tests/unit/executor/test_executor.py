"""
Unit tests for JobRunner, ProcessController, and Preemption (suspend/resume).
"""

import time
import tempfile
import pytest
from pathlib import Path

from src.packager.bundle import JobPackager
from src.executor.runner import JobRunner
from src.common.models import JobStatus


def test_job_runner_sync_execution():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create sample script that calculates squares and writes a result file
        script_file = tmp_path / "calc.py"
        script_file.write_text(
            "import sys, time, json\n"
            "from pathlib import Path\n"
            "print('Starting computation...')\n"
            "squares = [i*i for i in range(1000)]\n"
            "Path('output').mkdir(exist_ok=True)\n"
            "with open('output/squares.json', 'w') as f:\n"
            "    json.dump({'count': len(squares), 'sum': sum(squares)}, f)\n"
            "print('Done computation!')\n",
            encoding="utf-8"
        )

        bundle_bytes = JobPackager.create_bundle(
            entrypoint_file=script_file,
            job_name="calc_test",
            estimated_runtime_sec=5
        )

        runner = JobRunner(base_workspace_dir=tmp_path / "workspaces")
        result = runner.run_sync(bundle_source=bundle_bytes)

        assert result.status == JobStatus.COMPLETED
        assert result.exit_code == 0
        assert "Done computation!" in result.stdout
        assert result.metrics.duration_seconds > 0

        # Verify result bundle exists and contains output file
        result_bundle_file = runner.workspace_dir / "result_bundle.zip"
        assert result_bundle_file.exists()


def test_job_preemption_pause_resume():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Script that loops and sleeps
        script_file = tmp_path / "loop.py"
        script_file.write_text(
            "import time, sys\n"
            "print('Loop started')\n"
            "sys.stdout.flush()\n"
            "for i in range(15):\n"
            "    time.sleep(0.1)\n"
            "    print(f'Step {i}')\n"
            "    sys.stdout.flush()\n"
            "print('Loop finished')\n",
            encoding="utf-8"
        )

        bundle_bytes = JobPackager.create_bundle(
            entrypoint_file=script_file,
            job_name="preempt_test",
            estimated_runtime_sec=5
        )

        captured_logs = []
        runner = JobRunner(
            base_workspace_dir=tmp_path / "workspaces",
            log_callback=lambda st, text: captured_logs.append(text)
        )

        runner.setup_workspace(bundle_bytes)
        runner.run_async()

        time.sleep(0.3) # Let it start running
        assert runner.controller.is_running

        # Trigger Preemption Pause
        paused = runner.pause()
        assert paused is True
        assert runner.controller.is_paused
        assert runner.current_status == JobStatus.PAUSED

        # Sleep while paused
        time.sleep(0.5)

        # Trigger Resume
        resumed = runner.resume()
        assert resumed is True
        assert not runner.controller.is_paused
        assert runner.current_status == JobStatus.RUNNING

        # Wait for completion of both controller and background runner thread
        runner.wait(timeout=10)

        assert runner.controller.metrics.pause_count == 1
        assert runner.controller.metrics.total_pause_duration_sec >= 0.4
        assert runner.current_status == JobStatus.COMPLETED
