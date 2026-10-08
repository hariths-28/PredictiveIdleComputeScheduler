"""
Demo Job 3: Machine Learning Model Training (Scikit-Learn).
Trains a Random Forest classifier on a synthetic dataset, evaluates metrics,
and saves output artifacts (metrics JSON and prediction CSV).
"""

import os
import sys
import time
import json
import csv
from pathlib import Path
import numpy as np
from sklearn.datasets import make_classification
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

def train_model(n_samples: int = 50000, n_trees: int = 100):
    print(f"=== [GRID JOB] Distributed Scikit-Learn Model Training ===")
    print(f"Dataset Size: {n_samples:,} rows | Number of Trees: {n_trees}")
    print(f"Process PID: {os.getpid()}")
    sys.stdout.flush()

    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    print("[1/4] Generating synthetic tabular dataset (20 features, 2 classes)...")
    sys.stdout.flush()
    X, y = make_classification(
        n_samples=n_samples,
        n_features=20,
        n_informative=12,
        n_redundant=4,
        random_state=42
    )

    print("[2/4] Splitting train/test sets (80/20)...")
    sys.stdout.flush()
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    print(f"[3/4] Fitting RandomForestClassifier with {n_trees} estimators...")
    sys.stdout.flush()
    clf = RandomForestClassifier(n_estimators=n_trees, max_depth=12, random_state=42, n_jobs=-1)
    fit_start = time.time()
    clf.fit(X_train, y_train)
    fit_time = time.time() - fit_start
    print(f"      Model training completed in {fit_time:.2f}s")
    sys.stdout.flush()

    print("[4/4] Evaluating on holdout test set...")
    sys.stdout.flush()
    y_pred = clf.predict(X_test)
    y_proba = clf.predict_proba(X_test)[:, 1]

    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred)
    rec = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)

    total_time = time.time() - t0
    print(f"=== Training Pipeline Finished in {total_time:.2f}s ===")
    print(f"Test Accuracy:  {acc * 100:.2f}%")
    print(f"Precision:      {prec:.4f}")
    print(f"Recall:         {rec:.4f}")
    print(f"F1 Score:       {f1:.4f}")
    sys.stdout.flush()

    # Save metrics JSON
    metrics_path = output_dir / "model_metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump({
            "task": "tabular_random_forest",
            "samples": n_samples,
            "n_trees": n_trees,
            "accuracy": round(acc, 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1_score": round(f1, 4),
            "fit_time_sec": round(fit_time, 3),
            "total_time_sec": round(total_time, 3)
        }, f, indent=2)

    # Save sample predictions CSV
    pred_path = output_dir / "predictions.csv"
    with open(pred_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["sample_id", "true_label", "predicted_label", "confidence"])
        for idx in range(min(500, len(y_test))):
            writer.writerow([idx, int(y_test[idx]), int(y_pred[idx]), round(float(y_proba[idx]), 4)])

    print(f"Metrics saved to '{metrics_path}'")
    print(f"Predictions sample saved to '{pred_path}'")
    sys.stdout.flush()

if __name__ == "__main__":
    samples = 30000
    trees = 50
    if len(sys.argv) > 1:
        try:
            samples = int(sys.argv[1])
        except ValueError:
            pass
    if len(sys.argv) > 2:
        try:
            trees = int(sys.argv[2])
        except ValueError:
            pass
    train_model(n_samples=samples, n_trees=trees)
