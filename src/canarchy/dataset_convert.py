"""Conversion helpers for public CAN dataset files."""

from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import IO, Iterator

import requests

from canarchy.dataset_provider import DatasetError


_SUPPORTED_SOURCE_FORMATS = ("hcrl-csv", "candump")
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

    if source_format == "hcrl-csv":
        frames = list(_parse_hcrl_csv(src))
    elif source_format == "candump":
        frames = list(_parse_candump(src))
    else:
        raise AssertionError(f"unhandled source format: {source_format}")

    dest = Path(destination) if destination else src.with_suffix(".log" if output_format == "candump" else ".jsonl")
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
    elif source_format == "candump":
        frames = _parse_candump(src)
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
        "source": source_path,
        "destination": destination_label,
        "source_format": source_format,
        "output_format": output_format,
        "chunk_size": chunk_size,
        "chunks": counts["chunks"],
        "frame_count": counts["frame_count"],
        "provider_ref": provider_ref,
        "streamed": True,
    }


def stream_replay(
    source_url: str,
    *,
    source_format: str = "candump",
    output_format: str = "candump",
    rate: float = 1.0,
    max_frames: int | None = None,
    emit_frames: bool = True,
    handle: IO[str] | None = None,
) -> dict:
    """Netflix-style streaming replay: download and play frames with timing.
    
    Downloads from remote URL incrementally and replays with original timing * rate.
    No local file is required — frames stream directly from HTTP to output.
    """
    if source_format != "candump":
        raise ConversionError(
            code="UNSUPPORTED_SOURCE_FORMAT",
            message=f"Streaming replay only supports candump format, got '{source_format}'.",
            hint="Use source_format='candump' for streaming replay.",
        )

    if output_format not in _SUPPORTED_OUTPUT_FORMATS:
        raise ConversionError(
            code="UNSUPPORTED_OUTPUT_FORMAT",
            message=f"Output format '{output_format}' is not supported.",
            hint=f"Supported output formats: {', '.join(_SUPPORTED_OUTPUT_FORMATS)}.",
        )
    
    if rate <= 0:
        raise ConversionError(
            code="INVALID_RATE",
            message=f"Replay rate must be positive, got {rate}.",
            hint="Use a positive rate like 1.0 (real-time) or 0.5 (half-speed).",
        )

    frame_count = 0
    last_timestamp = None
    start_time = time.monotonic()
    output = handle or sys.stdout
    stop_reason = "eof"

    try:
        with requests.get(source_url, stream=True) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.strip():
                    continue

                # iter_lines() returns bytes, decode to string
                if isinstance(line, bytes):
                    line = line.decode("utf-8", errors="replace")

                # Parse candump line to get timestamp
                frame = _parse_candump_line(line)
                if frame is None:
                    continue

                if max_frames is not None and frame_count >= max_frames:
                    stop_reason = "max_frames"
                    break
                frame_count += 1

                # Timing: sleep to maintain original timing * rate
                if last_timestamp is not None and frame["timestamp"] > last_timestamp:
                    delay = (frame["timestamp"] - last_timestamp) / rate
                    if delay > 0:
                        time.sleep(min(delay, 1.0))  # Cap sleeps at 1s for safety

                last_timestamp = frame["timestamp"]

                if emit_frames:
                    if output_format == "candump":
                        output_line = f"({frame['timestamp']:.6f}) {frame.get('interface') or 'can0'} {frame['arbitration_id']:X}#{frame['data'].hex().upper()}"
                    elif output_format == "jsonl":
                        output_line = json.dumps(_frame_to_event(frame, source=source_format))
                    else:
                        raise AssertionError(f"unhandled output format: {output_format}")
                    try:
                        print(output_line, file=output, flush=True)
                    except BrokenPipeError:
                        stop_reason = "broken_pipe"
                        _silence_broken_stdout(output)
                        break
    except requests.RequestException as exc:
        raise ConversionError(
            code="DATASET_REPLAY_FETCH_FAILED",
            message=f"Failed to stream replay source: {source_url}",
            hint="Check the dataset replay URL, network connectivity, and provider availability.",
        ) from exc
            
    elapsed = time.monotonic() - start_time
    return {
        "source_url": source_url,
        "source_format": source_format,
        "output_format": output_format,
        "rate": rate,
        "frame_count": frame_count,
        "elapsed_seconds": elapsed,
        "stop_reason": stop_reason,
        "streamed": True,
    }


def _silence_broken_stdout(output: IO[str]) -> None:
    """Prevent Python shutdown from printing a second BrokenPipeError."""
    if output is not sys.stdout:
        return
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        os.close(devnull)
    except (AttributeError, OSError, ValueError):
        pass


def _parse_candump(path: Path) -> Iterator[dict]:
    """Parse candump format file incrementally."""
    with open(path) as f:
        for line in f:
            frame = _parse_candump_line(line)
            if frame:
                yield frame


def _parse_candump_line(line: str) -> dict | None:
    """Parse a single candump line like: (0.000000) can0 420#3F0000334200F257"""
    line = line.strip()
    if not line:
        return None
    
    match = re.match(r"\((\d+\.?\d*)\)\s+(\S+)\s+([0-9A-Fa-fXx]+)#([0-9A-Fa-f]*)", line)
    if not match:
        return None
    
    timestamp = float(match.group(1))
    interface = match.group(2)
    arb_id_str = match.group(3)
    data_hex = match.group(4)
    
    arb_id = int(arb_id_str, 16)
    data_bytes = bytes.fromhex(data_hex) if data_hex else b""
    
    return {
        "timestamp": timestamp,
        "interface": interface,
        "arbitration_id": arb_id,
        "data": data_bytes,
        "dlc": len(data_bytes),
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


def _frame_to_event(frame: dict, *, source: str) -> dict:
    """Convert a frame dict to a FrameEvent."""
    event = {
        "event_type": "frame",
        "source": source,
        "timestamp": frame["timestamp"],
        "payload": {
            "arbitration_id": frame["arbitration_id"],
            "data": frame["data"].hex().upper(),
            "interface": frame.get("interface"),
            "label": frame.get("label"),
        },
    }
    return event


def _stream_frames(
    frames: Iterator[dict],
    handle: IO[str],
    *,
    output_format: str,
    source: str,
    chunk_size: int,
    provider_ref: str | None,
) -> dict:
    """Stream frames to handle, emitting metadata chunks."""
    frame_count = 0
    chunk_index = 0
    frame_offset = 0

    for frame in frames:
        if output_format == "candump":
            line = f"({frame['timestamp']:.6f}) can0 {frame['arbitration_id']:x}#{frame['data'].hex().upper()}\n"
        elif output_format == "jsonl":
            event = _frame_to_event(frame, source=source)
            event["payload"]["dataset"] = {
                "chunk_index": chunk_index,
                "chunk_position": frame_count % chunk_size,
                "frame_offset": frame_offset,
                "provider_ref": provider_ref,
            }
            line = json.dumps(event) + "\n"
        else:
            raise AssertionError(f"unhandled output format: {output_format}")

        handle.write(line)
        frame_count += 1
        frame_offset += 1

        if frame_count % chunk_size == 0:
            chunk_index += 1

    # chunk_index is 0-based; if frame_count % chunk_size == 0, we have exactly frame_count/chunk_size chunks
    if frame_count % chunk_size == 0:
        chunks = frame_count // chunk_size
    else:
        chunks = (frame_count // chunk_size) + 1
    return {"frame_count": frame_count, "chunks": chunks}


def _write_candump(frames: list[dict], dest: Path) -> None:
    """Write frames as candump format."""
    lines = [
        f"({f['timestamp']:.6f}) can0 {f['arbitration_id']:x}#{f['data'].hex().upper()}"
        for f in frames
    ]
    dest.write_text("\n".join(lines) + "\n")


def _write_jsonl(frames: list[dict], dest: Path, *, source: str) -> None:
    """Write frames as JSONL FrameEvents."""
    lines = [json.dumps(_frame_to_event(f, source=source)) for f in frames]
    dest.write_text("\n".join(lines) + ("\n" if lines else ""))


def list_source_formats() -> list[str]:
    return list(_SUPPORTED_SOURCE_FORMATS)


def list_output_formats() -> list[str]:
    return list(_SUPPORTED_OUTPUT_FORMATS)
