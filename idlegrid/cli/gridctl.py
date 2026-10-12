"""
gridctl: Command-Line Interface for the Predictive Idle-Compute Scheduler.
Enables developers to submit ML/compute jobs, query live status, tail logs,
inspect cluster nodes, and download result artifacts.
"""

import sys
import os
from pathlib import Path

# Ensure root workspace is on python path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Reconfigure standard output encoding for Windows compatibility
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import time
import argparse
from typing import List, Optional
import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.text import Text
from rich.syntax import Syntax
from rich import print as rprint

from src.packager.bundle import JobPackager, ResultUnpackager
from src.executor.runner import JobRunner
from src.common.models import JobStatus, NodeStatus

console = Console(legacy_windows=False)
DEFAULT_ENDPOINT = "http://localhost:8000"


def format_status(status_str: str) -> Text:
    status_str = str(status_str).upper()
    if status_str in ("COMPLETED", "SUCCESS"):
        return Text(f"● {status_str}", style="bold green")
    elif status_str in ("RUNNING", "RESUMING"):
        return Text(f"⚡ {status_str}", style="bold cyan")
    elif status_str in ("PAUSED", "PREEMPTED"):
        return Text(f"⏸ {status_str}", style="bold yellow")
    elif status_str in ("QUEUED", "ASSIGNED"):
        return Text(f"⏳ {status_str}", style="bold blue")
    elif status_str in ("FAILED", "ERROR"):
        return Text(f"✖ {status_str}", style="bold red")
    elif status_str in ("CANCELLED",):
        return Text(f"⊘ {status_str}", style="bold magenta")
    return Text(status_str, style="white")


def format_node_status(status_str: str) -> Text:
    status_str = str(status_str).upper()
    if status_str == "IDLE_SAFE":
        return Text("🟢 IDLE (SAFE)", style="bold green")
    elif status_str == "IDLE_RISKY":
        return Text("🟡 IDLE (RISKY)", style="bold yellow")
    elif status_str == "HOST_ACTIVE":
        return Text("🔴 HOST ACTIVE", style="bold red")
    elif status_str == "BUSY":
        return Text("⚡ BUSY COMPUTING", style="bold cyan")
    return Text(f"⚪ {status_str}", style="dim")


def submit_cmd(args):
    """Submits a job script and optional files to the grid."""
    entrypoint = Path(args.script)
    if not entrypoint.exists():
        console.print(f"[bold red]Error:[/] Entrypoint file '{entrypoint}' not found.")
        sys.exit(1)

    extra_files = [Path(p) for p in args.data] if args.data else []
    req_file = Path(args.requirements) if args.requirements else None

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Packaging job bundle and manifest...", total=None)
        
        bundle_bytes = JobPackager.create_bundle(
            entrypoint_file=entrypoint,
            extra_files=extra_files,
            job_name=args.name or entrypoint.stem,
            args=args.job_args or [],
            requirements_file=req_file,
            timeout_seconds=args.timeout or 1800,
            estimated_runtime_sec=args.estimated_runtime or 60
        )
        progress.update(task, description=f"Bundle packaged ({len(bundle_bytes) / 1024:.1f} KB)")

    if args.local:
        console.print("[bold yellow]Running locally via embedded JobRunner...[/]")
        runner = JobRunner(
            log_callback=lambda st, text: sys.stdout.write(text) if args.follow else None
        )
        res = runner.run_sync(bundle_source=bundle_bytes)
        
        console.print()
        console.print(Panel(
            f"[bold]Job ID:[/] {res.job_id}\n"
            f"[bold]Status:[/] {format_status(res.status).markup}\n"
            f"[bold]Exit Code:[/] {res.exit_code}\n"
            f"[bold]Duration:[/] {res.metrics.duration_seconds:.2f}s\n"
            f"[bold]Peak RAM:[/] {res.metrics.peak_ram_mb:.1f} MB\n"
            f"[bold]Pause/Preempt Count:[/] {res.metrics.pause_count}",
            title="🏁 Local Run Summary",
            border_style="green" if res.status == JobStatus.COMPLETED else "red"
        ))
        return

    # Submit to Remote Dispatcher API
    endpoint = args.endpoint.rstrip("/")
    url = f"{endpoint}/api/jobs/submit"

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold green]Uploading job bundle to Central Dispatcher..."),
            console=console
        ) as progress:
            progress.add_task("upload", total=None)
            files = {"bundle": (f"{entrypoint.stem}.zip", bundle_bytes, "application/zip")}
            response = requests.post(url, files=files, timeout=15)

        if response.status_code in (200, 201):
            data = response.json()
            job_id = data.get("job_id")
            console.print(Panel(
                f"[bold green]✓ Job successfully submitted to grid![/]\n\n"
                f"[bold]Job ID:[/] [cyan]{job_id}[/]\n"
                f"[bold]Job Name:[/] {data.get('job_name')}\n"
                f"[bold]Initial Status:[/] {format_status(data.get('status', 'QUEUED')).markup}\n"
                f"[bold]Assigned Node:[/] {data.get('assigned_node_id', 'Pending Dispatcher/Oracle routing')}\n\n"
                f"[dim]Commands to monitor:\n"
                f"  gridctl status {job_id}\n"
                f"  gridctl logs {job_id} --follow\n"
                f"  gridctl download {job_id}[/]",
                title="🚀 Job Submission Confirmed",
                border_style="bright_blue"
            ))

            if args.follow:
                follow_logs(job_id, endpoint)
        else:
            console.print(f"[bold red]API Error ({response.status_code}):[/] {response.text}")
    except requests.RequestException as e:
        console.print(f"[bold red]Connection Error:[/] Could not connect to Dispatcher at {endpoint}.")
        console.print(f"[yellow]Tip: Run with --local to execute locally, or start the dashboard/dispatcher server.[/]")


def status_cmd(args):
    """Retrieves current job status from Dispatcher API."""
    endpoint = args.endpoint.rstrip("/")
    url = f"{endpoint}/api/jobs/{args.job_id}"

    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            table = Table(title=f"📊 Job Status: {args.job_id}", border_style="cyan", show_header=False)
            table.add_column("Property", style="bold white", width=22)
            table.add_column("Value", style="cyan")

            table.add_row("Status", format_status(data.get("status", "UNKNOWN")))
            table.add_row("Job Name", data.get("job_name", "-"))
            table.add_row("Entrypoint", data.get("entrypoint", "-"))
            table.add_row("Assigned Node", data.get("assigned_node_id") or "Awaiting Oracle Match")
            table.add_row("Duration", f"{data.get('duration_seconds', 0):.2f}s")
            table.add_row("Preemption Pauses", str(data.get("pause_count", 0)))
            table.add_row("Peak RAM", f"{data.get('peak_ram_mb', 0):.1f} MB")
            table.add_row("Artifacts", ", ".join(data.get("artifact_files", [])) or "None")

            console.print(table)
        else:
            console.print(f"[bold red]Job not found or error ({resp.status_code}):[/] {resp.text}")
    except requests.RequestException as e:
        console.print(f"[bold red]Failed to connect to {endpoint}:[/] {e}")


def follow_logs(job_id: str, endpoint: str):
    """Polls/streams logs until completion."""
    console.print(f"[dim]Streaming logs for {job_id}...[/]")
    url = f"{endpoint}/api/jobs/{job_id}/logs"
    status_url = f"{endpoint}/api/jobs/{job_id}"
    last_len = 0

    while True:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                full_log = r.json().get("logs", "")
                if len(full_log) > last_len:
                    new_chunk = full_log[last_len:]
                    sys.stdout.write(new_chunk)
                    sys.stdout.flush()
                    last_len = len(full_log)

            st_r = requests.get(status_url, timeout=5)
            if st_r.status_code == 200:
                st = st_r.json().get("status")
                if st in ("COMPLETED", "FAILED", "CANCELLED"):
                    console.print(f"\n[bold]Execution terminated with status: {format_status(st).markup}[/]")
                    break
        except Exception:
            pass
        time.sleep(1.0)


def logs_cmd(args):
    """Fetches or tails logs of a remote job."""
    endpoint = args.endpoint.rstrip("/")
    if args.follow:
        follow_logs(args.job_id, endpoint)
    else:
        url = f"{endpoint}/api/jobs/{args.job_id}/logs"
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                logs = r.json().get("logs", "(no logs available)")
                console.print(Panel(Syntax(logs, "python", theme="monokai", word_wrap=True), title=f"Logs: {args.job_id}"))
            else:
                console.print(f"[bold red]Error fetching logs ({r.status_code}):[/] {r.text}")
        except requests.RequestException as e:
            console.print(f"[bold red]Connection error:[/] {e}")


def download_cmd(args):
    """Downloads result artifacts for a completed job."""
    endpoint = args.endpoint.rstrip("/")
    url = f"{endpoint}/api/jobs/{args.job_id}/download"
    out_dir = Path(args.output or f"./results/{args.job_id}")

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold green]Downloading result artifacts bundle..."),
            console=console
        ) as progress:
            progress.add_task("dl", total=None)
            r = requests.get(url, timeout=30)

        if r.status_code == 200:
            result = ResultUnpackager.extract_result_bundle(r.content, out_dir)
            console.print(Panel(
                f"[bold green]✓ Artifacts extracted successfully to:[/] [cyan]{out_dir.resolve()}[/]\n\n"
                f"[bold]Job Status:[/] {format_status(result.status).markup}\n"
                f"[bold]Exit Code:[/] {result.exit_code}\n"
                f"[bold]Duration:[/] {result.metrics.duration_seconds:.2f}s\n"
                f"[bold]Extracted Files:[/] {', '.join(result.artifact_files)}",
                title="📦 Results Downloaded",
                border_style="green"
            ))
        else:
            console.print(f"[bold red]Download failed ({r.status_code}):[/] {r.text}")
    except requests.RequestException as e:
        console.print(f"[bold red]Connection error:[/] {e}")


def cluster_cmd(args):
    """Queries and displays live cluster nodes and ML Oracle predictions."""
    endpoint = args.endpoint.rstrip("/")
    url = f"{endpoint}/api/cluster/nodes"

    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            nodes = r.json()
            table = Table(title="🖥️  Live Idle-Compute Cluster Nodes", border_style="bright_blue")
            table.add_column("Node ID", style="bold white")
            table.add_column("Hostname / Host", style="cyan")
            table.add_column("State", style="white")
            table.add_column("CPU %", justify="right")
            table.add_column("RAM", justify="right")
            table.add_column("ML Oracle Pred. Window", style="bold magenta", justify="right")
            table.add_column("Current Job", style="yellow")

            for n in nodes:
                pred_sec = n.get("predicted_idle_window_seconds", 0)
                pred_str = f"{pred_sec // 60:.0f}m {pred_sec % 60:.0f}s" if pred_sec > 0 else "0s (Active Host)"
                table.add_row(
                    n.get("node_id", "-"),
                    n.get("hostname", "-"),
                    format_node_status(n.get("status", "OFFLINE")),
                    f"{n.get('cpu_percent', 0):.1f}%",
                    f"{n.get('ram_used_mb', 0):.0f} / {n.get('ram_total_mb', 0):.0f} MB",
                    pred_str,
                    n.get("current_job_id") or "[dim]idle[/]"
                )

            console.print(table)
        else:
            console.print(f"[bold red]Error fetching cluster topology ({r.status_code}):[/] {r.text}")
    except requests.RequestException as e:
        console.print(f"[bold red]Could not reach cluster at {endpoint}:[/] {e}")


def demo_run_cmd(args):
    """Executes a full interactive demo showcasing preemption, suspension, and result extraction."""
    console.print(Panel.fit(
        "[bold cyan]PREDICTIVE IDLE-COMPUTE SCHEDULER - ROLE 5 DEMO[/]\n"
        "[dim]Simulating job packaging, sandboxed execution, instant host preemption, and artifact collection.[/]",
        border_style="cyan"
    ))

    script_map = {
        "pi": Path("demo_jobs/monte_carlo_pi.py"),
        "matrix": Path("demo_jobs/matrix_stress.py"),
        "ml": Path("demo_jobs/tabular_ml_train.py")
    }

    target_script = script_map.get(args.type, script_map["pi"])
    console.print(f"[bold green]1. Packaging target job:[/] [white]{target_script}[/]")

    bundle_bytes = JobPackager.create_bundle(
        entrypoint_file=target_script,
        job_name=f"demo_{args.type}",
        estimated_runtime_sec=30
    )
    console.print(f"   ✓ Bundle generated ({len(bundle_bytes)/1024:.1f} KB)")

    console.print(f"\n[bold green]2. Launching Worker Sandbox Executor...[/]")
    runner = JobRunner(
        log_callback=lambda st, text: sys.stdout.write(f"[NODE-OUT] {text}")
    )

    runner.setup_workspace(bundle_bytes)
    runner.run_async()

    # Wait 2 seconds of execution
    time.sleep(2.0)

    console.print(f"\n[bold red]⚡ [SIMULATION EVENT] Laptop host moved mouse / launched game![/]")
    console.print(f"[bold yellow]   Triggering instant preemption via psutil.Process.suspend()...[/]")
    runner.pause()
    console.print(f"   ✓ Process paused! Host CPU freed immediately (Status: {runner.current_status})")
    
    # Stay paused for 2.5 seconds to demonstrate
    time.sleep(2.5)

    console.print(f"\n[bold green]⚡ [SIMULATION EVENT] Host is idle again (ML Oracle confirmed safe window).[/]")
    console.print(f"[bold cyan]   Resuming process execution via psutil.Process.resume()...[/]")
    runner.resume()

    # Wait for completion
    if runner.controller:
        runner.controller.wait()

    res = runner.run_sync() # Harvests packaged results
    
    console.print(f"\n[bold green]3. Harvesting Output Artifacts...[/]")
    out_dir = Path(f"./demo_results/{res.job_id}")
    ResultUnpackager.extract_result_bundle(runner.workspace_dir / "result_bundle.zip", out_dir)

    console.print(Panel(
        f"[bold green]✓ Full Demonstration Run Complete![/]\n\n"
        f"[bold]Job ID:[/] {res.job_id}\n"
        f"[bold]Final Status:[/] {format_status(res.status).markup}\n"
        f"[bold]Total Duration:[/] {res.metrics.duration_seconds:.2f}s\n"
        f"[bold]Preemption Pauses:[/] {res.metrics.pause_count} (Total Paused: {res.metrics.total_pause_duration_sec:.2f}s)\n"
        f"[bold]Peak RAM Sampled:[/] {res.metrics.peak_ram_mb:.1f} MB\n"
        f"[bold]Artifacts Saved to:[/] {out_dir.resolve()}",
        title="🎉 Demo Execution Complete",
        border_style="green"
    ))


def cli_main():
    parser = argparse.ArgumentParser(
        prog="gridctl",
        description="Predictive Idle-Compute Scheduler CLI (Role 5 Integration)"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # SUBMIT
    p_sub = subparsers.add_parser("submit", help="Submit a compute job to the grid")
    p_sub.add_argument("script", help="Path to main Python script (e.g. train.py)")
    p_sub.add_argument("--name", help="Human-readable job name")
    p_sub.add_argument("--data", nargs="+", help="Extra data files/folders to bundle")
    p_sub.add_argument("--requirements", "-r", help="Path to requirements.txt")
    p_sub.add_argument("--job-args", nargs="+", help="Arguments to pass to the user script")
    p_sub.add_argument("--timeout", type=int, default=1800, help="Job timeout in seconds")
    p_sub.add_argument("--estimated-runtime", type=int, default=60, help="Estimated duration in seconds")
    p_sub.add_argument("--follow", "-f", action="store_true", help="Follow and stream logs immediately")
    p_sub.add_argument("--local", action="store_true", help="Execute locally inside standalone runner")
    p_sub.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Dispatcher API endpoint")
    p_sub.set_defaults(func=submit_cmd)

    # STATUS
    p_stat = subparsers.add_parser("status", help="Get status of a submitted job")
    p_stat.add_argument("job_id", help="Job ID")
    p_stat.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Dispatcher API endpoint")
    p_stat.set_defaults(func=status_cmd)

    # LOGS
    p_logs = subparsers.add_parser("logs", help="View or follow logs of a job")
    p_logs.add_argument("job_id", help="Job ID")
    p_logs.add_argument("--follow", "-f", action="store_true", help="Stream live logs")
    p_logs.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Dispatcher API endpoint")
    p_logs.set_defaults(func=logs_cmd)

    # DOWNLOAD
    p_dl = subparsers.add_parser("download", help="Download result artifacts from a completed job")
    p_dl.add_argument("job_id", help="Job ID")
    p_dl.add_argument("--output", "-o", help="Target output folder")
    p_dl.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Dispatcher API endpoint")
    p_dl.set_defaults(func=download_cmd)

    # CLUSTER
    p_cls = subparsers.add_parser("cluster", help="View live cluster nodes and ML Oracle idle predictions")
    p_cls.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Dispatcher API endpoint")
    p_cls.set_defaults(func=cluster_cmd)

    # DEMO RUN
    p_demo = subparsers.add_parser("demo-run", help="Run full interactive demo with simulated preemption")
    p_demo.add_argument("--type", choices=["pi", "matrix", "ml"], default="pi", help="Demo job type")
    p_demo.set_defaults(func=demo_run_cmd)

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    cli_main()
