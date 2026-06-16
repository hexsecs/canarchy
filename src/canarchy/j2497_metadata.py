"""J2497 built-in metadata resources.

Provides lazy-loaded, cached access to the bundled J2497/J1587 MID catalog —
a trailer-oriented subset that resolves common source MIDs to ECU names —
mirroring ``canarchy.j1587_metadata``.
"""

from __future__ import annotations

import importlib.resources
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

# Fleet/OEM MID extensions: a JSON file shaped like the bundled mids.json
# ({"<mid>": {"name": ...}}) merged over the built-in catalog. Resolved from
# $CANARCHY_J2497_MID_OVERRIDES, falling back to ~/.canarchy/j2497_mids.json
# when present.
_MID_OVERRIDES_ENV = "CANARCHY_J2497_MID_OVERRIDES"
_MID_OVERRIDES_DEFAULT = Path.home() / ".canarchy" / "j2497_mids.json"


def _mid_overrides() -> dict[int, dict[str, Any]]:
    raw_path = os.environ.get(_MID_OVERRIDES_ENV)
    path = Path(raw_path) if raw_path else _MID_OVERRIDES_DEFAULT
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
def _mid_data() -> dict[int, dict[str, Any]]:
    text = (
        importlib.resources.files("canarchy.resources.j2497")
        .joinpath("mids.json")
        .read_text(encoding="utf-8")
    )
    data = {int(k): v for k, v in json.loads(text).items() if k.isdigit()}
    for mid, entry in _mid_overrides().items():
        data[mid] = {**data.get(mid, {}), **entry}
    return data


def mid_lookup(mid: int) -> dict[str, Any] | None:
    """Return all built-in metadata for the given J2497/J1587 MID, or None if unknown."""
    return _mid_data().get(mid)


@lru_cache(maxsize=1)
def known_mids() -> frozenset[int]:
    """MIDs present in the bundled catalog."""
    return frozenset(_mid_data())
