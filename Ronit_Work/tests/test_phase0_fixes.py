"""
Regression tests for Ronit's Phase 0 Deliverables:
1. Bug R1: demo-run single execution (no redundant run_sync after run_async)
2. Bug R2: Active execution timeout ignores paused/preempted duration
3. Bug R3: Timeout yields JobStatus.TIMED_OUT (not FAILED or CANCELLED)
4. Bug R5: format_status & format_node_status handle Enum instances and new contract statuses
5. Review 1 Demo Bridge: /healthz and /api/v1/heartbeat support for real node agents
"""

import time
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from src.common.models import JobStatus, NodeStatus
from src.executor.process_controller import ProcessController
from src.executor.runner import JobRunner
from src.packager.bundle import JobPackager
from src.cli.gridctl import format_status, format_node_status, demo_run_cmd
from src.dashboard.app import app, orchestrator


@pytest.fixture
def api_client():
    return TestClient(app)


def test_r5_format_status_enum_and_string_values():
    """Bug R5 regression: format_status and format_node_status handle Enum objects and string inputs cleanly."""
    # Test Enum inputs
    st_running = format_status(JobStatus.RUNNING)
    assert "RUNNING" in st_running.plain
    assert "JOBSTATUS" not in st_running.plain

    st_timed_out = format_status(JobStatus.TIMED_OUT)
    assert "TIMED_OUT" in st_timed_out.plain
    assert "JOBSTATUS" not in st_timed_out.plain

    st_completed = format_status(JobStatus.COMPLETED)
    assert "COMPLETED" in st_completed.plain

    st_paused = format_status(JobStatus.PAUSED)
    assert "PAUSED" in st_paused.plain

    # Test NodeStatus Enum inputs
    node_running = format_node_status(NodeStatus.RUNNING_JOB)
    assert "RUNNING JOB" in node_running.plain
    assert "NODESTATUS" not in node_running.plain

    node_host_busy = format_node_status(NodeStatus.HOST_BUSY)
    assert "HOST BUSY" in node_host_busy.plain

    node_idle_risky = format_node_status(NodeStatus.IDLE_RISKY)
    assert "IDLE (RISKY)" in node_idle_risky.plain

    # Test String inputs
    assert "COMPLETED" in format_status("COMPLETED").plain
    assert "TIMED_OUT" in format_status("TIMED_OUT").plain
    assert "RUNNING JOB" in format_node_status("RUNNING_JOB").plain


def test_r2_active_timeout_ignores_paused_time():
    """Bug R2 regression: Paused time must NOT count towards the job's active execution timeout."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        script_file = tmp_path / "pause_test.py"
        # Script sleeps in small increments for ~0.5s active compute
        script_file.write_text(
            "import time, sys\n"
            "for _ in range(5):\n"
            "    time.sleep(0.1)\n"
            "print('Script finished successfully')\n",
            encoding="utf-8"
        )

        controller = ProcessController(
            command=["python", str(script_file)],
            cwd=tmp_path
        )

        started = controller.start()
        assert started is True

        time.sleep(0.2)
        # Pause the process for 2.0 seconds
        controller.pause()
        assert controller.is_paused

        time.sleep(2.0)

        # Resume the process
        controller.resume()
        assert not controller.is_paused

        # Timeout is 2.0s of ACTIVE compute.
        # Total wall clock elapsed is ~0.2 + 2.0 (pause) + 0.5 = ~2.7s (> 2.0s).
        # Under the old wall-clock logic, this job would have timed out and failed.
        # Under the new active-time logic, active compute is ~0.8s (< 2.0s), so it completes.
        exit_code = controller.wait(timeout=2.0)

        assert exit_code == 0
        assert controller.status == JobStatus.COMPLETED
        assert controller.metrics.total_pause_duration_sec >= 1.9
        assert controller.metrics.duration_seconds >= 2.2
        assert controller.active_seconds() < 2.0


def test_r3_active_timeout_triggers_timed_out_status():
    """Bug R3 regression: When active execution time exceeds timeout, job terminates with TIMED_OUT."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        script_file = tmp_path / "infinite_loop.py"
        script_file.write_text(
            "import time\n"
            "while True:\n"
            "    time.sleep(0.05)\n",
            encoding="utf-8"
        )

        controller = ProcessController(
            command=["python", str(script_file)],
            cwd=tmp_path
        )

        controller.start()
        # Set a short timeout of 0.4 seconds
        exit_code = controller.wait(timeout=0.4)

        assert controller.status == JobStatus.TIMED_OUT
        assert controller.active_seconds() >= 0.4


def test_r1_demo_run_single_execution():
    """Bug R1 regression: demo-run should run the workload exactly once without calling run_sync again."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create quick mock demo script
        script_file = tmp_path / "mock_demo.py"
        script_file.write_text(
            "import time\n"
            "print('DEMO RUNNING')\n",
            encoding="utf-8"
        )

        run_sync_call_count = 0
        original_run_sync = JobRunner.run_sync

        def tracking_run_sync(self, *args, **kwargs):
            nonlocal run_sync_call_count
            run_sync_call_count += 1
            return original_run_sync(self, *args, **kwargs)

        with patch.object(JobRunner, "run_sync", tracking_run_sync):
            args = MagicMock()
            args.type = "pi"

            with patch("src.cli.gridctl.Path") as mock_path_cls:
                def path_side_effect(p):
                    if "demo_jobs" in str(p):
                        return script_file
                    return Path(p)
                mock_path_cls.side_effect = path_side_effect

                # Run demo command with very short sleeps
                with patch("time.sleep", return_value=None):
                    demo_run_cmd(args)

        # run_sync should have been called exactly ONCE (via run_async in the worker thread)
        assert run_sync_call_count == 1


def test_review1_demo_bridge_endpoints(api_client):
    """Review 1 demo bridge: verify /healthz and /api/v1/heartbeat endpoint contract."""
    # 1. Healthz check
    r_health = api_client.get("/healthz")
    assert r_health.status_code == 200
    health_data = r_health.json()
    assert health_data["status"] == "ok"
    assert health_data["service"] == "idlegrid-dispatcher"
    assert "nodes" in health_data

    # 2. Agent Heartbeat - Active state
    payload_active = {
        "node_id": "test-laptop-arya",
        "hostname": "Arya-ThinkPad",
        "state": "USER_ACTIVE",
        "os": "Windows",
        "metrics": {
            "cpu_usage_percent": 14.5,
            "ram_usage_percent": 45.0,
            "ram_total_mb": 16384,
            "ram_available_mb": 9011,
            "user_inactivity_sec": 2.5
        }
    }

    r_hb = api_client.post("/api/v1/heartbeat", json=payload_active)
    assert r_hb.status_code == 200
    hb_data = r_hb.json()
    assert hb_data["status"] == "ok"
    assert hb_data["node_status"] == NodeStatus.HOST_ACTIVE.value

    # Verify node exists in orchestrator
    node = orchestrator.nodes.get("test-laptop-arya")
    assert node is not None
    assert node.status == NodeStatus.HOST_ACTIVE
    assert node.source == "agent"
    assert node.os_name == "Windows"

    # 3. Agent Heartbeat - Idle state -> IDLE_RISKY in Phase 0
    payload_idle = {
        "node_id": "test-laptop-arya",
        "hostname": "Arya-ThinkPad",
        "state": "IDLE",
        "os": "Windows",
        "metrics": {
            "cpu_usage_percent": 2.1,
            "ram_usage_percent": 30.0,
            "ram_total_mb": 16384,
            "ram_available_mb": 11468,
            "user_inactivity_sec": 300.0
        }
    }
    r_hb2 = api_client.post("/api/v1/heartbeat", json=payload_idle)
    assert r_hb2.status_code == 200
    assert r_hb2.json()["node_status"] == NodeStatus.IDLE_RISKY.value

    # 4. Agent Staleness - Mark offline after 15s
    future_time = time.time() + 20.0
    stale_nodes = orchestrator.mark_stale_offline(now=future_time)
    assert "test-laptop-arya" in stale_nodes
    assert orchestrator.nodes["test-laptop-arya"].status == NodeStatus.OFFLINE
