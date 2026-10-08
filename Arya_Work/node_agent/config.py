import json
import uuid
import socket
import os

class NodeConfig:
    def __init__(
        self,
        dispatcher_url: str = "http://localhost:5000/api/v1/heartbeat",
        node_id: str = None,
        heartbeat_interval: int = 5,
        cpu_idle_threshold: float = 20.0,
        ram_idle_threshold: float = 80.0,
        user_inactivity_threshold_sec: int = 180,
        log_level: str = "INFO"
    ):
        self.dispatcher_url = dispatcher_url
        self.node_id = node_id or self._generate_default_node_id()
        self.heartbeat_interval = heartbeat_interval
        self.cpu_idle_threshold = cpu_idle_threshold
        self.ram_idle_threshold = ram_idle_threshold
        self.user_inactivity_threshold_sec = user_inactivity_threshold_sec
        self.log_level = log_level

    @staticmethod
    def _generate_default_node_id() -> str:
        """Generates a stable node ID based on hostname and MAC address."""
        hostname = socket.gethostname()
        mac = uuid.getnode()
        unique_str = f"{hostname}-{mac}"
        return f"node-{uuid.uuid5(uuid.NAMESPACE_DNS, unique_str).hex[:12]}"

    @classmethod
    def load_from_file(cls, filepath: str) -> "NodeConfig":
        """Loads configuration settings from a JSON file."""
        if not os.path.exists(filepath):
            return cls()

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        return cls(
            dispatcher_url=data.get("dispatcher_url", "http://localhost:5000/api/v1/heartbeat"),
            node_id=data.get("node_id"),
            heartbeat_interval=data.get("heartbeat_interval", 5),
            cpu_idle_threshold=data.get("cpu_idle_threshold", 20.0),
            ram_idle_threshold=data.get("ram_idle_threshold", 80.0),
            user_inactivity_threshold_sec=data.get("user_inactivity_threshold_sec", 180),
            log_level=data.get("log_level", "INFO")
        )

    def to_dict(self) -> dict:
        return {
            "dispatcher_url": self.dispatcher_url,
            "node_id": self.node_id,
            "heartbeat_interval": self.heartbeat_interval,
            "cpu_idle_threshold": self.cpu_idle_threshold,
            "ram_idle_threshold": self.ram_idle_threshold,
            "user_inactivity_threshold_sec": self.user_inactivity_threshold_sec,
            "log_level": self.log_level
        }
