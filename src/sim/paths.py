"""XDG paths and private, atomic JSON files."""
import json
import os
from pathlib import Path
import tempfile


def _xdg(name: str, default: str) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser() if value and Path(value).is_absolute() else Path.home() / default


def data_dir() -> Path:
    return _xdg("XDG_DATA_HOME", ".local/share") / "sim"


def state_dir() -> Path:
    return _xdg("XDG_STATE_HOME", ".local/state") / "sim"


def private_dir(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def write_json(path: Path, obj: dict) -> None:
    private_dir(path.parent)
    fd, tmp = tempfile.mkstemp(prefix=".sim-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(obj, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_json(path: Path) -> dict | None:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return None
