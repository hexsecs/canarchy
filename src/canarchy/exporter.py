"""Structured export helpers for CLI artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from canarchy.models import FrameEvent, serialize_events
from canarchy.session import SessionStore
from canarchy.transport import LocalTransport


@dataclass(slots=True)
class ExportError(Exception):
    code: str
    message: str
    hint: str

    def __str__(self) -> str:
        return self.message


def export_artifact(source: str, destination: str) -> dict[str, Any]:
    artifact = build_export_artifact(source)
    destination_path = Path(destination)
    export_format = destination_path.suffix.lower()
    if export_format not in {".json", ".jsonl"}:
        raise ExportError(
            code="EXPORT_FORMAT_UNSUPPORTED",
            message=f"Export destination '{destination}' uses an unsupported file format.",
            hint="Use a destination path ending in .json or .jsonl.",
        )

    try:
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        if export_format == ".json":
            destination_path.write_text(json.dumps(artifact, sort_keys=True) + "\n", encoding="utf-8")
        else:
            events = artifact["data"].get("events")
            if events is None:
                raise ExportError(
                    code="EXPORT_EVENTS_UNAVAILABLE",
                    message="The selected export source does not provide an event stream.",
                    hint="Export this source to a .json artifact instead of .jsonl.",
                )
            lines = [json.dumps(event, sort_keys=True) for event in events]
            destination_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    except ExportError:
        raise
    except OSError as exc:
        raise ExportError(
            code="EXPORT_WRITE_FAILED",
            message=f"Failed to write export artifact to '{destination}'.",
            hint="Check that the destination path is writable and try again.",
        ) from exc

    return {
        "artifact_type": artifact["data"]["artifact_type"],
        "destination": str(destination_path),
        "export_format": export_format.removeprefix("."),
        "exported_events": len(artifact["data"].get("events", [])),
        "source": source,
        "source_kind": artifact["data"]["source"]["kind"],
    }


def build_export_artifact(source: str) -> dict[str, Any]:
    if source.startswith("session:"):
        session_name = source.split(":", 1)[1]
        if not session_name:
            raise ExportError(
                code="EXPORT_SOURCE_UNSUPPORTED",
                message="Session export sources must include a session name.",
                hint="Use a source like session:lab-a.",
            )
        session = SessionStore().load(session_name)
        return {
            "ok": True,
            "command": "export",
            "data": {
                "artifact_type": "session_record",
                "session": session.to_payload(),
                "source": {"kind": "session", "value": session_name},
            },
            "warnings": [],
            "errors": [],
        }

    source_path = Path(source)
    if source_path.suffix.lower() in {".candump", ".log"} or source_path.exists():
        transport = LocalTransport()
        frames = transport.frames_from_file(source)
        events = serialize_events(
            [FrameEvent(frame=frame, source="export.capture_file").to_event() for frame in frames]
        )
        return {
            "ok": True,
            "command": "export",
            "data": {
                "artifact_type": "event_stream",
                "events": events,
                "file": source,
                "mode": "passive",
                "source": {"kind": "capture_file", "value": source},
            },
            "warnings": [],
            "errors": [],
        }

    raise ExportError(
        code="EXPORT_SOURCE_UNSUPPORTED",
        message=f"Export source '{source}' is not supported.",
        hint="Use a candump/log capture file path or a saved session source like session:lab-a.",
    )
