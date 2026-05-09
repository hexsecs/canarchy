"""pretty_j1939 integration for richer J1939 human-readable output.

Provides SA names, PGN labels, and decoded SPN field values in text-mode
output for j1939 decode / monitor / pgn / dm1 / summary commands.
Structured output (--json / --jsonl) is never affected.
"""

from __future__ import annotations

from pretty_j1939.describe import get_describer as _get_describer

_STRUCTURAL_KEYS = {"PGN", "SA", "DA", "Priority", "Bytes"}


def get_describer(da_json: str | None = None):
    """Return a configured J1939Describer instance."""
    return _get_describer(da_json=da_json)  # type: ignore[no-any-return]


def describe_frame(describer, arbitration_id: int, data_hex: str) -> dict[str, str] | None:
    """Decode SPN values from a raw CAN frame.

    Returns a dict of {field_name: value_string} for any SPNs that pretty_j1939
    can decode, excluding structural keys (SA, DA, PGN, Priority) that CANarchy
    already surfaces.  Returns None when the frame cannot be decoded.
    """
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
