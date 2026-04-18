"""Transport foundation for local CAN workflows."""

from __future__ import annotations

import os
import queue
import random
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Protocol

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
    serialize_events,
)
from canarchy.sample_data import (
    sample_j1939_monitor_frames,
    sample_uds_scan_transactions,
    sample_uds_trace_transactions,
    scaffold_transport_frames,
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


CANDUMP_CLASSIC_LINE_RE = re.compile(
    r"^\((?P<timestamp>\d+(?:\.\d+)?)\)\s+(?P<interface>\S+)\s+(?P<frame_id>[0-9A-Fa-f]+)#(?P<body>[0-9A-Fa-f]*|R)$"
)
CANDUMP_FD_LINE_RE = re.compile(
    r"^\((?P<timestamp>\d+(?:\.\d+)?)\)\s+(?P<interface>\S+)\s+(?P<frame_id>[0-9A-Fa-f]+)##(?P<flags>[0-9A-Fa-f])(?P<data>[0-9A-Fa-f]*)$"
)
SUPPORTED_CAPTURE_SUFFIXES = {".candump", ".log"}
CAN_ERR_FLAG = 0x20000000
SUPPORTED_CANDUMP_FD_FLAGS = 0x3


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

    def capture_stream(self, interface: str) -> Iterator[CanFrame]: ...

    def send(self, interface: str, frame: CanFrame) -> CanFrame: ...


class ScaffoldCanBackend:
    """Deterministic backend used when no live CAN backend is selected."""

    @property
    def backend_name(self) -> str:
        return "scaffold"

    def capture(self, interface: str) -> list[CanFrame]:
        self._require_interface(interface)
        return [frame.with_interface(interface) for frame in scaffold_transport_frames()[:2]]

    def capture_stream(self, interface: str) -> Iterator[CanFrame]:
        self._require_interface(interface)
        yield from (frame.with_interface(interface) for frame in scaffold_transport_frames()[:2])

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

    def capture_stream(self, interface: str) -> Iterator[CanFrame]:
        bus = self._open_bus(interface)
        try:
            while True:
                message = bus.recv(timeout=None)
                if message is None:
                    continue
                yield self._decode_message(message, interface)
        finally:
            bus.shutdown()

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


def _load_user_config() -> dict[str, str]:
    """Load ~/.canarchy/config.toml and return env-var-style overrides.

    Missing files and parse errors are silently ignored — the caller falls
    back to environment variables and hardcoded defaults.

    Config file format::

        [transport]
        backend = "python-can"
        interface = "udp_multicast"
        # capture_limit = 2
        # capture_timeout = 0.05

    Supported keys under ``[transport]``:

    * ``backend``        → ``CANARCHY_TRANSPORT_BACKEND``
    * ``interface``      → ``CANARCHY_PYTHON_CAN_INTERFACE``
    * ``capture_limit``  → ``CANARCHY_CAPTURE_LIMIT``
    * ``capture_timeout``→ ``CANARCHY_CAPTURE_TIMEOUT``
    """
    import tomllib

    config_path = Path.home() / ".canarchy" / "config.toml"
    if not config_path.exists():
        return {}
    try:
        with config_path.open("rb") as f:
            raw = tomllib.load(f)
    except Exception:
        return {}

    transport = raw.get("transport", {})
    key_map = {
        "backend": "CANARCHY_TRANSPORT_BACKEND",
        "interface": "CANARCHY_PYTHON_CAN_INTERFACE",
        "capture_limit": "CANARCHY_CAPTURE_LIMIT",
        "capture_timeout": "CANARCHY_CAPTURE_TIMEOUT",
    }
    return {
        env_key: str(transport[toml_key])
        for toml_key, env_key in key_map.items()
        if toml_key in transport
    }


def transport_backend_config() -> TransportBackendConfig:
    file_config = _load_user_config()

    def _get(env_key: str, default: str) -> str:
        return os.environ.get(env_key) or file_config.get(env_key) or default

    backend = _get("CANARCHY_TRANSPORT_BACKEND", "python-can").strip().lower() or "python-can"
    python_can_interface = (
        _get("CANARCHY_PYTHON_CAN_INTERFACE", "socketcan").strip().lower() or "socketcan"
    )
    capture_limit = int(_get("CANARCHY_CAPTURE_LIMIT", "2"))
    capture_timeout = float(_get("CANARCHY_CAPTURE_TIMEOUT", "0.05"))
    return TransportBackendConfig(
        backend=backend,
        python_can_interface=python_can_interface,
        capture_limit=max(capture_limit, 1),
        capture_timeout=max(capture_timeout, 0.0),
    )


def config_show_payload() -> dict[str, object]:
    """Return a structured dict describing the effective transport configuration.

    Each value is annotated with its *source*: ``"env"`` (environment variable),
    ``"file"`` (``~/.canarchy/config.toml``), or ``"default"`` (built-in default).
    """
    config_path = Path.home() / ".canarchy" / "config.toml"
    file_config = _load_user_config()

    env_key_map = {
        "backend": ("CANARCHY_TRANSPORT_BACKEND", "scaffold"),
        "interface": ("CANARCHY_PYTHON_CAN_INTERFACE", "virtual"),
        "capture_limit": ("CANARCHY_CAPTURE_LIMIT", "2"),
        "capture_timeout": ("CANARCHY_CAPTURE_TIMEOUT", "0.05"),
    }

    config = transport_backend_config()
    effective = {
        "backend": config.backend,
        "interface": config.python_can_interface,
        "capture_limit": config.capture_limit,
        "capture_timeout": config.capture_timeout,
    }

    sources: dict[str, str] = {}
    for field_name, (env_key, _default) in env_key_map.items():
        if os.environ.get(env_key):
            sources[field_name] = "env"
        elif env_key in file_config:
            sources[field_name] = "file"
        else:
            sources[field_name] = "default"

    return {
        **effective,
        "sources": sources,
        "config_file": str(config_path),
        "config_file_found": config_path.exists(),
    }


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


class LocalTransport:
    """Local transport facade that selects a live CAN backend when available."""

    def __init__(self, live_backend: LiveCanBackend | None = None) -> None:
        self.live_backend = live_backend or build_live_backend()

    def capture(self, interface: str) -> list[CanFrame]:
        return self.live_backend.capture(interface)

    def capture_stream(self, interface: str) -> Iterator[CanFrame]:
        return self.live_backend.capture_stream(interface)

    def send(self, interface: str, frame: CanFrame) -> CanFrame:
        return self.live_backend.send(interface, frame)

    def gateway_events(
        self,
        src: str,
        dst: str,
        *,
        src_backend: str | None = None,
        dst_backend: str | None = None,
        bidirectional: bool = False,
        count: int | None = None,
    ) -> list[dict[str, object]]:
        return list(
            self.gateway_stream_events(
                src,
                dst,
                src_backend=src_backend,
                dst_backend=dst_backend,
                bidirectional=bidirectional,
                count=count,
            )
        )

    def gateway_stream_events(
        self,
        src: str,
        dst: str,
        *,
        src_backend: str | None = None,
        dst_backend: str | None = None,
        bidirectional: bool = False,
        count: int | None = None,
    ) -> Iterator[dict[str, object]]:
        config = transport_backend_config()
        if config.backend != "python-can":
            raise TransportError(
                "GATEWAY_LIVE_BACKEND_REQUIRED",
                "Gateway mode requires the python-can backend.",
                "Set `CANARCHY_TRANSPORT_BACKEND=python-can` to bridge live CAN traffic.",
            )

        src_live_backend = PythonCanBackend(
            bus_interface=src_backend or config.python_can_interface,
            capture_limit=config.capture_limit,
            capture_timeout=config.capture_timeout,
        )
        dst_live_backend = PythonCanBackend(
            bus_interface=dst_backend or config.python_can_interface,
            capture_limit=config.capture_limit,
            capture_timeout=config.capture_timeout,
        )

        if bidirectional:
            yield from self._gateway_bidirectional_stream(
                src,
                dst,
                src_live_backend=src_live_backend,
                dst_live_backend=dst_live_backend,
                count=count,
            )
            return

        yield from self._gateway_unidirectional_stream(
            src,
            dst,
            src_live_backend=src_live_backend,
            dst_live_backend=dst_live_backend,
            count=count,
        )

    def backend_metadata(self) -> dict[str, str | int | float]:
        metadata: dict[str, str | int | float] = {
            "transport_backend": self.live_backend.backend_name,
        }
        if isinstance(self.live_backend, PythonCanBackend):
            metadata["python_can_interface"] = self.live_backend.bus_interface
            metadata["capture_limit"] = self.live_backend.capture_limit
            metadata["capture_timeout"] = self.live_backend.capture_timeout
        return metadata

    def filter(self, file_name: str, expression: str, frames: list[CanFrame] | None = None) -> list[CanFrame]:
        if frames is None:
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

    def capture_stream_events(self, interface: str) -> Iterator[dict[str, object]]:
        for frame in self.capture_stream(interface):
            yield serialize_events(
                [FrameEvent(frame=frame, source="transport.capture").to_event()]
            )[0]

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

    def filter_events(self, file_name: str, expression: str, frames: list[CanFrame] | None = None) -> list[dict[str, object]]:
        if frames is None:
            frames = self.filter(file_name, expression)
        else:
            frames = self.filter(file_name, expression, frames)
        return serialize_events(
            [FrameEvent(frame=frame, source="transport.filter").to_event() for frame in frames]
        )

    def j1939_monitor_events(self, pgn: int | None = None) -> list[dict[str, object]]:
        frames = sample_j1939_monitor_frames()
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
        return serialize_events([event.to_event() for event in sample_uds_scan_transactions()])

    def uds_trace_events(self, interface: str) -> list[dict[str, object]]:
        self._require_interface(interface)
        return serialize_events([event.to_event() for event in sample_uds_trace_transactions()])

    def generate_events(
        self, interface: str, frames: list[CanFrame], *, gap_ms: float = 0.0
    ) -> list[dict[str, object]]:
        events: list[object] = [
            AlertEvent(
                level="warning",
                code="ACTIVE_TRANSMIT",
                message="Active frame generation requested on the selected interface.",
                source="transport.generate",
            ).to_event(),
        ]
        for i, frame in enumerate(frames):
            if i > 0 and gap_ms > 0:
                time.sleep(gap_ms / 1000.0)
            sent_frame = self.send(interface, frame)
            events.append(FrameEvent(frame=sent_frame, source="transport.generate").to_event())
        return serialize_events(events)

    def _gateway_unidirectional_stream(
        self,
        src: str,
        dst: str,
        *,
        src_live_backend: PythonCanBackend,
        dst_live_backend: PythonCanBackend,
        count: int | None,
    ) -> Iterator[dict[str, object]]:
        src_bus = src_live_backend._open_bus(src)
        dst_bus = dst_live_backend._open_bus(dst)
        forwarded = 0
        try:
            while count is None or forwarded < count:
                message = src_bus.recv(timeout=src_live_backend.capture_timeout)
                if message is None:
                    continue
                frame = src_live_backend._decode_message(message, src)
                self._gateway_send(
                    dst_bus,
                    dst_live_backend,
                    frame,
                    destination=dst,
                )
                forwarded += 1
                yield self._gateway_event(frame, direction="src->dst")
        finally:
            src_bus.shutdown()
            dst_bus.shutdown()

    def _gateway_bidirectional_stream(
        self,
        src: str,
        dst: str,
        *,
        src_live_backend: PythonCanBackend,
        dst_live_backend: PythonCanBackend,
        count: int | None,
    ) -> Iterator[dict[str, object]]:
        src_bus = src_live_backend._open_bus(src)
        dst_bus = dst_live_backend._open_bus(dst)
        forwarded = 0
        forwarded_lock = threading.Lock()
        stop_event = threading.Event()
        forwarded_events: queue.Queue[dict[str, object]] = queue.Queue()
        errors: queue.Queue[TransportError] = queue.Queue()

        def worker(
            read_bus: object,
            write_bus: object,
            read_backend: PythonCanBackend,
            write_backend: PythonCanBackend,
            read_interface: str,
            write_interface: str,
            direction: str,
        ) -> None:
            nonlocal forwarded
            try:
                while not stop_event.is_set():
                    message = read_bus.recv(timeout=read_backend.capture_timeout)
                    if message is None:
                        continue

                    frame = read_backend._decode_message(message, read_interface)
                    event = self._gateway_event(frame, direction=direction)
                    with forwarded_lock:
                        if count is not None and forwarded >= count:
                            stop_event.set()
                            return
                        self._gateway_send(
                            write_bus,
                            write_backend,
                            frame,
                            destination=write_interface,
                        )
                        forwarded += 1
                        if count is not None and forwarded >= count:
                            stop_event.set()
                    forwarded_events.put(event)
            except TransportError as exc:
                errors.put(exc)
                stop_event.set()

        workers = [
            threading.Thread(
                target=worker,
                args=(
                    src_bus,
                    dst_bus,
                    src_live_backend,
                    dst_live_backend,
                    src,
                    dst,
                    "src->dst",
                ),
            ),
            threading.Thread(
                target=worker,
                args=(
                    dst_bus,
                    src_bus,
                    dst_live_backend,
                    src_live_backend,
                    dst,
                    src,
                    "dst->src",
                ),
            ),
        ]

        for worker_thread in workers:
            worker_thread.start()

        try:
            while True:
                if not errors.empty():
                    raise errors.get_nowait()
                try:
                    yield forwarded_events.get(timeout=0.05)
                    continue
                except queue.Empty:
                    pass
                if stop_event.is_set() and forwarded_events.empty():
                    break
                if all(not worker_thread.is_alive() for worker_thread in workers) and forwarded_events.empty():
                    break
        finally:
            stop_event.set()
            for worker_thread in workers:
                worker_thread.join()
            src_bus.shutdown()
            dst_bus.shutdown()

    def _gateway_send(
        self,
        bus: object,
        backend: PythonCanBackend,
        frame: CanFrame,
        *,
        destination: str,
    ) -> None:
        try:
            bus.send(backend._encode_message(frame))
        except Exception as exc:
            raise TransportError(
                "TRANSPORT_UNAVAILABLE",
                f"Failed to forward CAN frame to interface '{destination}'.",
                "Check that the python-can interface and channel are configured correctly.",
            ) from exc

    def _gateway_event(self, frame: CanFrame, *, direction: str) -> dict[str, object]:
        return serialize_events([FrameEvent(frame=frame, source=f"gateway.{direction}").to_event()])[0]

    def _require_interface(self, interface: str) -> None:
        ScaffoldCanBackend()._require_interface(interface)

    def _frames_for_file(self, file_name: str) -> list[CanFrame]:
        path = Path(file_name)
        if file_name.lower() in {"missing.log", "missing", "offline.log"} or not path.exists():
            raise TransportError(
                "CAPTURE_SOURCE_UNAVAILABLE",
                f"Capture source '{file_name}' is not available.",
                "Provide a readable capture file or generate traffic with `canarchy capture` first.",
            )
        if not path.is_file():
            raise TransportError(
                "CAPTURE_SOURCE_UNAVAILABLE",
                f"Capture source '{file_name}' is not a readable file.",
                "Provide a readable candump log file path.",
            )
        if path.suffix.lower() not in SUPPORTED_CAPTURE_SUFFIXES:
            supported_formats = ", ".join(sorted(SUPPORTED_CAPTURE_SUFFIXES))
            raise TransportError(
                "CAPTURE_FORMAT_UNSUPPORTED",
                f"Capture source '{file_name}' uses an unsupported file format.",
                f"Use a candump log file with one of these suffixes: {supported_formats}.",
            )

        try:
            return load_candump_file(path)
        except OSError as exc:
            raise TransportError(
                "CAPTURE_SOURCE_UNAVAILABLE",
                f"Capture source '{file_name}' could not be read.",
                "Check file permissions and try again.",
            ) from exc

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


def load_candump_file(path: Path) -> list[CanFrame]:
    frames: list[CanFrame] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue
        frames.append(parse_candump_line(stripped, path=path, line_number=line_number))
    return frames


def parse_candump_line(line: str, *, path: Path, line_number: int) -> CanFrame:
    fd_match = CANDUMP_FD_LINE_RE.match(line)
    if fd_match is not None:
        return parse_candump_fd_line(fd_match, path=path, line_number=line_number)

    classic_match = CANDUMP_CLASSIC_LINE_RE.match(line)
    if classic_match is not None:
        return parse_candump_classic_line(classic_match, path=path, line_number=line_number)

    raise TransportError(
        "CAPTURE_SOURCE_INVALID",
        f"Failed to parse candump log line {line_number} in '{path}'.",
        "Use candump forms like `(timestamp) interface id#data`, `id#R`, or `id##<flags><data>`.",
    )


def parse_candump_classic_line(match: re.Match[str], *, path: Path, line_number: int) -> CanFrame:
    frame_id_text = match.group("frame_id")
    raw_identifier = int(frame_id_text, 16)
    is_error_frame = bool(raw_identifier & CAN_ERR_FLAG)
    arbitration_id = raw_identifier & 0x1FFFFFFF if is_error_frame else raw_identifier
    body = match.group("body")
    is_remote_frame = body.upper() == "R"
    data_text = "" if is_remote_frame else body
    if len(data_text) % 2 != 0:
        raise TransportError(
            "CAPTURE_SOURCE_INVALID",
            f"Candump log line {line_number} in '{path}' contains invalid hex payload data.",
            "Use full byte pairs in the candump payload field.",
        )

    try:
        return CanFrame(
            arbitration_id=arbitration_id,
            data=bytes.fromhex(data_text),
            timestamp=float(match.group("timestamp")),
            interface=match.group("interface"),
            is_extended_id=bool(
                arbitration_id > 0x7FF or (len(frame_id_text) > 3 and not is_error_frame)
            ),
            is_remote_frame=is_remote_frame,
            is_error_frame=is_error_frame,
        )
    except ValueError as exc:
        raise TransportError(
            "CAPTURE_SOURCE_INVALID",
            f"Candump log line {line_number} in '{path}' is not a valid CAN frame.",
            "Check the frame identifier width and payload length for the selected frame type.",
        ) from exc


def parse_candump_fd_line(match: re.Match[str], *, path: Path, line_number: int) -> CanFrame:
    frame_id_text = match.group("frame_id")
    data_text = match.group("data")
    flags = int(match.group("flags"), 16)
    if flags & ~SUPPORTED_CANDUMP_FD_FLAGS:
        raise TransportError(
            "CAPTURE_SOURCE_INVALID",
            f"Candump log line {line_number} in '{path}' uses unsupported CAN FD flags 0x{flags:X}.",
            "Use CAN FD flags within the supported BRS/ESI subset.",
        )
    if len(data_text) % 2 != 0:
        raise TransportError(
            "CAPTURE_SOURCE_INVALID",
            f"Candump log line {line_number} in '{path}' contains invalid hex payload data.",
            "Use full byte pairs in the candump payload field.",
        )

    arbitration_id = int(frame_id_text, 16)
    try:
        return CanFrame(
            arbitration_id=arbitration_id,
            data=bytes.fromhex(data_text),
            timestamp=float(match.group("timestamp")),
            interface=match.group("interface"),
            is_extended_id=len(frame_id_text) > 3,
            frame_format="can_fd",
            bitrate_switch=bool(flags & 0x1),
            error_state_indicator=bool(flags & 0x2),
        )
    except ValueError as exc:
        raise TransportError(
            "CAPTURE_SOURCE_INVALID",
            f"Candump log line {line_number} in '{path}' is not a valid CAN FD frame.",
            "Check the frame identifier width, payload length, and CAN FD flags.",
        ) from exc


def generate_frames(
    interface: str,
    *,
    id_spec: str = "R",
    dlc_spec: str = "R",
    data_spec: str = "R",
    count: int = 1,
    gap_ms: float = 200.0,
    extended: bool = False,
) -> list[CanFrame]:
    frames: list[CanFrame] = []
    for i in range(count):
        if id_spec.upper() == "R":
            arb_id = random.randint(0, 0x1FFFFFFF if extended else 0x7FF)
        else:
            arb_id = int(id_spec, 16)
        is_extended = extended or arb_id > 0x7FF

        if dlc_spec.upper() == "R":
            dlc = random.randint(0, 8)
        else:
            dlc = int(dlc_spec)

        if data_spec.upper() == "R":
            data = bytes(random.randint(0, 255) for _ in range(dlc))
        elif data_spec.upper() == "I":
            data = bytes((i * dlc + j) % 256 for j in range(dlc))
        else:
            data = bytes.fromhex(data_spec)

        frames.append(
            CanFrame(
                arbitration_id=arb_id,
                data=data,
                interface=interface,
                is_extended_id=is_extended,
                timestamp=i * gap_ms / 1000.0,
            )
        )
    return frames
