"""Replay engine helpers."""

from __future__ import annotations

from dataclasses import dataclass

from canarchy.models import CanFrame, ReplayActionEvent, serialize_events


@dataclass(slots=True)
class ReplayPlan:
    rate: float
    frame_count: int
    duration: float
    events: list[dict[str, object]]


def build_replay_plan(frames: list[CanFrame], *, rate: float) -> ReplayPlan:
    if not frames:
        return ReplayPlan(rate=rate, frame_count=0, duration=0.0, events=[])

    base_timestamp = frames[0].timestamp or 0.0
    events = []
    for frame in frames:
        frame_timestamp = frame.timestamp if frame.timestamp is not None else base_timestamp
        relative_time = (frame_timestamp - base_timestamp) / rate
        events.append(
            ReplayActionEvent(
                action="send_frame",
                frame=frame,
                rate=rate,
                source="replay.engine",
                timestamp=relative_time,
            ).to_event()
        )

    duration = events[-1].timestamp or 0.0
    return ReplayPlan(
        rate=rate,
        frame_count=len(frames),
        duration=duration,
        events=serialize_events(events),
    )
