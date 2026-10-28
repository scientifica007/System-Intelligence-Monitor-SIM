"""Streaming, version-tolerant session statistics (without exposing process names)."""
from datetime import datetime
import math

from .paths import read_json
from .storage import session_path, stream_samples


def _timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.timestamp() if parsed.tzinfo else None
    except ValueError:
        return None


class _Mean:
    def __init__(self):
        self.count = 0
        self.total = 0.0
        self.minimum = None
        self.maximum = None

    def add(self, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return
        self.count += 1
        self.total += value
        self.minimum = value if self.minimum is None else min(self.minimum, value)
        self.maximum = value if self.maximum is None else max(self.maximum, value)

    def result(self):
        return {"count": self.count, "mean": round(self.total / self.count, 4) if self.count else None,
                "min": self.minimum, "max": self.maximum}


def summarize(session_id: str) -> dict:
    """Scan one session in O(number of sensors) memory, not O(number of samples)."""
    folder = session_path(session_id)
    manifest = read_json(folder / "manifest.json")
    if not isinstance(manifest, dict):
        raise ValueError("Session manifest is missing")
    interval = manifest.get("interval_seconds", 2)
    threshold = max(3.0, interval * 1.5) if isinstance(interval, (int, float)) and interval > 0 else 3.0
    cpu, mem, collected, lateness, write_time = (_Mean() for _ in range(5))
    temperature_stats = {}
    count = process_count = delayed_count = 0
    max_gap = None
    previous_ns = previous_wall = None
    first_time = last_time = first_ns = last_ns = None
    for item in stream_samples(session_id):
        if item.get("session_id") not in (None, session_id):
            raise ValueError(f"Foreign session ID in sample {count + 1}")
        count += 1
        stamp = item.get("timestamp_utc")
        epoch = _timestamp(stamp)
        ns = item.get("monotonic_ns")
        if not isinstance(ns, int) or isinstance(ns, bool):
            ns = None
        if count == 1:
            first_time, first_ns = stamp, ns
        last_time, last_ns = stamp, ns
        gap = None
        if previous_ns is not None and ns is not None:
            gap = (ns - previous_ns) / 1e9
        elif previous_wall is not None and epoch is not None:
            gap = epoch - previous_wall
        if gap is not None and gap >= 0:
            max_gap = max(max_gap or 0, gap)
            if gap > threshold:
                delayed_count += 1
        previous_ns, previous_wall = ns, epoch
        system = item.get("system") or {}
        cpu.add(system.get("cpu_percent_total"))
        mem.add(system.get("memory_used_bytes"))
        if item.get("processes_sampled", True):
            process_count += 1
        timing = item.get("timing") or {}
        collected.add(timing.get("collector_duration_ms"))
        lateness.add(timing.get("sampling_lateness_ms"))
        write_time.add(timing.get("previous_write_duration_ms"))
        for sensor in (item.get("temperatures") or {}).get("readings", []):
            key = f"{sensor.get('group', 'unknown')}/{sensor.get('label', 'unknown')}"
            temperature_stats.setdefault(key, _Mean()).add(sensor.get("current_celsius"))
    if not count:
        raise ValueError("Session contains no samples")
    if first_ns is not None and last_ns is not None:
        duration = (last_ns - first_ns) / 1e9
    else:
        a, b = _timestamp(first_time), _timestamp(last_time)
        duration = b - a if a is not None and b is not None else None
    size = (folder / "samples.jsonl").stat().st_size
    return {
        "session_id": session_id, "schema_version": manifest.get("schema_version"),
        "session_state": manifest.get("state"), "sample_count": count,
        "manifest_sample_count": manifest.get("sample_count"),
        "sample_count_matches_manifest": count == manifest.get("sample_count") if manifest.get("sample_count") is not None else None,
        "first_sample_utc": first_time, "last_sample_utc": last_time,
        "duration_seconds": round(duration, 3) if duration is not None else None,
        "sample_file_bytes": size,
        "observed_mb_per_hour": round(size / 1e6 * 3600 / duration, 3) if duration and duration > 0 else None,
        "target_interval_seconds": interval, "gap_threshold_seconds": threshold,
        "gaps_over_threshold": delayed_count,
        "max_gap_seconds": round(max_gap, 6) if max_gap is not None else None,
        "process_detail_samples": process_count,
        "system_cpu_percent": cpu.result(), "memory_used_bytes": mem.result(),
        "collector_duration_ms": collected.result(),
        "sampling_lateness_ms": lateness.result(),
        "previous_write_duration_ms": write_time.result(),
        "temperature_celsius": {key: value.result() for key, value in sorted(temperature_stats.items())},
        "reported_sampling_delay_events": manifest.get("sampling_delay_events"),
        "reported_skipped_deadlines": manifest.get("skipped_schedule_deadlines"),
        "interpretation_note": "Descriptive statistics; no invented samples or claims about root cause"
    }
