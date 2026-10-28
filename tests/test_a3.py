"""Alpha 3 regression tests, retaining the a1/a2 tests unchanged."""
import json
import time

import pytest

from sim import __version__
from sim.recorder import advance_deadline, delay_threshold_seconds
from sim.storage import new_session
from sim.summary import summarize
from test_sim import command, environment


def test_a3_version_and_absolute_scheduler():
    assert __version__ == "0.1.0a3"
    assert delay_threshold_seconds(2) == 3
    assert delay_threshold_seconds(10) == 15
    assert advance_deadline(10, 10.2, 2) == (12, 0)
    assert advance_deadline(10, 17.3, 2) == (18, 3)


def test_a3_legacy_summary_and_gap(environment, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", environment["XDG_DATA_HOME"])
    monkeypatch.setenv("XDG_STATE_HOME", environment["XDG_STATE_HOME"])
    sid, path = new_session("legacy", 2, 5)
    samples = [
        {"timestamp_utc": "2026-10-28T10:00:00+00:00", "monotonic_ns": 1_000_000_000,
         "system": {"cpu_percent_total": None, "memory_used_bytes": 1024},
         "processes": [], "processes_sampled": True},
        {"timestamp_utc": "2026-10-28T10:00:05+00:00", "monotonic_ns": 6_000_000_000,
         "system": {"cpu_percent_total": 40.0, "memory_used_bytes": 4096},
         "processes": [], "processes_sampled": False,
         "temperatures": {"readings": [{"group": "coretemp", "label": "Core 0", "current_celsius": 48}]}}
    ]
    (path / "samples.jsonl").write_text("".join(json.dumps(s) + "\n" for s in samples))
    result = summarize(sid)
    assert result["sample_count"] == 2
    assert result["process_detail_samples"] == 1
    assert result["max_gap_seconds"] == 5.0
    assert result["gaps_over_threshold"] == 1
    assert result["system_cpu_percent"]["mean"] == 40.0
    assert result["temperature_celsius"]["coretemp/Core 0"]["max"] == 48
    assert result["collector_duration_ms"]["mean"] is None
    cli = json.loads(command("summary", sid, "--json", env=environment).stdout)
    assert cli["max_gap_seconds"] == 5.0
    assert "Gaps" in command("summary", sid, env=environment).stdout


def test_a3_rejects_foreign_and_empty(environment, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", environment["XDG_DATA_HOME"])
    monkeypatch.setenv("XDG_STATE_HOME", environment["XDG_STATE_HOME"])
    sid, path = new_session("foreign", 2, 5)
    (path / "samples.jsonl").write_text(json.dumps({"session_id": "wrong"})+"\n")
    with pytest.raises(ValueError, match="Foreign"):
        summarize(sid)
    (path / "samples.jsonl").write_text("")
    with pytest.raises(ValueError, match="no samples"):
        summarize(sid)


def test_a3_real_recorder_timing_and_summary(environment):
    start = json.loads(command("start", "--interval", "0.5", "--process-every", "4", "--json", env=environment).stdout)
    sid = start["session_id"]
    try:
        time.sleep(1.6)
    finally:
        command("stop", env=environment)
    result = json.loads(command("summary", sid, "--json", env=environment).stdout)
    assert result["sample_count"] >= 2
    assert result["sample_count_matches_manifest"]
    assert result["collector_duration_ms"]["count"] == result["sample_count"]
    assert result["previous_write_duration_ms"]["count"] == result["sample_count"] - 1
    assert result["max_gap_seconds"] is not None
    assert result["observed_mb_per_hour"] > 0
