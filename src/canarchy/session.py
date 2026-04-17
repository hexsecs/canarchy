"""Session persistence helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class SessionError(Exception):
    code: str
    message: str
    hint: str

    def __str__(self) -> str:
        return self.message


@dataclass(slots=True)
class SessionRecord:
    name: str
    context: dict[str, Any]
    saved_at: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "context": self.context,
            "saved_at": self.saved_at,
        }


class SessionStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.cwd() / ".canarchy"
        self.sessions_dir = self.root / "sessions"
        self.active_session_path = self.root / "active_session.json"

    def save(self, name: str, context: dict[str, Any]) -> SessionRecord:
        self._ensure_paths()
        record = SessionRecord(
            name=name,
            context=context,
            saved_at=datetime.now(UTC).isoformat(),
        )
        session_path = self.sessions_dir / f"{name}.json"
        session_path.write_text(self._to_json(record.to_payload()) + "\n")
        self.active_session_path.write_text(self._to_json(record.to_payload()) + "\n")
        return record

    def load(self, name: str) -> SessionRecord:
        record = self._read_session(name)
        self._ensure_paths()
        self.active_session_path.write_text(self._to_json(record.to_payload()) + "\n")
        return record

    def show(self) -> dict[str, Any]:
        sessions: list[dict[str, Any]] = []
        if self.sessions_dir.exists():
            for session_path in sorted(self.sessions_dir.glob("*.json")):
                payload = self._read_json(session_path)
                sessions.append(
                    {
                        "name": payload["name"],
                        "saved_at": payload["saved_at"],
                        "context": payload["context"],
                    }
                )

        active = None
        if self.active_session_path.exists():
            active = self._read_json(self.active_session_path)

        return {
            "active_session": active,
            "sessions": sessions,
        }

    def _read_session(self, name: str) -> SessionRecord:
        session_path = self.sessions_dir / f"{name}.json"
        if not session_path.exists():
            raise SessionError(
                code="SESSION_NOT_FOUND",
                message=f"Session '{name}' was not found.",
                hint="Save the session first or inspect `session show` for available sessions.",
            )
        payload = self._read_json(session_path)
        return SessionRecord(
            name=payload["name"],
            context=payload["context"],
            saved_at=payload["saved_at"],
        )

    def _ensure_paths(self) -> None:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _read_json(self, path: Path) -> dict[str, Any]:
        import json

        return json.loads(path.read_text())

    def _to_json(self, payload: dict[str, Any]) -> str:
        import json

        return json.dumps(payload, sort_keys=True)


def build_session_context(args: Any) -> dict[str, Any]:
    context: dict[str, Any] = {}
    for key in ("interface", "dbc", "capture"):
        value = getattr(args, key, None)
        if value is not None:
            context[key] = value
    return context
