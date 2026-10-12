"""
Review 1 demo bridge: real laptops appear on the dashboard through node-agent heartbeats.
"""

import time

import pytest
from fastapi.testclient import TestClient

from idlegrid.common.models import NodeStatus
from idlegrid.dispatcher.app import app
from idlegrid.dispatcher.mock_cluster import ClusterOrchestrator


def agent_payload(node_id="laptop-harith", state="USER_ACTIVE", **metrics):
    """Shape produced by idlegrid.agent.client.HeartbeatSender.build_payload."""
    base_metrics = {
        "cpu_usage_percent": 12.5,
        "ram_usage_percent": 50.0,
        "ram_total_mb": 16384.0,
        "ram_available_mb": 8192.0,
        "user_inactivity_sec": 3.0,
    }
    base_metrics.update(metrics)
    return {
        "node_id": node_id,
        "timestamp": time.time(),
        "state": state,
        "hostname": f"{node_id}-host",
        "os": "Windows",
        "os_release": "11",
        "metrics": base_metrics,
    }


@pytest.fixture
def orchestrator(tmp_path):
    orch = ClusterOrchestrator(workspace_root=str(tmp_path / "ws"), sim_nodes=False)
    yield orch
    orch._running = False


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_sim_nodes_off_starts_empty(orchestrator):
    assert orchestrator.get_nodes() == []


@pytest.mark.parametrize(
    "state, expected",
    [
        ("USER_ACTIVE", NodeStatus.HOST_ACTIVE),
        ("ACTIVE", NodeStatus.HOST_ACTIVE),
        ("BUSY", NodeStatus.HOST_BUSY),
        ("IDLE", NodeStatus.IDLE_RISKY),
        ("UNKNOWN", NodeStatus.UNSCHEDULABLE),
        ("SOMETHING_NEW", NodeStatus.UNSCHEDULABLE),
    ],
)
def test_agent_state_maps_to_node_status(orchestrator, state, expected):
    node = orchestrator.register_heartbeat(agent_payload(state=state), "10.0.0.5")
    assert node.status == expected
    assert node.source == "agent"


def test_heartbeat_metrics_are_mapped(orchestrator):
    node = orchestrator.register_heartbeat(agent_payload(), "10.0.0.5")
    assert node.hostname == "laptop-harith-host"
    assert node.ip_address == "10.0.0.5"
    assert node.os_name == "Windows"
    assert node.cpu_percent == 12.5
    assert node.ram_percent == 50.0
    assert node.ram_total_mb == 16384.0
    assert node.ram_used_mb == 8192.0
    assert node.idle_time_seconds == 3.0
    assert node.is_user_active is True


def test_repeat_heartbeat_updates_same_node(orchestrator):
    orchestrator.register_heartbeat(agent_payload(state="USER_ACTIVE"), "10.0.0.5")
    orchestrator.register_heartbeat(agent_payload(state="IDLE"), "10.0.0.5")
    nodes = orchestrator.get_nodes()
    assert len(nodes) == 1
    assert nodes[0].status == NodeStatus.IDLE_RISKY


def test_real_laptop_is_never_picked_for_a_job(orchestrator):
    orchestrator.register_heartbeat(agent_payload(state="IDLE"), "10.0.0.5")
    assert orchestrator._select_best_node(estimated_runtime=60) is None


def test_simulate_button_does_not_change_real_laptop(orchestrator):
    orchestrator.register_heartbeat(agent_payload(state="USER_ACTIVE"), "10.0.0.5")
    node = orchestrator.toggle_node_host_activity("laptop-harith")
    assert node.status == NodeStatus.HOST_ACTIVE


def test_stale_laptop_goes_offline(orchestrator):
    orchestrator.register_heartbeat(agent_payload(), "10.0.0.5")
    assert orchestrator.mark_stale_offline() == []
    later = time.time() + orchestrator.OFFLINE_AFTER_SEC + 5
    assert orchestrator.mark_stale_offline(now=later) == ["laptop-harith"]
    assert orchestrator.get_nodes()[0].status == NodeStatus.OFFLINE
    # A fresh heartbeat brings it back.
    node = orchestrator.register_heartbeat(agent_payload(state="IDLE"), "10.0.0.5")
    assert node.status == NodeStatus.IDLE_RISKY


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "idlegrid-dispatcher"


def test_heartbeat_endpoint_registers_laptop(client):
    r = client.post("/api/v1/heartbeat", json=agent_payload(node_id="laptop-e2e", state="IDLE"))
    assert r.status_code == 200
    assert r.json()["node_status"] == "IDLE_RISKY"

    nodes = {n["node_id"]: n for n in client.get("/api/cluster/nodes").json()}
    assert nodes["laptop-e2e"]["source"] == "agent"
    assert nodes["laptop-e2e"]["status"] == "IDLE_RISKY"


@pytest.mark.parametrize(
    "payload",
    [
        {"metrics": {}},
        {"node_id": "", "metrics": {}},
        {"node_id": "laptop-x"},
        {"node_id": "laptop-x", "metrics": "not-a-dict"},
    ],
)
def test_heartbeat_endpoint_rejects_bad_payload(client, payload):
    assert client.post("/api/v1/heartbeat", json=payload).status_code == 422
