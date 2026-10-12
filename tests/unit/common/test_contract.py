"""
Contract lock (PRD section 15.4): fails if any shared model or enum in
idlegrid/common/models.py changes without a deliberate snapshot update.

To change the contract on purpose: update PRD Appendix A + docs/contract.md, bump
SCHEMA_VERSION, then regenerate the snapshot with
    UPDATE_CONTRACT_SNAPSHOT=1 pytest tests/unit/common/test_contract.py
and get the approvals listed in docs/contract.md.
"""

import enum
import inspect
import json
import os
import re
from pathlib import Path

from pydantic import BaseModel

from idlegrid.common import models

SNAPSHOT = Path(__file__).with_name("contract_snapshot.json")


def _annotation(tp) -> str:
    text = repr(tp)
    text = re.sub(r"<class '([\w.]+)'>", r"\1", text)
    text = re.sub(r"<enum '(\w+)'>", r"\1", text)
    text = text.replace("typing.", "").replace("idlegrid.common.models.", "")
    return text


def build_snapshot() -> dict:
    snap = {"schema_version": models.SCHEMA_VERSION, "enums": {}, "models": {}}
    for name, obj in sorted(vars(models).items()):
        if inspect.isclass(obj) and obj.__module__ == models.__name__:
            if issubclass(obj, enum.Enum):
                snap["enums"][name] = [m.value for m in obj]
            elif issubclass(obj, BaseModel):
                fields = {}
                for fname, f in obj.model_fields.items():
                    if f.is_required():
                        default = "<required>"
                    elif f.default_factory is not None:
                        default = "<factory>"
                    else:
                        default = repr(f.default.value if isinstance(f.default, enum.Enum) else f.default)
                    fields[fname] = {"type": _annotation(f.annotation), "default": default}
                snap["models"][name] = fields
    return snap


def test_contract_matches_snapshot():
    current = build_snapshot()
    if os.environ.get("UPDATE_CONTRACT_SNAPSHOT") == "1":
        SNAPSHOT.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert current == expected, (
        "Shared contract changed (idlegrid/common/models.py). If intended, follow the "
        "contract-change process in docs/contract.md and regenerate the snapshot."
    )


def test_schema_version_is_semver_major_minor():
    assert re.fullmatch(r"\d+\.\d+", models.SCHEMA_VERSION)


def test_terminal_status_sets_are_subsets():
    assert models.TERMINAL_JOB_STATUSES <= set(models.JobStatus)
    assert models.TERMINAL_ATTEMPT_STATUSES <= set(models.AttemptStatus)


def test_heartbeat_round_trip():
    hb = models.Heartbeat(
        node_id="node-0123456789ab", hostname="laptop", sent_at=1.0, host_state="IDLE",
        metrics=models.NodeMetrics(cpu_percent=5, host_cpu_percent=5, cpu_count=8, ram_percent=40,
                                   ram_available_mb=8000, ram_total_mb=16000, disk_free_gb=100,
                                   user_inactivity_sec=300),
        power=models.PowerInfo(on_ac_power=True, battery_percent=90),
        capabilities=models.NodeCapabilities(os="Windows", os_release="11", arch="AMD64", python_version="3.12",
                                             agent_version="0.1.0", cpu_count=8, ram_total_mb=16000, perf_score=1.0,
                                             input_method="win32_getlastinputinfo", input_precision="PRECISE",
                                             can_prevent_sleep=True, worker_env_hash="abc"),
        sharing=models.SharingPrefs(),
    )
    again = models.Heartbeat.model_validate_json(hb.model_dump_json())
    assert again == hb
    assert again.schema_version == models.SCHEMA_VERSION


def test_usage_batch_limit():
    import pytest
    sample = models.UsageSample(ts_utc=0, tz_offset_min=330, node_id="n", cpu_percent=1, host_cpu_percent=1,
                                ram_percent=1, user_inactivity_sec=None, input_method="none",
                                input_precision="NONE", host_state="UNKNOWN", on_ac_power=None,
                                battery_percent=None, job_running=False, agent_version="0.1.0")
    with pytest.raises(Exception):
        models.UsageBatch(node_id="n", samples=[sample] * 2001)
