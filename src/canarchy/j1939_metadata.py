"""J1939 built-in metadata resources.

Provides lazy-loaded, cached access to bundled PGN, SPN, and source address
metadata. DBC input takes precedence over these definitions for signal
extraction, scaling, and naming.
"""

from __future__ import annotations

import importlib.resources
import json
from functools import lru_cache
from typing import Any

_REQUIRED_DECODE_FIELDS = frozenset(("pgn", "start", "length", "resolution", "offset", "units"))


@lru_cache(maxsize=1)
def _spn_data() -> dict[int, dict[str, Any]]:
    text = (
        importlib.resources.files("canarchy.resources.j1939")
        .joinpath("spns.json")
        .read_text(encoding="utf-8")
    )
    return {int(k): v for k, v in json.loads(text).items() if k.isdigit()}


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


def source_address_lookup(addr: int) -> str | None:
    """Return the standard name for the given J1939 source address, or None."""
    return _source_address_data().get(addr)
