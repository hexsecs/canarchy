"""J1939 built-in metadata resources.

Provides lazy-loaded, cached access to bundled PGN, SPN, and source address
metadata. DBC input takes precedence over these definitions for signal
extraction, scaling, and naming.
"""

from __future__ import annotations

import importlib.resources
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

_REQUIRED_DECODE_FIELDS = frozenset(("pgn", "start", "length", "resolution", "offset", "units"))

# OEM/proprietary SPN extensions: a JSON file shaped like the bundled
# spns.json ({"<spn>": {"name": ...}}) merged over the built-in catalog.
# Resolved from $CANARCHY_J1939_SPN_OVERRIDES, falling back to
# ~/.canarchy/j1939_spns.json when present.
_SPN_OVERRIDES_ENV = "CANARCHY_J1939_SPN_OVERRIDES"
_SPN_OVERRIDES_DEFAULT = Path.home() / ".canarchy" / "j1939_spns.json"


def _spn_overrides() -> dict[int, dict[str, Any]]:
    raw_path = os.environ.get(_SPN_OVERRIDES_ENV)
    path = Path(raw_path) if raw_path else _SPN_OVERRIDES_DEFAULT
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
def _spn_data() -> dict[int, dict[str, Any]]:
    text = (
        importlib.resources.files("canarchy.resources.j1939")
        .joinpath("spns.json")
        .read_text(encoding="utf-8")
    )
    data = {int(k): v for k, v in json.loads(text).items() if k.isdigit()}
    for spn, entry in _spn_overrides().items():
        data[spn] = {**data.get(spn, {}), **entry}
    return data


@lru_cache(maxsize=1)
def _pgn_data() -> dict[int, dict[str, Any]]:
    text = (
        importlib.resources.files("canarchy.resources.j1939")
        .joinpath("pgns.json")
        .read_text(encoding="utf-8")
    )
    return {int(k): v for k, v in json.loads(text).items() if k.isdigit()}


@lru_cache(maxsize=1)
def _source_address_data() -> dict[int, str]:
    text = (
        importlib.resources.files("canarchy.resources.j1939")
        .joinpath("source_addresses.json")
        .read_text(encoding="utf-8")
    )
    return {int(k): v for k, v in json.loads(text).items() if k.isdigit()}


def spn_lookup(spn: int) -> dict[str, Any] | None:
    """Return all built-in metadata for the given SPN, or None if unknown."""
    return _spn_data().get(spn)


@lru_cache(maxsize=1)
def decodable_spns() -> frozenset[int]:
    """SPNs with enough built-in metadata for byte-level signal decoding."""
    return frozenset(
        spn for spn, entry in _spn_data().items() if _REQUIRED_DECODE_FIELDS.issubset(entry)
    )


def pgn_lookup(pgn: int) -> dict[str, Any] | None:
    """Return built-in metadata for the given PGN, or None if unknown."""
    return _pgn_data().get(pgn)


def spns_for_pgn(pgn: int) -> list[dict[str, Any]]:
    """Return built-in SPN definitions carried by the given PGN, sorted by SPN.

    Each entry is the SPN's catalog metadata with its ``spn`` number included.
    """
    return [
        {"spn": spn, **entry}
        for spn, entry in sorted(_spn_data().items())
        if entry.get("pgn") == pgn
    ]


def source_address_lookup(addr: int) -> str | None:
    """Return the standard name for the given J1939 source address, or None."""
    return _source_address_data().get(addr)


@lru_cache(maxsize=1)
def _fmi_data() -> dict[int, str]:
    text = (
        importlib.resources.files("canarchy.resources.j1939")
        .joinpath("fmis.json")
        .read_text(encoding="utf-8")
    )
    return {int(k): v for k, v in json.loads(text).items() if k.isdigit()}


def fmi_lookup(fmi: int) -> str | None:
    """Return the SAE J1939-73 description for the given FMI, or None."""
    return _fmi_data().get(fmi)
