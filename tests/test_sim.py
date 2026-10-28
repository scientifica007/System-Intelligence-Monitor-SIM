"""End-to-end CLI and local unit tests; no privileged access required."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil
import pytest

from sim.collect import Collector, _rate, _rate_float, doctor
from sim.storage import session_path


def command(*args, env, ok=True):
    result = subprocess.run([sys.executable, "-m", "sim", *args], env=env, text=True,
                            capture_output=True, timeout=20)
    if ok:
        assert result.returncode == 0, (result.stderr, result.stdout)
    return result


@pytest.fixture
def environment(tmp_path):
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "data")
    env["XDG_STATE_HOME"] = str(tmp_path / "state")
    env["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")
    yield env
    # Ensure a failed test never leaves the detached monitor running.
    command("stop", env=env)


def test_doctor_json(environment):
    result = json.loads(command("doctor", "--json", env=environment).stdout)
    assert result["system"]["cpu_logical"] >= 1
    assert result["capabilities"]["cpu"]["availability"] == "available"
    assert result["capabilities"]["gpu_per_process"]["availability"] == "not_implemented"


def test_first_rates_are_unknown_not_zero():
    collector = Collector()
    first = collector.sample(process_limit=5)
    assert first["system"]["cpu_percent_total"] is None
    assert first["system"]["disk_read_bytes_per_second"] is None
    assert first["gpu"]["utilization_percent"] is None
    assert first["gpu"]["availability"] == "not_implemented"
    time.sleep(0.02)
    second = collector.sample(process_limit=5)
    assert second["interval_ms"] > 0
    assert 0 <= second["system"]["cpu_percent_total"] <= 100


def test_rate_reset_and_identity():
    assert _rate(200, 100, 1.0) is None
    assert _rate(200, 300, 2.0) == 50
    assert _rate_float(10.0, 8.0, 2.0) is None
    assert _rate_float(None, 8.0, 2.0) is None
    assert _rate_float(0.0, 1.0, 2.0) == 50


def test_session_id_rejects_path_traversal():
    with pytest.raises(ValueError):
        session_path("../../private")


def test_cli_record_stop_and_export(environment, tmp_path):
    assert json.loads(command("status", "--json", env=environment).stdout)["state"] == "stopped"
    start = json.loads(command("start", "--interval", "0.5", "--label", "test", "--json", env=environment).stdout)
    sid = start["session_id"]
    try:
        assert start["state"] == "recording"
        status = json.loads(command("status", "--json", env=environment).stdout)
        assert status["state"] == "recording"
        assert "token" not in status
        duplicate = command("start", env=environment, ok=False)
        assert duplicate.returncode != 0
        time.sleep(1.1)
        cpu = json.loads(command("show", "cpu", "--json", env=environment).stdout)
        assert 0 <= cpu["cpu_percent_total"] <= 100
        top = json.loads(command("top", "--sort", "ram", "--limit", "3", "--json", env=environment).stdout)
        assert len(top["processes"]) <= 3
    finally:
        end = json.loads(command("stop", "--json", env=environment).stdout)
    assert end["state"] == "stopped"
    assert end["sample_count"] >= 2
    session = json.loads(command("sessions", "show", sid, "--json", env=environment).stdout)
    assert session["state"] == "stopped"
    assert session["sample_count"] >= 2
    out_jsonl = tmp_path / "sample.jsonl"
    out_json = tmp_path / "sample.json"
    command("export", sid, "--output", str(out_jsonl), env=environment)
    command("export", sid, "--format", "json", "--output", str(out_json), env=environment)
    samples = [json.loads(line) for line in out_jsonl.read_text().splitlines()]
    whole = json.loads(out_json.read_text())
    assert len(samples) == len(whole["samples"]) == session["sample_count"]
    assert all(item["session_id"] == sid for item in samples)
    assert (out_jsonl.stat().st_mode & 0o077) == 0
    already_exists = command("export", sid, "--output", str(out_jsonl), env=environment, ok=False)
    assert already_exists.returncode != 0
    assert json.loads(command("status", "--json", env=environment).stdout)["state"] == "stopped"


def test_invalid_config_and_missing_recording(environment):
    assert command("start", "--interval", "0.1", env=environment, ok=False).returncode != 0
    assert command("show", "cpu", env=environment, ok=False).returncode != 0
