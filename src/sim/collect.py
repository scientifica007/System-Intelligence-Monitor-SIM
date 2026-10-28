"""Collection uses direct OS counters; unsupported values remain null."""
from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import time

import psutil

from . import SCHEMA_VERSION


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def capability(available: bool, source: str | None, reason: str | None = None) -> dict:
    return {"availability": "available" if available else "unsupported", "source": source if available else None,
            "reason": None if available else (reason or "not supported by this system")}


def gpu_devices() -> list[dict]:
    devices = []
    for item in sorted(Path("/sys/class/drm").glob("card[0-9]*")):
        if not item.name[4:].isdigit():
            continue
        path = item / "device"
        try:
            vendor = (path / "vendor").read_text().strip()
            device = (path / "device").read_text().strip()
        except (OSError, UnicodeError):
            continue
        devices.append({"card": item.name, "vendor_id": vendor, "device_id": device})
    return devices


def doctor() -> dict:
    gpu = gpu_devices()
    try:
        temps = psutil.sensors_temperatures()
    except (OSError, AttributeError):
        temps = {}
    try:
        battery = psutil.sensors_battery()
    except (OSError, AttributeError):
        battery = None
    return {
        "schema_version": SCHEMA_VERSION, "checked_at_utc": now_utc(),
        "system": {"distribution": platform.platform(), "kernel": platform.release(),
                   "architecture": platform.machine(), "cpu_logical": psutil.cpu_count(logical=True),
                   "cpu_physical": psutil.cpu_count(logical=False),
                   "memory_total_bytes": psutil.virtual_memory().total},
        "gpu_devices": gpu,
        "capabilities": {
            "cpu": capability(True, "psutil/procfs"),
            "memory": capability(True, "psutil/procfs"),
            "swap": capability(True, "psutil/procfs"),
            "processes": capability(True, "psutil/procfs"),
            "disk_io": capability(psutil.disk_io_counters() is not None, "psutil/procfs"),
            "network_io": capability(psutil.net_io_counters() is not None, "psutil/procfs"),
            "gpu_inventory": capability(bool(gpu), "sysfs", "No readable DRM card inventory"),
            "gpu_per_process": capability(False, None, "Not implemented; hardware support varies"),
            "power_per_process": capability(False, None, "No reliable per-application watt meter"),
            "temperature": capability(bool(temps), "psutil/hwmon", "No readable temperature sensors"),
            "battery": capability(battery is not None, "psutil/power_supply", "No accessible battery"),
            "smart": capability(False, None, "SMART probe not implemented")
        }
    }


def _cpu_pct(before, after) -> float | None:
    if before is None:
        return None
    # On Linux guest/guest_nice are already part of user/nice time.
    # Counting them twice would bias total utilization.
    a = sum(v for k, v in zip(after._fields, after) if k not in ("guest", "guest_nice"))
    b = sum(v for k, v in zip(before._fields, before) if k not in ("guest", "guest_nice"))
    dt = a - b
    if dt <= 0:
        return None
    idle_index = after._fields.index("idle")
    idle = after[idle_index] - before[idle_index]
    if "iowait" in after._fields:
        n = after._fields.index("iowait")
        idle += after[n] - before[n]
    return round(max(0.0, min(100.0, 100 * (dt - idle) / dt)), 2)


def _rate(previous: int | None, current: int | None, seconds: float) -> float | None:
    if previous is None or current is None or seconds <= 0 or current < previous:
        return None
    return round((current - previous) / seconds, 2)


class Collector:
    """Produce one snapshot; first-sample rates are unknown, not zero."""

    def __init__(self) -> None:
        self.last_ns: int | None = None
        self.last_cpu = None
        self.last_disk = None
        self.last_net = None
        self.last_procs: dict[tuple[int, float], float] = {}
        self.logical = psutil.cpu_count(logical=True) or 1

    def sample(self, *, process_limit: int = 300) -> dict:
        time_ns = time.monotonic_ns()
        seconds = None if self.last_ns is None else (time_ns - self.last_ns) / 1e9
        cpu = psutil.cpu_times()
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = psutil.disk_io_counters()
        net = psutil.net_io_counters()
        current_procs: dict[tuple[int, float], float] = {}
        processes = []
        inaccessible = 0
        for proc in psutil.process_iter(["pid", "name", "create_time", "memory_info", "cpu_times"]):
            try:
                p = proc.info
                created = p["create_time"]
                cpu_times = p["cpu_times"]
                if created is None or cpu_times is None:
                    continue
                key = (p["pid"], created)
                consumed = cpu_times.user + cpu_times.system
                current_procs[key] = consumed
                previous = self.last_procs.get(key)
                one_core = _rate_float(previous, consumed, seconds)
                rss = p["memory_info"].rss if p["memory_info"] else None
                processes.append({"pid": p["pid"], "created_at_epoch": created,
                                  "name": p["name"], "rss_bytes": rss,
                                  "cpu_percent_one_core": one_core,
                                  "cpu_percent_machine": round(one_core / self.logical, 2) if one_core is not None else None})
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
                inaccessible += 1
        # Keep the largest processes by memory, but retain all identities in the baseline.
        processes.sort(key=lambda p: (p["rss_bytes"] or 0), reverse=True)
        processes = processes[:max(1, min(process_limit, 5000))]
        result = {
            "schema_version": SCHEMA_VERSION, "timestamp_utc": now_utc(),
            "monotonic_ns": time_ns,
            "interval_ms": round(seconds * 1000) if seconds is not None else None,
            "system": {"cpu_percent_total": _cpu_pct(self.last_cpu, cpu),
                       "cpu_logical": self.logical,
                       "memory_total_bytes": memory.total,
                       "memory_used_bytes": memory.used,
                       "memory_available_bytes": memory.available,
                       "swap_total_bytes": swap.total,
                       "swap_used_bytes": swap.used,
                       "disk_read_bytes_per_second": _rate(getattr(self.last_disk, "read_bytes", None), getattr(disk, "read_bytes", None), seconds or 0),
                       "disk_write_bytes_per_second": _rate(getattr(self.last_disk, "write_bytes", None), getattr(disk, "write_bytes", None), seconds or 0),
                       "net_recv_bytes_per_second": _rate(getattr(self.last_net, "bytes_recv", None), getattr(net, "bytes_recv", None), seconds or 0),
                       "net_sent_bytes_per_second": _rate(getattr(self.last_net, "bytes_sent", None), getattr(net, "bytes_sent", None), seconds or 0)},
            "processes": processes, "inaccessible_processes": inaccessible,
            "gpu": {"utilization_percent": None, "availability": "unsupported", "source": None},
            "power": {"watts": None, "availability": "unsupported", "source": None}
        }
        self.last_ns, self.last_cpu, self.last_disk, self.last_net, self.last_procs = (
            time_ns, cpu, disk, net, current_procs)
        return result


def _rate_float(before: float | None, after: float, seconds: float | None) -> float | None:
    if before is None or seconds is None or seconds <= 0 or after < before:
        return None
    return round(max(0.0, (after - before) * 100 / seconds), 2)
