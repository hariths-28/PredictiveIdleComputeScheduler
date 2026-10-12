import unittest
import os
import csv
import tempfile
from node_agent.config import NodeConfig
from node_agent.usage_logger import UsageLogger, CSV_HEADER

class TestUsageLogger(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.csv_path = os.path.join(self.temp_dir.name, "test_telemetry.csv")
        self.config = NodeConfig(node_id="test-node-001")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_initializes_csv_with_header(self):
        logger = UsageLogger(config=self.config, output_file=self.csv_path)
        self.assertTrue(os.path.isfile(self.csv_path))

        with open(self.csv_path, "r", encoding="utf-8") as f:
            reader = list(csv.reader(f))
            self.assertEqual(len(reader), 1)
            self.assertEqual(reader[0], CSV_HEADER)

    def test_log_snapshot_appends_row(self):
        logger = UsageLogger(config=self.config, output_file=self.csv_path)
        snapshot = logger.log_snapshot()

        with open(self.csv_path, "r", encoding="utf-8") as f:
            reader = list(csv.reader(f))
            self.assertEqual(len(reader), 2)
            row = reader[1]
            # Check node_id
            self.assertEqual(row[1], "test-node-001")
            # Check state matches snapshot
            self.assertEqual(row[2], snapshot["state"])
            # Check length matches header
            self.assertEqual(len(row), len(CSV_HEADER))

    def test_log_multiple_snapshots_appends_correctly(self):
        logger = UsageLogger(config=self.config, output_file=self.csv_path)
        logger.log_snapshot()
        logger.log_snapshot()
        logger.log_snapshot()

        with open(self.csv_path, "r", encoding="utf-8") as f:
            reader = list(csv.reader(f))
            self.assertEqual(len(reader), 4) # 1 header + 3 rows

if __name__ == "__main__":
    unittest.main()
