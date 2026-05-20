"""Tests for the canarchy.checksum module."""

from __future__ import annotations

import pytest

from canarchy.checksum import (
    CrcAlgorithm,
    chrysler_message_checksum,
    compute_checksum,
    crc8_sae_j1850,
    detect_algorithm_from_dbc,
    fca_giorgio_checksum,
    repair_crc,
    repair_stellantis_crc,
)


def test_crc8_sae_j1850_empty_input() -> None:
    result = crc8_sae_j1850(b"")
    assert result == 0x00


def test_crc8_sae_j1850_deterministic() -> None:
    a = crc8_sae_j1850(b"hello world")
    b = crc8_sae_j1850(b"hello world")
    assert a == b


def test_crc8_sae_j1850_table_vs_direct() -> None:
    """Verify table-based implementation matches a bit-by-bit reference."""
    def reference(data: bytes) -> int:
        crc = 0x00
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x80:
                    crc = ((crc << 1) ^ 0x1D) & 0xFF
                else:
                    crc = (crc << 1) & 0xFF
        return crc

    for payload in [b"", b"\x00", b"\xFF", b"test", bytes(range(256))]:
        assert crc8_sae_j1850(payload) == reference(payload)


def test_chrysler_checksum_deterministic() -> None:
    a = chrysler_message_checksum(b"\x00\x00\x00")
    b = chrysler_message_checksum(b"\x00\x00\x00")
    assert a == b


def test_chrysler_checksum_empty() -> None:
    assert chrysler_message_checksum(b"") == 0


def test_chrysler_checksum_different_payloads_different() -> None:
    a = chrysler_message_checksum(bytes([0x00, 0x00, 0x00]))
    b = chrysler_message_checksum(bytes([0x01, 0x00, 0x00]))
    assert a != b


def test_chrysler_checksum_all_zeros() -> None:
    """3-byte payload, CRC over first 2 zero bytes."""
    result = chrysler_message_checksum(bytes([0x00, 0x00, 0x00]))
    assert isinstance(result, int)
    assert 0 <= result <= 255


def test_chrysler_checksum_all_ones() -> None:
    result = chrysler_message_checksum(bytes([0xFF, 0xFF, 0x00]))
    assert isinstance(result, int)
    assert 0 <= result <= 255


def test_chrysler_checksum_8_byte_message() -> None:
    """CRC-8 computed over the first 7 bytes of an 8-byte payload."""
    result = chrysler_message_checksum(bytes([0xAA] * 7 + [0x00]))
    assert isinstance(result, int)
    assert 0 <= result <= 255


def test_repair_stellantis_crc_fixes_last_byte() -> None:
    raw = bytes([0x01, 0x00, 0xFF])
    repaired = repair_stellantis_crc(raw)
    assert len(repaired) == 3
    assert repaired[:2] == raw[:2]
    expected = chrysler_message_checksum(repaired)
    assert repaired[2] == expected


def test_repair_stellantis_crc_on_3_byte_payload() -> None:
    raw = bytes([0x80, 0x00, 0x00])
    repaired = repair_stellantis_crc(raw)
    assert len(repaired) == 3
    assert repaired[2] == chrysler_message_checksum(repaired)


def test_repair_stellantis_crc_8_byte() -> None:
    raw = bytes([0xAA] * 8)
    repaired = repair_stellantis_crc(raw)
    assert len(repaired) == 8
    assert repaired[7] == chrysler_message_checksum(repaired)


def test_repair_stellantis_crc_empty() -> None:
    assert repair_stellantis_crc(b"") == b""


def test_repair_stellantis_crc_single_byte() -> None:
    assert repair_stellantis_crc(bytes([0x00])) == bytes([0x00])


def test_repair_stellantis_crc_deterministic() -> None:
    raw = bytes([0x01, 0x00, 0x00])
    a = repair_stellantis_crc(raw)
    b = repair_stellantis_crc(raw)
    assert a == b


# ---------------------------------------------------------------------------
# compute_checksum dispatch tests
# ---------------------------------------------------------------------------


def test_compute_checksum_stellantis() -> None:
    payload = bytes([0x01, 0x02, 0x00])
    expected = chrysler_message_checksum(payload)
    result = compute_checksum(CrcAlgorithm.STELLANTIS, payload)
    assert result == expected


def test_compute_checksum_sae_j1850() -> None:
    payload = bytes([0x01, 0x02, 0x03, 0x00])
    result = compute_checksum(CrcAlgorithm.SAE_J1850, payload)
    assert result == crc8_sae_j1850(payload[:-1], init=0x00)


def test_compute_checksum_fca_giorgio_without_address() -> None:
    payload = bytes([0x01, 0x02, 0x03, 0x00])
    result = compute_checksum(CrcAlgorithm.FCA_GIORGIO, payload)
    expected = crc8_sae_j1850(payload[:-1], init=0x00) ^ 0x0A
    assert result == expected


def test_compute_checksum_fca_giorgio_with_address() -> None:
    payload = bytes([0x01, 0x02, 0x03, 0x00])
    result = compute_checksum(CrcAlgorithm.FCA_GIORGIO, payload, address=0xDE)
    expected = crc8_sae_j1850(payload[:-1], init=0x00) ^ 0x10
    assert result == expected


def test_compute_checksum_unknown_algorithm() -> None:
    """Unknown algorithm raises ValueError."""
    with pytest.raises(ValueError, match="Unknown CRC algorithm"):
        compute_checksum("bogus", b"\x00\x00")  # type: ignore[arg-type]


def test_compute_checksum_empty_data() -> None:
    """Empty data with SAE J1850 returns 0."""
    result = compute_checksum(CrcAlgorithm.SAE_J1850, b"")
    assert result == 0


def test_compute_checksum_single_byte() -> None:
    """Single byte with SAE J1850 returns 0 (only checksum byte)."""
    result = compute_checksum(CrcAlgorithm.SAE_J1850, b"\x00")
    assert result == 0


# ---------------------------------------------------------------------------
# detect_algorithm_from_dbc tests
# ---------------------------------------------------------------------------


def test_detect_algorithm_stellantis() -> None:
    assert detect_algorithm_from_dbc("_stellantis_common.dbc") == CrcAlgorithm.STELLANTIS


def test_detect_algorithm_chrysler() -> None:
    assert detect_algorithm_from_dbc("chrysler_ram_1500.dbc") == CrcAlgorithm.STELLANTIS


def test_detect_algorithm_fca_giorgio() -> None:
    assert detect_algorithm_from_dbc("fca_giorgio.dbc") == CrcAlgorithm.FCA_GIORGIO


def test_detect_algorithm_unknown() -> None:
    assert detect_algorithm_from_dbc("toyota_camry.dbc") is None


def test_detect_algorithm_with_path() -> None:
    assert detect_algorithm_from_dbc("/some/dir/_stellantis_common.dbc") == CrcAlgorithm.STELLANTIS


# ---------------------------------------------------------------------------
# repair_crc generic function tests
# ---------------------------------------------------------------------------


def test_repair_crc_default_stellantis() -> None:
    raw = bytes([0x01, 0x00, 0xFF])
    repaired = repair_crc(raw)
    assert len(repaired) == 3
    assert repaired[:2] == raw[:2]
    assert repaired[2] == chrysler_message_checksum(repaired)


def test_repair_crc_sae_j1850() -> None:
    raw = bytes([0x01, 0x02, 0x03, 0x00])
    repaired = repair_crc(raw, CrcAlgorithm.SAE_J1850)
    assert len(repaired) == 4
    assert repaired[:3] == raw[:3]
    expected = crc8_sae_j1850(repaired[:-1], init=0x00)
    assert repaired[3] == expected


def test_repair_crc_fca_giorgio_with_address() -> None:
    raw = bytes([0x01, 0x02, 0x03, 0x00])
    repaired = repair_crc(raw, CrcAlgorithm.FCA_GIORGIO, address=0xDE)
    assert len(repaired) == 4
    assert repaired[:3] == raw[:3]
    expected = crc8_sae_j1850(repaired[:-1], init=0x00) ^ 0x10
    assert repaired[3] == expected


def test_repair_crc_short_payload() -> None:
    assert repair_crc(b"") == b""


def test_repair_crc_single_byte() -> None:
    assert repair_crc(bytes([0x00])) == bytes([0x00])


def test_repair_crc_fca_giorgio_without_address_default_xor() -> None:
    """Without an address, FCA Giorgio uses the default XOR (0x0A)."""
    raw = bytes([0x01, 0x02, 0x03, 0x00])
    repaired = repair_crc(raw, CrcAlgorithm.FCA_GIORGIO)
    expected = crc8_sae_j1850(repaired[:-1], init=0x00) ^ 0x0A
    assert repaired[3] == expected


# ---------------------------------------------------------------------------
# FCA Giorgio XOR table tests
# ---------------------------------------------------------------------------


def test_fca_giorgio_known_address_0xDE() -> None:
    """0xDE should use XOR 0x10."""
    result = fca_giorgio_checksum(bytes([0x01, 0x02, 0x03, 0x00]), address=0xDE)
    expected = crc8_sae_j1850(bytes([0x01, 0x02, 0x03, 0x00]), init=0x00) ^ 0x10
    assert result == expected


def test_fca_giorgio_known_address_0x106() -> None:
    """0x106 should use XOR 0xF6."""
    result = fca_giorgio_checksum(bytes([0x01, 0x02, 0x03, 0x00]), address=0x106)
    expected = crc8_sae_j1850(bytes([0x01, 0x02, 0x03, 0x00]), init=0x00) ^ 0xF6
    assert result == expected


def test_fca_giorgio_known_address_0x122() -> None:
    """0x122 should use XOR 0xF1."""
    result = fca_giorgio_checksum(bytes([0x01, 0x02, 0x03, 0x00]), address=0x122)
    expected = crc8_sae_j1850(bytes([0x01, 0x02, 0x03, 0x00]), init=0x00) ^ 0xF1
    assert result == expected


def test_fca_giorgio_unknown_address_default_xor() -> None:
    """Unknown address uses default XOR 0x0A."""
    result = fca_giorgio_checksum(bytes([0x01, 0x02, 0x03, 0x00]), address=0x999)
    expected = crc8_sae_j1850(bytes([0x01, 0x02, 0x03, 0x00]), init=0x00) ^ 0x0A
    assert result == expected


def test_fca_giorgio_deterministic() -> None:
    a = fca_giorgio_checksum(bytes([0x01, 0x02, 0x03, 0x00]), address=0xDE)
    b = fca_giorgio_checksum(bytes([0x01, 0x02, 0x03, 0x00]), address=0xDE)
    assert a == b
