import unittest
import sys
from node_agent.config import NodeConfig
from node_agent.metrics_collector import MetricsCollector

class TestMetricsCollector(unittest.TestCase):
    def setUp(self):
        self.config = NodeConfig(
            cpu_idle_threshold=20.0,
            ram_idle_threshold=80.0,
            user_inactivity_threshold_sec=180
        )
        self.collector = MetricsCollector(self.config)

    def test_collect_returns_valid_dict(self):
        data = self.collector.collect()
        self.assertIn("timestamp", data)
        self.assertIn("hostname", data)
        self.assertIn("os", data)
        self.assertIn("state", data)
        self.assertIn("metrics", data)

        metrics = data["metrics"]
        self.assertIn("cpu_usage_percent", metrics)
        self.assertIn("ram_usage_percent", metrics)
        self.assertIn("ram_available_mb", metrics)
        self.assertIn("user_inactivity_sec", metrics)

    def test_determine_node_state_idle(self):
        # Low CPU (5%), Low RAM (30%), Inactivity > threshold (200s)
        state = self.collector.determine_node_state(
            cpu_usage=5.0,
            ram_usage=30.0,
            inactivity_sec=200.0
        )
        self.assertEqual(state, "IDLE")

    def test_determine_node_state_busy_high_cpu(self):
        # High CPU (85%), Low RAM (30%), Inactivity > threshold (200s)
        state = self.collector.determine_node_state(
            cpu_usage=85.0,
            ram_usage=30.0,
            inactivity_sec=200.0
        )
        self.assertEqual(state, "BUSY")

    def test_determine_node_state_busy_high_ram(self):
        # Low CPU (10%), High RAM (90%), Inactivity > threshold (200s)
        state = self.collector.determine_node_state(
            cpu_usage=10.0,
            ram_usage=90.0,
            inactivity_sec=200.0
        )
        self.assertEqual(state, "BUSY")

    def test_determine_node_state_user_active_windows(self):
        if sys.platform == "win32":
            # Inactivity (10s) < threshold (180s)
            state = self.collector.determine_node_state(
                cpu_usage=5.0,
                ram_usage=30.0,
                inactivity_sec=10.0
            )
            self.assertEqual(state, "USER_ACTIVE")

if __name__ == "__main__":
    unittest.main()
