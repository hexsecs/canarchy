"""Bounded, presentation-independent CAN identifier analysis for the TUI."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Iterable

from canarchy.j1939 import decompose_arbitration_id
from canarchy.models import CanFrame


@dataclass(frozen=True, slots=True)
class IdentifierKey:
    bus: str
    arbitration_id: int
    is_extended_id: bool

    @property
    def label(self) -> str:
        return f"0x{self.arbitration_id:X} {'ext' if self.is_extended_id else 'std'}"


@dataclass(frozen=True, slots=True)
class FrameObservation:
    sequence: int
    event_index: int
    key: IdentifierKey
    frame: CanFrame
    received_at: float
    decoded: tuple[str, ...] = ()


@dataclass(slots=True)
class IdentifierActivity:
    key: IdentifierKey
    count: int = 0
    history: deque[FrameObservation] = field(default_factory=deque)
    changed_offsets: tuple[int, ...] = ()
    last_payload: bytes = b""

    @property
    def latest(self) -> FrameObservation:
        return self.history[-1]

    def observe(self, observation: FrameObservation) -> None:
        self.changed_offsets = (
            tuple(
                index
                for index in range(max(len(self.last_payload), len(observation.frame.data)))
                if self.last_payload[index : index + 1] != observation.frame.data[index : index + 1]
            )
            if self.count
            else ()
        )
        self.count += 1
        self.last_payload = observation.frame.data
        self.history.append(observation)

    def rate_hz(self) -> float:
        recent = list(self.history)[-16:]
        if len(recent) < 2:
            return 0.0
        first = recent[0].frame.timestamp
        last = recent[-1].frame.timestamp
        if first is None or last is None or last <= first:
            first = recent[0].received_at
            last = recent[-1].received_at
        return (len(recent) - 1) / (last - first) if last > first else 0.0

    def activity_plot(self) -> str:
        samples = list(self.history)[-32:]
        if not samples:
            return "........"
        start = samples[0].received_at
        end = samples[-1].received_at
        width = max(end - start, 1.0)
        buckets = [0] * 8
        for sample in samples:
            index = min(7, int((sample.received_at - start) / width * 8))
            buckets[index] += 1
        peak = max(buckets)
        scale = " .:-=+*#"
        return "".join(
            scale[round(count / peak * (len(scale) - 1))] if count else "." for count in buckets
        )


class TrafficExplorer:
    """Bound observations and identifier history without depending on Textual."""

    def __init__(self, capacity: int = 1000) -> None:
        self.capacity = capacity
        self.sequence = 0
        self.observations: deque[FrameObservation] = deque()
        self.activities: dict[IdentifierKey, IdentifierActivity] = {}

    def clear(self) -> None:
        self.sequence = 0
        self.observations.clear()
        self.activities.clear()

    def resize(self, capacity: int) -> None:
        self.capacity = capacity
        self._trim()

    def ingest(
        self, events: Iterable[dict[str, Any]], *, received_at: float | None = None
    ) -> list[FrameObservation]:
        event_list = list(events)
        arrival = monotonic() if received_at is None else received_at
        decoded: dict[int, list[str]] = {}
        for event in event_list:
            if event.get("event_type") != "signal":
                continue
            payload = event.get("payload") or {}
            index = payload.get("frame_index")
            if isinstance(index, int) and not isinstance(index, bool):
                units = payload.get("units") or ""
                decoded.setdefault(index, []).append(
                    f"{payload.get('message_name', '?')}.{payload.get('signal_name', '?')}="
                    f"{payload.get('value', '?')} {units}".rstrip()
                )
        added: list[FrameObservation] = []
        frame_index = 0
        for event_index, event in enumerate(event_list):
            if event.get("event_type") != "frame":
                continue
            payload = (event.get("payload") or {}).get("frame") or {}
            try:
                frame = CanFrame(
                    arbitration_id=int(payload["arbitration_id"]),
                    data=bytes.fromhex(payload.get("data") or ""),
                    timestamp=payload.get("timestamp", event.get("timestamp")),
                    interface=payload.get("interface"),
                    is_extended_id=bool(payload.get("is_extended_id", False)),
                    is_remote_frame=bool(payload.get("is_remote_frame", False)),
                    is_error_frame=bool(payload.get("is_error_frame", False)),
                    bitrate_switch=bool(payload.get("bitrate_switch", False)),
                    error_state_indicator=bool(payload.get("error_state_indicator", False)),
                    frame_format=payload.get("frame_format", "can"),
                )
            except (KeyError, TypeError, ValueError):
                frame_index += 1
                continue
            bus = frame.interface or str(event.get("source") or "")
            key = IdentifierKey(bus, frame.arbitration_id, frame.is_extended_id)
            self.sequence += 1
            observation = FrameObservation(
                self.sequence, event_index, key, frame, arrival, tuple(decoded.get(frame_index, ()))
            )
            activity = self.activities.setdefault(key, IdentifierActivity(key))
            activity.observe(observation)
            self.observations.append(observation)
            added.append(observation)
            frame_index += 1
        self._trim()
        return added

    def _trim(self) -> None:
        while len(self.observations) > self.capacity:
            old = self.observations.popleft()
            activity = self.activities[old.key]
            activity.history.popleft()
            if not activity.history:
                del self.activities[old.key]

    def summary_rows(
        self, *, now: float | None = None
    ) -> list[tuple[IdentifierKey, tuple[str, ...]]]:
        current = monotonic() if now is None else now
        rows: list[tuple[IdentifierKey, tuple[str, ...]]] = []
        for key, activity in self.activities.items():
            age = max(0.0, current - activity.latest.received_at)
            changed = ",".join(str(index) for index in activity.changed_offsets) or "-"
            rows.append(
                (
                    key,
                    (
                        key.bus,
                        f"0x{key.arbitration_id:X}",
                        "ext" if key.is_extended_id else "std",
                        str(activity.count),
                        f"{activity.rate_hz():.1f}",
                        f"{age:.1f}s",
                        activity.last_payload.hex().upper(),
                        changed,
                        activity.activity_plot(),
                    ),
                )
            )
        return rows

    def detail(
        self, key: IdentifierKey, *, sequence: int | None = None, history_limit: int = 8
    ) -> str:
        activity = self.activities.get(key)
        if activity is None:
            return f"{key.bus} {key.label}\nHistory evicted from the bounded backlog."
        history = list(activity.history)
        selected_index = next(
            (index for index, item in enumerate(history) if item.sequence == sequence),
            len(history) - 1,
        )
        selected = history[selected_index]
        latest = selected.frame
        previous = history[selected_index - 1].frame.data if selected_index else None
        changed_offsets = (
            tuple(
                index
                for index in range(max(len(previous), len(latest.data)))
                if previous[index : index + 1] != latest.data[index : index + 1]
            )
            if previous is not None
            else ()
        )
        lines = [
            f"Bus: {key.bus}",
            f"Identifier: 0x{key.arbitration_id:X} ({'extended' if key.is_extended_id else 'standard'})",
            f"Timestamp: {latest.timestamp if latest.timestamp is not None else '(absent)'}",
            f"Format: {latest.frame_format}  DLC: {latest.dlc}",
            f"Flags: remote={latest.is_remote_frame} error={latest.is_error_frame} "
            f"BRS={latest.bitrate_switch} ESI={latest.error_state_indicator}",
            f"Raw hex: {latest.data.hex().upper()}",
            "Bytes (^ changed since previous payload; offsets are zero-based):",
            " ".join(
                f"{index:02d}:{value:02X}{'^' if index in changed_offsets else ' '}"
                for index, value in enumerate(latest.data)
            )
            or "(none)",
            "Bits: " + (" ".join(f"{value:08b}" for value in latest.data) or "(none)"),
        ]
        if key.is_extended_id:
            identifier = decompose_arbitration_id(key.arbitration_id)
            lines.append(f"J1939: PGN={identifier.pgn} SA=0x{identifier.source_address:02X}")
        lines.append("Decoded: " + ("; ".join(selected.decoded) or "(not available)"))
        lines.append("Recent history (oldest to newest):")
        for sample in history[max(0, selected_index - history_limit + 1) : selected_index + 1]:
            lines.append(f"  {sample.frame.timestamp}: {sample.frame.data.hex().upper()}")
        return "\n".join(lines)
