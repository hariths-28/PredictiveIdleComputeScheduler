import argparse
import sys
import os

# Add local directory to path for clean imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from node_agent.config import NodeConfig
from node_agent.agent import NodeAgent

def parse_args():
    parser = argparse.ArgumentParser(description="Predictive Idle-Compute Node Agent (Client Side)")
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
        help="Heartbeat transmission interval in seconds"
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

    agent = NodeAgent(config)
    agent.start()

if __name__ == "__main__":
    main()
