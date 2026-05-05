"""Local state: tracks every pod we've provisioned so we can warn about runaways
and build an immutable audit log. Stored under ~/.prime-intellect-mcp/ by default
(override with PRIME_INTELLECT_MCP_STATE_DIR)."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock
from typing import Any


def state_dir() -> Path:
    override = os.getenv("PRIME_INTELLECT_MCP_STATE_DIR")
    base = Path(override) if override else Path.home() / ".prime-intellect-mcp"
    base.mkdir(parents=True, exist_ok=True)
    return base


def state_file() -> Path:
    return state_dir() / "state.json"


def audit_file() -> Path:
    return state_dir() / "audit.log"


@dataclass
class TrackedPod:
    pod_id: str
    name: str | None
    hourly_usd: float
    started_at_unix: float
    max_lifetime_hours: int


_lock = Lock()


def _read() -> dict[str, dict[str, Any]]:
    p = state_file()
    if not p.exists():
        return {}
    try:
        loaded = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    return loaded


def _write(data: dict[str, dict[str, Any]]) -> None:
    p = state_file()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    tmp.replace(p)


def record_provisioned(tracked: TrackedPod) -> None:
    with _lock:
        data = _read()
        data[tracked.pod_id] = asdict(tracked)
        _write(data)


def record_terminated(pod_id: str) -> None:
    with _lock:
        data = _read()
        data.pop(pod_id, None)
        _write(data)


def list_tracked() -> list[TrackedPod]:
    with _lock:
        data = _read()
    return [TrackedPod(**v) for v in data.values()]


def append_audit(event: str, **fields: Any) -> None:
    line = json.dumps({"ts": time.time(), "event": event, **fields}, sort_keys=True)
    with _lock, audit_file().open("a") as f:
        f.write(line + "\n")
