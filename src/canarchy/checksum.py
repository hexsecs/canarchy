"""CAN checksums: Chrysler/Stellantis CRC-8, SAE J1850, and per-platform helpers."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

__all__ = [
    "CrcAlgorithm",
    "chrysler_message_checksum",
    "compute_checksum",
    "crc8_sae_j1850",
    "detect_algorithm_from_dbc",
    "repair_crc",
    "repair_stellantis_crc",
]

# ---------------------------------------------------------------------------
# Algorithm registry
# ---------------------------------------------------------------------------


class CrcAlgorithm(str, Enum):
    """Known CRC algorithms used by CAN DBC platforms."""

    STELLANTIS = "stellantis"
    SAE_J1850 = "sae-j1850"
    FCA_GIORGIO = "fca-giorgio"


# ---------------------------------------------------------------------------
# CRC-8/SAE-J1850 table
# ---------------------------------------------------------------------------

_CRC8_J1850_TABLE: list[int] | None = None


def _build_crc8_j1850_table() -> list[int]:
    poly = 0x1D
    table = []
    for byte in range(256):
        crc = byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) & 0xFF) ^ poly
            else:
                crc = (crc << 1) & 0xFF
        table.append(crc)
    return table


def crc8_sae_j1850(data: bytes, *, init: int = 0x00) -> int:
    """Compute CRC-8/SAE-J1850 over *data*.

    Polynomial ``0x1D``, init *init*, no reflection, no final XOR.
    """
    global _CRC8_J1850_TABLE
    if _CRC8_J1850_TABLE is None:
        _CRC8_J1850_TABLE = _build_crc8_j1850_table()
    crc = init
    for byte in data:
        idx = crc ^ byte
        crc = _CRC8_J1850_TABLE[idx]
    return crc


# ---------------------------------------------------------------------------
# Chrysler / Stellantis custom CRC
# ---------------------------------------------------------------------------


def chrysler_message_checksum(data: bytes) -> int:
    """Compute the Chrysler/Stellantis custom CRC-8 for an encoded message.

    Uses the non-linear bit-feedback algorithm reverse-engineered
    from Chrysler/FCA CAN traffic. The checksum is computed over all
    payload bytes **except** the last byte (the checksum position).

    Equivalent to the ``chrysler_checksum`` function in openpilot's
    ``opendbc/car/chrysler/chryslercan.py``.
    """
    if not data:
        return 0
    checksum = 0xFF
    for j in range(len(data) - 1):
        curr = data[j]
        shift = 0x80
        for _ in range(8):
            bit_sum = curr & shift
            temp_chk = checksum & 0x80
            if bit_sum:
                bit_sum = 0x1C
                if temp_chk:
                    bit_sum = 1
                checksum = (checksum << 1) & 0xFF
                temp_chk = checksum | 1
                bit_sum ^= temp_chk
            else:
                if temp_chk:
                    bit_sum = 0x1D
                checksum = (checksum << 1) & 0xFF
                bit_sum ^= checksum
            checksum = bit_sum & 0xFF
            shift >>= 1
    return (~checksum) & 0xFF


# ---------------------------------------------------------------------------
# FCA Giorgio per-address XOR table
# ---------------------------------------------------------------------------

_FCA_GIORGIO_XOR: dict[int, int] = {
    0xDE: 0x10,
    0x106: 0xF6,
    0x122: 0xF1,
}
_FCA_GIORGIO_XOR_DEFAULT = 0x0A


def fca_giorgio_checksum(data: bytes, address: int = 0) -> int:
    """Compute the FCA Giorgio platform CRC-8/SAE-J1850 with per-address XOR."""
    base = crc8_sae_j1850(data, init=0x00)
    xor_val = _FCA_GIORGIO_XOR.get(address, _FCA_GIORGIO_XOR_DEFAULT)
    return base ^ xor_val


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def compute_checksum(
    algorithm: CrcAlgorithm,
    data: bytes,
    *,
    address: int | None = None,
) -> int:
    """Compute the CAN message checksum for *algorithm* over *data*.

    Parameters
    ----------
    algorithm : CrcAlgorithm
        Which CRC algorithm to use.
    data : bytes
        Full encoded message payload. The last byte is treated as the
        checksum slot.
    address : int, optional
        CAN arbitration ID; required by some algorithms (e.g. FCA Giorgio).
    """
    if algorithm == CrcAlgorithm.STELLANTIS:
        return chrysler_message_checksum(data)
    if algorithm == CrcAlgorithm.SAE_J1850:
        return crc8_sae_j1850(data[:-1], init=0x00) if len(data) > 1 else 0
    if algorithm == CrcAlgorithm.FCA_GIORGIO:
        base = crc8_sae_j1850(data[:-1], init=0x00) if len(data) > 1 else 0
        xor_val = _FCA_GIORGIO_XOR.get(address or 0, _FCA_GIORGIO_XOR_DEFAULT)
        return base ^ xor_val
    msg = f"Unknown CRC algorithm: {algorithm!r}"
    raise ValueError(msg)


# ---------------------------------------------------------------------------
# DBC-to-algorithm detection
# ---------------------------------------------------------------------------

_DBC_NAME_PREFIX_MAP: list[tuple[str, CrcAlgorithm]] = [
    ("_stellantis_", CrcAlgorithm.STELLANTIS),
    ("chrysler_", CrcAlgorithm.STELLANTIS),
    ("fca_giorgio", CrcAlgorithm.FCA_GIORGIO),
]


def detect_algorithm_from_dbc(dbc_path: str) -> CrcAlgorithm | None:
    """Detect the CRC algorithm from a DBC file path or provider ref.

    Checks known name prefixes in order. Returns ``None`` when no
    known algorithm matches.
    """
    stem = Path(dbc_path).stem
    for prefix, algorithm in _DBC_NAME_PREFIX_MAP:
        if stem.startswith(prefix):
            return algorithm
    return None


# ---------------------------------------------------------------------------
# CRC repair helpers (post-mutation fixup)
# ---------------------------------------------------------------------------


def repair_crc(
    data: bytes,
    algorithm: CrcAlgorithm = CrcAlgorithm.STELLANTIS,
    *,
    address: int | None = None,
) -> bytes:
    """Replace the last byte of *data* with the correct CRC for *algorithm*.

    Parameters
    ----------
    data : bytes
        Full encoded message payload. The last byte is treated as the
        checksum slot and will be overwritten.
    algorithm : CrcAlgorithm
        Which CRC algorithm to use.  Defaults to Stellantis for
        backward compatibility.
    address : int, optional
        CAN arbitration ID; required by some algorithms (e.g. FCA Giorgio).
    """
    if len(data) < 2:
        return data
    crc = compute_checksum(algorithm, data, address=address)
    return data[:-1] + bytes([crc])


def repair_stellantis_crc(data: bytes) -> bytes:
    """Replace the last byte of *data* with the correct Stellantis CRC-8.

    Convenience wrapper around :func:`repair_crc` for backward compatibility.
    """
    return repair_crc(data, CrcAlgorithm.STELLANTIS)
