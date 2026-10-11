"""Unit tests for synthetic trace generator and Appendix D CSV compliance.

PRD §10.4.3, Appendix D.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from idlegrid.oracle.availability import sessionize
from idlegrid.oracle.synthetic import (
    APPENDIX_D_HEADER,
    SyntheticTraceGenerator,
    format_iso_utc,
    parse_iso_utc,
    read_usage_csv,
    samples_to_csv_rows,
    write_usage_csv,
)


def test_iso_utc_formatting_roundtrip():
    ts = 1728984615.123
    iso_str = format_iso_utc(ts)
    assert iso_str.endswith("Z")
    parsed_ts = parse_iso_utc(iso_str)
    assert pytest.approx(ts, abs=0.002) == parsed_ts


def test_synthetic_trace_generator_schema(tmp_path: Path):
    gen = SyntheticTraceGenerator(node_id="node-test1", seed=123)
    # Generate 1 hour of telemetry (240 samples at 15s intervals)
    now = 1728984615.0
    samples = gen.generate_trace(duration_hours=1.0, end_time=now)
    assert len(samples) > 0
    assert samples[-1].ts_utc <= now

    # Verify monotonic increasing timestamps
    timestamps = [s.ts_utc for s in samples]
    assert timestamps == sorted(timestamps)

    # Convert to CSV rows
    csv_rows = samples_to_csv_rows(samples)
    assert len(csv_rows) == len(samples)

    # Verify Appendix D headers
    first_row = csv_rows[0]
    assert list(first_row.keys()) == APPENDIX_D_HEADER

    # Save to disk and re-read
    csv_file = tmp_path / "test_usage.csv"
    write_usage_csv(samples, csv_file)
    assert csv_file.exists()

    reloaded = read_usage_csv(csv_file)
    assert len(reloaded) == len(samples)
    for orig, rel in zip(samples, reloaded):
        assert orig.node_id == rel.node_id
        assert pytest.approx(orig.ts_utc, abs=0.002) == rel.ts_utc
        assert orig.host_state == rel.host_state
        assert orig.input_precision == rel.input_precision
        assert orig.job_running == rel.job_running
        assert orig.agent_version == rel.agent_version


def test_synthetic_sessions_integration():
    # Verify that synthetic traces produce valid sessions through sessionize
    gen = SyntheticTraceGenerator(node_id="node-sim", seed=42)
    samples = gen.generate_trace(duration_hours=12.0)
    sessions = sessionize(samples)
    assert len(sessions) > 0

    for s in sessions:
        assert s.node_id == "node-sim"
        assert s.start <= s.end
        assert s.end_reason in {"ACTIVE", "BUSY", "UNPLUGGED", "GAP", "CENSORED"}
