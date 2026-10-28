"""Stable command-line interface to the Linux recorder."""
import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time

import psutil

from . import __version__
from .collect import Collector, doctor
from .paths import private_dir, read_json, write_json
from .storage import (control_lock, current_state, list_sessions, new_session,
                      process_alive, read_latest_sample, session_path, state_dir,
                      state_file, stream_samples)


def output(obj, json_mode=False) -> None:
    if json_mode:
        print(json.dumps(obj, indent=2, ensure_ascii=False))
    elif isinstance(obj, (dict, list)):
        print(json.dumps(obj, indent=2, ensure_ascii=False))
    else:
        print(obj)


def start(args) -> int:
    if not 0.5 <= args.interval <= 3600:
        raise ValueError("--interval must be between 0.5 and 3600 seconds")
    if not 1 <= args.process_limit <= 5000:
        raise ValueError("--process-limit must be between 1 and 5000")
    if not 1 <= args.process_every <= 3600:
        raise ValueError("--process-every must be between 1 and 3600")
    if not 1 <= args.max_session_mib <= 100000:
        raise ValueError("--max-session-mib must be between 1 and 100000")
    if len(args.label) > 120:
        raise ValueError("Label must be 120 characters or shorter")
    with control_lock():
        state = current_state()
        if state["recording"]:
            raise ValueError(f"Recorder already running: {state['session_id']}")
        session_id, path = new_session(args.label, args.interval, args.process_limit,
                                       args.process_every, args.max_session_mib)
        token = secrets.token_hex(16)
        logfile = private_dir(state_dir()) / "recorder.stderr.log"
        with os.fdopen(os.open(logfile, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "ab") as log:
            proc = subprocess.Popen([sys.executable, "-m", "sim.recorder",
                                     "--session-id", session_id, "--token", token,
                                     "--interval", str(args.interval), "--limit", str(args.process_limit),
                                     "--process-every", str(args.process_every),
                                     "--max-session-mib", str(args.max_session_mib)],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log,
                                    start_new_session=True, close_fds=True)
        try:
            started = psutil.Process(proc.pid).create_time()
        except psutil.NoSuchProcess:
            started = -1
        write_json(state_file(), {"state": "starting", "pid": proc.pid,
                                  "pid_created_at_epoch": started, "token": token,
                                  "session_id": session_id, "started_at_utc": read_json(path / "manifest.json")["started_at_utc"]})
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            manifest = read_json(path / "manifest.json") or {}
            if manifest.get("state") == "recording" and (path / "samples.jsonl").exists():
                output({"state": "recording", "session_id": session_id, "pid": proc.pid,
                        "path": str(path), "interval_seconds": args.interval,
                        "process_every": args.process_every,
                        "max_session_mib": args.max_session_mib}, args.json)
                return 0
            if proc.poll() is not None:
                raise RuntimeError(f"Recorder exited during start; inspect {path / 'recorder-error.log'}")
            time.sleep(0.1)
        raise RuntimeError(f"Recorder startup timed out; inspect {path / 'recorder-error.log'}")


def stop(args) -> int:
    with control_lock():
        state = read_json(state_file())
        if not process_alive(state):
            output({"state": "stopped", "message": "No active recording"}, args.json)
            return 0
        os.kill(state["pid"], signal.SIGTERM)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if not process_alive(state):
                manifest = read_json(session_path(state["session_id"]) / "manifest.json") or {}
                output({"state": manifest.get("state", "stopped"), "session_id": state["session_id"],
                        "sample_count": manifest.get("sample_count")}, args.json)
                return 0
            time.sleep(0.1)
        raise RuntimeError("Recorder did not stop within 10 seconds; manual investigation required")


def latest() -> dict:
    state = current_state()
    if not state["recording"]:
        raise ValueError("No active recorder; start with `sim start` first")
    item = read_latest_sample(state["session_id"])
    if item is None:
        raise ValueError("Recorder has not written a sample yet")
    item["sample_age_note"] = "Last recorded sample, not a new instantaneous reading"
    return item


def show(args):
    item = latest()
    if args.resource == "cpu":
        val = {"timestamp_utc": item["timestamp_utc"], "cpu_percent_total": item["system"]["cpu_percent_total"],
               "cpu_logical": item["system"]["cpu_logical"]}
    elif args.resource == "ram":
        val = {"timestamp_utc": item["timestamp_utc"], **{k: v for k, v in item["system"].items() if "memory" in k or "swap" in k}}
    elif args.resource == "disk":
        val = {"timestamp_utc": item["timestamp_utc"], **{k: v for k, v in item["system"].items() if k.startswith("disk_")}}
    elif args.resource == "network":
        val = {"timestamp_utc": item["timestamp_utc"], **{k: v for k, v in item["system"].items() if k.startswith("net_")}}
    else:
        val = {"timestamp_utc": item["timestamp_utc"], **item[args.resource]}
    output(val, args.json)


def top(args):
    state = current_state()
    if not state["recording"]:
        raise ValueError("No active recorder; start with `sim start` first")
    item = read_latest_sample(state["session_id"], require_processes=True)
    if item is None:
        raise ValueError("Recorder has not written a process snapshot yet")
    key = "rss_bytes" if args.sort == "ram" else "cpu_percent_one_core"
    proc = sorted(item["processes"], key=lambda p: p[key] if p[key] is not None else -1, reverse=True)[:args.limit]
    if args.json:
        output({"timestamp_utc": item["timestamp_utc"], "sort": args.sort, "processes": proc,
                "snapshot_note": "Last detailed process sample, not necessarily latest system sample"}, True)
    else:
        print(f"Last process sample: {item['timestamp_utc']} | CPU% = one logical CPU (may exceed 100%)")
        print(f"{'PID':>7} {'CPU%':>9} {'RSS MiB':>10}  Name")
        for p in proc:
            c = "n/a" if p["cpu_percent_one_core"] is None else f"{p['cpu_percent_one_core']:.1f}"
            m = "n/a" if p["rss_bytes"] is None else f"{p['rss_bytes'] / 1024**2:.1f}"
            print(f"{p['pid']:>7} {c:>9} {m:>10}  {p['name']}")


def live(args):
    try:
        while True:
            obj = latest()
            s = obj["system"]
            print(f"{obj['timestamp_utc']} CPU={s['cpu_percent_total']}% RAM={s['memory_used_bytes'] / 1024**3:.2f} GiB", flush=True)
            time.sleep(args.refresh)
    except KeyboardInterrupt:
        print("Live view closed; recorder continues.")


def export(args):
    manifest = read_json(session_path(args.session_id) / "manifest.json")
    if not manifest:
        raise ValueError("Session manifest is missing")
    # Exclusive create: never overwrite data or follow a pre-existing output symlink.
    dest = Path(args.output).expanduser()
    with dest.open("x", encoding="utf-8") as out:
        os.chmod(dest, 0o600)
        if args.format == "jsonl":
            for sample in stream_samples(args.session_id):
                out.write(json.dumps(sample, ensure_ascii=False) + "\n")
        else:
            out.write(json.dumps({"schema_version": manifest["schema_version"], "manifest": manifest}, ensure_ascii=False)[:-1])
            out.write(',"samples":[')
            for n, sample in enumerate(stream_samples(args.session_id)):
                if n:
                    out.write(",")
                out.write(json.dumps(sample, ensure_ascii=False))
            out.write("]}\n")
    output({"output": str(dest), "format": args.format}, args.json)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sim", description="Linux performance monitoring and background recording")
    p.add_argument("--version", action="version", version=f"SIM {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    d = sub.add_parser("doctor", help="Probe available system metrics and sensors")
    d.add_argument("--json", action="store_true")
    d.add_argument("--memory-modules", action="store_true", help="Opt-in SMBIOS inventory; requires root")
    a = sub.add_parser("start", help="Start background recorder")
    a.add_argument("--interval", type=float, default=2.0)
    a.add_argument("--process-limit", type=int, default=300)
    a.add_argument("--process-every", type=int, default=5, help="Detailed process sample every N system samples")
    a.add_argument("--max-session-mib", type=int, default=128, help="Stop near this size limit in MiB")
    a.add_argument("--label", default="")
    a.add_argument("--json", action="store_true")
    for name in ("stop", "status"):
        sub.add_parser(name).add_argument("--json", action="store_true")
    sh = sub.add_parser("show", help="View most recent recorded metric")
    sh.add_argument("resource", choices=["cpu", "ram", "disk", "network", "gpu", "power", "temperatures"])
    sh.add_argument("--json", action="store_true")
    top_p = sub.add_parser("top", help="Highest recorded resource consumers")
    top_p.add_argument("--sort", choices=["cpu", "ram"], default="cpu")
    top_p.add_argument("--limit", type=int, default=15)
    top_p.add_argument("--json", action="store_true")
    lv = sub.add_parser("live", help="Watch last saved samples; Ctrl+C closes view only")
    lv.add_argument("--refresh", type=float, default=2.0)
    ss = sub.add_parser("sessions", help="List or inspect sessions")
    sss = ss.add_subparsers(dest="action", required=True)
    sss.add_parser("list").add_argument("--json", action="store_true")
    detail = sss.add_parser("show")
    detail.add_argument("session_id")
    detail.add_argument("--json", action="store_true")
    ex = sub.add_parser("export", help="Export a recorded session")
    ex.add_argument("session_id")
    ex.add_argument("--format", choices=["jsonl", "json"], default="jsonl")
    ex.add_argument("--output", required=True)
    ex.add_argument("--json", action="store_true")
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "doctor":
            output(doctor(with_memory_modules=args.memory_modules), args.json)
        elif args.command == "start":
            return start(args)
        elif args.command == "stop":
            return stop(args)
        elif args.command == "status":
            output(current_state(), args.json)
        elif args.command == "show":
            show(args)
        elif args.command == "top":
            top(args)
        elif args.command == "live":
            if not 0.25 <= args.refresh <= 3600:
                raise ValueError("--refresh must be between 0.25 and 3600")
            live(args)
        elif args.command == "sessions":
            if args.action == "list":
                output(list_sessions(), args.json)
            else:
                output(read_json(session_path(args.session_id) / "manifest.json"), args.json)
        elif args.command == "export":
            export(args)
        return 0
    except (ValueError, FileNotFoundError, PermissionError, RuntimeError, OSError) as exc:
        print(f"sim: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
