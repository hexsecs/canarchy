"""CANarchy-owned DBC metadata types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class SignalInfo:
    name: str
    message_name: str
    start_bit: int
    length: int
    byte_order: str
    is_signed: bool
    scale: Any
    offset: Any
    minimum: Any
    maximum: Any
    unit: str | None
    choices: dict[str, str] | None
    is_multiplexer: bool
    multiplexer_ids: list[int] | None

    def to_payload(self) -> dict[str, Any]:
        return {
            "byte_order": self.byte_order,
            "choices": self.choices,
            "is_multiplexer": self.is_multiplexer,
            "is_signed": self.is_signed,
            "length": self.length,
            "maximum": self.maximum,
            "message_name": self.message_name,
            "minimum": self.minimum,
            "multiplexer_ids": self.multiplexer_ids,
            "name": self.name,
            "offset": self.offset,
            "scale": self.scale,
            "start_bit": self.start_bit,
            "unit": self.unit,
        }


@dataclass(slots=True, frozen=True)
class MessageInfo:
    name: str
    arbitration_id: int
    arbitration_id_hex: str
    is_extended_id: bool
    length: int
    cycle_time_ms: int | None
    senders: list[str]
    signals: list[SignalInfo]

    def to_payload(self) -> dict[str, Any]:
        return {
            "arbitration_id": self.arbitration_id,
            "arbitration_id_hex": self.arbitration_id_hex,
            "cycle_time_ms": self.cycle_time_ms,
            "is_extended_id": self.is_extended_id,
            "length": self.length,
            "name": self.name,
            "senders": self.senders,
            "signal_count": len(self.signals),
            "signals": [signal.to_payload() for signal in self.signals],
        }


@dataclass(slots=True, frozen=True)
class DatabaseInfo:
    path: str
    format: str
    message_count: int
    signal_count: int
    node_count: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "message_count": self.message_count,
            "node_count": self.node_count,
            "path": self.path,
            "signal_count": self.signal_count,
        }


@dataclass(slots=True, frozen=True)
class DatabaseInspection:
    database: DatabaseInfo
    messages: list[MessageInfo]
    selected_message: str | None = None

    def to_payload(self, *, signals_only: bool = False) -> dict[str, Any]:
        if signals_only:
            signals = [
                signal.to_payload() for message in self.messages for signal in message.signals
            ]
            return {
                "database": self.database.to_payload(),
                "message": self.selected_message,
                "signal_count": len(signals),
                "signals": signals,
            }

        return {
            "database": self.database.to_payload(),
            "message": self.selected_message,
            "messages": [message.to_payload() for message in self.messages],
        }

    def to_events(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = [
            {
                "event_type": "dbc_database",
                "payload": self.database.to_payload(),
                "source": "dbc.inspect",
                "timestamp": None,
            }
        ]
        for message in self.messages:
            message_payload = message.to_payload()
            events.append(
                {
                    "event_type": "dbc_message",
                    "payload": {
                        key: value for key, value in message_payload.items() if key != "signals"
                    },
                    "source": "dbc.inspect",
                    "timestamp": None,
                }
            )
            for signal in message.signals:
                events.append(
                    {
                        "event_type": "dbc_signal",
                        "payload": signal.to_payload(),
                        "source": "dbc.inspect",
                        "timestamp": None,
                    }
                )
        return events
