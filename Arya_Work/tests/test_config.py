import unittest
import os
import json
import tempfile
from node_agent.config import NodeConfig

class TestNodeConfig(unittest.TestCase):
    def test_default_config(self):
        config = NodeConfig()
        self.assertEqual(config.dispatcher_url, "http://localhost:5000/api/v1/heartbeat")
        self.assertEqual(config.heartbeat_interval, 5)
        self.assertTrue(config.node_id.startswith("node-"))
        self.assertEqual(config.cpu_idle_threshold, 20.0)

    def test_load_from_json_file(self):
        sample_data = {
            "dispatcher_url": "http://192.168.1.100:8000/heartbeat",
            "node_id": "lab-pc-01",
            "heartbeat_interval": 10,
            "cpu_idle_threshold": 15.5,
            "ram_idle_threshold": 70.0,
            "user_inactivity_threshold_sec": 300,
            "log_level": "DEBUG"
        }
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f:
            json.dump(sample_data, f)
            temp_path = f.name

        try:
            config = NodeConfig.load_from_file(temp_path)
            self.assertEqual(config.dispatcher_url, "http://192.168.1.100:8000/heartbeat")
            self.assertEqual(config.node_id, "lab-pc-01")
            self.assertEqual(config.heartbeat_interval, 10)
            self.assertEqual(config.cpu_idle_threshold, 15.5)
            self.assertEqual(config.ram_idle_threshold, 70.0)
            self.assertEqual(config.user_inactivity_threshold_sec, 300)
            self.assertEqual(config.log_level, "DEBUG")
        finally:
            os.remove(temp_path)

if __name__ == "__main__":
    unittest.main()
