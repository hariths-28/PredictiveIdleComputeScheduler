import argparse
import sys
import os

# Add local directory to path for clean imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from node_agent.config import NodeConfig
from node_agent.agent import NodeAgent

import subprocess
import time
import threading

def parse_args():
    parser = argparse.ArgumentParser(description="Predictive Idle-Compute Node Agent (Role 1: The Spy)")
    parser.add_argument(
        "--config",
        type=str,
        default="config.json",
        help="Path to JSON configuration file (default: config.json)"
    )
    parser.add_argument(
        "--dispatcher",
        type=str,
        default=None,
        help="Dispatcher REST API URL endpoint"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Telemetry / Heartbeat interval in seconds (default: 5s, or 15s in --log-only mode)"
    )
    parser.add_argument(
        "--node-id",
        type=str,
        default=None,
        help="Custom Node ID override"
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="Logging level"
    )
    # Phase 0 & Review 1 Flags
    parser.add_argument(
        "--log-only",
        action="store_true",
        help="Run in headless logging mode (Phase 0 Step 1): logs 15s telemetry directly to CSV without requiring Dispatcher"
    )
    parser.add_argument(
        "--csv-file",
        type=str,
        default=None,
        help="Path to telemetry CSV file (default: laptop_telemetry.csv)"
    )
    parser.add_argument(
        "--watch-pid",
        type=int,
        default=None,
        help="Attach Kill Switch to a running process PID"
    )
    parser.add_argument(
        "--simulate-job",
        action="store_true",
        help="Spawn a dummy background workload for Review 1 demo to showcase live Kill Switch preemption upon user movement"
    )
    return parser.parse_args()

def main():
    args = parse_args()
    
    # Load configuration from file if exists, otherwise defaults
    config = NodeConfig.load_from_file(args.config)

    # Apply CLI overrides if provided
    if args.dispatcher:
        config.dispatcher_url = args.dispatcher
    if args.interval:
        config.heartbeat_interval = args.interval
    if args.node_id:
        config.node_id = args.node_id
    if args.log_level:
        config.log_level = args.log_level
    if args.csv_file:
        config.csv_output_file = args.csv_file

    agent = NodeAgent(config)

    # If --simulate-job is requested, spawn a dummy worker process to demonstrate preemption
    simulated_proc = None
    if args.simulate_job:
        print("[DEMO] Spawning background worker process to demonstrate Kill Switch preemption...")
        sim_code = "import time; print('Worker running...'); [time.sleep(1) for _ in range(300)]"
        simulated_proc = subprocess.Popen([sys.executable, "-c", sim_code])
        agent.register_job(simulated_proc.pid, job_id="demo-ml-search-job")
        print(f"[DEMO] Guarded PID {simulated_proc.pid} under Kill Switch. Move mouse / type to trigger preemption!")

    if args.watch_pid:
        agent.register_job(args.watch_pid, job_id=f"job-{args.watch_pid}")

    try:
        if args.log_only:
            # Standalone Phase 0 harvester mode (every 15s by default)
            target_csv = args.csv_file or "laptop_telemetry.csv"
            interval = args.interval or 15
            agent.start_log_only(output_file=target_csv, interval=interval)
        else:
            agent.start()
    finally:
        if simulated_proc and simulated_proc.poll() is None:
            simulated_proc.terminate()

if __name__ == "__main__":
    main()
