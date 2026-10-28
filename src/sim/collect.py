"""Collection uses direct OS counters; unsupported values remain null."""
from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import subprocess
import shutil
import time

import psutil

from . import SCHEMA_VERSION


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def capability(available: bool, source: str | None, reason: str | None = None, unavailable: str = "unsupported") -> dict:
    return {"availability": "available" if available else unavailable,
            "source": source if available else None,
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
        try:
            driver = (path / "driver").resolve(strict=True).name
        except (OSError, RuntimeError):
            driver = None
        devices.append({"card": item.name, "vendor_id": vendor, "device_id": device, "driver": driver})
    return devices


def os_release() -> dict:
    try:
        return platform.freedesktop_os_release()
    except (AttributeError, OSError, ValueError):
        return {}


def temperature_readings() -> dict:
    try:
        groups = psutil.sensors_temperatures(fahrenheit=False)
    except (OSError, AttributeError, RuntimeError):
        groups = {}
    readings = []
    for group, sensors in sorted(groups.items()):
        for index, sensor in enumerate(sensors):
            current = getattr(sensor, "current", None)
            if current is None:
                continue
            readings.append({"group": group, "label": sensor.label or f"sensor-{index}",
                             "current_celsius": current,
                             "high_celsius": getattr(sensor, "high", None),
                             "critical_celsius": getattr(sensor, "critical", None),
                             "source": "psutil/hwmon"})
    return {"availability": "available" if readings else "not_detected",
            "source": "psutil/hwmon" if readings else None,
            "readings": readings}


def power_supply(root: Path = Path("/sys/class/power_supply")) -> list[dict]:
    supplies = []
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return supplies
    for entry in entries:
        if not entry.is_dir():
            continue
        try:
            kind = (entry / "type").read_text().strip()
        except OSError:
            kind = "unknown"
        supplies.append({"name": entry.name, "type": kind})
    return supplies


def memory_modules() -> dict:
    """Explicit opt-in privileged SMBIOS read, no serial numbers."""
    if os.geteuid() != 0:
        return {"availability": "permission_required", "source": None,
                "reason": "Run doctor --memory-modules as root explicitly; normal monitoring needs no root",
                "modules": []}
    if not shutil.which("dmidecode"):
        return {"availability": "unavailable", "source": None,
                "reason": "dmidecode is not installed", "modules": []}
    try:
        proc = subprocess.run(["dmidecode", "-t", "17"], capture_output=True,
                              text=True, timeout=5, check=True)
    except (OSError, subprocess.SubprocessError):
        return {"availability": "unavailable", "source": None,
                "reason": "SMBIOS inventory could not be read", "modules": []}
    fields = {"Size": "size", "Locator": "locator", "Bank Locator": "bank_locator",
              "Type": "type", "Speed": "speed"}
    modules = []
    current = None
    for line in proc.stdout.splitlines():
        if line.strip() == "Memory Device":
            if current is not None:
                modules.append(current)
            current = {}
        elif current is not None and ":" in line:
            key, value = line.strip().split(":", 1)
            if key in fields:
                current[fields[key]] = value.strip()
    if current is not None:
        modules.append(current)
    return {"availability": "available" if modules else "not_detected",
            "source": "dmidecode/SMBIOS", "modules": modules}


def doctor(*, with_memory_modules: bool = False) -> dict:
    gpu = gpu_devices()
    temperatures = temperature_readings()
    supplies = power_supply()
    distro = os_release()
    try:
        battery = psutil.sensors_battery()
    except (OSError, AttributeError, RuntimeError):
        battery = None
    return {
        "schema_version": SCHEMA_VERSION, "checked_at_utc": now_utc(),
        "system": {"distribution": distro.get("PRETTY_NAME") or platform.platform(),
                   "os_id": distro.get("ID"), "os_name": distro.get("NAME"),
                   "os_version": distro.get("VERSION_ID"), "os_codename": distro.get("VERSION_CODENAME"),
                   "kernel": platform.release(), "architecture": platform.machine(),
                   "cpu_logical": psutil.cpu_count(logical=True), "cpu_physical": psutil.cpu_count(logical=False),
                   "memory_total_bytes": psutil.virtual_memory().total},
        "memory_modules": memory_modules() if with_memory_modules else {
            "availability": "not_collected", "source": None,
            "reason": "Opt-in with doctor --memory-modules (privileged)", "modules": []},
        "gpu_devices": gpu,
        "power_supplies": supplies,
        "temperature_sensors": temperatures,
        "capabilities": {
            "cpu": capability(True, "psutil/procfs"),
            "memory": capability(True, "psutil/procfs"),
            "swap": capability(True, "psutil/procfs"),
            "processes": capability(True, "psutil/procfs"),
            "disk_io": capability(psutil.disk_io_counters() is not None, "psutil/procfs", unavailable="not_detected"),
            "network_io": capability(psutil.net_io_counters() is not None, "psutil/procfs", unavailable="not_detected"),
            "gpu_inventory": capability(bool(gpu), "sysfs", "No readable DRM card inventory", "not_detected"),
            "gpu_per_process": capability(False, None, "Not implemented; hardware support varies", "not_implemented"),
            "power_per_process": capability(False, None, "No reliable per-application watt meter", "not_implemented"),
            "temperature": capability(bool(temperatures["readings"]), "psutil/hwmon", "No readable temperature sensors", "not_detected"),
            "battery": capability(battery is not None, "psutil/power_supply", "No accessible battery reading", "not_detected"),
            "smart": capability(False, None, "SMART probe not implemented", "not_implemented")
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
        self.last_process_ns: int | None = None
        self.logical = psutil.cpu_count(logical=True) or 1

    def sample(self, *, process_limit: int = 300, include_processes: bool = True) -> dict:
        time_ns = time.monotonic_ns()
        seconds = None if self.last_ns is None else (time_ns - self.last_ns) / 1e9
        cpu = psutil.cpu_times()
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = psutil.disk_io_counters()
        net = psutil.net_io_counters()
        proc_seconds = None if self.last_process_ns is None else (time_ns - self.last_process_ns) / 1e9
        process_interval_ms = round(proc_seconds * 1000) if include_processes and proc_seconds is not None else None
        current_procs: dict[tuple[int, float], float] = {}
        processes = []
        inaccessible = 0
        for proc in (psutil.process_iter(["pid", "name", "create_time", "memory_info", "cpu_times"]) if include_processes else []):
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
                one_core = _rate_float(previous, consumed, proc_seconds)
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
            "processes": processes, "processes_sampled": include_processes,
            "process_interval_ms": process_interval_ms,
            "inaccessible_processes": inaccessible if include_processes else None,
            "temperatures": temperature_readings(),
            "gpu": {"utilization_percent": None, "availability": "not_implemented", "source": None},
            "power": {"watts": None, "availability": "unsupported", "source": None}
        }
        self.last_ns, self.last_cpu, self.last_disk, self.last_net = time_ns, cpu, disk, net
        if include_processes:
            self.last_procs = current_procs
            self.last_process_ns = time_ns
        return result


def _rate_float(before: float | None, after: float, seconds: float | None) -> float | None:
    if before is None or seconds is None or seconds <= 0 or after < before:
        return None
    return round(max(0.0, (after - before) * 100 / seconds), 2)
