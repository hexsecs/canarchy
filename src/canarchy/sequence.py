"""CANarchy sequence replay — YAML/JSON multi-message coordinated transmit."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class SequenceError(Exception):
    """Raised when a sequence file is invalid or a frame cannot be encoded."""


@dataclass(slots=True)
class FrameSpec:
    frame_id: int
    signals: dict[str, float]
    dbc: str | None = None
    is_extended_id: bool = False


@dataclass(slots=True)
class SequenceStep:
    delay_ms: float
    frames: list[FrameSpec] = field(default_factory=list)
    dbc: str | None = None


@dataclass(slots=True)
class SequenceFile:
    steps: list[SequenceStep] = field(default_factory=list)
    dbc: str | None = None


def _parse_frame(raw: Any) -> FrameSpec:
    if not isinstance(raw, dict):
        raise SequenceError(f"each frame must be a dict, got {type(raw).__name__}")
    if "id" not in raw:
        raise SequenceError("each frame must have an 'id' field")

    frame_id_raw = raw["id"]
    if isinstance(frame_id_raw, str):
        try:
            frame_id = int(frame_id_raw, 0)
        except ValueError:
            raise SequenceError(f"invalid frame id: {frame_id_raw!r}")
    elif isinstance(frame_id_raw, int):
        frame_id = frame_id_raw
    else:
        raise SequenceError(
            f"frame id must be an integer or hex string, got {type(frame_id_raw).__name__}"
        )

    signals = raw.get("signals", {})
    if not isinstance(signals, dict):
        raise SequenceError("frame 'signals' must be a dict")

    return FrameSpec(
        frame_id=frame_id,
        signals=dict(signals),
        dbc=raw.get("dbc"),
        is_extended_id=bool(raw.get("is_extended_id", False)),
    )


def _parse_step(raw: Any) -> SequenceStep:
    if not isinstance(raw, dict):
        raise SequenceError(f"each step must be a dict, got {type(raw).__name__}")

    delay_ms = raw.get("delay_ms", 0)
    if not isinstance(delay_ms, (int, float)):
        raise SequenceError(f"'delay_ms' must be a number, got {type(delay_ms).__name__}")
    if not math.isfinite(float(delay_ms)) or float(delay_ms) < 0:
        raise SequenceError(f"'delay_ms' must be a finite non-negative number, got {delay_ms!r}")

    raw_frames = raw.get("frames", [])
    if not isinstance(raw_frames, list):
        raise SequenceError("'frames' must be a list")

    return SequenceStep(
        delay_ms=float(delay_ms),
        frames=[_parse_frame(f) for f in raw_frames],
        dbc=raw.get("dbc"),
    )


def load_sequence(path: str | Path) -> SequenceFile:
    path = Path(path)
    try:
        text = path.read_text()
    except OSError as exc:
        raise SequenceError(f"cannot read sequence file: {exc}") from exc

    try:
        if path.suffix.lower() in (".yaml", ".yml"):
            import yaml

            raw = yaml.safe_load(text)
        else:
            raw = json.loads(text)
    except Exception as exc:
        raise SequenceError(f"failed to parse sequence file: {exc}") from exc

    if raw is None:
        raise SequenceError("sequence file is empty")

    top_dbc: str | None = None
    if isinstance(raw, list):
        steps_raw = raw
    elif isinstance(raw, dict):
        top_dbc = raw.get("dbc")
        steps_raw = raw.get("steps", [])
        if not isinstance(steps_raw, list):
            raise SequenceError("'steps' must be a list")
    else:
        raise SequenceError("sequence file must be a list of steps or a dict with a 'steps' key")

    return SequenceFile(
        steps=[_parse_step(s) for s in steps_raw],
        dbc=top_dbc,
    )


def encode_frame(
    frame: FrameSpec,
    fallback_dbc: str | None,
) -> tuple[int, bytes, bool, str | None]:
    """Encode one FrameSpec to bytes.

    Returns (frame_id, data, is_extended_id, message_name).
    """
    dbc_ref = frame.dbc or fallback_dbc
    if dbc_ref is None:
        raise SequenceError(
            f"no DBC specified for frame id 0x{frame.frame_id:X}; "
            "set 'dbc' at the file, step, or frame level"
        )

    resolved_path = _resolve_dbc(dbc_ref)

    try:
        import cantools

        db = cantools.database.load_file(resolved_path)
    except Exception as exc:
        raise SequenceError(f"cannot load DBC file {resolved_path!r}: {exc}") from exc

    try:
        message = db.get_message_by_frame_id(frame.frame_id)
    except Exception:
        raise SequenceError(f"frame id 0x{frame.frame_id:X} not found in DBC {resolved_path!r}")

    try:
        data = message.encode(frame.signals, padding=True)
    except Exception as exc:
        raise SequenceError(
            f"cannot encode frame 0x{frame.frame_id:X} ({message.name}): {exc}"
        ) from exc

    return frame.frame_id, bytes(data), frame.is_extended_id, message.name


def _resolve_dbc(ref: str) -> str:
    try:
        from canarchy.dbc_provider import get_registry

        resolution = get_registry().resolve(ref)
        return str(resolution.local_path)
    except Exception:
        return ref


def encode_sequence(
    seq: SequenceFile,
) -> list[dict[str, Any]]:
    """Pre-encode every step in the sequence.

    Returns a list of step dicts ready for events or transmission.
    """
    encoded: list[dict[str, Any]] = []
    for step_idx, step in enumerate(seq.steps):
        fallback_dbc = step.dbc or seq.dbc
        frames: list[dict[str, Any]] = []
        for frame in step.frames:
            frame_id, data, is_extended, msg_name = encode_frame(frame, fallback_dbc)
            frames.append(
                {
                    "frame_id": frame_id,
                    "frame_id_hex": f"0x{frame_id:08X}",
                    "data": data.hex(),
                    "message_name": msg_name,
                    "is_extended_id": is_extended,
                }
            )
        encoded.append(
            {
                "step": step_idx,
                "delay_ms": step.delay_ms,
                "frame_count": len(frames),
                "frames": frames,
            }
        )
    return encoded
