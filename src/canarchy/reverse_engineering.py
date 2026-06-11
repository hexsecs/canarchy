"""Reverse-engineering helpers for recorded CAN traffic."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from math import isfinite, log2
from pathlib import Path
from statistics import StatisticsError, correlation, median
from typing import Any

from canarchy.models import CanFrame

# J1939 transport-protocol PGNs whose payloads carry protocol plumbing
# (sequence numbers, control bytes) rather than application signals. RE
# heuristics must not report these as discovered counters/signals (#407).
J1939_TRANSPORT_PGNS = frozenset(
    {
        0xEB00,  # TP.DT — transport data transfer (byte 0 is a sequence number)
        0xEC00,  # TP.CM — transport connection management
        0xC700,  # ETP.DT — extended transport data transfer
        0xC800,  # ETP.CM — extended transport connection management
    }
)


def j1939_annotation(arbitration_id: int) -> dict[str, Any] | None:
    """Decode a 29-bit J1939 arbitration id into PGN / source-address fields.

    Returns ``None`` for ids that do not decompose as J1939 (#406).
    """
    from canarchy.j1939 import decompose_arbitration_id
    from canarchy.j1939_metadata import pgn_lookup, source_address_lookup

    try:
        identifier = decompose_arbitration_id(arbitration_id)
    except ValueError:
        return None
    meta = pgn_lookup(identifier.pgn) or {}
    return {
        "pgn": identifier.pgn,
        "pgn_label": meta.get("label"),
        "pgn_name": meta.get("name"),
        "source_address": identifier.source_address,
        "source_address_name": source_address_lookup(identifier.source_address),
        "j1939_transport": identifier.pgn in J1939_TRANSPORT_PGNS,
    }


def j1939_annotations(frames: list[CanFrame]) -> dict[int, dict[str, Any]]:
    """Map each extended (29-bit) arbitration id in ``frames`` to its annotation."""
    annotations: dict[int, dict[str, Any]] = {}
    for frame in frames:
        if frame.is_extended_id and frame.arbitration_id not in annotations:
            annotation = j1939_annotation(frame.arbitration_id)
            if annotation is not None:
                annotations[frame.arbitration_id] = annotation
    return annotations


def j1939_transport_ids(frames: list[CanFrame]) -> list[dict[str, Any]]:
    """List the J1939 transport-protocol ids present in ``frames``."""
    excluded: list[dict[str, Any]] = []
    for arb_id, annotation in sorted(j1939_annotations(frames).items()):
        if annotation["j1939_transport"]:
            excluded.append(
                {
                    "arbitration_id": arb_id,
                    "arbitration_id_hex": f"0x{arb_id:X}",
                    "pgn": annotation["pgn"],
                    "pgn_label": annotation["pgn_label"],
                }
            )
    return excluded


def _annotated_payload(
    payload: dict[str, object], annotations: dict[int, dict[str, Any]]
) -> dict[str, object]:
    arb_id = payload["arbitration_id"]
    assert isinstance(arb_id, int)
    payload.setdefault("arbitration_id_hex", f"0x{arb_id:X}")
    annotation = annotations.get(arb_id)
    if annotation is not None:
        payload.update(annotation)
    return payload


class ReferenceSeriesError(Exception):
    """Raised when a reference series file is invalid or overlaps insufficiently."""

    def __init__(self, code: str, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.hint = hint


@dataclass(slots=True, frozen=True)
class ReferenceData:
    name: str | None
    timestamps: tuple[float, ...]
    values: tuple[float, ...]

    def __len__(self) -> int:
        return len(self.timestamps)


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


@dataclass(slots=True, frozen=True)
class CorrelationCandidate:
    arbitration_id: int
    start_bit: int
    bit_length: int
    pearson_r: float
    spearman_r: float
    sample_count: int
    lag_ms: float

    def to_payload(self) -> dict[str, object]:
        return {
            "arbitration_id": self.arbitration_id,
            "start_bit": self.start_bit,
            "bit_length": self.bit_length,
            "pearson_r": self.pearson_r,
            "spearman_r": self.spearman_r,
            "sample_count": self.sample_count,
            "lag_ms": self.lag_ms,
        }


@dataclass(slots=True, frozen=True)
class AnomalyCandidate:
    arbitration_id: int
    kind: str  # "timing" | "unknown-id" | "dropped-id"
    score: float
    z_score: float
    sample_count: int
    timestamp: float | None
    rationale: str
    z_score_capped: bool = False

    def to_payload(self) -> dict[str, object]:
        return {
            "arbitration_id": self.arbitration_id,
            "arbitration_id_hex": f"0x{self.arbitration_id:X}",
            "kind": self.kind,
            "score": self.score,
            "z_score": self.z_score,
            "z_score_capped": self.z_score_capped,
            "sample_count": self.sample_count,
            "timestamp": self.timestamp,
            "rationale": self.rationale,
        }


def counter_candidates(frames: list[CanFrame]) -> list[dict[str, object]]:
    annotations = j1939_annotations(frames)
    grouped_frames: dict[int, list[CanFrame]] = defaultdict(list)
    for frame in frames:
        if frame.is_remote_frame or frame.is_error_frame:
            continue
        annotation = annotations.get(frame.arbitration_id)
        if annotation is not None and annotation["j1939_transport"]:
            # TP.DT sequence numbers look like perfect counters; they are
            # protocol plumbing, not application counters (#407).
            continue
        grouped_frames[frame.arbitration_id].append(frame)

    candidates: list[CounterCandidate] = []
    for arbitration_id, group in grouped_frames.items():
        if len(group) < 4:
            continue
        max_payload_bits = min(len(frame.data) for frame in group) * 8
        for bit_length in (4, 8):
            for start_bit in range(0, max_payload_bits - bit_length + 1, 4):
                candidate = _counter_candidate_for_field(
                    group, arbitration_id, start_bit, bit_length
                )
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
    return [_annotated_payload(candidate.to_payload(), annotations) for candidate in candidates]


def entropy_candidates(frames: list[CanFrame]) -> list[dict[str, object]]:
    annotations = j1939_annotations(frames)
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
        annotation = annotations.get(arbitration_id)
        if annotation is not None and annotation["j1939_transport"]:
            rationale_parts.append("J1939 transport-protocol framing, not an application signal")
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
    return [_annotated_payload(candidate.to_payload(), annotations) for candidate in candidates]


def signal_analysis(frames: list[CanFrame]) -> dict[str, object]:
    annotations = j1939_annotations(frames)
    excluded_transport = j1939_transport_ids(frames)
    excluded_ids = {entry["arbitration_id"] for entry in excluded_transport}
    grouped_frames: dict[int, list[CanFrame]] = defaultdict(list)
    for frame in frames:
        if frame.arbitration_id in excluded_ids:
            continue
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
                candidate = _signal_candidate_for_field(
                    group, arbitration_id, start_bit, bit_length
                )
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
        "candidates": [
            _annotated_payload(candidate.to_payload(), annotations) for candidate in candidates
        ],
        "analysis_by_id": analysis_by_id,
        "low_sample_ids": low_sample_ids,
        "excluded_transport_ids": excluded_transport,
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
            (midrange_change_score * 0.55)
            + (span_ratio * 0.25)
            + (unique_ratio * 0.2)
            + bit_length_bonus,
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


def load_reference_series(path: str) -> ReferenceData:
    """Load and validate a reference series from a JSON or JSONL file.

    Accepts JSON (array of samples or object with 'name'+'samples') and JSONL (one sample per line).
    Each sample must have numeric 'timestamp' and 'value' fields.
    Raises ReferenceSeriesError on missing file, bad format, or fewer than 10 samples.
    """
    p = Path(path)
    if not p.exists():
        raise ReferenceSeriesError(
            code="INVALID_REFERENCE_FILE",
            message=f"Reference file not found: {path}",
            hint="Provide a valid path to a JSON or JSONL reference series file.",
        )
    try:
        content = p.read_text()
    except OSError as exc:
        raise ReferenceSeriesError(
            code="INVALID_REFERENCE_FILE",
            message=f"Cannot read reference file: {exc}",
            hint="Ensure the reference file is readable.",
        ) from exc

    name: str | None = None
    raw_samples: list[object] = []

    if path.endswith(".jsonl"):
        for line_no, line in enumerate(content.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                raw_samples.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ReferenceSeriesError(
                    code="INVALID_REFERENCE_FILE",
                    message=f"Invalid JSONL at line {line_no}: {exc}",
                    hint="Each line must be a valid JSON object with 'timestamp' and 'value' fields.",
                ) from exc
    else:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ReferenceSeriesError(
                code="INVALID_REFERENCE_FILE",
                message=f"Invalid JSON in reference file: {exc}",
                hint="The file must be valid JSON: an array of samples or an object with 'name' and 'samples'.",
            ) from exc
        if isinstance(data, list):
            raw_samples = data
        elif isinstance(data, dict):
            name = data.get("name")
            raw_samples = data.get("samples", [])
            if not isinstance(raw_samples, list):
                raise ReferenceSeriesError(
                    code="INVALID_REFERENCE_FILE",
                    message="Reference file 'samples' field must be an array.",
                    hint="Provide a 'samples' key with an array of {timestamp, value} objects.",
                )
        else:
            raise ReferenceSeriesError(
                code="INVALID_REFERENCE_FILE",
                message="Reference file must be a JSON array or an object with 'name' and 'samples'.",
                hint="Provide a JSON array of {timestamp, value} objects or an object with 'name' and 'samples'.",
            )

    if len(raw_samples) < 10:
        raise ReferenceSeriesError(
            code="INVALID_REFERENCE_FILE",
            message=f"Reference file contains {len(raw_samples)} samples; at least 10 are required.",
            hint="Provide a reference series with at least 10 timestamped numeric samples.",
        )

    timestamps: list[float] = []
    values: list[float] = []
    for i, sample in enumerate(raw_samples):
        if not isinstance(sample, dict):
            raise ReferenceSeriesError(
                code="INVALID_REFERENCE_FILE",
                message=f"Sample {i} is not a JSON object.",
                hint="Each sample must be a JSON object with 'timestamp' and 'value' fields.",
            )
        if "timestamp" not in sample or "value" not in sample:
            raise ReferenceSeriesError(
                code="INVALID_REFERENCE_FILE",
                message=f"Sample {i} is missing 'timestamp' or 'value'.",
                hint="Each sample must have 'timestamp' (number) and 'value' (number) fields.",
            )
        try:
            t = float(sample["timestamp"])
            v = float(sample["value"])
        except (TypeError, ValueError) as exc:
            raise ReferenceSeriesError(
                code="INVALID_REFERENCE_FILE",
                message=f"Sample {i} has non-numeric 'timestamp' or 'value': {exc}",
                hint="'timestamp' and 'value' must be numeric.",
            ) from exc
        if not isfinite(t) or not isfinite(v):
            raise ReferenceSeriesError(
                code="INVALID_REFERENCE_FILE",
                message=f"Sample {i} has non-finite 'timestamp' or 'value' ({t!r}, {v!r}).",
                hint="'timestamp' and 'value' must be finite numbers (NaN and Infinity are not accepted).",
            )
        timestamps.append(t)
        values.append(v)

    pairs = sorted(zip(timestamps, values))
    return ReferenceData(
        name=name,
        timestamps=tuple(p[0] for p in pairs),
        values=tuple(p[1] for p in pairs),
    )


def correlate_candidates(frames: list[CanFrame], ref: ReferenceData) -> dict[str, object]:
    """Correlate candidate bit fields against a reference time series.

    Returns a ranked list of candidates with Pearson r, Spearman r, sample count, and optimal lag_ms.
    Raises ReferenceSeriesError with INSUFFICIENT_OVERLAP if fewer than 10 capture frames overlap
    with the reference time range.
    """
    ref_ts = list(ref.timestamps)
    ref_vs = list(ref.values)
    ref_min = ref_ts[0]
    ref_max = ref_ts[-1]

    eligible = [
        frame
        for frame in frames
        if not frame.is_remote_frame
        and not frame.is_error_frame
        and frame.data
        and frame.timestamp is not None
        and ref_min <= frame.timestamp <= ref_max
    ]
    if len(eligible) < 10:
        raise ReferenceSeriesError(
            code="INSUFFICIENT_OVERLAP",
            message=(
                f"Only {len(eligible)} capture frame(s) overlap with the reference series time range "
                f"[{ref_min}, {ref_max}]; at least 10 are required."
            ),
            hint="Ensure the capture and reference series share a sufficient time range.",
        )

    grouped: dict[int, list[CanFrame]] = defaultdict(list)
    for frame in eligible:
        grouped[frame.arbitration_id].append(frame)

    lag_candidates_ms = [0]
    for _step in range(50, 501, 50):
        lag_candidates_ms.append(_step)
        lag_candidates_ms.append(-_step)

    candidates: list[CorrelationCandidate] = []
    for arbitration_id, group in grouped.items():
        max_payload_bits = min(len(frame.data) for frame in group) * 8
        for bit_length in (4, 8, 16):
            for start_bit in range(0, max_payload_bits - bit_length + 1, bit_length):
                candidate = _correlation_candidate_for_field(
                    group,
                    arbitration_id,
                    start_bit,
                    bit_length,
                    ref_ts,
                    ref_vs,
                    lag_candidates_ms,
                )
                if candidate is not None:
                    candidates.append(candidate)

    candidates.sort(key=lambda c: (-abs(c.pearson_r), c.arbitration_id, c.start_bit, c.bit_length))
    return {
        "candidate_count": len(candidates),
        "candidates": [c.to_payload() for c in candidates],
    }


def _correlation_candidate_for_field(
    frames: list[CanFrame],
    arbitration_id: int,
    start_bit: int,
    bit_length: int,
    ref_ts: list[float],
    ref_vs: list[float],
    lag_candidates_ms: list[int],
) -> CorrelationCandidate | None:
    frame_ts = [frame.timestamp for frame in frames]  # already filtered: all not None
    field_vals = [float(_extract_field_value(frame, start_bit, bit_length)) for frame in frames]

    best_lag_ms = 0
    best_pearson = 0.0

    for lag_ms in lag_candidates_ms:
        lag_s = lag_ms / 1000.0
        x: list[float] = []
        y: list[float] = []
        for fv, ft in zip(field_vals, frame_ts):
            ref_val = _interpolate_reference(ref_ts, ref_vs, ft + lag_s)  # type: ignore[arg-type]
            if ref_val is not None:
                x.append(fv)
                y.append(ref_val)
        if len(x) < 10:
            continue
        try:
            r = max(-1.0, min(1.0, correlation(x, y)))
        except StatisticsError:
            continue
        if abs(r) > abs(best_pearson):
            best_pearson = r
            best_lag_ms = lag_ms

    if best_pearson == 0.0:
        return None

    lag_s = best_lag_ms / 1000.0
    final_x: list[float] = []
    final_y: list[float] = []
    for fv, ft in zip(field_vals, frame_ts):
        ref_val = _interpolate_reference(ref_ts, ref_vs, ft + lag_s)  # type: ignore[arg-type]
        if ref_val is not None:
            final_x.append(fv)
            final_y.append(ref_val)

    if len(final_x) < 10:
        return None

    try:
        pearson_r = round(max(-1.0, min(1.0, correlation(final_x, final_y))), 4)
    except StatisticsError:
        return None

    try:
        spearman_r = round(max(-1.0, min(1.0, correlation(_rank(final_x), _rank(final_y)))), 4)
    except StatisticsError:
        spearman_r = 0.0

    return CorrelationCandidate(
        arbitration_id=arbitration_id,
        start_bit=start_bit,
        bit_length=bit_length,
        pearson_r=pearson_r,
        spearman_r=spearman_r,
        sample_count=len(final_x),
        lag_ms=float(best_lag_ms),
    )


def _interpolate_reference(
    ref_ts: list[float], ref_vs: list[float], query_t: float
) -> float | None:
    """Linear interpolation of reference at query_t; returns None if outside reference range."""
    if query_t < ref_ts[0] or query_t > ref_ts[-1]:
        return None
    lo, hi = 0, len(ref_ts) - 1
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if ref_ts[mid] <= query_t:
            lo = mid
        else:
            hi = mid
    t0, t1 = ref_ts[lo], ref_ts[hi]
    v0, v1 = ref_vs[lo], ref_vs[hi]
    if t1 == t0:
        return float(v0)
    return float(v0 + (v1 - v0) * (query_t - t0) / (t1 - t0))


def _rank(values: list[float]) -> list[float]:
    """Compute average ranks for Spearman r (handles ties with average rank)."""
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n and values[order[j]] == values[order[i]]:
            j += 1
        avg = (i + j - 1) / 2.0 + 1.0
        for k in range(i, j):
            ranks[order[k]] = avg
        i = j
    return ranks


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


# --- Anomaly detection -----------------------------------------------------

_ANOMALY_MIN_GAPS = 3
# Without a separate baseline, statistics learned from an id's own (possibly
# bursty) traffic need more evidence before timing deviations are scored;
# sparse ids are reported as low-rate instead of ranked as anomalies (#408).
_ANOMALY_SELF_MIN_GAPS = 10
# Reported z-scores are capped: beyond this the magnitude is an artifact of a
# near-zero spread estimate, not a meaningful number of standard deviations.
_ANOMALY_Z_CAP = 100.0
_ANOMALY_DEFAULT_Z = 3.0
# Robust coefficient of variation (scaled MAD over the median inter-frame gap)
# above which an id is treated as event-driven rather than cyclic, so its
# irregular timing is not flagged. Cyclic buses jitter well under this; event
# traffic sits far above it.
_ANOMALY_DEFAULT_CV_MAX = 0.5
# When a DBC declares a cycle time but the capture lacks the jitter to estimate
# a spread, allow deviations up to this fraction of the declared period.
_ANOMALY_PERIOD_TOLERANCE = 0.1


def _id_timestamps(frames: list[CanFrame]) -> dict[int, list[float]]:
    """Group ordered timestamps per arbitration id, skipping remote/error frames."""
    grouped: dict[int, list[float]] = defaultdict(list)
    for frame in frames:
        if frame.is_remote_frame or frame.is_error_frame:
            continue
        grouped[frame.arbitration_id].append(float(frame.timestamp))
    for timestamps in grouped.values():
        timestamps.sort()
    return grouped


def _inter_frame_gaps(timestamps: list[float]) -> list[float]:
    return [b - a for a, b in zip(timestamps, timestamps[1:]) if b - a >= 0]


def _robust_gap_statistics(gaps: list[float]) -> tuple[float, float]:
    """Return (median, MAD-derived spread) of a gap list.

    The median absolute deviation is scaled by 1.4826 so it approximates a
    standard deviation for normally distributed jitter. Median and MAD are used
    instead of mean and stdev because they are not corrupted by a minority of
    outlier gaps: a single timing glitch in an otherwise cyclic stream cannot
    inflate the spread and mask itself, nor push a cyclic id over the event gate.
    """
    center = median(gaps)
    mad = median([abs(gap - center) for gap in gaps])
    return center, 1.4826 * mad


def _classify_cyclic(
    arb_id: int,
    ref_gaps: list[float],
    dbc_timing: dict[int, dict[str, Any]] | None,
    cv_max: float,
    min_gaps: int = _ANOMALY_MIN_GAPS,
) -> dict[str, Any]:
    """Decide whether an id's timing should be checked, and how.

    A DBC entry (cycle time / send type) is authoritative when present; otherwise
    a robust coefficient of variation (scaled MAD over median) classifies the id.
    Ids with fewer than ``min_gaps`` reference gaps are not timing-scored.
    Returns a record with ``cyclic`` (bool), ``source``
    (``dbc`` | ``cv`` | ``insufficient-samples``), the expected gap ``center`` and
    ``spread`` to score against, and the robust ``cv``.
    """
    record: dict[str, Any] = {
        "arbitration_id": arb_id,
        "arbitration_id_hex": f"0x{arb_id:X}",
        "cyclic": False,
        "source": None,
        "cv": None,
        "gap_count": len(ref_gaps),
    }

    center = spread = robust_cv = None
    if len(ref_gaps) >= _ANOMALY_MIN_GAPS:
        center, spread = _robust_gap_statistics(ref_gaps)
        if center > 0:
            robust_cv = spread / center
            record["cv"] = round(robust_cv, 4)

    entry = (dbc_timing or {}).get(arb_id)
    if entry is not None:
        send_type = (entry.get("send_type") or "").lower()
        cycle_time_ms = entry.get("cycle_time_ms")
        record["source"] = "dbc"
        record["send_type"] = entry.get("send_type")
        record["cycle_time_ms"] = cycle_time_ms
        # An explicit non-cyclic send type, or the absence of any cycle time,
        # marks the message as event-driven: skip timing analysis.
        is_event = ("cyclic" not in send_type and send_type != "") or not cycle_time_ms
        if is_event:
            record["cyclic"] = False
            return record
        period = cycle_time_ms / 1000.0
        # Score against the declared period; use the robust observed spread when
        # meaningfully large, else floor it to a fixed fraction of the period.
        period_spread = max(spread or 0.0, period * _ANOMALY_PERIOD_TOLERANCE)
        record.update({"cyclic": True, "center": period, "spread": period_spread})
        return record

    # No DBC: fall back to the robust coefficient-of-variation guard.
    if robust_cv is None:
        record["source"] = "insufficient-samples"
        return record
    record["source"] = "cv"
    if robust_cv > cv_max:
        record["cyclic"] = False
        return record
    # The id looks cyclic, but a bursty/sparse stream can also produce a tight
    # median gap. Require enough evidence before scoring its timing; otherwise
    # report it as a low-rate id instead of ranking artifact deviations (#408).
    if len(ref_gaps) < min_gaps:
        record["source"] = "low-sample"
        record["low_rate"] = True
        return record
    # Floor the spread to a fraction of the period so a near-perfectly regular
    # baseline (MAD ~ 0, modulo float noise) still yields a sane finite z-score
    # for an outlier rather than dividing by an effectively-zero spread.
    scoring_spread = max(spread, center * _ANOMALY_PERIOD_TOLERANCE)
    record.update({"cyclic": True, "center": center, "spread": scoring_spread})
    return record


def anomaly_candidates(
    frames: list[CanFrame],
    *,
    baseline: list[CanFrame] | None = None,
    z_threshold: float = _ANOMALY_DEFAULT_Z,
    cv_max: float = _ANOMALY_DEFAULT_CV_MAX,
    dbc_timing: dict[int, dict[str, Any]] | None = None,
    min_samples: int | None = None,
) -> dict[str, Any]:
    """Flag inter-frame-timing outliers and unexpected/dropped arbitration IDs.

    With ``baseline``, per-id gap statistics and the expected id set are learned
    from the reference capture and the input is scored against them. Without a
    baseline, the input is scored against its own learned statistics
    (self-consistency), id-presence anomalies are not emitted, and a higher
    minimum sample count applies so sparse/bursty ids are reported as low-rate
    instead of being ranked on artifact z-scores (#408). Reported z-scores are
    capped at ±100σ.

    Only ids judged *cyclic* are timing-checked, so event-based and event-periodic
    messages are not falsely flagged. Classification uses the DBC ``cycle_time`` /
    send type when ``dbc_timing`` is supplied (authoritative), and otherwise the
    observed coefficient of variation against ``cv_max``.
    """
    input_ts = _id_timestamps(frames)
    baseline_ts = _id_timestamps(baseline) if baseline is not None else input_ts
    has_baseline = baseline is not None
    if min_samples is None:
        min_samples = _ANOMALY_MIN_GAPS if has_baseline else _ANOMALY_SELF_MIN_GAPS
    annotations = j1939_annotations(frames)

    candidates: list[AnomalyCandidate] = []
    classifications: list[dict[str, Any]] = []

    # Timing anomalies: the single most-deviant inter-frame gap per id.
    for arb_id, timestamps in sorted(input_ts.items()):
        ref_gaps = _inter_frame_gaps(baseline_ts.get(arb_id, []))
        classification = _classify_cyclic(
            arb_id, ref_gaps, dbc_timing, cv_max, min_gaps=min_samples
        )
        annotation = annotations.get(arb_id)
        if annotation is not None:
            classification.update(annotation)
        classifications.append(classification)
        if not classification["cyclic"]:
            continue
        center = classification["center"]
        spread = classification["spread"]
        observed_gaps = _inter_frame_gaps(timestamps)
        if not observed_gaps:
            continue
        # Locate the gap with the largest absolute z-score against the baseline.
        worst_z = 0.0
        worst_gap = 0.0
        worst_index = 0
        for index, gap in enumerate(observed_gaps):
            z = (gap - center) / spread
            if abs(z) > abs(worst_z):
                worst_z, worst_gap, worst_index = z, gap, index
        if abs(worst_z) < z_threshold:
            continue
        z_capped = abs(worst_z) > _ANOMALY_Z_CAP
        if z_capped:
            worst_z = _ANOMALY_Z_CAP if worst_z > 0 else -_ANOMALY_Z_CAP
        # The gap ends at the second timestamp of the pair.
        timestamp = timestamps[worst_index + 1]
        source_note = (
            "declared cycle time" if classification["source"] == "dbc" else "baseline median"
        )
        deviation_note = (
            f"more than {round(_ANOMALY_Z_CAP)}σ (capped)"
            if z_capped
            else f"{round(abs(worst_z), 2)}σ"
        )
        candidates.append(
            AnomalyCandidate(
                arbitration_id=arb_id,
                kind="timing",
                score=round(abs(worst_z), 3),
                z_score=round(worst_z, 3),
                z_score_capped=z_capped,
                sample_count=len(observed_gaps),
                timestamp=timestamp,
                rationale=(
                    f"inter-frame gap {round(worst_gap, 6)}s deviates "
                    f"{deviation_note} from {source_note} {round(center, 6)}s"
                ),
            )
        )

    # Presence anomalies only make sense against a separate baseline.
    if has_baseline:
        baseline_ids = set(baseline_ts)
        input_ids = set(input_ts)
        for arb_id in sorted(input_ids - baseline_ids):
            count = len(input_ts[arb_id])
            candidates.append(
                AnomalyCandidate(
                    arbitration_id=arb_id,
                    kind="unknown-id",
                    score=float(count),
                    z_score=0.0,
                    sample_count=count,
                    timestamp=input_ts[arb_id][0],
                    rationale=f"arbitration id absent from baseline ({count} frames observed)",
                )
            )
        for arb_id in sorted(baseline_ids - input_ids):
            count = len(baseline_ts[arb_id])
            candidates.append(
                AnomalyCandidate(
                    arbitration_id=arb_id,
                    kind="dropped-id",
                    score=float(count),
                    z_score=0.0,
                    sample_count=0,
                    timestamp=None,
                    rationale=f"baseline id missing from input ({count} baseline frames)",
                )
            )

    candidates.sort(
        key=lambda candidate: (
            -candidate.score,
            candidate.kind,
            candidate.arbitration_id,
        )
    )
    cyclic_ids = sorted(c["arbitration_id"] for c in classifications if c["cyclic"])
    event_ids = sorted(
        c["arbitration_id"]
        for c in classifications
        if not c["cyclic"] and c["source"] != "insufficient-samples"
    )
    low_rate_ids = sorted(
        c["arbitration_id"]
        for c in classifications
        if c["source"] in {"insufficient-samples", "low-sample"}
    )
    return {
        "candidate_count": len(candidates),
        "candidates": [
            _annotated_payload(candidate.to_payload(), annotations) for candidate in candidates
        ],
        "mode": "baseline" if has_baseline else "self-consistency",
        "z_threshold": z_threshold,
        "cv_max": cv_max,
        "min_samples": min_samples,
        "timing_source": "dbc" if dbc_timing else "observed",
        "cyclic_ids": cyclic_ids,
        "event_ids": event_ids,
        "low_rate_ids": low_rate_ids,
        "classifications": classifications,
    }
