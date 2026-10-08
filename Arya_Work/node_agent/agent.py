import time
import logging
import signal
import sys
from node_agent.config import NodeConfig
from node_agent.metrics_collector import MetricsCollector
from node_agent.heartbeat_sender import HeartbeatSender

def setup_logging(log_level_str: str):
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

class NodeAgent:
    def __init__(self, config: NodeConfig):
        self.config = config
        setup_logging(config.log_level)
        self.logger = logging.getLogger("NodeAgent")
        self.collector = MetricsCollector(config)
        self.sender = HeartbeatSender(config)
        self._running = False

    def start(self):
        """Starts the Node Agent main monitoring and heartbeat loop."""
        self._running = True
        self.logger.info(f"Node Agent starting... Node ID: {self.config.node_id}")
        self.logger.info(f"Dispatcher URL: {self.config.dispatcher_url}")
        self.logger.info(f"Heartbeat Interval: {self.config.heartbeat_interval}s")

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        count = 0
        while self._running:
            try:
                metrics_data = self.collector.collect()
                state = metrics_data["state"]
                count += 1

                self.logger.info(
                    f"[{count}] State: {state} | CPU: {metrics_data['metrics']['cpu_usage_percent']}% | "
                    f"RAM: {metrics_data['metrics']['ram_usage_percent']}% | "
                    f"Inactivity: {metrics_data['metrics']['user_inactivity_sec']}s"
                )

                success = self.sender.send_heartbeat(metrics_data)
                if not success:
                    self.logger.warning("Heartbeat delivery unacknowledged. Will retry next interval.")

            except Exception as e:
                self.logger.error(f"Unexpected error in agent loop: {e}", exc_info=True)

            # Sleep in 0.5s increments to respond promptly to shutdown signals
            sleep_ticks = int(self.config.heartbeat_interval * 2)
            for _ in range(sleep_ticks):
                if not self._running:
                    break
                time.sleep(0.5)

        self.logger.info("Node Agent stopped gracefully.")

    def stop(self):
        """Stops the Node Agent loop."""
        self._running = False

    def _handle_shutdown(self, signum, frame):
        self.logger.info("Received termination signal. Shutting down Node Agent...")
        self.stop()

