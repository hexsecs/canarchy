"""Cross-capture corpus analysis."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from canarchy.models import CanFrame
from canarchy.transport import LocalTransport


def _mean_gap_ms(timestamps: list[float]) -> float | None:
    if len(timestamps) < 2:
        return None
    gaps = [(timestamps[i + 1] - timestamps[i]) * 1000.0 for i in range(len(timestamps) - 1)]
    return sum(gaps) / len(gaps)


def _stddev(values: list[float]) -> float:
    if len(values) <= 1:
        return 0.0
    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    return math.sqrt(variance)


def _byte_cv(frames_for_id: list[CanFrame]) -> list[float]:
    if not frames_for_id:
        return []
    byte_count = max(len(f.data) for f in frames_for_id)
    cvs: list[float] = []
    for pos in range(byte_count):
        vals = [f.data[pos] for f in frames_for_id if pos < len(f.data)]
        if not vals:
            cvs.append(0.0)
            continue
        mean = sum(vals) / len(vals)
        std = _stddev([float(v) for v in vals])
        cv = std / mean if mean != 0.0 else (0.0 if std == 0.0 else float("inf"))
        cvs.append(cv)
    return cvs


def corpus_analysis(
    capture_files: list[str],
    *,
    offset: int = 0,
    max_frames: int | None = None,
    seconds: float | None = None,
) -> dict[str, Any]:
    if not capture_files:
        return {
            "captures": [],
            "capture_count": 0,
            "total_frames": 0,
            "coverage": [],
            "id_set_changes": {
                "always_present": [],
                "sometimes_present": [],
                "only_in_one": [],
            },
            "cycle_time_drift": [],
            "signal_stability": [],
            "summary": {
                "unique_ids": 0,
                "stable_ids": 0,
                "drifting_ids": 0,
                "new_ids": 0,
            },
        }

    transport = LocalTransport()

    per_capture_index: list[dict[int, list[CanFrame]]] = []
    total_frames = 0

    for path in capture_files:
        bounded = transport.frames_from_file(
            path, offset=offset, max_frames=max_frames, seconds=seconds
        )
        id_map: dict[int, list[CanFrame]] = defaultdict(list)
        for frame in bounded:
            if not frame.is_remote_frame and not frame.is_error_frame:
                id_map[frame.arbitration_id].append(frame)
        per_capture_index.append(dict(id_map))
        total_frames += sum(len(v) for v in id_map.values())

    all_ids: set[int] = set()
    for idx in per_capture_index:
        all_ids.update(idx.keys())

    capture_count = len(capture_files)

    coverage: list[dict[str, Any]] = []
    for arb_id in sorted(all_ids):
        counts = [len(idx.get(arb_id, [])) for idx in per_capture_index]
        present = sum(1 for c in counts if c > 0)
        coverage.append(
            {
                "arbitration_id": arb_id,
                "arbitration_id_hex": f"0x{arb_id:X}",
                "frame_counts": counts,
                "capture_count": present,
                "present_in_all": present == capture_count,
            }
        )

    always_present = sorted(
        arb_id for arb_id in all_ids if all(arb_id in idx for idx in per_capture_index)
    )
    sometimes_present = sorted(
        arb_id
        for arb_id in all_ids
        if sum(1 for idx in per_capture_index if arb_id in idx) > 1 and arb_id not in always_present
    )
    only_in_one = sorted(
        arb_id for arb_id in all_ids if sum(1 for idx in per_capture_index if arb_id in idx) == 1
    )

    cycle_time_drift: list[dict[str, Any]] = []
    if capture_count >= 2:
        for arb_id in sorted(all_ids):
            per_capture_means: list[float | None] = []
            for idx in per_capture_index:
                frames_here = idx.get(arb_id, [])
                if len(frames_here) < 4:
                    per_capture_means.append(None)
                    continue
                timestamps = [f.timestamp for f in frames_here if f.timestamp is not None]
                per_capture_means.append(_mean_gap_ms(timestamps) if len(timestamps) >= 2 else None)

            valid_means = [m for m in per_capture_means if m is not None]
            if len(valid_means) < 2:
                continue

            std = _stddev(valid_means)
            mean_of_means = sum(valid_means) / len(valid_means)
            drift_ratio = std / mean_of_means if mean_of_means != 0.0 else 0.0

            cycle_time_drift.append(
                {
                    "arbitration_id": arb_id,
                    "arbitration_id_hex": f"0x{arb_id:X}",
                    "per_capture_mean_ms": per_capture_means,
                    "cross_capture_stddev_ms": std,
                    "drift_ratio": drift_ratio,
                }
            )

    all_frames_by_id: dict[int, list[CanFrame]] = defaultdict(list)
    for idx in per_capture_index:
        for arb_id, frames in idx.items():
            all_frames_by_id[arb_id].extend(frames)

    signal_stability: list[dict[str, Any]] = []
    for arb_id in sorted(all_ids):
        frames_for_id = all_frames_by_id.get(arb_id, [])
        if not frames_for_id:
            continue
        cvs = _byte_cv(frames_for_id)
        byte_count = len(cvs)
        if byte_count == 0:
            continue
        stable_bytes = sum(1 for cv in cvs if cv < 0.1)
        varying_bytes = byte_count - stable_bytes
        stability_score = stable_bytes / byte_count

        signal_stability.append(
            {
                "arbitration_id": arb_id,
                "arbitration_id_hex": f"0x{arb_id:X}",
                "byte_count": byte_count,
                "stable_bytes": stable_bytes,
                "varying_bytes": varying_bytes,
                "stability_score": stability_score,
            }
        )

    stable_ids = sum(1 for entry in signal_stability if entry["stability_score"] == 1.0)
    drifting_ids = sum(1 for entry in cycle_time_drift if entry["drift_ratio"] > 0.2)
    new_ids = len(sometimes_present) + len(only_in_one)

    return {
        "captures": list(capture_files),
        "capture_count": capture_count,
        "total_frames": total_frames,
        "coverage": coverage,
        "id_set_changes": {
            "always_present": always_present,
            "sometimes_present": sometimes_present,
            "only_in_one": only_in_one,
        },
        "cycle_time_drift": cycle_time_drift,
        "signal_stability": signal_stability,
        "summary": {
            "unique_ids": len(all_ids),
            "stable_ids": stable_ids,
            "drifting_ids": drifting_ids,
            "new_ids": new_ids,
        },
    }
