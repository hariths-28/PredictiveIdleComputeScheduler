import time
import logging
import signal
import sys
from node_agent.config import NodeConfig
from node_agent.metrics_collector import MetricsCollector
from node_agent.heartbeat_sender import HeartbeatSender
from node_agent.kill_switch import KillSwitch, PreemptionEvent
from node_agent.usage_logger import UsageLogger

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
        self.kill_switch = KillSwitch(default_action=config.preemption_action)
        
        self.usage_logger = None
        if config.csv_output_file:
            self.usage_logger = UsageLogger(
                config=config,
                output_file=config.csv_output_file,
                collector=self.collector,
                log_interval=config.heartbeat_interval
            )
            
        self._running = False

    def register_job(self, pid: int, job_id: str = None) -> bool:
        """Exposes job registration to the executor (Role 5) or local runner."""
        return self.kill_switch.register_job(pid, job_id)

    def unregister_job(self, pid: int):
        """Unregisters job when execution finishes."""
        self.kill_switch.unregister_job(pid)

    def start(self):
        """Starts the Node Agent main monitoring, Kill Switch, and heartbeat loop."""
        self._running = True
        self.logger.info(f"Node Agent starting... Node ID: {self.config.node_id}")
        self.logger.info(f"Dispatcher URL: {self.config.dispatcher_url}")
        self.logger.info(f"Heartbeat Interval: {self.config.heartbeat_interval}s")
        if self.config.csv_output_file:
            self.logger.info(f"Usage Telemetry Logging enabled -> {self.config.csv_output_file}")

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        count = 0
        while self._running:
            try:
                metrics_data = self.collector.collect()
                state = metrics_data["state"]
                inactivity_sec = metrics_data["metrics"]["user_inactivity_sec"]
                count += 1

                # 1. Check Kill Switch preemption trigger (immediate host priority)
                preemption_events = self.kill_switch.on_state_update(state, inactivity_sec)
                if preemption_events:
                    self.logger.warning(
                        f"Preempted {len(preemption_events)} active compute job(s) due to user return!"
                    )

                self.logger.info(
                    f"[{count}] State: {state} | CPU: {metrics_data['metrics']['cpu_usage_percent']}% | "
                    f"RAM: {metrics_data['metrics']['ram_usage_percent']}% | "
                    f"Inactivity: {inactivity_sec}s | Jobs guarded: {len(self.kill_switch.monitored_jobs)}"
                )

                # 2. Local CSV persistence (if configured)
                if self.usage_logger:
                    self.usage_logger.log_snapshot()

                # 3. Transmit heartbeat to coordinator
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

    def start_log_only(self, output_file: str = "laptop_telemetry.csv", interval: int = 15):
        """Specialized Phase 0 mode: Runs continuous 15s telemetry harvesting without network dependency."""
        self.logger.info(f"Starting Node Agent in LOG-ONLY Mode [Interval: {interval}s]")
        logger_instance = UsageLogger(
            config=self.config,
            output_file=output_file,
            collector=self.collector,
            log_interval=interval
        )
        logger_instance.start()

    def stop(self):
        """Stops the Node Agent loop."""
        self._running = False

    def _handle_shutdown(self, signum, frame):
        self.logger.info("Received termination signal. Shutting down Node Agent...")
        self.stop()

