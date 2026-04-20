"""J1939 decoder abstraction.

This module isolates the CLI from the concrete J1939 protocol helpers so the
current curated implementation can be replaced later with a library-backed
decoder without reshaping command handlers first.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

import j1939 as can_j1939

from canarchy.j1939 import DM1_PGN, SpnDefinition, decompose_arbitration_id
from canarchy.j1939_metadata import decodable_spns, spn_lookup
from canarchy.models import CanFrame, J1939ObservationEvent


class J1939Decoder(Protocol):
    def supported_spns(self) -> set[int]: ...

    def decode_events(self, frames: Iterable[CanFrame]) -> list[J1939ObservationEvent]: ...

    def decode_pgn_events(self, frames: Iterable[CanFrame], pgn: int) -> list[J1939ObservationEvent]: ...

    def spn_observations(self, frames: Iterable[CanFrame], spn: int) -> list[dict[str, object]]: ...

    def transport_protocol_sessions(self, frames: Iterable[CanFrame]) -> list[dict[str, object]]: ...

    def dm1_messages(self, frames: Iterable[CanFrame]) -> list[dict[str, object]]: ...


@dataclass(slots=True)
class CanJ1939Decoder:
    """J1939 decoder backed by can-j1939 primitives and curated SPN metadata."""

    TP_CM_RTS = 0x10
    TP_CM_CTS = 0x11
    TP_CM_EOM_ACK = 0x13
    TP_CM_BAM = 0x20
    TP_CM_ABORT = 0xFF

    def supported_spns(self) -> set[int]:
        return decodable_spns()

    def decode_events(self, frames: Iterable[CanFrame]) -> list[J1939ObservationEvent]:
        return self._decode_events(frames, pgn=None)

    def decode_pgn_events(self, frames: Iterable[CanFrame], pgn: int) -> list[J1939ObservationEvent]:
        return self._decode_events(frames, pgn=pgn)

    def _decode_events(self, frames: Iterable[CanFrame], pgn: int | None) -> list[J1939ObservationEvent]:
        events: list[J1939ObservationEvent] = []
        for frame in frames:
            if not frame.is_extended_id:
                continue
            identifier = decompose_arbitration_id(frame.arbitration_id)
            if pgn is not None and identifier.pgn != pgn:
                continue
            events.append(
                J1939ObservationEvent(
                    pgn=identifier.pgn,
                    source_address=identifier.source_address,
                    destination_address=identifier.destination_address,
                    priority=identifier.priority,
                    frame=frame,
                    source="transport.j1939.decode",
                )
            )
        return events

    def spn_observations(self, frames: Iterable[CanFrame], spn: int) -> list[dict[str, object]]:
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

    def transport_protocol_sessions(self, frames: Iterable[CanFrame]) -> list[dict[str, object]]:
        sessions: list[dict[str, object]] = []
        open_sessions: dict[tuple[int, int | None], dict[str, object]] = {}
        tp_cm_pgn = can_j1939.ParameterGroupNumber.PGN.TP_CM
        tp_dt_pgn = can_j1939.ParameterGroupNumber.PGN.DATATRANSFER

        for frame in frames:
            if not frame.is_extended_id:
                continue
            identifier = decompose_arbitration_id(frame.arbitration_id)
            if identifier.pgn == tp_cm_pgn and len(frame.data) >= 8:
                control = frame.data[0]
                if control in {self.TP_CM_BAM, self.TP_CM_RTS}:
                    transfer_pgn = frame.data[5] | (frame.data[6] << 8) | (frame.data[7] << 16)
                    session = {
                        "session_type": "bam" if control == self.TP_CM_BAM else "rts_cts",
                        "acknowledged": False,
                        "control": control,
                        "cts_count": 0,
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
                    if control == self.TP_CM_RTS:
                        session["max_packets_per_cts"] = frame.data[4]
                    open_sessions[(identifier.source_address, identifier.destination_address)] = session
                    sessions.append(session)
                    continue

                reverse_key = (identifier.destination_address, identifier.source_address)
                session = open_sessions.get(reverse_key)
                if session is None:
                    continue
                if control == self.TP_CM_CTS:
                    session["cts_count"] = int(session.get("cts_count", 0)) + 1
                    session["last_cts_next_packet"] = frame.data[2]
                    session["last_cts_window"] = frame.data[1]
                    continue
                if control == self.TP_CM_EOM_ACK:
                    session["acknowledged"] = True
                    session["ack_timestamp"] = frame.timestamp
                    continue
                if control == self.TP_CM_ABORT:
                    session["aborted"] = True
                    session["abort_reason"] = frame.data[1]
                    session["complete"] = False
                    continue

            if identifier.pgn == tp_dt_pgn and len(frame.data) >= 2:
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
                    "aborted": bool(session.get("aborted", False)),
                    "complete": len(payload) >= total_bytes and packet_count >= total_packets,
                    "packet_count": packet_count,
                    "reassembled_data": payload.hex(),
                }
            )
        return summaries

    def dm1_messages(self, frames: Iterable[CanFrame]) -> list[dict[str, object]]:
        messages: list[dict[str, object]] = []
        open_sessions: dict[tuple[int, int | None], dict[str, object]] = {}
        tp_sessions: list[dict[str, object]] = []
        tp_cm_pgn = can_j1939.ParameterGroupNumber.PGN.TP_CM
        tp_dt_pgn = can_j1939.ParameterGroupNumber.PGN.DATATRANSFER

        for frame in frames:
            if not frame.is_extended_id:
                continue
            identifier = decompose_arbitration_id(frame.arbitration_id)
            if identifier.pgn != DM1_PGN:
                if identifier.pgn == tp_cm_pgn and len(frame.data) >= 8:
                    control = frame.data[0]
                    if control in {self.TP_CM_BAM, self.TP_CM_RTS}:
                        transfer_pgn = frame.data[5] | (frame.data[6] << 8) | (frame.data[7] << 16)
                        if transfer_pgn != DM1_PGN:
                            continue
                        session = {
                            "destination_address": identifier.destination_address,
                            "packets": {},
                            "source_address": identifier.source_address,
                            "timestamp": frame.timestamp,
                            "total_bytes": frame.data[1] | (frame.data[2] << 8),
                            "total_packets": frame.data[3],
                            "transfer_pgn": transfer_pgn,
                        }
                        open_sessions[(identifier.source_address, identifier.destination_address)] = session
                        tp_sessions.append(session)
                        continue

                    reverse_key = (identifier.destination_address, identifier.source_address)
                    session = open_sessions.get(reverse_key)
                    if session is None:
                        continue
                    if control == self.TP_CM_ABORT:
                        session["aborted"] = True
                    continue

                if identifier.pgn == tp_dt_pgn and len(frame.data) >= 2:
                    key = (identifier.source_address, identifier.destination_address)
                    session = open_sessions.get(key)
                    if session is None:
                        continue
                    packets = session["packets"]
                    assert isinstance(packets, dict)
                    packets[frame.data[0]] = frame.data[1:]
                continue

            messages.append(
                self._build_dm1_message(
                    payload=frame.data,
                    source_address=identifier.source_address,
                    destination_address=identifier.destination_address,
                    transport="direct",
                    timestamp=frame.timestamp,
                )
            )

        for session in tp_sessions:
            packets = session.pop("packets")
            assert isinstance(packets, dict)
            total_packets = int(session["total_packets"])
            packet_count = len(packets)
            reassembled = b"".join(packets[index] for index in range(1, total_packets + 1) if index in packets)
            total_bytes = int(session["total_bytes"])
            payload = reassembled[:total_bytes]
            if bool(session.get("aborted", False)) or len(payload) < total_bytes or packet_count < total_packets:
                continue
            messages.append(
                self._build_dm1_message(
                    payload=payload,
                    source_address=int(session["source_address"]),
                    destination_address=session["destination_address"],
                    transport="tp",
                    timestamp=session["timestamp"],
                )
            )

        return sorted(messages, key=lambda message: (message["timestamp"] or 0.0, message["source_address"]))

    def _build_dm1_message(
        self,
        *,
        payload: bytes,
        source_address: int,
        destination_address: int | None,
        transport: str,
        timestamp: float | None,
    ) -> dict[str, object]:
        dtcs = self._parse_dtcs(payload[4:])
        return {
            "active_dtc_count": len(dtcs),
            "destination_address": destination_address,
            "dtcs": dtcs,
            "lamp_status": self._decode_lamp_status(payload[:2]),
            "source_address": source_address,
            "timestamp": timestamp,
            "transport": transport,
        }

    def _decode_lamp_status(self, lamp_bytes: bytes) -> dict[str, str]:
        value = int.from_bytes(lamp_bytes.ljust(2, b"\x00"), byteorder="little")
        return {
            "mil": self._lamp_state(value & 0x3),
            "red_stop": self._lamp_state((value >> 2) & 0x3),
            "amber_warning": self._lamp_state((value >> 4) & 0x3),
            "protect": self._lamp_state((value >> 6) & 0x3),
        }

    def _lamp_state(self, bits: int) -> str:
        return {
            0: "off",
            1: "on",
            2: "error",
            3: "not_available",
        }[bits]

    def _parse_dtcs(self, payload: bytes) -> list[dict[str, object]]:
        dtcs: list[dict[str, object]] = []
        for offset in range(0, len(payload) - (len(payload) % 4), 4):
            raw = payload[offset : offset + 4]
            dtc = int.from_bytes(raw, byteorder="little")
            spn = (dtc & 0xFFFF) | ((dtc >> 5) & 0x70000)
            fmi = (dtc >> 16) & 0x1F
            occurrence_count = (dtc >> 24) & 0x7F
            conversion_method = (dtc >> 31) & 0x01
            spn_meta = spn_lookup(spn)
            dtcs.append(
                {
                    "spn": spn,
                    "name": spn_meta["name"] if spn_meta is not None else None,
                    "fmi": fmi,
                    "occurrence_count": occurrence_count,
                    "conversion_method": conversion_method,
                }
            )
        return dtcs


def get_j1939_decoder() -> J1939Decoder:
    return CanJ1939Decoder()
