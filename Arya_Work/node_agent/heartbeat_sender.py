import logging
import requests
from typing import Optional, Dict, Any

logger = logging.getLogger("NodeAgent.HeartbeatSender")

class HeartbeatSender:
    def __init__(self, config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def build_payload(self, metrics_data: dict) -> dict:
        """Enriches collected metrics into a standard Dispatcher heartbeat payload."""
        return {
            "node_id": self.config.node_id,
            "timestamp": metrics_data["timestamp"],
            "state": metrics_data["state"],
            "hostname": metrics_data["hostname"],
            "os": metrics_data["os"],
            "os_release": metrics_data["os_release"],
            "metrics": metrics_data["metrics"]
        }

    def send_heartbeat(self, metrics_data: dict) -> bool:
        """
        Sends HTTP POST heartbeat payload to the Dispatcher.
        Returns True if successful, False if failed.
        """
        payload = self.build_payload(metrics_data)
        url = self.config.dispatcher_url

        try:
            response = self.session.post(url, json=payload, timeout=5)
            if response.status_code in (200, 201, 202):
                logger.debug(f"Heartbeat sent successfully to {url} [Node: {self.config.node_id}]")
                return True
            else:
                logger.warning(
                    f"Dispatcher returned non-200 status code: {response.status_code} - {response.text}"
                )
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to transmit heartbeat to Dispatcher ({url}): {e}")
            return False
