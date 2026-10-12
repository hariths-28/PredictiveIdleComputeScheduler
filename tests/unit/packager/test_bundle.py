"""
Unit tests for JobPackager, JobUnpackager, ResultPackager, and ResultUnpackager.
"""

import os
import tempfile
import pytest
from pathlib import Path

from src.packager.bundle import JobPackager, JobUnpackager, ResultPackager, ResultUnpackager
from src.common.models import JobStatus, JobResult, ExecutionMetrics


def test_job_package_and_unpackage():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create a mock entrypoint script
        entrypoint = tmp_path / "mock_train.py"
        entrypoint.write_text("print('Hello Grid'); open('output/model.txt', 'w').write('trained_weights')", encoding="utf-8")

        # Create a mock dataset file
        data_file = tmp_path / "dataset.csv"
        data_file.write_text("id,val\n1,100\n2,200", encoding="utf-8")

        # Package bundle
        bundle_bytes = JobPackager.create_bundle(
            entrypoint_file=entrypoint,
            extra_files=[data_file],
            job_name="unit_test_job",
            args=["--epochs", "5"],
            estimated_runtime_sec=45
        )

        assert len(bundle_bytes) > 0

        # Unpack bundle into another directory
        extract_dir = tmp_path / "extracted_workspace"
        manifest = JobUnpackager.extract_bundle(bundle_bytes, extract_dir)

        assert manifest.job_name == "unit_test_job"
        assert manifest.entrypoint == "mock_train.py"
        assert manifest.args == ["--epochs", "5"]
        assert manifest.estimated_runtime_sec == 45
        assert (extract_dir / "mock_train.py").exists()
        assert (extract_dir / "dataset.csv").exists()
        assert (extract_dir / "output").exists()


def test_result_package_and_unpackage():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        ws_dir = tmp_path / "workspace"
        ws_dir.mkdir()
        out_dir = ws_dir / "output"
        out_dir.mkdir()

        # Write sample output artifacts
        (out_dir / "predictions.csv").write_text("id,pred\n1,0.95\n2,0.88", encoding="utf-8")
        (ws_dir / "stdout.log").write_text("Epoch 1/5 finished\nEpoch 5/5 finished\n", encoding="utf-8")

        job_result = JobResult(
            job_id="job_test_123",
            status=JobStatus.COMPLETED,
            exit_code=0,
            stdout="Epoch 1/5 finished\nEpoch 5/5 finished\n",
            metrics=ExecutionMetrics(duration_seconds=12.5, peak_ram_mb=128.0)
        )

        # Package results
        result_bundle_bytes = ResultPackager.create_result_bundle(
            workspace_dir=ws_dir,
            job_result=job_result
        )

        assert len(result_bundle_bytes) > 0

        # Unpack on client
        client_dir = tmp_path / "client_results"
        extracted_result = ResultUnpackager.extract_result_bundle(result_bundle_bytes, client_dir)

        assert extracted_result.job_id == "job_test_123"
        assert extracted_result.status == JobStatus.COMPLETED
        assert extracted_result.metrics.duration_seconds == 12.5
        assert (client_dir / "output" / "predictions.csv").exists()
        assert (client_dir / "logs" / "stdout.log").exists()
