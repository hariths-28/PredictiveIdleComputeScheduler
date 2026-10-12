"""Run the coordinator (dispatcher + dashboard): `idlegrid-dispatcher` or `python -m idlegrid.dispatcher`."""

import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(prog="idlegrid-dispatcher", description="IdleGrid coordinator")
    parser.add_argument(
        "--host", default="127.0.0.1", help="Bind address (use 0.0.0.0 so other laptops can reach it)"
    )
    parser.add_argument("--port", type=int, default=8000, help="Port (default 8000)")
    parser.add_argument(
        "--no-sim", action="store_true", help="Hide the 4 simulated laptops (real laptops only)"
    )
    args = parser.parse_args()
    if args.no_sim:
        os.environ["IDLEGRID_SIM_NODES"] = "0"
    # Exactly one worker: the scheduler state lives in this process (PRD section 10.3.4).
    uvicorn.run("idlegrid.dispatcher.app:app", host=args.host, port=args.port, workers=1)


if __name__ == "__main__":
    main()
