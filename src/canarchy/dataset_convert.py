"""Conversion helpers for public CAN dataset files."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import IO, Iterator

from canarchy.dataset_provider import DatasetError


_SUPPORTED_SOURCE_FORMATS = ("hcrl-csv",)
_SUPPORTED_OUTPUT_FORMATS = ("candump", "jsonl")


class ConversionError(DatasetError):
    """Raised when a conversion step fails."""


def convert_file(
    source_path: str,
    *,
    source_format: str,
    output_format: str,
    destination: str | None = None,
) -> dict:
    """Convert a dataset file to candump or JSONL format."""
    if source_format not in _SUPPORTED_SOURCE_FORMATS:
        raise ConversionError(
            code="UNSUPPORTED_SOURCE_FORMAT",
            message=f"Source format '{source_format}' is not supported.",
            hint=f"Supported source formats: {', '.join(_SUPPORTED_SOURCE_FORMATS)}.",
        )
    if output_format not in _SUPPORTED_OUTPUT_FORMATS:
        raise ConversionError(
            code="UNSUPPORTED_OUTPUT_FORMAT",
            message=f"Output format '{output_format}' is not supported.",
            hint=f"Supported output formats: {', '.join(_SUPPORTED_OUTPUT_FORMATS)}.",
        )

    src = Path(source_path)
    if not src.exists():
        raise ConversionError(
            code="SOURCE_NOT_FOUND",
            message=f"Source file not found: {source_path}",
            hint="Provide a valid path to a downloaded dataset file.",
        )

    if destination is None:
        suffix = ".log" if output_format == "candump" else ".jsonl"
        destination = str(src.with_suffix(suffix))

    if source_format == "hcrl-csv":
        frames = list(_parse_hcrl_csv(src))
    else:
        raise AssertionError(f"unhandled source format: {source_format}")

    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if output_format == "candump":
        _write_candump(frames, dest)
    elif output_format == "jsonl":
        _write_jsonl(frames, dest, source=source_format)

    return {
        "source": str(src),
        "destination": str(dest),
        "source_format": source_format,
        "output_format": output_format,
        "frame_count": len(frames),
    }


def stream_file(
    source_path: str,
    *,
    source_format: str,
    output_format: str,
    destination: str | None = None,
    chunk_size: int = 1000,
    provider_ref: str | None = None,
) -> dict:
    """Stream a dataset file to candump or JSONL without materializing all frames."""
    if source_format not in _SUPPORTED_SOURCE_FORMATS:
        raise ConversionError(
            code="UNSUPPORTED_SOURCE_FORMAT",
            message=f"Source format '{source_format}' is not supported.",
            hint=f"Supported source formats: {', '.join(_SUPPORTED_SOURCE_FORMATS)}.",
        )
    if output_format not in _SUPPORTED_OUTPUT_FORMATS:
        raise ConversionError(
            code="UNSUPPORTED_OUTPUT_FORMAT",
            message=f"Output format '{output_format}' is not supported.",
            hint=f"Supported output formats: {', '.join(_SUPPORTED_OUTPUT_FORMATS)}.",
        )
    if chunk_size < 1:
        raise ConversionError(
            code="INVALID_CHUNK_SIZE",
            message="Chunk size must be at least 1.",
            hint="Use `--chunk-size` with a positive integer.",
        )

    src = Path(source_path)
    if not src.exists():
        raise ConversionError(
            code="SOURCE_NOT_FOUND",
            message=f"Source file not found: {source_path}",
            hint="Provide a valid path to a downloaded dataset file.",
        )

    if source_format == "hcrl-csv":
        frames = _parse_hcrl_csv(src)
    else:
        raise AssertionError(f"unhandled source format: {source_format}")

    if destination is None or destination == "-":
        counts = _stream_frames(
            frames,
            sys.stdout,
            output_format=output_format,
            source=source_format,
            chunk_size=chunk_size,
            provider_ref=provider_ref,
        )
        destination_label = "-"
    else:
        dest = Path(destination)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w") as handle:
            counts = _stream_frames(
                frames,
                handle,
                output_format=output_format,
                source=source_format,
                chunk_size=chunk_size,
                provider_ref=provider_ref,
            )
        destination_label = str(dest)

    return {
        "source": str(src),
        "destination": destination_label,
        "source_format": source_format,
        "output_format": output_format,
        "chunk_size": chunk_size,
        "chunks": counts["chunks"],
        "frame_count": counts["frame_count"],
        "provider_ref": provider_ref,
        "streamed": True,
    }


def _parse_hcrl_csv(path: Path) -> Iterator[dict]:
    """Parse HCRL Car-Hacking CSV format.

    Expected columns: Timestamp, ID, DLC, Data[, Label]
    Data column is space-separated hex bytes.
    """
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ConversionError(
                code="MALFORMED_SOURCE",
                message="CSV file has no header row.",
                hint="HCRL CSV files must have a header: Timestamp,ID,DLC,Data[,Label].",
            )
        required = {"Timestamp", "ID", "DLC", "Data"}
        missing = required - set(reader.fieldnames)
        if missing:
            raise ConversionError(
                code="MALFORMED_SOURCE",
                message=f"CSV is missing required columns: {', '.join(sorted(missing))}.",
                hint="Expected columns: Timestamp, ID, DLC, Data (and optionally Label).",
            )
        for line_num, row in enumerate(reader, start=2):
            try:
                timestamp = float(row["Timestamp"])
                arb_id = int(row["ID"], 16)
                data_bytes = bytes(int(b, 16) for b in row["Data"].strip().split())
                label = row.get("Label", "").strip() or None
            except (ValueError, KeyError) as exc:
                raise ConversionError(
                    code="MALFORMED_SOURCE",
                    message=f"Malformed row at line {line_num}: {exc}",
                    hint="Check that Timestamp is a float, ID is hex, and Data is space-separated hex bytes.",
                ) from exc
            yield {"timestamp": timestamp, "arbitration_id": arb_id, "data": data_bytes, "label": label}


def _stream_frames(
    frames: Iterator[dict],
    handle: IO[str],
    *,
    output_format: str,
    source: str,
    chunk_size: int,
    provider_ref: str | None,
) -> dict:
    frame_count = 0
    chunk_index = 0
    chunk_position = 0
    for frame in frames:
        if chunk_position >= chunk_size:
            chunk_index += 1
            chunk_position = 0
        if output_format == "candump":
            handle.write(_format_candump_frame(frame))
        elif output_format == "jsonl":
            event = _frame_to_event(
                frame,
                source=source,
                provider_ref=provider_ref,
                frame_offset=frame_count,
                chunk_index=chunk_index,
                chunk_position=chunk_position,
            )
            handle.write(json.dumps(event, sort_keys=True) + "\n")
        frame_count += 1
        chunk_position += 1
    handle.flush()
    return {"frame_count": frame_count, "chunks": chunk_index + (1 if chunk_position else 0)}


def _format_candump_frame(frame: dict) -> str:
    ts = f"{frame['timestamp']:.6f}"
    arb_id = f"{frame['arbitration_id']:X}"
    data_hex = frame["data"].hex().upper()
    return f"({ts}) can0 {arb_id}#{data_hex}\n"


def _frame_to_event(
    frame: dict,
    *,
    source: str,
    provider_ref: str | None = None,
    frame_offset: int | None = None,
    chunk_index: int | None = None,
    chunk_position: int | None = None,
) -> dict:
    event = {
        "event_type": "frame",
        "source": source,
        "timestamp": frame["timestamp"],
        "payload": {
            "arbitration_id": frame["arbitration_id"],
            "data": frame["data"].hex(),
            "interface": None,
        },
    }
    if frame.get("label"):
        event["payload"]["label"] = frame["label"]
    if provider_ref is not None or frame_offset is not None or chunk_index is not None:
        event["payload"]["dataset"] = {
            "provider_ref": provider_ref,
            "frame_offset": frame_offset,
            "chunk_index": chunk_index,
            "chunk_position": chunk_position,
        }
    return event


def _write_candump(frames: list[dict], dest: Path) -> None:
    """Write frames in candump log format: (timestamp) interface id#data"""
    dest.write_text("".join(_format_candump_frame(frame) for frame in frames))


def _write_jsonl(frames: list[dict], dest: Path, *, source: str) -> None:
    """Write frames as JSONL FrameEvents."""
    lines = [json.dumps(_frame_to_event(frame, source=source)) for frame in frames]
    dest.write_text("\n".join(lines) + ("\n" if lines else ""))


def list_source_formats() -> list[str]:
    return list(_SUPPORTED_SOURCE_FORMATS)


def list_output_formats() -> list[str]:
    return list(_SUPPORTED_OUTPUT_FORMATS)
