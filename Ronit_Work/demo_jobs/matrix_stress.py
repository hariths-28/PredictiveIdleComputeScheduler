"""
Demo Job 2: Matrix Multiplication Compute Stress Test.
Performs intensive floating-point tensor operations to simulate heavy scientific workloads.
Writes output/matrix_benchmarks.csv and output/matrix_stats.json.
"""

import os
import sys
import time
import json
import csv
from pathlib import Path
import numpy as np

def run_matrix_benchmark(matrix_size: int = 1500, iterations: int = 4):
    print(f"=== [GRID JOB] Matrix Multiplication Stress Test ===")
    print(f"Matrix Dimension: {matrix_size}x{matrix_size} | Iterations: {iterations}")
    print(f"Process PID: {os.getpid()}")
    sys.stdout.flush()

    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    total_start = time.time()

    for it in range(1, iterations + 1):
        print(f"[Iter {it}/{iterations}] Generating random matrices ({matrix_size}x{matrix_size})...")
        sys.stdout.flush()
        
        t0 = time.time()
        A = np.random.randn(matrix_size, matrix_size).astype(np.float32)
        B = np.random.randn(matrix_size, matrix_size).astype(np.float32)
        gen_time = time.time() - t0

        print(f"[Iter {it}/{iterations}] Performing dot product C = A @ B ...")
        sys.stdout.flush()
        
        t1 = time.time()
        C = np.matmul(A, B)
        mult_time = time.time() - t1

        # GFLOPS calculation: 2 * N^3 operations
        gflops = (2.0 * (matrix_size ** 3)) / (mult_time * 1e9)
        c_mean = float(np.mean(C))
        c_std = float(np.std(C))

        print(f"[Iter {it}/{iterations}] Done in {mult_time:.3f}s ({gflops:.2f} GFLOPS) | Mean={c_mean:.4f}, Std={c_std:.4f}")
        sys.stdout.flush()

        results.append({
            "iteration": it,
            "matrix_size": matrix_size,
            "mult_time_sec": round(mult_time, 4),
            "gflops": round(gflops, 2),
            "mean": round(c_mean, 4),
            "std": round(c_std, 4)
        })
        time.sleep(0.2)

    total_time = time.time() - total_start
    avg_gflops = sum(r["gflops"] for r in results) / len(results)

    print(f"=== Matrix Benchmark Completed in {total_time:.2f}s | Avg Throughput: {avg_gflops:.2f} GFLOPS ===")
    sys.stdout.flush()

    # Save benchmark CSV
    csv_file = output_dir / "matrix_benchmarks.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["iteration", "matrix_size", "mult_time_sec", "gflops", "mean", "std"])
        writer.writeheader()
        writer.writerows(results)

    # Save stats JSON
    json_file = output_dir / "matrix_stats.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump({
            "task": "matrix_stress_test",
            "matrix_dimension": matrix_size,
            "iterations": iterations,
            "total_duration_sec": round(total_time, 3),
            "average_gflops": round(avg_gflops, 2),
            "results": results
        }, f, indent=2)

    print(f"Results written to '{csv_file}' and '{json_file}'")
    sys.stdout.flush()

if __name__ == "__main__":
    size = 1200
    iters = 3
    if len(sys.argv) > 1:
        try:
            size = int(sys.argv[1])
        except ValueError:
            pass
    if len(sys.argv) > 2:
        try:
            iters = int(sys.argv[2])
        except ValueError:
            pass
    run_matrix_benchmark(matrix_size=size, iterations=iters)
