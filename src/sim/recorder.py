"""Detached recorder process. Parent commands control it by verified identity."""
import argparse
import os
import signal
import sys
import threading
import time

from .collect import Collector, doctor, now_utc
from .paths import read_json, write_json
from .storage import append_jsonl, session_path, state_file


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
        # The first sample deliberately has unknown rates; no fake 0% CPU.
        with os.fdopen(os.open(path / "samples.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as samples, \
             os.fdopen(os.open(path / "events.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as events:
            append_jsonl(events, {"event": "recording_started", "timestamp_utc": now_utc()})
            while not stop_event.is_set():
                start = time.monotonic()
                include_processes = count == 0 or count % process_every == 0 or detail_next
                item = collector.sample(process_limit=limit, include_processes=include_processes)
                item["session_id"] = session_id
                cpu = item["system"]["cpu_percent_total"]
                detail_next = cpu is not None and cpu >= 75.0
                append_jsonl(samples, item)
                count += 1
                if samples.tell() >= size_limit_bytes:
                    reason = "size_limit"
                    append_jsonl(events, {"event": "session_size_limit", "timestamp_utc": now_utc(),
                                          "limit_mib": max_session_mib})
                    break
                if count % 10 == 0:
                    os.fsync(samples.fileno())
                stop_event.wait(max(0.0, interval - (time.monotonic() - start)))
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
        manifest.update({"state": reason, "ended_at_utc": now_utc(), "sample_count": count})
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
