"""
End-to-End API and Integration test for dashboard endpoints, preemption, and job dispatch.
"""

import time
import requests
import pytest
from fastapi.testclient import TestClient

from src.dashboard.app import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_html_and_static_endpoints(client):
    # Test HTML dashboard
    r_html = client.get("/")
    assert r_html.status_code == 200
    assert "PREDICTIVE IDLE-COMPUTE GRID" in r_html.text

    # Test CSS
    r_css = client.get("/static/css/styles.css")
    assert r_css.status_code == 200
    assert "backdrop-filter" in r_css.text

    # Test JS
    r_js = client.get("/static/js/app.js")
    assert r_js.status_code == 200
    assert "initWebSocket" in r_js.text


def test_cluster_nodes_and_preemption_toggle(client):
    # Get cluster nodes
    r_nodes = client.get("/api/cluster/nodes")
    assert r_nodes.status_code == 200
    nodes = r_nodes.json()
    assert len(nodes) >= 4

    target_node = nodes[0]["node_id"]
    initial_status = nodes[0]["status"]

    # Toggle host activity
    r_toggle = client.post(f"/api/cluster/nodes/{target_node}/toggle-host-activity")
    assert r_toggle.status_code == 200
    new_status = r_toggle.json()["status"]
    assert new_status != initial_status

    # Toggle back
    r_toggle_back = client.post(f"/api/cluster/nodes/{target_node}/toggle-host-activity")
    assert r_toggle_back.status_code == 200
    assert r_toggle_back.json()["status"] == initial_status


def test_job_submission_and_lifecycle(client):
    # Submit demo ML job
    r_sub = client.post("/api/jobs/submit", data={"job_type": "pi"})
    assert r_sub.status_code == 200
    data = r_sub.json()
    job_id = data["job_id"]
    assert data["job_name"] == "WebDemo_PI"

    # Wait for execution
    time.sleep(2.5)

    # Check status
    r_stat = client.get(f"/api/jobs/{job_id}")
    assert r_stat.status_code == 200
    stat_data = r_stat.json()
    assert stat_data["status"] in ("RUNNING", "COMPLETED")

    # Check logs
    r_logs = client.get(f"/api/jobs/{job_id}/logs")
    assert r_logs.status_code == 200
    assert "Monte Carlo Pi Estimation" in r_logs.json()["logs"]

    # Wait for completion if still running
    max_wait = 10
    while stat_data["status"] == "RUNNING" and max_wait > 0:
        time.sleep(1.0)
        stat_data = client.get(f"/api/jobs/{job_id}").json()
        max_wait -= 1

    assert stat_data["status"] == "COMPLETED"

    # Download artifacts
    r_dl = client.get(f"/api/jobs/{job_id}/download")
    assert r_dl.status_code == 200
    assert len(r_dl.content) > 100
