"""Filesystem locations used across IdleGrid (resolved from the package, not the working directory)."""

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PACKAGE_DIR.parent
DASHBOARD_DIR = PACKAGE_DIR / "dashboard"
EXAMPLE_JOBS_DIR = REPO_ROOT / "examples" / "jobs"
