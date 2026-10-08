"""
FastAPI application serving the REST API and the live Web Dashboard UI.
"""

import os
import sys
import io
import json
import asyncio
from pathlib import Path

# Ensure root workspace is on python path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from typing import Optional, List
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from src.dashboard.mock_cluster import ClusterOrchestrator
from src.packager.bundle import JobPackager

app = FastAPI(title="Predictive Idle-Compute Scheduler", version="1.0.0")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

STATIC_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

orchestrator = ClusterOrchestrator(workspace_root="./workspaces")


# --- REST API ENDPOINTS ---

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Renders the main glassmorphism dashboard page."""
    html_file = TEMPLATES_DIR / "index.html"
    if not html_file.exists():
        return HTMLResponse("<h1>Dashboard HTML template loading...</h1>")
    with open(html_file, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/api/cluster/nodes")
async def get_cluster_nodes():
    """Returns real-time status and ML Oracle predictions for all cluster nodes."""
    return [node.model_dump() for node in orchestrator.get_nodes()]


@app.post("/api/cluster/nodes/{node_id}/toggle-host-activity")
async def toggle_node_host(node_id: str):
    """Simulates node host starting/stopping activity to trigger instant preemption."""
    node = orchestrator.toggle_node_host_activity(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node.model_dump()


@app.post("/api/jobs/submit")
async def submit_job_bundle(
    bundle: Optional[UploadFile] = File(None),
    job_type: Optional[str] = Form(None)
):
    """
    Accepts either an uploaded .zip bundle from `gridctl submit`,
    or a preset `job_type` ('pi', 'matrix', 'ml') submitted from the Web UI.
    """
    if bundle:
        bundle_bytes = await bundle.read()
    elif job_type:
        demo_map = {
            "pi": Path("demo_jobs/monte_carlo_pi.py"),
            "matrix": Path("demo_jobs/matrix_stress.py"),
            "ml": Path("demo_jobs/tabular_ml_train.py")
        }
        script_path = demo_map.get(job_type)
        if not script_path or not script_path.exists():
            raise HTTPException(status_code=400, detail="Invalid job type or demo script missing")
        
        bundle_bytes = JobPackager.create_bundle(
            entrypoint_file=script_path,
            job_name=f"WebDemo_{job_type.upper()}",
            estimated_runtime_sec=20
        )
    else:
        raise HTTPException(status_code=400, detail="Must provide either a zip bundle or a job_type")

    job_record = orchestrator.submit_job(bundle_bytes)
    return job_record


@app.get("/api/jobs")
async def list_jobs():
    """Returns history and status of all submitted jobs."""
    return orchestrator.get_all_jobs()


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Returns details and execution metrics for a specific job."""
    job = orchestrator.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/jobs/{job_id}/logs")
async def get_job_logs(job_id: str):
    """Returns full stdout/stderr log output for a job."""
    job = orchestrator.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    logs = orchestrator.get_job_logs(job_id)
    return {"job_id": job_id, "logs": logs}


@app.get("/api/jobs/{job_id}/download")
async def download_job_artifacts(job_id: str):
    """Downloads the packaged result_bundle.zip for a completed job."""
    bundle_path = orchestrator.get_result_bundle_path(job_id)
    if not bundle_path or not bundle_path.exists():
        raise HTTPException(status_code=404, detail="Artifact bundle not ready or job incomplete")
    return FileResponse(
        path=str(bundle_path),
        filename=f"result_{job_id}.zip",
        media_type="application/zip"
    )


@app.post("/api/jobs/{job_id}/pause")
async def pause_job_endpoint(job_id: str):
    ok = orchestrator.pause_job(job_id)
    return {"job_id": job_id, "paused": ok}


@app.post("/api/jobs/{job_id}/resume")
async def resume_job_endpoint(job_id: str):
    ok = orchestrator.resume_job(job_id)
    return {"job_id": job_id, "resumed": ok}


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job_endpoint(job_id: str):
    orchestrator.cancel_job(job_id)
    return {"job_id": job_id, "cancelled": True}


# --- WEBSOCKET TELEMETRY STREAM ---

@app.websocket("/ws/telemetry")
async def ws_telemetry(websocket: WebSocket):
    """Pushes real-time cluster state, active job status, and logs over WebSocket."""
    await websocket.accept()
    orchestrator.ws_subscribers.append(websocket)
    try:
        while True:
            nodes_data = [n.model_dump() for n in orchestrator.get_nodes()]
            jobs_data = orchestrator.get_all_jobs()
            
            # Find newest/active job logs
            active_logs = {}
            for j in jobs_data[-3:]: # send logs for recent jobs
                jid = j["job_id"]
                active_logs[jid] = orchestrator.get_job_logs(jid)

            payload = {
                "nodes": nodes_data,
                "jobs": jobs_data,
                "logs": active_logs,
                "timestamp": asyncio.get_event_loop().time()
            }

            await websocket.send_json(payload)
            await asyncio.sleep(0.6)
    except (WebSocketDisconnect, Exception):
        if websocket in orchestrator.ws_subscribers:
            orchestrator.ws_subscribers.remove(websocket)


def start_server(host: str = "0.0.0.0", port: int = 8000):
    """Starts the Uvicorn web server."""
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_server()
