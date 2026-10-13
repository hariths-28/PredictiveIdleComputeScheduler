import os
import csv
import time
import logging
from datetime import datetime
from typing import Optional
from node_agent.config import NodeConfig
from node_agent.metrics_collector import MetricsCollector

logger = logging.getLogger("NodeAgent.UsageLogger")

CSV_HEADER = [
    "timestamp",
    "node_id",
    "state",
    "cpu_pct",
    "ram_pct",
    "ram_available_mb",
    "disk_usage_pct",
    "net_bytes_sent",
    "net_bytes_recv",
    "user_inactivity_sec",
    "battery_charging",
    "battery_pct",
    "mouse_events_last_min",
    "key_events_last_min"
]

class UsageLogger:
    """
    Continuous Usage Logger for Phase 0 Step 1.
    Harvests hardware and user telemetry every N seconds (default: 15s)
    and flushes to a persistent CSV file for ML model training.
    """
    def __init__(
        self,
        config: NodeConfig,
        output_file: str = "laptop_telemetry.csv",
        collector: Optional[MetricsCollector] = None,
        log_interval: int = 15
    ):
        self.config = config
        self.output_file = output_file
        self.collector = collector or MetricsCollector(config)
        self.log_interval = log_interval
        self._running = False
        self._init_csv_file()

    def _init_csv_file(self):
        """Ensures the target CSV file exists and has the appropriate header."""
        file_exists = os.path.isfile(self.output_file)
        if not file_exists:
            # Create parent directories if needed
            os.makedirs(os.path.dirname(os.path.abspath(self.output_file)), exist_ok=True)
            with open(self.output_file, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(CSV_HEADER)
                f.flush()
            logger.info(f"Initialized new usage telemetry file: {self.output_file}")
        else:
            logger.info(f"Appending to existing usage telemetry file: {self.output_file}")

    def log_snapshot(self) -> dict:
        """Collects a single telemetry snapshot and appends it to the CSV."""
        metrics_data = self.collector.collect()
        m = metrics_data["metrics"]

        # Formatted readable timestamp for ML feature extraction
        readable_ts = datetime.fromtimestamp(metrics_data["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")

        row = [
            readable_ts,
            self.config.node_id,
            metrics_data["state"],
            m.get("cpu_pct", m.get("cpu_usage_percent", 0.0)),
            m.get("ram_pct", m.get("ram_usage_percent", 0.0)),
            m.get("ram_available_mb", 0.0),
            m.get("disk_usage_percent", 0.0),
            m.get("net_bytes_sent", 0),
            m.get("net_bytes_recv", 0),
            m.get("user_inactivity_sec", 0.0),
            m.get("battery_charging", 1),
            m.get("battery_pct", 100.0),
            m.get("mouse_events_last_min", 0),
            m.get("key_events_last_min", 0)
        ]

        with open(self.output_file, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(row)
            f.flush()

        logger.debug(
            f"Logged snapshot: {readable_ts} | State: {metrics_data['state']} | "
            f"CPU: {m.get('cpu_pct')}% | RAM: {m.get('ram_pct')}% | Idle: {m.get('user_inactivity_sec')}s"
        )
        return metrics_data

    def start(self):
        """Runs the continuous telemetry logging loop."""
        self._running = True
        logger.info(
            f"Starting continuous telemetry logger [Interval: {self.log_interval}s, Output: {self.output_file}]"
        )
        
        count = 0
        try:
            while self._running:
                start_loop = time.time()
                data = self.log_snapshot()
                count += 1

                if count % 10 == 0:
                    logger.info(
                        f"Harvested {count} records. Current State: {data['state']} "
                        f"(Inactivity: {data['metrics']['user_inactivity_sec']}s)"
                    )

                # Sleep responsive to interruption
                elapsed = time.time() - start_loop
                sleep_remaining = max(0.0, self.log_interval - elapsed)
                
                # Check running flag frequently during sleep
                sleep_ticks = int(sleep_remaining * 2)
                for _ in range(sleep_ticks):
                    if not self._running:
                        break
                    time.sleep(0.5)

        except KeyboardInterrupt:
            logger.info("Logging loop interrupted by user.")
        finally:
            self.stop()

    def stop(self):
        """Halts the logging loop."""
        self._running = False
        logger.info("Continuous usage logger stopped.")
