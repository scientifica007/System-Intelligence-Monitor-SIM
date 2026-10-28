"""Session files, state identity, secure writes and streaming JSONL."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import secrets

import psutil

from . import SCHEMA_VERSION
from .collect import now_utc
from .paths import data_dir, state_dir, private_dir, read_json, write_json


def state_file() -> Path:
    return state_dir() / "recorder.json"


def sessions_dir() -> Path:
    return data_dir() / "sessions"


@contextmanager
def control_lock():
    private_dir(state_dir())
    fd = os.open(state_dir() / "control.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def process_alive(state: dict | None) -> bool:
    if not state or not isinstance(state.get("pid"), int):
        return False
    try:
        actual = psutil.Process(state["pid"])
        return abs(actual.create_time() - state["pid_created_at_epoch"]) < 0.1 and actual.is_running() and actual.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, KeyError, TypeError):
        return False


def current_state() -> dict:
    state = read_json(state_file())
    if not state:
        return {"state": "stopped", "recording": False}
    if not process_alive(state):
        return {"state": "stopped", "recording": False, "note": "Recorder is not running; last session may be interrupted",
                "last_session_id": state.get("session_id")}
    return {"state": "recording", "recording": True, "pid": state["pid"],
            "session_id": state["session_id"], "started_at_utc": state.get("started_at_utc")}


def new_session(label: str, interval: float, limit: int) -> tuple[str, Path]:
    private_dir(sessions_dir())
    sid = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)
    path = sessions_dir() / sid
    path.mkdir(mode=0o700)
    manifest = {"schema_version": SCHEMA_VERSION, "session_id": sid, "label": label,
                "started_at_utc": now_utc(), "ended_at_utc": None, "state": "starting",
                "interval_seconds": interval, "process_limit": limit, "sample_count": 0}
    write_json(path / "manifest.json", manifest)
    return sid, path


def session_path(session_id: str) -> Path:
    if not session_id or len(session_id) > 80 or not all(c.isalnum() or c in "-_" for c in session_id):
        raise ValueError("Invalid session ID")
    path = sessions_dir() / session_id
    if not (path / "manifest.json").is_file():
        raise FileNotFoundError(f"Session not found: {session_id}")
    return path


def list_sessions() -> list[dict]:
    if not sessions_dir().exists():
        return []
    results = []
    for path in sorted(sessions_dir().iterdir(), reverse=True):
        if path.is_dir():
            data = read_json(path / "manifest.json")
            if isinstance(data, dict):
                results.append(data)
    return results


def append_jsonl(handle, data: dict) -> None:
    handle.write(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")
    handle.flush()


def read_latest_sample(session_id: str) -> dict | None:
    path = session_path(session_id) / "samples.jsonl"
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            end = handle.tell()
            if not end:
                return None
            offset = max(0, end - 4 * 1024 * 1024)
            handle.seek(offset)
            lines = handle.read().splitlines()
            if offset and lines:
                lines = lines[1:]
            for line in reversed(lines):
                try:
                    return json.loads(line)
                except (ValueError, UnicodeError):
                    continue
    except FileNotFoundError:
        return None
    return None


def stream_samples(session_id: str):
    path = session_path(session_id) / "samples.jsonl"
    with path.open(encoding="utf-8") as handle:
        for n, line in enumerate(handle, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Corrupted JSONL at line {n}") from exc
