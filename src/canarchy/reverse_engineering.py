"""Reverse-engineering helpers for recorded CAN traffic."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import log2
from typing import Any

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


@dataclass(slots=True, frozen=True)
class EntropyByteSummary:
    arbitration_id: int
    byte_position: int
    entropy: float
    unique_values: int

    def to_payload(self) -> dict[str, object]:
        return {
            "arbitration_id": self.arbitration_id,
            "byte_position": self.byte_position,
            "entropy": self.entropy,
            "unique_values": self.unique_values,
        }


@dataclass(slots=True, frozen=True)
class EntropyCandidate:
    arbitration_id: int
    frame_count: int
    mean_byte_entropy: float
    max_byte_entropy: float
    low_sample: bool
    rationale: str
    byte_entropies: tuple[EntropyByteSummary, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "arbitration_id": self.arbitration_id,
            "frame_count": self.frame_count,
            "mean_byte_entropy": self.mean_byte_entropy,
            "max_byte_entropy": self.max_byte_entropy,
            "low_sample": self.low_sample,
            "rationale": self.rationale,
            "byte_entropies": [summary.to_payload() for summary in self.byte_entropies],
        }


@dataclass(slots=True, frozen=True)
class SignalCandidate:
    arbitration_id: int
    start_bit: int
    bit_length: int
    score: float
    rationale: str
    sample_count: int
    observed_min: int
    observed_max: int
    change_rate: float

    def to_payload(self) -> dict[str, object]:
        return {
            "arbitration_id": self.arbitration_id,
            "start_bit": self.start_bit,
            "bit_length": self.bit_length,
            "score": self.score,
            "rationale": self.rationale,
            "sample_count": self.sample_count,
            "observed_min": self.observed_min,
            "observed_max": self.observed_max,
            "change_rate": self.change_rate,
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


def entropy_candidates(frames: list[CanFrame]) -> list[dict[str, object]]:
    grouped_frames: dict[int, list[CanFrame]] = defaultdict(list)
    for frame in frames:
        if not frame.is_remote_frame and not frame.is_error_frame and frame.data:
            grouped_frames[frame.arbitration_id].append(frame)

    candidates: list[EntropyCandidate] = []
    for arbitration_id, group in grouped_frames.items():
        byte_count = min(len(frame.data) for frame in group)
        byte_summaries = tuple(
            _entropy_byte_summary(group, arbitration_id, byte_position)
            for byte_position in range(byte_count)
        )
        if not byte_summaries:
            continue
        entropies = [summary.entropy for summary in byte_summaries]
        low_sample = len(group) < 10
        rationale_parts = [
            f"{len(group)} frames observed",
            f"mean byte entropy {round(sum(entropies) / len(entropies), 3)} bits",
        ]
        if low_sample:
            rationale_parts.append("low sample count")
        candidates.append(
            EntropyCandidate(
                arbitration_id=arbitration_id,
                frame_count=len(group),
                mean_byte_entropy=round(sum(entropies) / len(entropies), 3),
                max_byte_entropy=round(max(entropies), 3),
                low_sample=low_sample,
                rationale="; ".join(rationale_parts),
                byte_entropies=byte_summaries,
            )
        )

    candidates.sort(
        key=lambda candidate: (
            -candidate.mean_byte_entropy,
            -candidate.max_byte_entropy,
            candidate.arbitration_id,
        )
    )
    return [candidate.to_payload() for candidate in candidates]


def signal_analysis(frames: list[CanFrame]) -> dict[str, object]:
    grouped_frames: dict[int, list[CanFrame]] = defaultdict(list)
    for frame in frames:
        if not frame.is_remote_frame and not frame.is_error_frame and frame.data:
            grouped_frames[frame.arbitration_id].append(frame)

    candidates: list[SignalCandidate] = []
    analysis_by_id: list[dict[str, object]] = []
    low_sample_ids: list[int] = []

    for arbitration_id in sorted(grouped_frames):
        group = grouped_frames[arbitration_id]
        frame_count = len(group)
        payload_bits = min(len(frame.data) for frame in group) * 8
        evaluated_fields = 0
        accepted_fields = 0

        if frame_count < 5:
            low_sample_ids.append(arbitration_id)
            analysis_by_id.append(
                {
                    "arbitration_id": arbitration_id,
                    "frame_count": frame_count,
                    "payload_bits": payload_bits,
                    "evaluated_fields": 0,
                    "candidate_count": 0,
                    "low_sample": True,
                }
            )
            continue

        for bit_length in (4, 8, 16):
            for start_bit in range(0, payload_bits - bit_length + 1, bit_length):
                evaluated_fields += 1
                candidate = _signal_candidate_for_field(group, arbitration_id, start_bit, bit_length)
                if candidate is None:
                    continue
                accepted_fields += 1
                candidates.append(candidate)

        analysis_by_id.append(
            {
                "arbitration_id": arbitration_id,
                "frame_count": frame_count,
                "payload_bits": payload_bits,
                "evaluated_fields": evaluated_fields,
                "candidate_count": accepted_fields,
                "low_sample": False,
            }
        )

    candidates.sort(
        key=lambda candidate: (
            -candidate.score,
            candidate.arbitration_id,
            candidate.start_bit,
            candidate.bit_length,
        )
    )

    return {
        "candidate_count": len(candidates),
        "candidates": [candidate.to_payload() for candidate in candidates],
        "analysis_by_id": analysis_by_id,
        "low_sample_ids": low_sample_ids,
    }


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


def _signal_candidate_for_field(
    frames: list[CanFrame], arbitration_id: int, start_bit: int, bit_length: int
) -> SignalCandidate | None:
    values = [_extract_field_value(frame, start_bit, bit_length) for frame in frames]
    if len(values) < 5:
        return None

    transitions = len(values) - 1
    if transitions <= 0:
        return None

    changed_steps = sum(1 for current, following in zip(values, values[1:]) if current != following)
    change_rate = changed_steps / transitions
    unique_values = len(set(values))
    if unique_values < 2:
        return None

    observed_min = min(values)
    observed_max = max(values)
    max_value = (1 << bit_length) - 1
    span_ratio = 0.0 if max_value <= 0 else (observed_max - observed_min) / max_value
    midrange_change_score = max(0.0, 1.0 - (abs(change_rate - 0.5) / 0.5))
    unique_ratio = unique_values / len(values)
    bit_length_bonus = {4: 0.0, 8: 0.08, 16: 0.05}[bit_length]

    score = round(
        min(
            1.0,
            (midrange_change_score * 0.55) + (span_ratio * 0.25) + (unique_ratio * 0.2) + bit_length_bonus,
        ),
        3,
    )
    if score < 0.2:
        return None

    rationale_parts = [
        f"change rate {round(change_rate, 3)} across {transitions} transitions",
        f"observed range {observed_min}..{observed_max}",
        f"{unique_values} unique values across {len(values)} samples",
    ]
    if 0.05 <= change_rate <= 0.95:
        rationale_parts.append("change rate sits inside the preferred signal band")
    elif change_rate == 0.0:
        rationale_parts.append("field is too stable to be a useful signal candidate")
    else:
        rationale_parts.append("field changes nearly every frame, reducing signal confidence")

    return SignalCandidate(
        arbitration_id=arbitration_id,
        start_bit=start_bit,
        bit_length=bit_length,
        score=score,
        rationale="; ".join(rationale_parts),
        sample_count=len(values),
        observed_min=observed_min,
        observed_max=observed_max,
        change_rate=round(change_rate, 3),
    )


def _extract_field_value(frame: CanFrame, start_bit: int, bit_length: int) -> int:
    raw_value = int.from_bytes(frame.data, byteorder="little", signed=False)
    return (raw_value >> start_bit) & ((1 << bit_length) - 1)


def _entropy_byte_summary(
    frames: list[CanFrame], arbitration_id: int, byte_position: int
) -> EntropyByteSummary:
    values = [frame.data[byte_position] for frame in frames]
    counts: dict[int, int] = defaultdict(int)
    for value in values:
        counts[value] += 1

    total = len(values)
    entropy = 0.0
    for count in counts.values():
        probability = count / total
        entropy -= probability * log2(probability)

    return EntropyByteSummary(
        arbitration_id=arbitration_id,
        byte_position=byte_position,
        entropy=round(entropy, 3),
        unique_values=len(counts),
    )


def score_dbc_candidates(
    capture_ids: dict[int, int],
    catalog: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Score each catalog DBC by how well it covers the capture's arbitration IDs.

    capture_ids maps arbitration_id -> frame_count.
    Each catalog entry must have: name, source_ref, message_ids (list[int]).
    Score = fraction of total captured frames whose ID is known to the DBC.
    """
    if not capture_ids or not catalog:
        return []

    total_capture_ids = len(capture_ids)
    total_frames = sum(capture_ids.values()) or 1

    results: list[dict[str, Any]] = []
    for entry in catalog:
        message_ids: set[int] = set(entry.get("message_ids", []))
        if not message_ids:
            continue

        matched_ids = {arb_id for arb_id in capture_ids if arb_id in message_ids}
        if not matched_ids:
            continue

        matched_frames = sum(capture_ids[arb_id] for arb_id in matched_ids)
        score = round(matched_frames / total_frames, 2)

        results.append(
            {
                "name": entry["name"],
                "source_ref": entry.get("source_ref", f"opendbc:{entry['name']}"),
                "score": score,
                "matched_ids": len(matched_ids),
                "total_capture_ids": total_capture_ids,
            }
        )

    results.sort(key=lambda x: (-x["score"], x["name"]))
    return results
