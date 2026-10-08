import sys
import time
import platform
import psutil
import socket

# Windows idle time detection setup using ctypes
if sys.platform == "win32":
    import ctypes

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

def get_user_inactivity_seconds() -> float:
    """Returns the seconds elapsed since the last user mouse/keyboard input."""
    if sys.platform == "win32":
        try:
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
                # GetTickCount returns milliseconds since system boot
                millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
                # Handle tick count wraparound (every ~49.7 days)
                if millis < 0:
                    millis += 2**32
                return round(millis / 1000.0, 2)
        except Exception:
            pass
    return 0.0

class MetricsCollector:
    def __init__(self, config):
        self.config = config
        # Prime psutil cpu monitoring
        psutil.cpu_percent(interval=None)

    def collect(self) -> dict:
        """Collects full system hardware metrics and determines idle state."""
        cpu_usage = psutil.cpu_percent(interval=None)
        cpu_count = psutil.cpu_count(logical=True)
        memory_info = psutil.virtual_memory()
        disk_info = psutil.disk_usage("/")
        net_info = psutil.net_io_counters()

        inactivity_sec = get_user_inactivity_seconds()

        # Determine node state
        state = self.determine_node_state(
            cpu_usage=cpu_usage,
            ram_usage=memory_info.percent,
            inactivity_sec=inactivity_sec
        )

        return {
            "timestamp": round(time.time(), 3),
            "hostname": socket.gethostname(),
            "os": platform.system(),
            "os_release": platform.release(),
            "state": state,
            "metrics": {
                "cpu_usage_percent": cpu_usage,
                "cpu_count": cpu_count,
                "ram_usage_percent": memory_info.percent,
                "ram_available_mb": round(memory_info.available / (1024 * 1024), 2),
                "ram_total_mb": round(memory_info.total / (1024 * 1024), 2),
                "disk_usage_percent": disk_info.percent,
                "disk_free_gb": round(disk_info.free / (1024**3), 2),
                "net_bytes_sent": net_info.bytes_sent,
                "net_bytes_recv": net_info.bytes_recv,
                "user_inactivity_sec": inactivity_sec
            }
        }

    def determine_node_state(self, cpu_usage: float, ram_usage: float, inactivity_sec: float) -> str:
        """
        State determination logic:
        - USER_ACTIVE: If user has moved mouse / used keyboard within user_inactivity_threshold_sec
        - BUSY: If CPU usage or RAM usage exceeds idle thresholds
        - IDLE: System is quiet, low load, and no recent user interaction
        """
        if sys.platform == "win32" and inactivity_sec < self.config.user_inactivity_threshold_sec:
            return "USER_ACTIVE"
        
        if cpu_usage > self.config.cpu_idle_threshold or ram_usage > self.config.ram_idle_threshold:
            return "BUSY"

        return "IDLE"
