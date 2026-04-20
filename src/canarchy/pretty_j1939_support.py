"""Optional pretty_j1939 integration for richer J1939 human-readable output.

When pretty_j1939 is installed (pip install canarchy[j1939-pretty]), this module
enables SPN value decoding from raw CAN frame data for human-oriented output modes.
Structured output (--json / --jsonl) is never affected.

When pretty_j1939 is not installed the public API is still importable and all
functions return None / False so call-sites require no conditional guards.
"""

from __future__ import annotations

try:
    from pretty_j1939.describe import get_describer as _get_describer

    _AVAILABLE = True
except ImportError:  # pragma: no cover
    _AVAILABLE = False


_STRUCTURAL_KEYS = {"PGN", "SA", "DA", "Priority", "Bytes"}


def is_available() -> bool:
    return _AVAILABLE


def get_describer(da_json: str | None = None):
    """Return a J1939Describer instance, or None when pretty_j1939 is absent."""
    if not _AVAILABLE:
        return None
    return _get_describer(da_json=da_json)  # type: ignore[no-any-return]


def describe_frame(describer, arbitration_id: int, data_hex: str) -> dict[str, str] | None:
    """Decode SPN values from a raw CAN frame.

    Returns a dict of {field_name: value_string} for any SPNs that pretty_j1939
    can decode, excluding structural keys (SA, DA, PGN, Priority) that CANarchy
    already surfaces.  Returns None when pretty_j1939 is unavailable or the frame
    cannot be decoded.
    """
    if describer is None:
        return None
    try:
        data_bytes = bytes.fromhex(data_hex)
        result = describer(data_bytes, arbitration_id)
        decoded = {
            k: str(v)
            for k, v in result.items()
            if not k.startswith("_") and k not in _STRUCTURAL_KEYS
        }
        return decoded or None
    except Exception:
        return None
