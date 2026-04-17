"""Transport foundation for local CAN workflows."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Protocol

try:
    import can as python_can
except ImportError:  # pragma: no cover - exercised through backend selection failures
    python_can = None

from canarchy.j1939 import decompose_arbitration_id
from canarchy.models import (
    AlertEvent,
    CanFrame,
    FrameEvent,
    J1939ObservationEvent,
    UdsTransactionEvent,
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


@dataclass(slots=True, frozen=True)
class TransportBackendConfig:
    backend: str
    python_can_interface: str = "virtual"
    capture_limit: int = 2
    capture_timeout: float = 0.05


class LiveCanBackend(Protocol):
    @property
    def backend_name(self) -> str: ...

    def capture(self, interface: str) -> list[CanFrame]: ...

    def send(self, interface: str, frame: CanFrame) -> CanFrame: ...


class ScaffoldCanBackend:
    """Deterministic backend used when no live CAN backend is selected."""

    @property
    def backend_name(self) -> str:
        return "scaffold"

    def capture(self, interface: str) -> list[CanFrame]:
        self._require_interface(interface)
        return [frame.with_interface(interface) for frame in recorded_frames()[:2]]

    def send(self, interface: str, frame: CanFrame) -> CanFrame:
        self._require_interface(interface)
        return frame.with_interface(interface)

    def _require_interface(self, interface: str) -> None:
        if interface.lower() in {"offline0", "down0", "missing0"}:
            raise TransportError(
                "TRANSPORT_UNAVAILABLE",
                f"Interface '{interface}' is not available.",
                "Use an active local CAN interface such as `can0`.",
            )


class PythonCanBackend:
    """python-can backend for live local CAN capture and transmit."""

    def __init__(
        self,
        *,
        bus_interface: str = "virtual",
        capture_limit: int = 2,
        capture_timeout: float = 0.05,
    ) -> None:
        self.bus_interface = bus_interface
        self.capture_limit = capture_limit
        self.capture_timeout = capture_timeout

    @property
    def backend_name(self) -> str:
        return "python-can"

    def capture(self, interface: str) -> list[CanFrame]:
        frames: list[CanFrame] = []
        bus = self._open_bus(interface)
        try:
            while len(frames) < self.capture_limit:
                message = bus.recv(timeout=self.capture_timeout)
                if message is None:
                    break
                frames.append(self._decode_message(message, interface))
        finally:
            bus.shutdown()
        return frames

    def send(self, interface: str, frame: CanFrame) -> CanFrame:
        bus = self._open_bus(interface)
        try:
            try:
                bus.send(self._encode_message(frame))
            except Exception as exc:
                raise TransportError(
                    "TRANSPORT_UNAVAILABLE",
                    f"Failed to send CAN frame on interface '{interface}'.",
                    "Check that the python-can backend is available and the channel is configured.",
                ) from exc
        finally:
            bus.shutdown()
        return frame.with_interface(interface).with_timestamp(time.time())

    def _open_bus(self, interface: str):
        if python_can is None:
            raise TransportError(
                "TRANSPORT_UNAVAILABLE",
                "python-can is not installed.",
                "Install the `python-can` dependency or select the scaffold backend.",
            )

        try:
            return python_can.Bus(
                channel=interface,
                interface=self.bus_interface,
                receive_own_messages=self.bus_interface == "virtual",
            )
        except Exception as exc:
            raise TransportError(
                "TRANSPORT_UNAVAILABLE",
                f"Interface '{interface}' is not available.",
                "Check that the python-can interface and channel are configured correctly.",
            ) from exc

    def _decode_message(self, message, interface: str) -> CanFrame:
        return CanFrame(
            arbitration_id=message.arbitration_id,
            data=bytes(message.data),
            frame_format="can_fd" if getattr(message, "is_fd", False) else "can",
            interface=interface,
            is_extended_id=message.is_extended_id,
            is_remote_frame=message.is_remote_frame,
            is_error_frame=message.is_error_frame,
            bitrate_switch=getattr(message, "bitrate_switch", False),
            error_state_indicator=getattr(message, "error_state_indicator", False),
            timestamp=message.timestamp,
        )

    def _encode_message(self, frame: CanFrame):
        assert python_can is not None
        return python_can.Message(
            arbitration_id=frame.arbitration_id,
            data=frame.data,
            is_extended_id=frame.is_extended_id,
            is_remote_frame=frame.is_remote_frame,
            is_error_frame=frame.is_error_frame,
            is_fd=frame.frame_format == "can_fd",
            bitrate_switch=frame.bitrate_switch,
            error_state_indicator=frame.error_state_indicator,
        )


def transport_backend_config() -> TransportBackendConfig:
    backend = os.environ.get("CANARCHY_TRANSPORT_BACKEND", "scaffold").strip().lower() or "scaffold"
    python_can_interface = (
        os.environ.get("CANARCHY_PYTHON_CAN_INTERFACE", "virtual").strip().lower() or "virtual"
    )
    capture_limit = int(os.environ.get("CANARCHY_CAPTURE_LIMIT", "2"))
    capture_timeout = float(os.environ.get("CANARCHY_CAPTURE_TIMEOUT", "0.05"))
    return TransportBackendConfig(
        backend=backend,
        python_can_interface=python_can_interface,
        capture_limit=max(capture_limit, 1),
        capture_timeout=max(capture_timeout, 0.0),
    )


def build_live_backend(config: TransportBackendConfig | None = None) -> LiveCanBackend:
    config = config or transport_backend_config()
    if config.backend == "scaffold":
        return ScaffoldCanBackend()
    if config.backend == "python-can":
        return PythonCanBackend(
            bus_interface=config.python_can_interface,
            capture_limit=config.capture_limit,
            capture_timeout=config.capture_timeout,
        )
    raise TransportError(
        "TRANSPORT_BACKEND_INVALID",
        f"Unknown transport backend '{config.backend}'.",
        "Use `python-can` or `scaffold` for CANARCHY_TRANSPORT_BACKEND.",
    )


def recorded_frames() -> list[CanFrame]:
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


class LocalTransport:
    """Local transport facade that selects a live CAN backend when available."""

    def __init__(self, live_backend: LiveCanBackend | None = None) -> None:
        self.live_backend = live_backend or build_live_backend()

    def capture(self, interface: str) -> list[CanFrame]:
        return self.live_backend.capture(interface)

    def send(self, interface: str, frame: CanFrame) -> CanFrame:
        return self.live_backend.send(interface, frame)

    def backend_metadata(self) -> dict[str, str | int | float]:
        metadata: dict[str, str | int | float] = {
            "transport_backend": self.live_backend.backend_name,
        }
        if isinstance(self.live_backend, PythonCanBackend):
            metadata["python_can_interface"] = self.live_backend.bus_interface
            metadata["capture_limit"] = self.live_backend.capture_limit
            metadata["capture_timeout"] = self.live_backend.capture_timeout
        return metadata

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
        frames = [frame for frame in recorded_frames() if frame.is_extended_id]
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

    def uds_scan_events(self, interface: str) -> list[dict[str, object]]:
        self._require_interface(interface)
        events = [
            UdsTransactionEvent(
                request_id=0x7DF,
                response_id=0x7E8,
                service=0x10,
                service_name="DiagnosticSessionControl",
                request_data=bytes.fromhex("1001"),
                response_data=bytes.fromhex("5001003201F4"),
                ecu_address=0x7E8,
                source="transport.uds.scan",
                timestamp=0.0,
            ).to_event(),
            UdsTransactionEvent(
                request_id=0x7DF,
                response_id=0x7E9,
                service=0x22,
                service_name="ReadDataByIdentifier",
                request_data=bytes.fromhex("22F190"),
                response_data=bytes.fromhex("62F19056494E313233"),
                ecu_address=0x7E9,
                source="transport.uds.scan",
                timestamp=0.1,
            ).to_event(),
        ]
        return serialize_events(events)

    def uds_trace_events(self, interface: str) -> list[dict[str, object]]:
        self._require_interface(interface)
        events = [
            UdsTransactionEvent(
                request_id=0x7E0,
                response_id=0x7E8,
                service=0x10,
                service_name="DiagnosticSessionControl",
                request_data=bytes.fromhex("1003"),
                response_data=bytes.fromhex("5003003201F4"),
                ecu_address=0x7E8,
                source="transport.uds.trace",
                timestamp=0.0,
            ).to_event(),
            UdsTransactionEvent(
                request_id=0x7E0,
                response_id=0x7E8,
                service=0x27,
                service_name="SecurityAccess",
                request_data=bytes.fromhex("2701"),
                response_data=bytes.fromhex("670112345678"),
                ecu_address=0x7E8,
                source="transport.uds.trace",
                timestamp=0.2,
            ).to_event(),
        ]
        return serialize_events(events)

    def _require_interface(self, interface: str) -> None:
        ScaffoldCanBackend()._require_interface(interface)

    def _frames_for_file(self, file_name: str) -> list[CanFrame]:
        if file_name.lower() in {"missing.log", "missing", "offline.log"}:
            raise TransportError(
                "CAPTURE_SOURCE_UNAVAILABLE",
                f"Capture source '{file_name}' is not available.",
                "Provide a readable capture file or generate traffic with `canarchy capture` first.",
            )
        return recorded_frames()

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
