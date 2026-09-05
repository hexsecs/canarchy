"""Cross-capture comparison for plain (non-J1939-specific) CAN captures.

Bundles per-arbitration-id frame-count/rate, cycle-time, and payload-entropy
deltas between two or more captures into a single envelope, mirroring the shape
of ``j1939 compare`` for generic CAN traffic so an agent can answer "what
changed between these captures?" in a single call instead of stitching together
``stats``, ``re anomalies``, and ``re corpus`` by hand (#458).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from canarchy.corpus import _mean_gap_ms, _stddev
from canarchy.models import CanFrame
from canarchy.reverse_engineering import (
    _capture_span_seconds,
    _group_mean_byte_entropy,
    j1939_annotation,
)
from canarchy.transport import LocalTransport

# Thresholds mirror the anomaly detector (#457) so the two tools agree on what
# counts as a rate drop/spike, an entropy collapse, or timing drift.
_RATE_DROP = 0.5
_RATE_SPIKE = 2.0
_ENTROPY_DROP = 0.5
_ENTROPY_MIN_BASELINE = 1.0
_TIMING_DRIFT = 0.2


def _index_capture(frames: list[CanFrame]) -> dict[tuple[int, bool], list[CanFrame]]:
    """Group data frames by numeric ID and identifier type (skip remote/error)."""
    id_map: dict[tuple[int, bool], list[CanFrame]] = defaultdict(list)
    for frame in frames:
        if not frame.is_remote_frame and not frame.is_error_frame:
            id_map[(frame.arbitration_id, frame.is_extended_id)].append(frame)
    return dict(id_map)


def _identifier_payloads(identifiers: list[tuple[int, bool]]) -> list[dict[str, Any]]:
    return [
        {"arbitration_id": arb_id, "is_extended_id": extended}
        for arb_id, extended in sorted(identifiers)
    ]


def _change_score(
    rate_ratio: list[float | None],
    entropy_delta: list[float | None],
    drift_ratio: float | None,
    flags: list[str],
    others: list[int],
) -> float:
    """Rank an id by how much it diverges from the baseline capture."""
    score = 0.0
    rate_dev = [abs(1.0 - rate_ratio[i]) for i in others if rate_ratio[i] is not None]
    score += max(rate_dev, default=0.0)
    entropy_dev = [abs(entropy_delta[i]) for i in others if entropy_delta[i] is not None]
    # Normalise entropy (0..8 bits) onto roughly the same scale as the rate term.
    score += max(entropy_dev, default=0.0) / 8.0
    if drift_ratio is not None:
        score += drift_ratio
    if "new-vs-baseline" in flags or "dropped-vs-baseline" in flags:
        score += 1.0
    return round(score, 4)


def compare_captures(
    capture_files: list[str],
    *,
    baseline: str | None = None,
    offset: int = 0,
    max_frames: int | None = None,
    seconds: float | None = None,
    top: int | None = 20,
) -> dict[str, Any]:
    """Compare captures per (arbitration_id, is_extended_id) against a baseline.

    Returns, for each id, per-file frame counts, frame rates, mean inter-frame
    gaps, and mean per-byte payload entropy, plus deltas/ratios versus the
    baseline file and a cross-capture cycle-time drift ratio (reusing the corpus
    drift logic). Entries are ranked by a combined change score and capped at
    ``top`` (use 0 / None for no cap); ``id_count`` counts distinct ID/type pairs.
    Numeric summary lists are deduplicated compatibility views; the parallel
    ``*_identifiers`` lists preserve type and include entries beyond ``top``.
    """
    transport = LocalTransport()
    per_capture: list[dict[tuple[int, bool], list[CanFrame]]] = []
    spans: list[float | None] = []
    for path in capture_files:
        frames = transport.frames_from_file(
            path, offset=offset, max_frames=max_frames, seconds=seconds
        )
        per_capture.append(_index_capture(frames))
        spans.append(_capture_span_seconds(frames))

    baseline_index = 0
    if baseline is not None and baseline in capture_files:
        baseline_index = capture_files.index(baseline)

    all_ids = sorted({arb_id for idx in per_capture for arb_id in idx})
    others = [i for i in range(len(per_capture)) if i != baseline_index]

    comparison: list[dict[str, Any]] = []
    new_ids: list[tuple[int, bool]] = []
    dropped_ids: list[tuple[int, bool]] = []
    rate_drop_ids: list[tuple[int, bool]] = []
    rate_spike_ids: list[tuple[int, bool]] = []
    entropy_collapse_ids: list[tuple[int, bool]] = []
    timing_drift_ids: list[tuple[int, bool]] = []

    for identifier in all_ids:
        arb_id, is_extended_id = identifier
        frame_counts = [len(idx.get(identifier, [])) for idx in per_capture]
        rates: list[float | None] = []
        gaps: list[float | None] = []
        entropies: list[float | None] = []
        for index, idx in enumerate(per_capture):
            group = idx.get(identifier, [])
            span = spans[index]
            rates.append(round(len(group) / span, 4) if group and span else None)
            timestamps = [f.timestamp for f in group if f.timestamp is not None]
            mean_gap = _mean_gap_ms(timestamps) if len(timestamps) >= 2 else None
            gaps.append(round(mean_gap, 4) if mean_gap is not None else None)
            mean_entropy = _group_mean_byte_entropy(group)
            entropies.append(round(mean_entropy, 4) if mean_entropy is not None else None)

        present = [count > 0 for count in frame_counts]
        base_count = frame_counts[baseline_index]
        base_rate = rates[baseline_index]
        base_entropy = entropies[baseline_index]
        present_in_baseline = present[baseline_index]

        frame_count_delta = [count - base_count for count in frame_counts]
        rate_ratio: list[float | None] = [
            round(rate / base_rate, 4) if rate is not None and base_rate else None for rate in rates
        ]
        entropy_delta: list[float | None] = [
            round(entropy - base_entropy, 4)
            if entropy is not None and base_entropy is not None
            else None
            for entropy in entropies
        ]

        # Cross-capture cycle-time drift, reusing the corpus drift formulation.
        valid_gaps = [gap for gap in gaps if gap is not None]
        drift_ratio: float | None = None
        if len(valid_gaps) >= 2:
            mean_of_means = sum(valid_gaps) / len(valid_gaps)
            drift_ratio = round(_stddev(valid_gaps) / mean_of_means, 4) if mean_of_means else 0.0

        flags: list[str] = []
        if not present_in_baseline and any(present):
            flags.append("new-vs-baseline")
            new_ids.append(identifier)
        if present_in_baseline and not all(present):
            flags.append("dropped-vs-baseline")
            dropped_ids.append(identifier)
        if any(rate_ratio[i] is not None and rate_ratio[i] <= _RATE_DROP for i in others):
            flags.append("rate-drop")
            rate_drop_ids.append(identifier)
        if any(rate_ratio[i] is not None and rate_ratio[i] >= _RATE_SPIKE for i in others):
            flags.append("rate-spike")
            rate_spike_ids.append(identifier)
        if base_entropy is not None and base_entropy >= _ENTROPY_MIN_BASELINE:
            if any(
                entropies[i] is not None and (entropies[i] / base_entropy) <= _ENTROPY_DROP
                for i in others
            ):
                flags.append("entropy-collapse")
                entropy_collapse_ids.append(identifier)
        if drift_ratio is not None and drift_ratio > _TIMING_DRIFT:
            flags.append("timing-drift")
            timing_drift_ids.append(identifier)

        entry: dict[str, Any] = {
            "arbitration_id": arb_id,
            "arbitration_id_hex": f"0x{arb_id:X}",
            "is_extended_id": is_extended_id,
            "present": present,
            "present_in_baseline": present_in_baseline,
            "frame_counts": frame_counts,
            "frame_count_delta": frame_count_delta,
            "rates_hz": rates,
            "rate_ratio": rate_ratio,
            "mean_gap_ms": gaps,
            "cycle_time_drift_ratio": drift_ratio,
            "mean_byte_entropy": entropies,
            "entropy_delta": entropy_delta,
            "change_score": _change_score(rate_ratio, entropy_delta, drift_ratio, flags, others),
            "flags": flags,
        }
        if is_extended_id:
            annotation = j1939_annotation(arb_id)
            if annotation is not None:
                entry.update(annotation)
        comparison.append(entry)

    total = len(comparison)
    comparison.sort(
        key=lambda item: (-item["change_score"], item["arbitration_id"], item["is_extended_id"])
    )
    shown = comparison if top is None or top <= 0 else comparison[:top]

    return {
        "files": list(capture_files),
        "file_count": len(capture_files),
        "baseline": capture_files[baseline_index] if capture_files else None,
        "baseline_index": baseline_index,
        "id_count": total,
        "returned_count": len(shown),
        "top": top,
        "comparison": shown,
        "summary": {
            "unique_ids": total,
            "new_ids": sorted({arb_id for arb_id, _ in new_ids}),
            "new_identifiers": _identifier_payloads(new_ids),
            "dropped_ids": sorted({arb_id for arb_id, _ in dropped_ids}),
            "dropped_identifiers": _identifier_payloads(dropped_ids),
            "rate_drop_ids": sorted({arb_id for arb_id, _ in rate_drop_ids}),
            "rate_drop_identifiers": _identifier_payloads(rate_drop_ids),
            "rate_spike_ids": sorted({arb_id for arb_id, _ in rate_spike_ids}),
            "rate_spike_identifiers": _identifier_payloads(rate_spike_ids),
            "entropy_collapse_ids": sorted({arb_id for arb_id, _ in entropy_collapse_ids}),
            "entropy_collapse_identifiers": _identifier_payloads(entropy_collapse_ids),
            "timing_drift_ids": sorted({arb_id for arb_id, _ in timing_drift_ids}),
            "timing_drift_identifiers": _identifier_payloads(timing_drift_ids),
        },
    }
