"""
Root entrypoint for gridctl CLI.
Usage:
    python gridctl.py submit <script.py>
    python gridctl.py demo-run --type pi
    python gridctl.py cluster
"""
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.cli.gridctl import cli_main

if __name__ == "__main__":
    cli_main()
