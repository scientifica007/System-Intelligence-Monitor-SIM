"""Detached recorder with observable monotonic scheduling and no fabricated samples."""
import argparse
import os
import signal
import sys
import threading
import time

from .collect import Collector, doctor, now_utc
from .paths import read_json, write_json
from .storage import append_jsonl, session_path, state_file



def delay_threshold_seconds(interval: float) -> float:
    """Avoid treating normal low-frequency sampling as a delay."""
    return max(3.0, interval * 1.5)


def advance_deadline(deadline: float, completed_at: float, interval: float) -> tuple[float, int]:
    """Move to the first future absolute time-slot; never spin to catch up."""
    upcoming = deadline + interval
    if upcoming > completed_at:
        return upcoming, 0
    skipped = int((completed_at - upcoming) // interval) + 1
    return upcoming + skipped * interval, skipped


def record(session_id: str, token: str, interval: float, limit: int,
           process_every: int = 1, max_session_mib: int = 128) -> int:
    path = session_path(session_id)
    manifest_path = path / "manifest.json"
    stop_event = threading.Event()

    def stop(_signal, _frame):
        stop_event.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    count = 0
    reason = "stopped"
    delay_events = 0
    skipped_total = 0
    try:
        # The parent may still be atomically publishing the initial state.
        # Wait briefly rather than treating scheduler ordering as an error.
        state = None
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = read_json(state_file())
            if state and state.get("token") == token and state.get("session_id") == session_id:
                break
            time.sleep(0.02)
        else:
            raise RuntimeError("Recorder state/token mismatch")
        manifest = read_json(manifest_path)
        manifest["state"] = "recording"
        write_json(manifest_path, manifest)
        write_json(path / "capabilities.json", doctor())
        collector = Collector()
        size_limit_bytes = max_session_mib * 1024 * 1024
        detail_next = False
        next_deadline = time.monotonic()
        last_sample_ns = None
        previous_write_ms = None
        delay_threshold = delay_threshold_seconds(interval)
        # The first sample deliberately has unknown rates; no fake 0% CPU.
        with os.fdopen(os.open(path / "samples.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as samples, \
             os.fdopen(os.open(path / "events.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as events:
            append_jsonl(events, {"event": "recording_started", "timestamp_utc": now_utc()})
            while not stop_event.is_set():
                if stop_event.wait(max(0.0, next_deadline - time.monotonic())):
                    break
                started_ns = time.monotonic_ns()
                lateness_ms = max(0.0, (started_ns / 1e9 - next_deadline) * 1000)
                include_processes = count == 0 or count % process_every == 0 or detail_next
                item = collector.sample(process_limit=limit, include_processes=include_processes)
                collected_ns = time.monotonic_ns()
                item["session_id"] = session_id
                item["timing"] = {
                    "collector_duration_ms": round((collected_ns - started_ns) / 1e6, 3),
                    "sampling_lateness_ms": round(lateness_ms, 3),
                    "previous_write_duration_ms": previous_write_ms,
                }
                sample_ns = item.get("monotonic_ns")
                if not isinstance(sample_ns, int):
                    sample_ns = started_ns
                if last_sample_ns is not None:
                    gap_seconds = (sample_ns - last_sample_ns) / 1e9
                    if gap_seconds > delay_threshold:
                        delay_events += 1
                        append_jsonl(events, {"event": "sampling_delay",
                                              "timestamp_utc": now_utc(),
                                              "sample_timestamp_utc": item.get("timestamp_utc"),
                                              "gap_seconds": round(gap_seconds, 6),
                                              "target_interval_seconds": interval,
                                              "threshold_seconds": delay_threshold})
                last_sample_ns = sample_ns
                cpu = item["system"]["cpu_percent_total"]
                detail_next = cpu is not None and cpu >= 75.0
                write_started_ns = time.monotonic_ns()
                append_jsonl(samples, item)
                count += 1
                if count % 10 == 0:
                    os.fsync(samples.fileno())
                previous_write_ms = round((time.monotonic_ns() - write_started_ns) / 1e6, 3)
                if samples.tell() >= size_limit_bytes:
                    reason = "size_limit"
                    append_jsonl(events, {"event": "session_size_limit", "timestamp_utc": now_utc(),
                                          "limit_mib": max_session_mib})
                    break
                next_deadline, missed = advance_deadline(next_deadline, time.monotonic(), interval)
                if missed:
                    skipped_total += missed
                    append_jsonl(events, {"event": "schedule_overrun", "timestamp_utc": now_utc(),
                                          "skipped_deadlines": missed, "target_interval_seconds": interval})
            append_jsonl(events, {"event": "recording_stopped", "timestamp_utc": now_utc(), "reason": reason})
            os.fsync(samples.fileno())
        return 0
    except Exception as exc:
        reason = "failed"
        with (path / "recorder-error.log").open("a", encoding="utf-8") as errors:
            os.chmod(path / "recorder-error.log", 0o600)
            errors.write(f"{now_utc()} {type(exc).__name__}: {exc}\n")
        return 1
    finally:
        manifest = read_json(manifest_path) or {}
        manifest.update({"state": reason, "ended_at_utc": now_utc(), "sample_count": count,
                         "sampling_delay_events": delay_events,
                         "skipped_schedule_deadlines": skipped_total})
        write_json(manifest_path, manifest)
        # Preserve the state file on exit for post-mortem context; process identity
        # check makes status report stopped, and next start overwrites it.


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--interval", type=float, required=True)
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument("--process-every", type=int, default=1)
    parser.add_argument("--max-session-mib", type=int, default=128)
    args = parser.parse_args()
    return record(args.session_id, args.token, args.interval, args.limit,
                  args.process_every, args.max_session_mib)


if __name__ == "__main__":
    sys.exit(main())
