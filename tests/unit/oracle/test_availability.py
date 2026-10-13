"""Unit tests for availability definition and sessionizer.

PRD §10.4.4, §10.4.11.
"""
from __future__ import annotations

from idlegrid.common.models import HostState, InputDetection, UsageSample
from idlegrid.oracle.availability import (
    IDLE_THRESHOLD_SEC,
    MAX_GAP_SEC,
    SAMPLE_INTERVAL_SEC,
    elapsed_idle,
    is_available,
    sessionize,
)


def make_sample(
    ts_utc: float,
    node_id: str = "node-1",
    host_state: HostState = HostState.IDLE,
    user_inactivity_sec: float | None = 120.0,
    on_ac_power: bool | None = True,
    input_precision: InputDetection = InputDetection.PRECISE,
    cpu_percent: float = 5.0,
    ram_percent: float = 30.0,
) -> UsageSample:
    return UsageSample(
        ts_utc=ts_utc,
        tz_offset_min=330,
        node_id=node_id,
        cpu_percent=cpu_percent,
        host_cpu_percent=cpu_percent,
        ram_percent=ram_percent,
        user_inactivity_sec=user_inactivity_sec,
        input_method="macos_coregraphics",
        input_precision=input_precision,
        host_state=host_state,
        on_ac_power=on_ac_power,
        battery_percent=90.0 if on_ac_power else 50.0,
        job_running=False,
        agent_version="0.1.0",
    )


def test_constants():
    assert IDLE_THRESHOLD_SEC == 120.0
    assert SAMPLE_INTERVAL_SEC == 15.0
    assert MAX_GAP_SEC == 45.0


def test_is_available():
    # Base available sample
    s = make_sample(1000.0)
    assert is_available(s) is True

    # Unavailable due to host_state
    assert is_available(make_sample(1000.0, host_state=HostState.ACTIVE)) is False
    assert is_available(make_sample(1000.0, host_state=HostState.BUSY)) is False

    # Unavailable due to AC power
    assert is_available(make_sample(1000.0, on_ac_power=False), require_ac=True) is False
    # But available if AC power is not required
    assert is_available(make_sample(1000.0, on_ac_power=False), require_ac=False) is True
    # None on_ac_power (desktop) counts as AC
    assert is_available(make_sample(1000.0, on_ac_power=None), require_ac=True) is True

    # Unavailable if input detection precision is NONE
    assert is_available(make_sample(1000.0, input_precision=InputDetection.NONE)) is False


def test_sessionize_empty():
    assert sessionize([]) == []


def test_sessionize_single_sample_censored():
    # Single available sample at end of data produces CENSORED session
    s1 = make_sample(1000.0, user_inactivity_sec=120.0)
    sessions = sessionize([s1])
    assert len(sessions) == 1
    sess = sessions[0]
    assert sess.node_id == "node-1"
    assert sess.start == 1000.0
    assert sess.end == 1000.0 + SAMPLE_INTERVAL_SEC
    assert sess.end_reason == "CENSORED"


def test_sessionize_active_end_with_exact_moment_correction():
    # User returns: host_state becomes ACTIVE after 3 available samples
    # Input occurred 5.0 seconds before sample at 1045.0
    s1 = make_sample(1000.0, user_inactivity_sec=120.0)
    s2 = make_sample(1015.0, user_inactivity_sec=135.0)
    s3 = make_sample(1030.0, user_inactivity_sec=150.0)
    # Next sample at 1045.0 shows ACTIVE with user_inactivity_sec = 5.0
    s_active = make_sample(1045.0, host_state=HostState.ACTIVE, user_inactivity_sec=5.0)

    sessions = sessionize([s1, s2, s3, s_active])
    assert len(sessions) == 1
    sess = sessions[0]
    assert sess.start == 1000.0
    # Exact moment of input: 1045.0 - 5.0 = 1040.0
    assert sess.end == 1040.0
    assert sess.end_reason == "ACTIVE"


def test_sessionize_start_calculation_with_excess_inactivity():
    # First sample was detected with inactivity = 180s (> 120s threshold by 60s)
    # Previous active sample was at 900.0
    s_prev = make_sample(900.0, host_state=HostState.ACTIVE, user_inactivity_sec=2.0)
    s1 = make_sample(1000.0, user_inactivity_sec=180.0)  # 60s extra -> start at 940.0
    s2 = make_sample(1015.0, user_inactivity_sec=195.0)

    sessions = sessionize([s_prev, s1, s2])
    assert len(sessions) == 1
    sess = sessions[0]
    # start = 1000 - (180 - 120) = 940.0; clipped to >= 900.0 (prev sample ts)
    assert sess.start == 940.0
    assert sess.end_reason == "CENSORED"


def test_sessionize_start_clipped_to_previous_sample():
    # If excess inactivity would push start before previous sample, clip it
    s_prev = make_sample(950.0, host_state=HostState.ACTIVE, user_inactivity_sec=2.0)
    s1 = make_sample(1000.0, user_inactivity_sec=200.0)  # 80s extra -> 920.0 < 950.0

    sessions = sessionize([s_prev, s1])
    assert len(sessions) == 1
    sess = sessions[0]
    assert sess.start == 950.0  # clipped to prev ts


def test_sessionize_unplugged_end():
    # Battery unplugged while require_ac=True
    s1 = make_sample(1000.0, on_ac_power=True)
    s2 = make_sample(1015.0, on_ac_power=False)  # Unplugged

    sessions = sessionize([s1, s2], require_ac=True)
    assert len(sessions) == 1
    sess = sessions[0]
    assert sess.end == 1015.0
    assert sess.end_reason == "UNPLUGGED"


def test_sessionize_busy_end():
    # Laptop becomes CPU busy
    s1 = make_sample(1000.0, host_state=HostState.IDLE)
    s2 = make_sample(1015.0, host_state=HostState.BUSY)

    sessions = sessionize([s1, s2])
    assert len(sessions) == 1
    sess = sessions[0]
    assert sess.end == 1015.0
    assert sess.end_reason == "BUSY"


def test_sessionize_gap_end():
    # Missed samples (> MAX_GAP_SEC = 45s)
    s1 = make_sample(1000.0)
    s2 = make_sample(1015.0)
    # Next sample arrives at 1070.0 (gap = 55s > 45s)
    s3 = make_sample(1070.0)

    sessions = sessionize([s1, s2, s3])
    assert len(sessions) == 2
    sess1, sess2 = sessions
    assert sess1.end == 1015.0 + SAMPLE_INTERVAL_SEC
    assert sess1.end_reason == "GAP"
    assert sess2.start == 1070.0
    assert sess2.end_reason == "CENSORED"


def test_sessionize_multiple_nodes():
    # Samples from two different nodes interleaved
    n1_s1 = make_sample(1000.0, node_id="node-A")
    n2_s1 = make_sample(1000.0, node_id="node-B")
    n1_s2 = make_sample(1015.0, node_id="node-A")
    n2_s2 = make_sample(1015.0, node_id="node-B")

    sessions = sessionize([n1_s1, n2_s1, n1_s2, n2_s2])
    assert len(sessions) == 2
    nodes = {s.node_id for s in sessions}
    assert nodes == {"node-A", "node-B"}


def test_elapsed_idle():
    assert elapsed_idle(100.0, 150.0) == 50.0
    assert elapsed_idle(100.0, 90.0) == 0.0  # clamp to 0
