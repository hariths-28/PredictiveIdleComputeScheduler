import unittest
from unittest.mock import patch, MagicMock
import requests
from node_agent.config import NodeConfig
from node_agent.heartbeat_sender import HeartbeatSender

class TestHeartbeatSender(unittest.TestCase):
    def setUp(self):
        self.config = NodeConfig(
            dispatcher_url="http://mock-dispatcher.local/api/v1/heartbeat",
            node_id="test-node-123"
        )
        self.sender = HeartbeatSender(self.config)
        self.sample_metrics = {
            "timestamp": 1700000000.0,
            "hostname": "test-host",
            "os": "Windows",
            "os_release": "10",
            "state": "IDLE",
            "metrics": {
                "cpu_usage_percent": 12.0,
                "ram_usage_percent": 45.0,
                "user_inactivity_sec": 300.0
            }
        }

    def test_build_payload(self):
        payload = self.sender.build_payload(self.sample_metrics)
        self.assertEqual(payload["node_id"], "test-node-123")
        self.assertEqual(payload["state"], "IDLE")
        self.assertEqual(payload["hostname"], "test-host")
        self.assertEqual(payload["metrics"]["cpu_usage_percent"], 12.0)

    @patch("requests.Session.post")
    def test_send_heartbeat_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        success = self.sender.send_heartbeat(self.sample_metrics)
        self.assertTrue(success)
        mock_post.assert_called_once()

    @patch("requests.Session.post")
    def test_send_heartbeat_connection_error(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError("Failed to connect")

        success = self.sender.send_heartbeat(self.sample_metrics)
        self.assertFalse(success)

if __name__ == "__main__":
    unittest.main()
