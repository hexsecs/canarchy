"""J1939 decoder abstraction.

This module isolates the CLI from the concrete J1939 protocol helpers so the
current curated implementation can be replaced later with a library-backed
decoder without reshaping command handlers first.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import j1939 as can_j1939

from canarchy.j1939 import DM1_PGN, SUPPORTED_SPN_DEFINITIONS, decompose_arbitration_id
from canarchy.models import CanFrame, J1939ObservationEvent


class J1939Decoder(Protocol):
    def supported_spns(self) -> set[int]: ...

    def decode_events(self, frames: list[CanFrame]) -> list[J1939ObservationEvent]: ...

    def decode_pgn_events(self, frames: list[CanFrame], pgn: int) -> list[J1939ObservationEvent]: ...

    def spn_observations(self, frames: list[CanFrame], spn: int) -> list[dict[str, object]]: ...

    def transport_protocol_sessions(self, frames: list[CanFrame]) -> list[dict[str, object]]: ...

    def dm1_messages(self, frames: list[CanFrame]) -> list[dict[str, object]]: ...


@dataclass(slots=True)
class CanJ1939Decoder:
    """J1939 decoder backed by can-j1939 primitives and curated SPN metadata."""

    def supported_spns(self) -> set[int]:
        return set(SUPPORTED_SPN_DEFINITIONS)

    def decode_events(self, frames: list[CanFrame]) -> list[J1939ObservationEvent]:
        return self._decode_events(frames, pgn=None)

    def decode_pgn_events(self, frames: list[CanFrame], pgn: int) -> list[J1939ObservationEvent]:
        return self._decode_events(frames, pgn=pgn)

    def _decode_events(self, frames: list[CanFrame], pgn: int | None) -> list[J1939ObservationEvent]:
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

    def spn_observations(self, frames: list[CanFrame], spn: int) -> list[dict[str, object]]:
        definition = SUPPORTED_SPN_DEFINITIONS[spn]
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

    def transport_protocol_sessions(self, frames: list[CanFrame]) -> list[dict[str, object]]:
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
                    "complete": len(payload) >= total_bytes and packet_count >= total_packets,
                    "packet_count": packet_count,
                    "reassembled_data": payload.hex(),
                }
            )
        return summaries

    def dm1_messages(self, frames: list[CanFrame]) -> list[dict[str, object]]:
        messages: list[dict[str, object]] = []
        for frame in frames:
            if not frame.is_extended_id:
                continue
            identifier = decompose_arbitration_id(frame.arbitration_id)
            if identifier.pgn != DM1_PGN:
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

        for session in self.transport_protocol_sessions(frames):
            if session["transfer_pgn"] != DM1_PGN or not session["complete"]:
                continue
            payload = bytes.fromhex(str(session["reassembled_data"]))
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
            parsed = can_j1939.DTC(dtc=int.from_bytes(raw, byteorder="little"))
            definition = SUPPORTED_SPN_DEFINITIONS.get(parsed.spn)
            dtcs.append(
                {
                    "spn": parsed.spn,
                    "name": definition.name if definition is not None else None,
                    "fmi": parsed.fmi,
                    "occurrence_count": parsed.oc,
                    "conversion_method": parsed.cm,
                }
            )
        return dtcs


def get_j1939_decoder() -> J1939Decoder:
    return CanJ1939Decoder()
