"""Reverse-engineering helpers for recorded CAN traffic."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from canarchy.models import CanFrame


@dataclass(slots=True, frozen=True)
class CounterCandidate:
    arbitration_id: int
    start_bit: int
    bit_length: int
    score: float
    rationale: str
    sample_count: int
    monotonicity_ratio: float
    rollover_detected: bool
    observed_min: int
    observed_max: int

    def to_payload(self) -> dict[str, object]:
        return {
            "arbitration_id": self.arbitration_id,
            "start_bit": self.start_bit,
            "bit_length": self.bit_length,
            "score": self.score,
            "rationale": self.rationale,
            "sample_count": self.sample_count,
            "monotonicity_ratio": self.monotonicity_ratio,
            "rollover_detected": self.rollover_detected,
            "observed_min": self.observed_min,
            "observed_max": self.observed_max,
        }


def counter_candidates(frames: list[CanFrame]) -> list[dict[str, object]]:
    grouped_frames: dict[int, list[CanFrame]] = defaultdict(list)
    for frame in frames:
        if not frame.is_remote_frame and not frame.is_error_frame:
            grouped_frames[frame.arbitration_id].append(frame)

    candidates: list[CounterCandidate] = []
    for arbitration_id, group in grouped_frames.items():
        if len(group) < 4:
            continue
        max_payload_bits = min(len(frame.data) for frame in group) * 8
        for bit_length in (4, 8):
            for start_bit in range(0, max_payload_bits - bit_length + 1, 4):
                candidate = _counter_candidate_for_field(group, arbitration_id, start_bit, bit_length)
                if candidate is not None:
                    candidates.append(candidate)

    candidates.sort(
        key=lambda candidate: (
            -candidate.score,
            candidate.arbitration_id,
            candidate.start_bit,
            candidate.bit_length,
        )
    )
    return [candidate.to_payload() for candidate in candidates]


def _counter_candidate_for_field(
    frames: list[CanFrame], arbitration_id: int, start_bit: int, bit_length: int
) -> CounterCandidate | None:
    values = [_extract_field_value(frame, start_bit, bit_length) for frame in frames]
    if len(values) < 4:
        return None

    transitions = len(values) - 1
    if transitions <= 0:
        return None

    max_value = (1 << bit_length) - 1
    monotonic_steps = 0
    rollover_detected = False
    for current, following in zip(values, values[1:]):
        if following == current + 1:
            monotonic_steps += 1
            continue
        if current == max_value and following == 0:
            monotonic_steps += 1
            rollover_detected = True

    monotonicity_ratio = monotonic_steps / transitions
    unique_values = len(set(values))
    if monotonicity_ratio < 0.75 or unique_values < 4:
        return None

    score = monotonicity_ratio
    if rollover_detected:
        score += 0.1
    if unique_values >= min(len(values), 8):
        score += 0.05
    score = round(min(score, 1.0), 3)

    observed_min = min(values)
    observed_max = max(values)
    rationale_parts = [
        f"{monotonic_steps}/{transitions} adjacent samples increment by one",
        f"observed range {observed_min}..{observed_max}",
    ]
    if rollover_detected:
        rationale_parts.append("rollover observed")
    rationale = "; ".join(rationale_parts)

    return CounterCandidate(
        arbitration_id=arbitration_id,
        start_bit=start_bit,
        bit_length=bit_length,
        score=score,
        rationale=rationale,
        sample_count=len(values),
        monotonicity_ratio=round(monotonicity_ratio, 3),
        rollover_detected=rollover_detected,
        observed_min=observed_min,
        observed_max=observed_max,
    )


def _extract_field_value(frame: CanFrame, start_bit: int, bit_length: int) -> int:
    raw_value = int.from_bytes(frame.data, byteorder="little", signed=False)
    return (raw_value >> start_bit) & ((1 << bit_length) - 1)
