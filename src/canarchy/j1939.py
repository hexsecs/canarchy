"""J1939 protocol helpers."""

from __future__ import annotations

from dataclasses import dataclass

import j1939 as can_j1939

from canarchy.j1939_metadata import spn_lookup
from canarchy.models import CanFrame

TP_CM_PGN = 0x00EC00
TP_DT_PGN = 0x00EB00
DM1_PGN = 0x00FECA


@dataclass(slots=True, frozen=True)
class SpnDefinition:
    spn: int
    name: str
    pgn: int
    start: int
    length: int
    resolution: float
    offset: float
    units: str
    byteorder: str = "little"



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

    message_id = can_j1939.MessageId(can_id=arbitration_id)
    parameter_group_number = can_j1939.ParameterGroupNumber()
    parameter_group_number.from_message_id(message_id)

    priority = message_id.priority
    reserved = 0
    data_page = parameter_group_number.data_page
    pdu_format = parameter_group_number.pdu_format
    pdu_specific = parameter_group_number.pdu_specific
    source_address = message_id.source_address

    if parameter_group_number.is_pdu1_format:
        pgn = (data_page << 16) | (pdu_format << 8)
        destination_address = pdu_specific
    else:
        pgn = parameter_group_number.value
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


def spn_observations(frames: list[CanFrame], spn: int) -> list[dict[str, object]]:
    meta = spn_lookup(spn)
    if meta is None:
        return []
    definition = SpnDefinition(
        spn=spn,
        name=meta["name"],
        pgn=meta["pgn"],
        start=meta["start"],
        length=meta["length"],
        resolution=meta["resolution"],
        offset=meta["offset"],
        units=meta["units"],
        byteorder=meta.get("byteorder", "little"),
    )
    observations: list[dict[str, object]] = []
    for frame in frames:
        if not frame.is_extended_id:
            continue
        identifier = decompose_arbitration_id(frame.arbitration_id)
        if identifier.pgn != definition.pgn:
            continue
        end = definition.start + definition.length
        if len(frame.data) < end:
            continue
        raw = frame.data[definition.start:end]
        raw_value = int.from_bytes(raw, byteorder=definition.byteorder)
        value = (raw_value * definition.resolution) + definition.offset
        observations.append(
            {
                "spn": definition.spn,
                "name": definition.name,
                "pgn": definition.pgn,
                "source_address": identifier.source_address,
                "destination_address": identifier.destination_address,
                "units": definition.units,
                "raw": raw.hex(),
                "value": value,
                "timestamp": frame.timestamp,
            }
        )
    return observations


def transport_protocol_sessions(frames: list[CanFrame]) -> list[dict[str, object]]:
    sessions: list[dict[str, object]] = []
    open_sessions: dict[tuple[int, int | None], dict[str, object]] = {}

    for frame in frames:
        if not frame.is_extended_id:
            continue
        identifier = decompose_arbitration_id(frame.arbitration_id)
        if identifier.pgn == TP_CM_PGN and len(frame.data) >= 8:
            control = frame.data[0]
            if control != 0x20:
                continue
            transfer_pgn = frame.data[5] | (frame.data[6] << 8) | (frame.data[7] << 16)
            session = {
                "session_type": "bam",
                "control": control,
                "destination_address": identifier.destination_address,
                "packet_count": 0,
                "packets": {},
                "priority": identifier.priority,
                "source_address": identifier.source_address,
                "timestamp": frame.timestamp,
                "total_bytes": frame.data[1] | (frame.data[2] << 8),
                "total_packets": frame.data[3],
                "transfer_pgn": transfer_pgn,
            }
            open_sessions[(identifier.source_address, identifier.destination_address)] = session
            sessions.append(session)
            continue

        if identifier.pgn == TP_DT_PGN and len(frame.data) >= 2:
            key = (identifier.source_address, identifier.destination_address)
            session = open_sessions.get(key)
            if session is None:
                continue
            sequence = frame.data[0]
            packets = session["packets"]
            assert isinstance(packets, dict)
            packets[sequence] = frame.data[1:]

    summaries: list[dict[str, object]] = []
    for session in sessions:
        packets = session.pop("packets")
        assert isinstance(packets, dict)
        total_packets = int(session["total_packets"])
        packet_count = len(packets)
        reassembled = b"".join(packets[index] for index in range(1, total_packets + 1) if index in packets)
        total_bytes = int(session["total_bytes"])
        payload = reassembled[:total_bytes]
        summaries.append(
            {
                **session,
                "complete": len(payload) >= total_bytes and packet_count >= total_packets,
                "packet_count": packet_count,
                "reassembled_data": payload.hex(),
            }
        )
    return summaries


def dm1_messages(frames: list[CanFrame]) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = []
    for frame in frames:
        if not frame.is_extended_id:
            continue
        identifier = decompose_arbitration_id(frame.arbitration_id)
        if identifier.pgn != DM1_PGN:
            continue
        messages.append(
            _build_dm1_message(
                payload=frame.data,
                source_address=identifier.source_address,
                destination_address=identifier.destination_address,
                transport="direct",
                timestamp=frame.timestamp,
            )
        )

    for session in transport_protocol_sessions(frames):
        if session["transfer_pgn"] != DM1_PGN or not session["complete"]:
            continue
        payload = bytes.fromhex(str(session["reassembled_data"]))
        messages.append(
            _build_dm1_message(
                payload=payload,
                source_address=int(session["source_address"]),
                destination_address=session["destination_address"],
                transport="tp",
                timestamp=session["timestamp"],
            )
        )

    return sorted(messages, key=lambda message: (message["timestamp"] or 0.0, message["source_address"]))


def _build_dm1_message(
    *,
    payload: bytes,
    source_address: int,
    destination_address: int | None,
    transport: str,
    timestamp: float | None,
) -> dict[str, object]:
    dtcs = _parse_dtcs(payload[4:])
    return {
        "active_dtc_count": len(dtcs),
        "destination_address": destination_address,
        "dtcs": dtcs,
        "lamp_status": _decode_lamp_status(payload[:2]),
        "source_address": source_address,
        "timestamp": timestamp,
        "transport": transport,
    }


def _decode_lamp_status(lamp_bytes: bytes) -> dict[str, str]:
    value = int.from_bytes(lamp_bytes.ljust(2, b"\x00"), byteorder="little")
    return {
        "mil": _lamp_state(value & 0x3),
        "red_stop": _lamp_state((value >> 2) & 0x3),
        "amber_warning": _lamp_state((value >> 4) & 0x3),
        "protect": _lamp_state((value >> 6) & 0x3),
    }


def _lamp_state(bits: int) -> str:
    return {
        0: "off",
        1: "on",
        2: "error",
        3: "not_available",
    }[bits]


def _parse_dtcs(payload: bytes) -> list[dict[str, object]]:
    dtcs: list[dict[str, object]] = []
    for offset in range(0, len(payload) - (len(payload) % 4), 4):
        raw = payload[offset : offset + 4]
        dtc = int.from_bytes(raw, byteorder="little")
        spn = (dtc & 0xFFFF) | ((dtc >> 5) & 0x70000)
        fmi = (dtc >> 16) & 0x1F
        occurrence_count = (dtc >> 24) & 0x7F
        conversion_method = (dtc >> 31) & 0x01
        meta = spn_lookup(spn)
        dtcs.append(
            {
                "spn": spn,
                "name": meta["name"] if meta is not None else None,
                "fmi": fmi,
                "occurrence_count": occurrence_count,
                "conversion_method": conversion_method,
            }
        )
    return dtcs
