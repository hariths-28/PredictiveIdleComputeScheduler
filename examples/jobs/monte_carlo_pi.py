"""
Demo Job 1: Distributed Monte Carlo Pi Estimation.
Simulates random darts thrown at a 1x1 quadrant to approximate Pi.
Generates step-by-step telemetry and writes output/pi_estimate.csv.
"""

import os
import sys
import time
import math
import random
import csv
import json
from pathlib import Path

def run_monte_carlo(total_samples: int = 5_000_000, checkpoint_interval: int = 1_000_000):
    print(f"=== [GRID JOB] Starting Monte Carlo Pi Estimation ===")
    print(f"Total Samples: {total_samples:,} | Checkpoint Every: {checkpoint_interval:,} samples")
    print(f"Process PID: {os.getpid()} | Python Interpreter: {sys.executable}")
    sys.stdout.flush()

    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)

    inside_circle = 0
    start_time = time.time()

    checkpoints = []

    for i in range(1, total_samples + 1):
        x = random.random()
        y = random.random()
        if x * x + y * y <= 1.0:
            inside_circle += 1

        if i % checkpoint_interval == 0:
            current_pi = 4.0 * inside_circle / i
            error = abs(current_pi - math.pi)
            elapsed = time.time() - start_time
            print(f"[{elapsed:6.2f}s] Sample: {i:9,d} | Pi Estimate: {current_pi:.6f} | Error: {error:.6e}")
            sys.stdout.flush()

            checkpoints.append({
                "samples": i,
                "pi_estimate": current_pi,
                "error": error,
                "elapsed_sec": round(elapsed, 3)
            })
            # Small sleep to simulate sustained background compute without locking CPU 100% instantly
            time.sleep(0.1)

    final_pi = 4.0 * inside_circle / total_samples
    total_time = time.time() - start_time
    final_error = abs(final_pi - math.pi)

    print(f"=== COMPLETED in {total_time:.2f}s ===")
    print(f"True Pi:     {math.pi:.10f}")
    print(f"Estimate:    {final_pi:.10f}")
    print(f"Final Error: {final_error:.6e}")
    sys.stdout.flush()

    # Write CSV artifact
    csv_path = output_dir / "pi_estimate.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["samples", "pi_estimate", "error", "elapsed_sec"])
        writer.writeheader()
        writer.writerows(checkpoints)

    # Write JSON summary
    summary_path = output_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "task": "monte_carlo_pi",
            "total_samples": total_samples,
            "final_pi_estimate": final_pi,
            "true_pi": math.pi,
            "error": final_error,
            "duration_seconds": round(total_time, 3)
        }, f, indent=2)

    print(f"Artifacts successfully written to '{csv_path}' and '{summary_path}'")
    sys.stdout.flush()

if __name__ == "__main__":
    samples = 3_000_000
    if len(sys.argv) > 1:
        try:
            samples = int(sys.argv[1])
        except ValueError:
            pass
    run_monte_carlo(total_samples=samples, checkpoint_interval=samples // 5)
