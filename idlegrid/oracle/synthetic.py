"""Synthetic trace generator for tests.

PRD §10.4.3 & Appendix D.
Simulates realistic student laptop availability sessions per node,
then derives Appendix D UsageSample rows with monotonic inactivity growth,
no future timestamps, and strict contract adherence.
"""
from __future__ import annotations

import csv
import random
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from idlegrid.common.models import HostState, InputDetection, UsageSample

IDLE_THRESHOLD_SEC = 120.0
SAMPLE_INTERVAL_SEC = 15.0


def format_iso_utc(ts: float) -> str:
    """Format an epoch timestamp to ISO 8601 UTC with milliseconds and Z suffix."""
    dt = datetime.fromtimestamp(ts, tz=UTC)
    ms = int(dt.microsecond / 1000)
    return dt.strftime(f"%Y-%m-%dT%H:%M:%S.{ms:03d}Z")


def parse_iso_utc(iso_str: str) -> float:
    """Parse an ISO 8601 UTC string with Z suffix to epoch seconds."""
    s = iso_str.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    return dt.timestamp()


class SyntheticTraceGenerator:
    """Generates synthetic usage telemetry conforming to Appendix D."""

    def __init__(
        self,
        node_id: str = "node-3f2a9c1b7d4e",
        tz_offset_min: int = 330,  # Default IST
        agent_version: str = "0.1.0",
        seed: int | None = 42,
    ) -> None:
        self.node_id = node_id
        self.tz_offset_min = tz_offset_min
        self.agent_version = agent_version
        self.rng = random.Random(seed)

    def _get_behavior_profile(self, hour: int, is_weekend: bool) -> tuple[float, float, float]:
        """Return (p_idle, mean_idle_min, std_idle_min) for a given local hour."""
        # 02:00 - 08:00: Sleep (very high idle probability, long idle sessions)
        if 2 <= hour < 8:
            return 0.92, 180.0, 45.0
        # 10:00 - 16:00: Classes / Study (moderate idle on weekdays)
        if 10 <= hour < 16 and not is_weekend:
            return 0.55, 45.0, 15.0
        # 19:00 - 23:00: Active use / Gaming / Streaming (low idle)
        if 19 <= hour < 23:
            return 0.15, 15.0, 5.0
        # Default / other times
        return 0.40, 30.0, 10.0

    def generate_trace(
        self,
        duration_hours: float = 24.0,
        end_time: float | None = None,
    ) -> list[UsageSample]:
        """Generate a series of UsageSample rows at 15-second intervals.

        Timestamps strictly end at `end_time` (defaults to current time).
        """
        if end_time is None:
            end_time = time.time()

        total_seconds = int(duration_hours * 3600)
        start_time = end_time - total_seconds

        samples: list[UsageSample] = []
        current_time = start_time

        in_session = False
        session_remaining_sec = 0.0
        inactivity_sec = 0.0

        while current_time <= end_time:
            # Determine local hour based on tz_offset_min
            local_dt = datetime.fromtimestamp(
                current_time + self.tz_offset_min * 60,
                tz=UTC,
            )
            hour = local_dt.hour
            is_weekend = local_dt.weekday() >= 5

            p_idle, mean_idle_min, std_idle_min = self._get_behavior_profile(hour, is_weekend)

            if not in_session:
                if self.rng.random() < p_idle:
                    # Enter an idle session
                    in_session = True
                    idle_len_min = max(5.0, self.rng.gauss(mean_idle_min, std_idle_min))
                    session_remaining_sec = idle_len_min * 60.0
                    inactivity_sec = IDLE_THRESHOLD_SEC
                else:
                    # Active period: low user inactivity
                    in_session = False
                    session_remaining_sec = self.rng.uniform(60.0, 600.0)
                    inactivity_sec = self.rng.uniform(0.0, 15.0)

            if in_session:
                host_state = HostState.IDLE
                cpu_pct = round(self.rng.uniform(2.0, 12.0), 2)
                ram_pct = round(self.rng.uniform(25.0, 50.0), 2)
                on_ac = True if hour < 8 else (self.rng.random() < 0.85)
                battery_pct = round(self.rng.uniform(80.0, 100.0), 1) if on_ac else 75.0
                user_inact = round(inactivity_sec, 1)

                session_remaining_sec -= SAMPLE_INTERVAL_SEC
                inactivity_sec += SAMPLE_INTERVAL_SEC
                if session_remaining_sec <= 0:
                    in_session = False
            else:
                host_state = HostState.ACTIVE if self.rng.random() < 0.9 else HostState.BUSY
                cpu_pct = round(self.rng.uniform(20.0, 85.0), 2)
                ram_pct = round(self.rng.uniform(45.0, 80.0), 2)
                on_ac = self.rng.random() < 0.70
                battery_pct = round(self.rng.uniform(40.0, 95.0), 1)
                user_inact = round(self.rng.uniform(0.1, 10.0), 1)

                session_remaining_sec -= SAMPLE_INTERVAL_SEC

            sample = UsageSample(
                ts_utc=current_time,
                tz_offset_min=self.tz_offset_min,
                node_id=self.node_id,
                cpu_percent=cpu_pct,
                host_cpu_percent=cpu_pct,
                ram_percent=ram_pct,
                user_inactivity_sec=user_inact,
                input_method="macos_coregraphics",
                input_precision=InputDetection.PRECISE,
                host_state=host_state,
                on_ac_power=on_ac,
                battery_percent=battery_pct,
                job_running=False,
                agent_version=self.agent_version,
            )
            samples.append(sample)
            current_time += SAMPLE_INTERVAL_SEC

        return samples


def samples_to_csv_rows(samples: Sequence[UsageSample]) -> list[dict[str, str]]:
    """Convert UsageSample models into dictionaries matching Appendix D columns."""
    rows: list[dict[str, str]] = []
    for s in samples:
        on_ac_str = "" if s.on_ac_power is None else ("1" if s.on_ac_power else "0")
        batt_str = "" if s.battery_percent is None else f"{s.battery_percent:.1f}"
        inact_str = "" if s.user_inactivity_sec is None else f"{s.user_inactivity_sec:.1f}"

        rows.append(
            {
                "ts_utc": format_iso_utc(s.ts_utc),
                "tz_offset_min": str(s.tz_offset_min),
                "node_id": s.node_id,
                "cpu_percent": f"{s.cpu_percent:.1f}",
                "host_cpu_percent": f"{s.host_cpu_percent:.1f}",
                "ram_percent": f"{s.ram_percent:.1f}",
                "user_inactivity_sec": inact_str,
                "input_method": s.input_method,
                "input_precision": s.input_precision.value
                if isinstance(s.input_precision, InputDetection)
                else str(s.input_precision),
                "host_state": s.host_state.value
                if isinstance(s.host_state, HostState)
                else str(s.host_state),
                "on_ac_power": on_ac_str,
                "battery_percent": batt_str,
                "job_running": "1" if s.job_running else "0",
                "agent_version": s.agent_version,
            }
        )
    return rows


APPENDIX_D_HEADER = [
    "ts_utc",
    "tz_offset_min",
    "node_id",
    "cpu_percent",
    "host_cpu_percent",
    "ram_percent",
    "user_inactivity_sec",
    "input_method",
    "input_precision",
    "host_state",
    "on_ac_power",
    "battery_percent",
    "job_running",
    "agent_version",
]


def write_usage_csv(samples: Sequence[UsageSample], dest_path: Path | str) -> Path:
    """Write usage samples to a CSV file matching Appendix D."""
    path = Path(dest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = samples_to_csv_rows(samples)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=APPENDIX_D_HEADER)
        writer.writeheader()
        writer.writerows(rows)
    return path


def read_usage_csv(src_path: Path | str) -> list[UsageSample]:
    """Read an Appendix D CSV file into UsageSample models."""
    path = Path(src_path)
    samples: list[UsageSample] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            on_ac: bool | None = None
            if row["on_ac_power"] == "1":
                on_ac = True
            elif row["on_ac_power"] == "0":
                on_ac = False

            batt: float | None = (
                float(row["battery_percent"]) if row["battery_percent"] != "" else None
            )
            inact: float | None = (
                float(row["user_inactivity_sec"]) if row["user_inactivity_sec"] != "" else None
            )

            samples.append(
                UsageSample(
                    ts_utc=parse_iso_utc(row["ts_utc"]),
                    tz_offset_min=int(row["tz_offset_min"]),
                    node_id=row["node_id"],
                    cpu_percent=float(row["cpu_percent"]),
                    host_cpu_percent=float(row["host_cpu_percent"]),
                    ram_percent=float(row["ram_percent"]),
                    user_inactivity_sec=inact,
                    input_method=row["input_method"],
                    input_precision=InputDetection(row["input_precision"]),
                    host_state=HostState(row["host_state"]),
                    on_ac_power=on_ac,
                    battery_percent=batt,
                    job_running=row["job_running"] == "1",
                    agent_version=row["agent_version"],
                )
            )
    return samples
