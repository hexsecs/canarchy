"""J1587 built-in metadata resources.

Provides lazy-loaded, cached access to the bundled PID catalog, mirroring
``canarchy.j1939_metadata``.
"""

from __future__ import annotations

import importlib.resources
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

_REQUIRED_DECODE_FIELDS = frozenset(("length", "resolution", "offset", "units"))

# Fleet/OEM PID extensions: a JSON file shaped like the bundled pids.json
# ({"<pid>": {"name": ...}}) merged over the built-in catalog. Resolved from
# $CANARCHY_J1587_PID_OVERRIDES, falling back to ~/.canarchy/j1587_pids.json
# when present.
_PID_OVERRIDES_ENV = "CANARCHY_J1587_PID_OVERRIDES"
_PID_OVERRIDES_DEFAULT = Path.home() / ".canarchy" / "j1587_pids.json"


def _pid_overrides() -> dict[int, dict[str, Any]]:
    raw_path = os.environ.get(_PID_OVERRIDES_ENV)
    path = Path(raw_path) if raw_path else _PID_OVERRIDES_DEFAULT
    if not path.is_file():
        return {}
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(entries, dict):
        return {}
    return {
        int(key): value
        for key, value in entries.items()
        if str(key).isdigit() and isinstance(value, dict)
    }


@lru_cache(maxsize=1)
def _pid_data() -> dict[int, dict[str, Any]]:
    text = (
        importlib.resources.files("canarchy.resources.j1587")
        .joinpath("pids.json")
        .read_text(encoding="utf-8")
    )
    data = {int(k): v for k, v in json.loads(text).items() if k.isdigit()}
    for pid, entry in _pid_overrides().items():
        data[pid] = {**data.get(pid, {}), **entry}
    return data


def pid_lookup(pid: int) -> dict[str, Any] | None:
    """Return all built-in metadata for the given J1587 PID, or None if unknown."""
    return _pid_data().get(pid)


@lru_cache(maxsize=1)
def decodable_pids() -> frozenset[int]:
    """PIDs with enough built-in metadata for byte-level value decoding."""
    return frozenset(
        pid for pid, entry in _pid_data().items() if _REQUIRED_DECODE_FIELDS.issubset(entry)
    )
