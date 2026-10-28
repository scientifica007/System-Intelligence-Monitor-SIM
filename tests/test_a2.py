"""Alpha 2 regression tests: sparse collection, probes and cap."""
import json
from pathlib import Path
import signal
import time
from types import SimpleNamespace
import pytest
from sim import __version__, collect, recorder
from sim.collect import Collector, doctor, temperature_readings, memory_modules, gpu_devices
from sim.paths import read_json, write_json
from sim.storage import new_session, state_file, read_latest_sample


def test_version_and_distro(monkeypatch):
    assert __version__ == "0.1.0a3"
    monkeypatch.setattr(collect.platform, "freedesktop_os_release",
                        lambda: {"PRETTY_NAME": "Ubuntu 24.04.5 LTS", "VERSION_ID": "24.04", "ID": "ubuntu"})
    d = doctor()
    assert d["system"]["distribution"] == "Ubuntu 24.04.5 LTS"
    assert d["system"]["os_version"] == "24.04"
    assert "power_supplies" in d and "temperature_sensors" in d
    assert d["capabilities"]["smart"]["availability"] == "not_implemented"


def test_gpu_inventory_driver(tmp_path, monkeypatch):
    dev = tmp_path / "card1" / "device"
    dev.mkdir(parents=True)
    (dev / "vendor").write_text("0x8086\n")
    (dev / "device").write_text("0x0046\n")
    driver = tmp_path / "drivers" / "i915"
    driver.mkdir(parents=True)
    (dev / "driver").symlink_to(driver)
    monkeypatch.setattr(collect, "Path", lambda _: tmp_path)
    devices = gpu_devices()
    assert devices == [{"card": "card1", "vendor_id": "0x8086",
                        "device_id": "0x0046", "driver": "i915"}]


def test_temperature_presence_and_absence(monkeypatch):
    monkeypatch.setattr(collect.psutil, "sensors_temperatures", lambda fahrenheit=False: {})
    assert temperature_readings()["availability"] == "not_detected"
    sample = SimpleNamespace(label="CPU", current=53.0, high=90.0, critical=100.0)
    monkeypatch.setattr(collect.psutil, "sensors_temperatures", lambda fahrenheit=False: {"coretemp": [sample]})
    assert temperature_readings()["readings"][0]["current_celsius"] == 53.0


def test_smbios_requires_explicit_permission(monkeypatch):
    monkeypatch.setattr(collect.os, "geteuid", lambda: 1000)
    assert memory_modules()["availability"] == "permission_required"
    assert doctor()["memory_modules"]["availability"] == "not_collected"


def test_sparse_processes_and_timestamps():
    c = Collector()
    first = c.sample(process_limit=4)
    time.sleep(.04)
    skipped = c.sample(process_limit=4, include_processes=False)
    time.sleep(.04)
    resumed = c.sample(process_limit=4)
    assert first["processes_sampled"] is True
    assert skipped["processes_sampled"] is False and skipped["processes"] == []
    assert resumed["processes_sampled"] is True
    assert resumed["process_interval_ms"] is not None and resumed["process_interval_ms"] >= 60
    assert "temperatures" in skipped


def test_old_and_new_process_snapshots(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    sid, path = new_session("legacy", 1.0, 4)
    with (path / "samples.jsonl").open("w") as f:
        f.write(json.dumps({"timestamp_utc": "old", "processes": [{"pid": 1}]}) + "\n")
        f.write(json.dumps({"timestamp_utc": "new", "processes": [], "processes_sampled": False}) + "\n")
    assert read_latest_sample(sid)["timestamp_utc"] == "new"
    assert read_latest_sample(sid, require_processes=True)["timestamp_utc"] == "old"


def test_session_limit_is_terminal(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    sid, path = new_session("cap", .5, 1, 5, 1)
    write_json(state_file(), {"session_id": sid, "token": "test-token"})
    class BigCollector:
        def sample(self, **kwargs):
            return {"system": {"cpu_percent_total": 5}, "blob": "x" * 1049000}
    monkeypatch.setattr(recorder, "Collector", BigCollector)
    original_term, original_int = signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT)
    try:
        assert recorder.record(sid, "test-token", .5, 1, 5, 1) == 0
    finally:
        signal.signal(signal.SIGTERM, original_term)
        signal.signal(signal.SIGINT, original_int)
    assert read_json(path / "manifest.json")["state"] == "size_limit"
    assert "session_size_limit" in (path / "events.jsonl").read_text()
