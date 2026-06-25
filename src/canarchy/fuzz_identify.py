"""Fuzz-replay culprit identification via deterministic bisection.

CANarchy can replay and fuzz frames, but it lacked CaringCaribou's ``fuzzer
identify`` human-in-the-loop workflow: replay a fuzz log and narrow down the
specific frame that produced an observed effect. This module implements that as
a deterministic, automation-friendly bisection — the operator marks each
replayed window as ``effect`` / ``no-effect`` (non-interactively, via flags or a
file) and the engine narrows the candidate set toward a single culprit frame.

The narrowing engine (:func:`narrow`) is pure and stateless: given the frame
count and the observations recorded so far, it returns the current candidate
range, the next window to replay, and a resolved culprit once the search
converges. A single ``fuzz identify`` invocation therefore runs one round —
optionally replaying the next window on a live bus — and reports the state, so
the operator records an observation and re-invokes. With a complete observation
sequence supplied up front it resolves the culprit with no transmission at all,
which is exactly what the tests exercise.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from canarchy.models import CanFrame
from canarchy.transport import load_candump_file


class FuzzIdentifyError(Exception):
    """Raised for invalid logs / observations before any replay."""

    def __init__(self, code: str, message: str, hint: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


_TRUE_TOKENS = frozenset({"effect", "true", "yes", "1", "reproduced", "hit"})
_FALSE_TOKENS = frozenset({"no-effect", "no_effect", "none", "false", "no", "0", "miss"})


def parse_observation(value: object) -> bool:
    """Coerce an observation token to ``True`` (effect) or ``False`` (no effect)."""
    if isinstance(value, bool):
        return value
    token = str(value).strip().lower()
    if token in _TRUE_TOKENS:
        return True
    if token in _FALSE_TOKENS:
        return False
    raise FuzzIdentifyError(
        code="FUZZ_IDENTIFY_INVALID_OBSERVATION",
        message=f"Observation {value!r} is not 'effect' or 'no-effect'.",
        hint="Use effect/no-effect (or true/false).",
    )


def load_observations_file(path: str) -> list[bool]:
    try:
        raw = Path(path).read_text()
    except OSError as exc:
        raise FuzzIdentifyError(
            code="FUZZ_IDENTIFY_OBSERVATIONS_UNAVAILABLE",
            message=f"Could not read observations file {path!r}: {exc}.",
            hint="Check the path and permissions.",
        ) from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FuzzIdentifyError(
            code="FUZZ_IDENTIFY_INVALID_OBSERVATIONS",
            message=f"Observations file {path!r} is not valid JSON: {exc}.",
            hint='Provide a JSON array like ["no-effect", "effect"].',
        ) from exc
    if not isinstance(parsed, list):
        raise FuzzIdentifyError(
            code="FUZZ_IDENTIFY_INVALID_OBSERVATIONS",
            message="Observations file must contain a JSON array.",
            hint='Provide a JSON array like ["no-effect", "effect"].',
        )
    return [parse_observation(entry) for entry in parsed]


def _frame_from_json(obj: dict) -> CanFrame | None:
    # Accept a bare frame object, a FrameEvent (`{"payload": {"frame": {...}}}`,
    # as emitted by `canarchy ... --jsonl`), or a `{"payload": {...}}` wrapper.
    source = obj
    payload = source.get("payload")
    if isinstance(payload, dict):
        source = payload
    inner_frame = source.get("frame")
    if isinstance(inner_frame, dict):
        source = inner_frame
    if "arbitration_id" not in source or "data" not in source:
        return None
    try:
        arbitration_id = int(source["arbitration_id"])
        data = bytes.fromhex(str(source["data"]))
    except (ValueError, TypeError):
        return None
    return CanFrame(
        arbitration_id=arbitration_id,
        data=data,
        is_extended_id=bool(source.get("is_extended_id", arbitration_id > 0x7FF)),
    )


def load_identify_frames(path: str) -> list[CanFrame]:
    """Load frames from a candump capture or a JSONL fuzz log / replay plan."""
    text_path = Path(path)
    if not text_path.exists():
        raise FuzzIdentifyError(
            code="FUZZ_IDENTIFY_LOG_UNAVAILABLE",
            message=f"Fuzz log {path!r} does not exist.",
            hint="Pass a candump capture or a JSONL fuzz log / replay plan.",
        )
    try:
        raw = text_path.read_text()
    except OSError as exc:
        raise FuzzIdentifyError(
            code="FUZZ_IDENTIFY_LOG_UNAVAILABLE",
            message=f"Could not read fuzz log {path!r}: {exc}.",
            hint="Check the path and permissions.",
        ) from exc

    frames: list[CanFrame] = []
    stripped = raw.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        # JSONL (one object per line) or a JSON array of frame objects.
        candidates: list[dict] = []
        if stripped.startswith("["):
            try:
                loaded = json.loads(raw)
            except json.JSONDecodeError:
                loaded = []
            if isinstance(loaded, list):
                candidates = [obj for obj in loaded if isinstance(obj, dict)]
        else:
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    candidates.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        for obj in candidates:
            if not isinstance(obj, dict):
                continue
            frame = _frame_from_json(obj)
            if frame is not None:
                frames.append(frame)
    else:
        frames = load_candump_file(text_path)

    if not frames:
        raise FuzzIdentifyError(
            code="FUZZ_IDENTIFY_INVALID_LOG",
            message=f"Fuzz log {path!r} contained no replayable frames.",
            hint="Provide a candump capture or a JSONL log of CAN frames.",
        )
    return frames


@dataclass(frozen=True, slots=True)
class NarrowState:
    num_frames: int
    candidate_lo: int
    candidate_hi: int  # inclusive
    rounds_completed: int
    resolved: bool
    culprit: int | None
    next_window: tuple[int, int] | None  # inclusive (lo, hi) to replay next
    confidence: float
    rationale: str

    @property
    def candidate_count(self) -> int:
        return self.candidate_hi - self.candidate_lo + 1

    @property
    def planned_rounds(self) -> int:
        return 0 if self.num_frames <= 1 else math.ceil(math.log2(self.num_frames))


def narrow(num_frames: int, observations: list[bool]) -> NarrowState:
    """Bisect toward the culprit frame given the observations recorded so far.

    Each round replays the lower half of the current candidate range; an
    ``effect`` observation keeps the lower half, ``no-effect`` keeps the upper.
    """
    if num_frames < 1:
        raise FuzzIdentifyError(
            code="FUZZ_IDENTIFY_INVALID_LOG",
            message="A fuzz log needs at least one frame.",
            hint="Provide a log with one or more frames.",
        )
    lo, hi = 0, num_frames - 1
    used = 0
    for obs in observations:
        if lo >= hi:
            break
        mid = (lo + hi) // 2
        if obs:
            hi = mid
        else:
            lo = mid + 1
        used += 1

    resolved = lo >= hi
    culprit = lo if resolved else None
    if resolved:
        next_window: tuple[int, int] | None = None
    else:
        mid = (lo + hi) // 2
        next_window = (lo, mid)

    span = max(num_frames - 1, 1)
    confidence = 1.0 - (hi - lo) / span

    if resolved:
        rationale = f"Identified the culprit frame at index {culprit} after {used} round(s)."
    else:
        rationale = (
            f"Narrowed to {hi - lo + 1} candidate frame(s) (indices {lo}-{hi}) after "
            f"{used} round(s); replay frames {next_window[0]}-{next_window[1]} next and "
            "mark effect/no-effect."
        )

    return NarrowState(
        num_frames=num_frames,
        candidate_lo=lo,
        candidate_hi=hi,
        rounds_completed=used,
        resolved=resolved,
        culprit=culprit,
        next_window=next_window,
        confidence=round(confidence, 4),
        rationale=rationale,
    )


def frame_record(frames: list[CanFrame], index: int) -> dict[str, object]:
    frame = frames[index]
    return {
        "index": index,
        "arbitration_id": frame.arbitration_id,
        "is_extended_id": frame.is_extended_id,
        "data": frame.data.hex(),
    }
