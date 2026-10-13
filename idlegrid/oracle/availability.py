"""Single source of truth for node availability and sessionization.

PRD §10.4.4.
Shared across Oracle, Simulator, Analytics and Agent.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from idlegrid.common.models import HostState, InputDetection, Session, UsageSample

IDLE_THRESHOLD_SEC: float = 120.0  # Must equal agent idle_threshold_sec
SAMPLE_INTERVAL_SEC: float = 15.0
MAX_GAP_SEC: float = 45.0  # > 3 missed samples = agent off / laptop asleep


def is_available(s: UsageSample, require_ac: bool = True) -> bool:
    """Determine whether a single usage sample represents an available node.

    An available sample must:
    1. Have host_state == "IDLE"
    2. Be on AC power (if require_ac is True; None / desktop counts as AC)
    3. Have valid input detection (input_precision != "NONE")
    """
    host_state_str = s.host_state.value if isinstance(s.host_state, HostState) else str(s.host_state)
    if host_state_str != "IDLE":
        return False

    if require_ac and s.on_ac_power is False:
        return False

    precision_str = (
        s.input_precision.value
        if isinstance(s.input_precision, InputDetection)
        else str(s.input_precision)
    )
    return precision_str != "NONE"


def sessionize(
    samples: Sequence[UsageSample],
    require_ac: bool = True,
) -> list[Session]:
    """Maximal runs of available samples with consecutive gaps <= MAX_GAP_SEC.

    Semantics per PRD §10.4.4:
    - start = first.ts - (first.user_inactivity_sec - IDLE_THRESHOLD_SEC),
      clipped to >= previous sample ts (if one exists).
    - end:
      - next sample exists within MAX_GAP_SEC and host_state == ACTIVE:
        end = next.ts - next.user_inactivity_sec (exact input moment),
        end_reason = "ACTIVE"
      - next sample exists within MAX_GAP_SEC and unavailable for another reason:
        end = next.ts,
        end_reason = "UNPLUGGED" if (require_ac and next.on_ac_power is False) else "BUSY"
      - gap > MAX_GAP_SEC:
        end = last.ts + SAMPLE_INTERVAL_SEC, end_reason = "GAP"
      - end of data:
        end = last.ts + SAMPLE_INTERVAL_SEC, end_reason = "CENSORED"
    """
    if not samples:
        return []

    # Group samples by node_id, preserving / sorting chronologically
    by_node: dict[str, list[UsageSample]] = defaultdict(list)
    for s in samples:
        by_node[s.node_id].append(s)

    all_sessions: list[Session] = []

    for node_id, node_samples in by_node.items():
        node_samples.sort(key=lambda x: x.ts_utc)

        current_session_start: float | None = None
        last_avail_sample: UsageSample | None = None
        prev_sample: UsageSample | None = None

        for s in node_samples:
            s_avail = is_available(s, require_ac=require_ac)

            if current_session_start is not None:
                # We are currently tracking an active session
                gap = s.ts_utc - (prev_sample.ts_utc if prev_sample else s.ts_utc)
                if gap > MAX_GAP_SEC:
                    # Gap exceeded threshold: close previous session with GAP
                    assert last_avail_sample is not None
                    end = last_avail_sample.ts_utc + SAMPLE_INTERVAL_SEC
                    all_sessions.append(
                        Session(
                            node_id=node_id,
                            start=current_session_start,
                            end=max(current_session_start, end),
                            end_reason="GAP",
                        )
                    )
                    current_session_start = None
                    last_avail_sample = None
                    # Fall through to check if current sample starts a new session

                elif not s_avail:
                    # Next sample exists within MAX_GAP_SEC but is not available
                    host_state_str = (
                        s.host_state.value if isinstance(s.host_state, HostState) else str(s.host_state)
                    )
                    if host_state_str == "ACTIVE":
                        inact = s.user_inactivity_sec if s.user_inactivity_sec is not None else 0.0
                        end = s.ts_utc - inact
                        end_reason = "ACTIVE"
                    elif require_ac and s.on_ac_power is False:
                        end = s.ts_utc
                        end_reason = "UNPLUGGED"
                    else:
                        end = s.ts_utc
                        end_reason = "BUSY"

                    assert last_avail_sample is not None
                    # Ensure end is at least last available sample's timestamp
                    end = max(last_avail_sample.ts_utc, end)
                    all_sessions.append(
                        Session(
                            node_id=node_id,
                            start=current_session_start,
                            end=max(current_session_start, end),
                            end_reason=end_reason,
                        )
                    )
                    current_session_start = None
                    last_avail_sample = None
                    prev_sample = s
                    continue

                else:
                    # Next sample within MAX_GAP_SEC and available: extend session
                    last_avail_sample = s
                    prev_sample = s
                    continue

            # Start of a new session
            if s_avail:
                inact = (
                    s.user_inactivity_sec
                    if s.user_inactivity_sec is not None
                    else IDLE_THRESHOLD_SEC
                )
                offset = max(0.0, inact - IDLE_THRESHOLD_SEC)
                calc_start = s.ts_utc - offset
                if prev_sample is not None:
                    calc_start = max(calc_start, prev_sample.ts_utc)
                current_session_start = calc_start
                last_avail_sample = s

            prev_sample = s

        # If data ended while a session was still open
        if current_session_start is not None and last_avail_sample is not None:
            end = last_avail_sample.ts_utc + SAMPLE_INTERVAL_SEC
            all_sessions.append(
                Session(
                    node_id=node_id,
                    start=current_session_start,
                    end=max(current_session_start, end),
                    end_reason="CENSORED",
                )
            )

    return all_sessions


def elapsed_idle(available_since: float, now: float) -> float:
    """Calculate elapsed idle time in seconds."""
    return max(0.0, now - available_since)
