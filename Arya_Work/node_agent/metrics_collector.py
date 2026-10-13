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
    """
    Returns the seconds elapsed since the last user mouse/keyboard input.
    Supports Windows (ctypes GetLastInputInfo), macOS (ioreg HIDIdleTime),
    and Linux (xprintidle), with graceful fallback.
    """
    # 1. Windows: Win32 GetLastInputInfo
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

    # 2. macOS: Query IOHIDSystem for HIDIdleTime (in nanoseconds)
    elif sys.platform == "darwin":
        try:
            import subprocess
            cmd = ["ioreg", "-c", "IOHIDSystem"]
            output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=1).decode("utf-8")
            for line in output.splitlines():
                if "HIDIdleTime" in line:
                    nanos = int(line.split("=")[-1].strip())
                    return round(nanos / 1_000_000_000.0, 2)
        except Exception:
            pass
        return 0.0

    # 3. Linux: Check xprintidle (returns idle time in milliseconds)
    elif sys.platform.startswith("linux"):
        try:
            import subprocess
            output = subprocess.check_output(["xprintidle"], stderr=subprocess.DEVNULL, timeout=1).decode("utf-8")
            millis = int(output.strip())
            return round(millis / 1000.0, 2)
        except Exception:
            pass
        return 0.0

    return 0.0


def get_battery_info() -> dict:
    """Returns battery charging status and percentage via psutil."""
    try:
        battery = psutil.sensors_battery()
        if battery is None:
            # Desktop or device with no battery sensor: treat as charging/AC power
            return {"battery_charging": 1, "battery_pct": 100.0}
        
        is_charging = 1 if (battery.power_plugged or battery.power_plugged is None) else 0
        return {
            "battery_charging": is_charging,
            "battery_pct": round(battery.percent, 1)
        }
    except Exception:
        return {"battery_charging": 1, "battery_pct": 100.0}


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
        battery_data = get_battery_info()

        # Approximate event flags based on inactivity for ML Oracle compatibility
        is_user_recently_active = inactivity_sec < 60.0
        mouse_events_est = 25 if is_user_recently_active else 0
        key_events_est = 15 if is_user_recently_active else 0

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
                # Legacy / Primary keys (maintaining test backward compatibility)
                "cpu_usage_percent": cpu_usage,
                "cpu_count": cpu_count,
                "ram_usage_percent": memory_info.percent,
                "ram_available_mb": round(memory_info.available / (1024 * 1024), 2),
                "ram_total_mb": round(memory_info.total / (1024 * 1024), 2),
                "disk_usage_percent": disk_info.percent,
                "disk_free_gb": round(disk_info.free / (1024**3), 2),
                "net_bytes_sent": net_info.bytes_sent,
                "net_bytes_recv": net_info.bytes_recv,
                "user_inactivity_sec": inactivity_sec,
                # ML Oracle & Shared Telemetry contract keys
                "cpu_pct": cpu_usage,
                "ram_pct": memory_info.percent,
                "battery_charging": battery_data["battery_charging"],
                "battery_pct": battery_data["battery_pct"],
                "mouse_events_last_min": mouse_events_est,
                "key_events_last_min": key_events_est
            }
        }

    def determine_node_state(self, cpu_usage: float, ram_usage: float, inactivity_sec: float) -> str:
        """
        State determination logic:
        - USER_ACTIVE: If user has interacted within user_inactivity_threshold_sec
        - BUSY: If CPU usage or RAM usage exceeds idle thresholds
        - IDLE: System is quiet, low load, and no recent user interaction
        """
        if inactivity_sec < self.config.user_inactivity_threshold_sec:
            return "USER_ACTIVE"
        
        if cpu_usage > self.config.cpu_idle_threshold or ram_usage > self.config.ram_idle_threshold:
            return "BUSY"

        return "IDLE"
