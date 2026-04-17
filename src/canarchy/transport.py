"""Transport foundation for local CAN workflows."""

from __future__ import annotations

from dataclasses import dataclass

from canarchy.j1939 import decompose_arbitration_id
from canarchy.models import (
    AlertEvent,
    CanFrame,
    FrameEvent,
    J1939ObservationEvent,
    serialize_events,
)


@dataclass(slots=True)
class TransportStats:
    total_frames: int
    unique_arbitration_ids: int
    interfaces: list[str]

    def to_payload(self) -> dict[str, int | list[str]]:
        return {
            "interfaces": self.interfaces,
            "total_frames": self.total_frames,
            "unique_arbitration_ids": self.unique_arbitration_ids,
        }


class TransportError(Exception):
    """Raised when a transport backend cannot complete a request."""

    def __init__(self, code: str, message: str, hint: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


class LocalTransport:
    """Deterministic local transport scaffold for CLI workflows."""

    def capture(self, interface: str) -> list[CanFrame]:
        self._require_interface(interface)
        return [frame.with_interface(interface) for frame in self._recorded_frames()[:2]]

    def send(self, interface: str, frame: CanFrame) -> CanFrame:
        self._require_interface(interface)
        return frame.with_interface(interface)

    def filter(self, file_name: str, expression: str) -> list[CanFrame]:
        frames = self._frames_for_file(file_name)
        normalized = expression.strip().lower()
        if normalized.startswith("id=="):
            wanted_id = int(normalized.split("==", 1)[1], 0)
            return [frame for frame in frames if frame.arbitration_id == wanted_id]
        if normalized.startswith("pgn=="):
            wanted_pgn = int(normalized.split("==", 1)[1], 0)
            return [frame for frame in frames if self._pgn(frame) == wanted_pgn]
        if normalized == "all":
            return frames
        raise TransportError(
            "FILTER_EXPRESSION_UNSUPPORTED",
            "Filter expression is not supported by the current transport scaffold.",
            "Use `all`, `id==0x...`, or `pgn==...` until the full filter engine is implemented.",
        )

    def stats(self, file_name: str) -> TransportStats:
        frames = self._frames_for_file(file_name)
        return TransportStats(
            total_frames=len(frames),
            unique_arbitration_ids=len({frame.arbitration_id for frame in frames}),
            interfaces=sorted({frame.interface or "unknown" for frame in frames}),
        )

    def frames_from_file(self, file_name: str) -> list[CanFrame]:
        return self._frames_for_file(file_name)

    def capture_events(self, interface: str) -> list[dict[str, object]]:
        frames = self.capture(interface)
        return serialize_events(
            [FrameEvent(frame=frame, source="transport.capture").to_event() for frame in frames]
        )

    def send_events(self, interface: str, frame: CanFrame) -> list[dict[str, object]]:
        sent_frame = self.send(interface, frame)
        events = [
            AlertEvent(
                level="warning",
                code="ACTIVE_TRANSMIT",
                message="Active transmission requested on the selected interface.",
                source="transport.send",
            ).to_event(),
            FrameEvent(frame=sent_frame, source="transport.send").to_event(),
        ]
        return serialize_events(events)

    def filter_events(self, file_name: str, expression: str) -> list[dict[str, object]]:
        frames = self.filter(file_name, expression)
        return serialize_events(
            [FrameEvent(frame=frame, source="transport.filter").to_event() for frame in frames]
        )

    def j1939_monitor_events(self, pgn: int | None = None) -> list[dict[str, object]]:
        frames = [frame for frame in self._recorded_frames() if frame.is_extended_id]
        return serialize_events(
            [
                event.to_event()
                for event in self._j1939_events(frames, pgn=pgn, source="transport.j1939.monitor")
            ]
        )

    def j1939_decode_events(
        self, file_name: str, pgn: int | None = None
    ) -> list[dict[str, object]]:
        frames = [frame for frame in self._frames_for_file(file_name) if frame.is_extended_id]
        return serialize_events(
            [
                event.to_event()
                for event in self._j1939_events(frames, pgn=pgn, source="transport.j1939.decode")
            ]
        )

    def _require_interface(self, interface: str) -> None:
        if interface.lower() in {"offline0", "down0", "missing0"}:
            raise TransportError(
                "TRANSPORT_UNAVAILABLE",
                f"Interface '{interface}' is not available.",
                "Use an active local CAN interface such as `can0`.",
            )

    def _frames_for_file(self, file_name: str) -> list[CanFrame]:
        if file_name.lower() in {"missing.log", "missing", "offline.log"}:
            raise TransportError(
                "CAPTURE_SOURCE_UNAVAILABLE",
                f"Capture source '{file_name}' is not available.",
                "Provide a readable capture file or generate traffic with `canarchy capture` first.",
            )
        return self._recorded_frames()

    def _recorded_frames(self) -> list[CanFrame]:
        return [
            CanFrame(
                arbitration_id=0x18FEEE31,
                data=bytes.fromhex("11223344"),
                frame_format="can",
                interface="can0",
                is_extended_id=True,
                timestamp=0.0,
            ),
            CanFrame(
                arbitration_id=0x18F00431,
                data=bytes.fromhex("AABBCCDD"),
                frame_format="can",
                interface="can0",
                is_extended_id=True,
                timestamp=0.1,
            ),
            CanFrame(
                arbitration_id=0x18FEF100,
                data=bytes.fromhex("0102030405060708"),
                frame_format="can",
                interface="can1",
                is_extended_id=True,
                timestamp=0.2,
            ),
        ]

    def _pgn(self, frame: CanFrame) -> int:
        return decompose_arbitration_id(frame.arbitration_id).pgn

    def _j1939_events(
        self,
        frames: list[CanFrame],
        *,
        pgn: int | None,
        source: str,
    ) -> list[J1939ObservationEvent]:
        events: list[J1939ObservationEvent] = []
        for frame in frames:
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
                    source=source,
                )
            )
        return events
