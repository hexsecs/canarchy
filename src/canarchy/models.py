"""Core frame and event models for CANarchy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

FrameFormat = Literal["can", "can_fd"]
EventType = Literal[
    "frame",
    "decoded_message",
    "signal",
    "j1939_pgn",
    "uds_transaction",
    "replay_event",
    "alert",
]


@dataclass(slots=True, frozen=True)
class CanFrame:
    arbitration_id: int
    data: bytes = field(repr=False)
    timestamp: float | None = None
    interface: str | None = None
    is_extended_id: bool = False
    is_remote_frame: bool = False
    is_error_frame: bool = False
    bitrate_switch: bool = False
    error_state_indicator: bool = False
    frame_format: FrameFormat = "can"

    def __post_init__(self) -> None:
        if self.arbitration_id < 0:
            raise ValueError("arbitration_id must be zero or greater")

        max_id = 0x1FFFFFFF if self.is_extended_id else 0x7FF
        if self.arbitration_id > max_id:
            raise ValueError(
                f"arbitration_id exceeds {'extended' if self.is_extended_id else 'standard'} CAN range"
            )

        payload_length = len(self.data)
        if self.frame_format == "can" and payload_length > 8:
            raise ValueError("classic CAN payloads may not exceed 8 bytes")
        if self.frame_format == "can_fd" and payload_length > 64:
            raise ValueError("CAN FD payloads may not exceed 64 bytes")

        if self.is_remote_frame and payload_length:
            raise ValueError("remote frames may not contain payload bytes")

        if self.bitrate_switch and self.frame_format != "can_fd":
            raise ValueError("bitrate_switch is only valid for CAN FD frames")

        if self.error_state_indicator and self.frame_format != "can_fd":
            raise ValueError("error_state_indicator is only valid for CAN FD frames")

    @property
    def dlc(self) -> int:
        return len(self.data)

    def to_payload(self) -> dict[str, Any]:
        return {
            "arbitration_id": self.arbitration_id,
            "bitrate_switch": self.bitrate_switch,
            "data": self.data.hex(),
            "dlc": self.dlc,
            "error_state_indicator": self.error_state_indicator,
            "frame_format": self.frame_format,
            "interface": self.interface,
            "is_error_frame": self.is_error_frame,
            "is_extended_id": self.is_extended_id,
            "is_remote_frame": self.is_remote_frame,
            "timestamp": self.timestamp,
        }

    def with_interface(self, interface: str | None) -> CanFrame:
        return CanFrame(
            arbitration_id=self.arbitration_id,
            data=self.data,
            timestamp=self.timestamp,
            interface=interface,
            is_extended_id=self.is_extended_id,
            is_remote_frame=self.is_remote_frame,
            is_error_frame=self.is_error_frame,
            bitrate_switch=self.bitrate_switch,
            error_state_indicator=self.error_state_indicator,
            frame_format=self.frame_format,
        )


@dataclass(slots=True, frozen=True)
class Event:
    event_type: EventType
    source: str
    payload: dict[str, Any]
    timestamp: float | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "payload": self.payload,
            "source": self.source,
            "timestamp": self.timestamp,
        }


@dataclass(slots=True, frozen=True)
class FrameEvent:
    frame: CanFrame
    source: str = "engine"
    timestamp: float | None = None

    def to_event(self) -> Event:
        return Event(
            event_type="frame",
            source=self.source,
            payload={"frame": self.frame.to_payload()},
            timestamp=self.timestamp if self.timestamp is not None else self.frame.timestamp,
        )


@dataclass(slots=True, frozen=True)
class DecodedMessageEvent:
    message_name: str
    frame: CanFrame
    signals: dict[str, Any]
    source: str = "decoder"
    timestamp: float | None = None

    def to_event(self) -> Event:
        return Event(
            event_type="decoded_message",
            source=self.source,
            payload={
                "frame": self.frame.to_payload(),
                "message_name": self.message_name,
                "signals": self.signals,
            },
            timestamp=self.timestamp if self.timestamp is not None else self.frame.timestamp,
        )


@dataclass(slots=True, frozen=True)
class SignalValueEvent:
    signal_name: str
    value: Any
    units: str | None = None
    message_name: str | None = None
    source: str = "decoder"
    timestamp: float | None = None

    def to_event(self) -> Event:
        payload = {
            "message_name": self.message_name,
            "signal_name": self.signal_name,
            "units": self.units,
            "value": self.value,
        }
        return Event(
            event_type="signal",
            source=self.source,
            payload=payload,
            timestamp=self.timestamp,
        )


@dataclass(slots=True, frozen=True)
class J1939ObservationEvent:
    pgn: int
    source_address: int
    frame: CanFrame
    destination_address: int | None = None
    priority: int | None = None
    source: str = "j1939"
    timestamp: float | None = None

    def __post_init__(self) -> None:
        if self.pgn < 0 or self.pgn > 0x3FFFF:
            raise ValueError("pgn must be between 0 and 262143")
        if self.source_address < 0 or self.source_address > 0xFF:
            raise ValueError("source_address must be between 0 and 255")
        if self.destination_address is not None and (
            self.destination_address < 0 or self.destination_address > 0xFF
        ):
            raise ValueError("destination_address must be between 0 and 255")
        if self.priority is not None and (self.priority < 0 or self.priority > 7):
            raise ValueError("priority must be between 0 and 7")

    def to_event(self) -> Event:
        return Event(
            event_type="j1939_pgn",
            source=self.source,
            payload={
                "destination_address": self.destination_address,
                "frame": self.frame.to_payload(),
                "pgn": self.pgn,
                "priority": self.priority,
                "source_address": self.source_address,
            },
            timestamp=self.timestamp if self.timestamp is not None else self.frame.timestamp,
        )


@dataclass(slots=True, frozen=True)
class ReplayActionEvent:
    action: str
    frame: CanFrame | None = None
    rate: float | None = None
    source: str = "replay"
    timestamp: float | None = None

    def to_event(self) -> Event:
        payload = {"action": self.action, "rate": self.rate}
        if self.frame is not None:
            payload["frame"] = self.frame.to_payload()
        return Event(
            event_type="replay_event",
            source=self.source,
            payload=payload,
            timestamp=self.timestamp
            if self.timestamp is not None
            else (self.frame.timestamp if self.frame else None),
        )


@dataclass(slots=True, frozen=True)
class UdsTransactionEvent:
    request_id: int
    response_id: int
    service: int
    service_name: str
    request_data: bytes = field(repr=False)
    response_data: bytes = field(repr=False)
    ecu_address: int | None = None
    source: str = "uds"
    timestamp: float | None = None

    def to_event(self) -> Event:
        return Event(
            event_type="uds_transaction",
            source=self.source,
            payload={
                "ecu_address": self.ecu_address,
                "request_data": self.request_data.hex(),
                "request_id": self.request_id,
                "response_data": self.response_data.hex(),
                "response_id": self.response_id,
                "service": self.service,
                "service_name": self.service_name,
            },
            timestamp=self.timestamp,
        )


@dataclass(slots=True, frozen=True)
class AlertEvent:
    level: Literal["info", "warning", "error"]
    message: str
    code: str | None = None
    source: str = "engine"
    timestamp: float | None = None

    def to_event(self) -> Event:
        return Event(
            event_type="alert",
            source=self.source,
            payload={"code": self.code, "level": self.level, "message": self.message},
            timestamp=self.timestamp,
        )


def serialize_events(events: list[Event]) -> list[dict[str, Any]]:
    return [event.to_payload() for event in events]
