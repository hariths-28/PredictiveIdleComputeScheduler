"""
Job packaging and artifact management engine.
Handles bundling user code, datasets, requirements, and manifests into portable grid bundles,
as well as extracting workspaces on worker nodes and harvesting output artifacts.
"""

import os
import io
import json
import zipfile
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Union
import uuid
import time

from src.common.models import JobManifest, JobResult, JobStatus, ExecutionMetrics


class JobPackager:
    """Packages Python scripts, dependencies, datasets, and manifests into a portable zip bundle."""

    @staticmethod
    def create_bundle(
        entrypoint_file: Union[str, Path],
        extra_files: Optional[List[Union[str, Path]]] = None,
        job_name: Optional[str] = None,
        args: Optional[List[str]] = None,
        requirements_file: Optional[Union[str, Path]] = None,
        env_vars: Optional[Dict[str, str]] = None,
        timeout_seconds: int = 1800,
        estimated_runtime_sec: int = 60,
        output_bundle_path: Optional[Union[str, Path]] = None
    ) -> bytes:
        """
        Creates a zip bundle containing all source files and a manifest.json.
        Returns the zip archive as bytes, and optionally saves to output_bundle_path.
        """
        entrypoint_path = Path(entrypoint_file).resolve()
        if not entrypoint_path.exists():
            raise FileNotFoundError(f"Entrypoint file '{entrypoint_path}' does not exist.")

        job_id = f"job_{uuid.uuid4().hex[:10]}"
        if not job_name:
            job_name = entrypoint_path.stem

        packaged_files = [entrypoint_path.name]

        # Read requirements if provided
        requirements_list: Optional[List[str]] = None
        if requirements_file:
            req_path = Path(requirements_file).resolve()
            if req_path.exists():
                with open(req_path, "r", encoding="utf-8") as f:
                    requirements_list = [line.strip() for line in f if line.strip() and not line.startswith("#")]
                packaged_files.append(req_path.name)

        # Collect extra files
        extra_paths: List[Path] = []
        if extra_files:
            for ef in extra_files:
                ef_path = Path(ef).resolve()
                if not ef_path.exists():
                    raise FileNotFoundError(f"Extra file/dir '{ef_path}' does not exist.")
                extra_paths.append(ef_path)
                packaged_files.append(ef_path.name)

        # Create Manifest
        manifest = JobManifest(
            job_id=job_id,
            job_name=job_name,
            entrypoint=entrypoint_path.name,
            args=args or [],
            created_at=time.time(),
            timeout_seconds=timeout_seconds,
            estimated_runtime_sec=estimated_runtime_sec,
            requirements=requirements_list,
            env_vars=env_vars or {},
            files=packaged_files
        )

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            # 1. Write Manifest
            zip_file.writestr("manifest.json", manifest.model_dump_json(indent=2))

            # 2. Write Entrypoint
            zip_file.write(entrypoint_path, arcname=entrypoint_path.name)

            # 3. Write Requirements
            if requirements_file and Path(requirements_file).exists():
                zip_file.write(Path(requirements_file), arcname=Path(requirements_file).name)

            # 4. Write Extra Files or Directories
            for path in extra_paths:
                if path.is_file():
                    zip_file.write(path, arcname=path.name)
                elif path.is_dir():
                    for root, _, files in os.walk(path):
                        for file in files:
                            full_path = Path(root) / file
                            rel_path = full_path.relative_to(path.parent)
                            zip_file.write(full_path, arcname=str(rel_path))

        bundle_bytes = buffer.getvalue()

        if output_bundle_path:
            out_path = Path(output_bundle_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "wb") as f:
                f.write(bundle_bytes)

        return bundle_bytes


class JobUnpackager:
    """Extracts a job bundle onto a worker machine into an isolated workspace."""

    @staticmethod
    def extract_bundle(
        bundle_source: Union[bytes, str, Path],
        target_dir: Union[str, Path]
    ) -> JobManifest:
        """
        Safely extracts the zip bundle into target_dir and returns the parsed JobManifest.
        Creates an 'output' directory in the workspace for script artifacts.
        """
        dest_dir = Path(target_dir).resolve()
        dest_dir.mkdir(parents=True, exist_ok=True)

        if isinstance(bundle_source, (str, Path)):
            zip_input = Path(bundle_source).resolve()
            zip_ref = zipfile.ZipFile(zip_input, "r")
        else:
            zip_ref = zipfile.ZipFile(io.BytesIO(bundle_source), "r")

        with zip_ref:
            # Safety check: prevent zip path traversal
            for member in zip_ref.namelist():
                member_path = (dest_dir / member).resolve()
                if not str(member_path).startswith(str(dest_dir)):
                    raise ValueError(f"Malicious zip traversal attempt detected: {member}")

            zip_ref.extractall(dest_dir)

        manifest_path = dest_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError("Bundle missing required 'manifest.json'")

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_dict = json.load(f)
            manifest = JobManifest(**manifest_dict)

        # Create output directory for user scripts to dump artifacts
        (dest_dir / "output").mkdir(exist_ok=True)

        return manifest


class ResultPackager:
    """Bundles execution artifacts, logs, and metadata on the worker machine into a result bundle."""

    @staticmethod
    def create_result_bundle(
        workspace_dir: Union[str, Path],
        job_result: JobResult,
        output_bundle_path: Optional[Union[str, Path]] = None
    ) -> bytes:
        """
        Packages workspace artifacts (contents of 'output/' and logs) alongside job_result.json.
        """
        ws_dir = Path(workspace_dir).resolve()
        output_dir = ws_dir / "output"

        buffer = io.BytesIO()
        artifact_list: List[str] = []

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            # 1. Collect files from output/ directory
            if output_dir.exists() and output_dir.is_dir():
                for root, _, files in os.walk(output_dir):
                    for file in files:
                        full_path = Path(root) / file
                        rel_path = full_path.relative_to(output_dir)
                        zip_file.write(full_path, arcname=f"output/{rel_path}")
                        artifact_list.append(f"output/{rel_path}")

            # 2. Write stdout and stderr logs if present
            stdout_path = ws_dir / "stdout.log"
            stderr_path = ws_dir / "stderr.log"

            if stdout_path.exists():
                zip_file.write(stdout_path, arcname="logs/stdout.log")
                artifact_list.append("logs/stdout.log")
            elif job_result.stdout:
                zip_file.writestr("logs/stdout.log", job_result.stdout)
                artifact_list.append("logs/stdout.log")

            if stderr_path.exists():
                zip_file.write(stderr_path, arcname="logs/stderr.log")
                artifact_list.append("logs/stderr.log")
            elif job_result.stderr:
                zip_file.writestr("logs/stderr.log", job_result.stderr)
                artifact_list.append("logs/stderr.log")

            # Update job result artifact files
            job_result.artifact_files = artifact_list

            # 3. Write final result metadata JSON
            zip_file.writestr("job_result.json", job_result.model_dump_json(indent=2))

        bundle_bytes = buffer.getvalue()

        if output_bundle_path:
            out_path = Path(output_bundle_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "wb") as f:
                f.write(bundle_bytes)

        return bundle_bytes


class ResultUnpackager:
    """Unpacks a result bundle on the client machine."""

    @staticmethod
    def extract_result_bundle(
        bundle_source: Union[bytes, str, Path],
        target_dir: Union[str, Path]
    ) -> JobResult:
        """
        Extracts results and logs to target_dir and returns the JobResult object.
        """
        dest_dir = Path(target_dir).resolve()
        dest_dir.mkdir(parents=True, exist_ok=True)

        if isinstance(bundle_source, (str, Path)):
            zip_ref = zipfile.ZipFile(bundle_source, "r")
        else:
            zip_ref = zipfile.ZipFile(io.BytesIO(bundle_source), "r")

        with zip_ref:
            for member in zip_ref.namelist():
                member_path = (dest_dir / member).resolve()
                if not str(member_path).startswith(str(dest_dir)):
                    raise ValueError(f"Malicious zip traversal attempt detected: {member}")
            zip_ref.extractall(dest_dir)

        result_path = dest_dir / "job_result.json"
        if not result_path.exists():
            raise FileNotFoundError("Result bundle missing 'job_result.json'")

        with open(result_path, "r", encoding="utf-8") as f:
            result_dict = json.load(f)
            return JobResult(**result_dict)
