import unittest
import sys
import subprocess
import time
import psutil
from node_agent.kill_switch import KillSwitch, PreemptionEvent

class TestKillSwitch(unittest.TestCase):
    def setUp(self):
        self.kill_switch = KillSwitch(default_action="terminate")
        self.dummy_proc = None

    def tearDown(self):
        if self.dummy_proc and self.dummy_proc.poll() is None:
            self.dummy_proc.kill()
            self.dummy_proc.wait()

    def test_register_and_unregister_job(self):
        # Spawn a short-lived sleeper process
        self.dummy_proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
        pid = self.dummy_proc.pid

        self.assertTrue(self.kill_switch.register_job(pid, job_id="test-job-42"))
        self.assertTrue(self.kill_switch.has_active_jobs())

        self.kill_switch.unregister_job(pid)
        self.assertFalse(self.kill_switch.has_active_jobs())

    def test_preemption_terminates_process(self):
        self.dummy_proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
        pid = self.dummy_proc.pid
        self.kill_switch.register_job(pid, job_id="test-job-preempt")

        events = self.kill_switch.trigger_preemption(reason="Simulated user return")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].job_id, "test-job-preempt")
        self.assertEqual(events[0].pid, pid)

        # Confirm process has been terminated
        time.sleep(0.3)
        self.assertFalse(psutil.pid_exists(pid) and psutil.Process(pid).is_running())

    def test_on_state_update_triggers_when_user_active(self):
        self.dummy_proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
        pid = self.dummy_proc.pid
        self.kill_switch.register_job(pid, job_id="test-auto-preempt")

        # When IDLE, no preemption should happen
        events_idle = self.kill_switch.on_state_update(current_state="IDLE", inactivity_sec=200.0)
        self.assertEqual(len(events_idle), 0)

        # When USER_ACTIVE, preemption must trigger immediately
        events_active = self.kill_switch.on_state_update(current_state="USER_ACTIVE", inactivity_sec=2.5)
        self.assertEqual(len(events_active), 1)
        self.assertEqual(events_active[0].pid, pid)

if __name__ == "__main__":
    unittest.main()
