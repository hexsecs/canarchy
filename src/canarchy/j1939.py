"""J1939 protocol helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class J1939Identifier:
    priority: int
    reserved: int
    data_page: int
    pdu_format: int
    pdu_specific: int
    source_address: int
    pgn: int
    destination_address: int | None

    def to_payload(self) -> dict[str, int | None]:
        return {
            "data_page": self.data_page,
            "destination_address": self.destination_address,
            "pdu_format": self.pdu_format,
            "pdu_specific": self.pdu_specific,
            "pgn": self.pgn,
            "priority": self.priority,
            "reserved": self.reserved,
            "source_address": self.source_address,
        }


def decompose_arbitration_id(arbitration_id: int) -> J1939Identifier:
    if arbitration_id < 0 or arbitration_id > 0x1FFFFFFF:
        raise ValueError("J1939 arbitration_id must be a 29-bit CAN identifier")

    priority = (arbitration_id >> 26) & 0x7
    reserved = (arbitration_id >> 25) & 0x1
    data_page = (arbitration_id >> 24) & 0x1
    pdu_format = (arbitration_id >> 16) & 0xFF
    pdu_specific = (arbitration_id >> 8) & 0xFF
    source_address = arbitration_id & 0xFF

    if pdu_format < 240:
        pgn = (data_page << 16) | (pdu_format << 8)
        destination_address = pdu_specific
    else:
        pgn = (data_page << 16) | (pdu_format << 8) | pdu_specific
        destination_address = None

    return J1939Identifier(
        priority=priority,
        reserved=reserved,
        data_page=data_page,
        pdu_format=pdu_format,
        pdu_specific=pdu_specific,
        source_address=source_address,
        pgn=pgn,
        destination_address=destination_address,
    )
