"""Session persistence and reproducible research-record provenance.

A session is both the lightweight context store it has always been (interface,
DBC, capture) and a research record: it carries content hashes for its inputs,
the invocations that consumed them, the artifacts they produced, and the
operator's annotations, so a finding can be traced back to the exact bytes and
settings that produced it.

Nothing in this module executes a recorded command, opens a transport, or
transmits a frame. Loading and verifying a session only read files.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from canarchy import __version__

# Manifest version history:
#   1 — name/context/saved_at only; written before provenance recording existed.
#   2 — adds inputs, invocations, artifacts, annotations, and version metadata.
SCHEMA_VERSION = 2
LEGACY_SCHEMA_VERSION = 1

# Configuration sections worth recording: they change how analysis behaves.
# Anything outside this list (including credentials) is never serialized.
_CONFIG_SECTION_ALLOWLIST = ("transport", "dbc", "safety", "fuzz", "j1939")

# Environment variables that change analysis behaviour. `CANARCHY_SERVER_KEY`
# and every unrelated variable are deliberately absent.
_ENV_ALLOWLIST = (
    "CANARCHY_CAPTURE_LIMIT",
    "CANARCHY_CAPTURE_TIMEOUT",
    "CANARCHY_DATASETS_DEFAULT_PROVIDER",
    "CANARCHY_DBC_DEFAULT_PROVIDER",
    "CANARCHY_DBC_OPENDBC_REF",
    "CANARCHY_DBC_OPENDBC_REPO",
    "CANARCHY_DEFAULT_INTERFACE",
    "CANARCHY_J1587_PID_OVERRIDES",
    "CANARCHY_J1939_DBC",
    "CANARCHY_J1939_SPN_OVERRIDES",
    "CANARCHY_J2497_MID_OVERRIDES",
    "CANARCHY_PYTHON_CAN_INTERFACE",
    "CANARCHY_TRANSPORT_BACKEND",
)

# Second line of defence: an allowlisted section must still not leak a key that
# looks like a credential.
_SECRET_KEY_PATTERN = re.compile(
    r"(token|secret|password|passwd|credential|cookie|session_id|api_?key|_key$|^key$|auth)",
    re.IGNORECASE,
)

_TEXT_MEDIA_SUFFIXES = {
    ".candump": "text/plain",
    ".csv": "text/csv",
    ".dbc": "text/plain",
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
    ".log": "text/plain",
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
}

# An embedded artifact lives inside the manifest; keep manifests readable.
_MAX_EMBED_BYTES = 1_048_576


@dataclass(slots=True)
class SessionError(Exception):
    code: str
    message: str
    hint: str

    def __str__(self) -> str:
        return self.message


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_of_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _relative_to(path: Path, base: Path) -> str | None:
    """Return `path` relative to `base` in posix form, or None if outside it."""
    try:
        return Path(os.path.relpath(path, base)).as_posix() if _is_within(path, base) else None
    except ValueError:  # different drives on Windows
        return None


def _is_within(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True


def _media_type_for(path: Path) -> str:
    return _TEXT_MEDIA_SUFFIXES.get(path.suffix.lower(), "application/octet-stream")


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:8]}"


def _sanitize_config(value: Any) -> tuple[Any, list[str]]:
    """Drop secret-looking keys from a configuration mapping.

    Returns the sanitized value and the dotted names of everything removed, so
    the record states what it withheld instead of silently shrinking.
    """
    redacted: list[str] = []
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, sub_value in value.items():
            if _SECRET_KEY_PATTERN.search(str(key)):
                redacted.append(str(key))
                continue
            sub_clean, sub_redacted = _sanitize_config(sub_value)
            cleaned[str(key)] = sub_clean
            redacted.extend(f"{key}.{name}" for name in sub_redacted)
        return cleaned, redacted
    if isinstance(value, list):
        cleaned_list = []
        for item in value:
            item_clean, item_redacted = _sanitize_config(item)
            cleaned_list.append(item_clean)
            redacted.extend(item_redacted)
        return cleaned_list, redacted
    return value, redacted


def _config_path() -> Path:
    return Path.home() / ".canarchy" / "config.toml"


def effective_config() -> dict[str, Any]:
    """Return the allowlisted configuration that applied to this invocation.

    Only the documented `[transport]`, `[dbc]`, `[safety]`, `[fuzz]`, and
    `[j1939]` sections and the `CANARCHY_*` variables that change analysis
    behaviour are recorded; credentials never are.
    """
    config: dict[str, Any] = {}
    redacted: list[str] = []
    path = _config_path()
    if path.exists():
        import tomllib

        try:
            raw = tomllib.loads(path.read_text())
        except (OSError, ValueError):
            raw = {}
        for section in _CONFIG_SECTION_ALLOWLIST:
            if section not in raw:
                continue
            cleaned, section_redacted = _sanitize_config(raw[section])
            config[section] = cleaned
            redacted.extend(f"{section}.{name}" for name in section_redacted)

    environment = {
        name: os.environ[name]
        for name in _ENV_ALLOWLIST
        if name in os.environ and not _SECRET_KEY_PATTERN.search(name)
    }
    return {
        "config_file": str(path) if path.exists() else None,
        "sections": config,
        "environment_variables": environment,
        "redacted_keys": sorted(set(redacted)),
    }


def environment_snapshot() -> dict[str, Any]:
    """Describe the interpreter and the backends available for analysis."""
    backends: dict[str, str | None] = {}
    for module_name, label in (("can", "python_can"), ("cantools", "cantools")):
        try:
            module = __import__(module_name)
        except Exception:  # pragma: no cover - import guard, not a behaviour
            backends[label] = None
        else:
            backends[label] = str(getattr(module, "__version__", "unknown"))
    return {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "backends": backends,
    }


def _provider_metadata(path: Path) -> dict[str, Any] | None:
    """Return DBC provider provenance when `path` is a provider cache file.

    Cached provider files live at
    `~/.canarchy/cache/dbc/providers/<provider>/files/<commit>/<file>`, so the
    provider name and commit are recoverable from the path and the rest comes
    from that provider's cache manifest.
    """
    from canarchy.dbc_cache import cache_root, load_manifest

    root = cache_root() / "providers"
    if not _is_within(path, root):
        return None
    try:
        parts = path.relative_to(root).parts
    except ValueError:  # pragma: no cover - guarded by _is_within
        return None
    if len(parts) < 4 or parts[1] != "files":
        return None
    provider, commit = parts[0], parts[2]
    metadata: dict[str, Any] = {"name": provider, "commit": commit}
    try:
        manifest = load_manifest(provider)
    except (OSError, ValueError):
        manifest = None
    if manifest:
        metadata["repo"] = manifest.get("repo")
        metadata["ref"] = manifest.get("ref")
        metadata["manifest_commit"] = manifest.get("commit")
        metadata["generated_at"] = manifest.get("generated_at")
    return metadata


@dataclass(slots=True)
class FileRecord:
    """A hashed file referenced by a session: an input or an artifact."""

    record_id: str
    path: str
    absolute_path: str | None = None
    relative_path: str | None = None
    sha256: str | None = None
    size_bytes: int | None = None
    modified_at: str | None = None
    status: str = "recorded"
    detail: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "absolute_path": self.absolute_path,
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "modified_at": self.modified_at,
            "status": self.status,
            "detail": self.detail,
        }


def _record_file(record_id: str, raw_path: str, *, store_base: Path) -> FileRecord:
    """Hash `raw_path` and describe it three ways: as given, absolute, relative.

    An unreadable file is recorded with `status: unreadable` rather than
    failing the save — a record that names a missing input is more useful than
    no record at all.
    """
    record = FileRecord(record_id=record_id, path=raw_path)
    try:
        resolved = Path(raw_path).expanduser().resolve()
        stat = resolved.stat()
        record.absolute_path = str(resolved)
        record.relative_path = _relative_to(resolved, store_base)
        record.sha256 = _sha256_of_file(resolved)
        record.size_bytes = stat.st_size
        record.modified_at = datetime.fromtimestamp(stat.st_mtime, UTC).isoformat()
    except OSError as exc:
        record.status = "unreadable"
        record.detail = str(exc)
    return record


def _input_payload(
    *, input_id: str, role: str, record: FileRecord, provider: dict[str, Any] | None
) -> dict[str, Any]:
    payload = {"input_id": input_id, "role": role, **record.to_payload()}
    payload["provider"] = provider
    return payload


def _resolve_entry_path(entry: dict[str, Any], *, store_base: Path, root: Path | None) -> Path:
    """Pick the best on-disk location for a recorded entry.

    A relocation root wins over the recorded absolute path so a session moved
    to another checkout or machine verifies against the files it was given.
    """
    candidates: list[Path] = []
    relative = entry.get("relative_path")
    if root is not None and relative:
        candidates.append(root / relative)
    absolute = entry.get("absolute_path")
    if absolute:
        candidates.append(Path(absolute))
    if relative:
        candidates.append(store_base / relative)
    candidates.append(Path(str(entry.get("path", ""))).expanduser())
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _embedded_bytes(embedded: dict[str, Any]) -> bytes:
    content = str(embedded.get("content", ""))
    if embedded.get("encoding") == "base64":
        return base64.b64decode(content)
    return content.encode("utf-8")


def _verify_entry(
    entry: dict[str, Any], *, id_key: str, store_base: Path, root: Path | None
) -> dict[str, Any]:
    report: dict[str, Any] = {
        id_key: entry.get(id_key),
        "path": entry.get("path"),
        "expected_sha256": entry.get("sha256"),
        "expected_size_bytes": entry.get("size_bytes"),
        "actual_sha256": None,
        "actual_size_bytes": None,
        "resolved_path": None,
        "status": "unverifiable",
        "detail": None,
    }
    if "role" in entry:
        report["role"] = entry["role"]
    if "kind" in entry:
        report["kind"] = entry["kind"]

    embedded = entry.get("embedded")
    if embedded:
        payload = _embedded_bytes(embedded)
        report["resolved_path"] = None
        report["actual_sha256"] = _sha256_of_bytes(payload)
        report["actual_size_bytes"] = len(payload)
        report["source"] = "embedded"
        if entry.get("sha256") is None:
            report["detail"] = "Artifact was embedded without a recorded hash."
        elif report["actual_sha256"] == entry["sha256"]:
            report["status"] = "unchanged"
        else:
            report["status"] = "changed"
            report["detail"] = "Embedded content does not match its recorded hash."
        return report

    resolved = _resolve_entry_path(entry, store_base=store_base, root=root)
    report["resolved_path"] = str(resolved)
    report["source"] = "file"
    if entry.get("sha256") is None:
        report["detail"] = "No content hash was recorded for this entry."
        return report
    if not resolved.exists():
        report["status"] = "missing"
        report["detail"] = "File is not present at any recorded or relocated path."
        return report
    try:
        report["actual_sha256"] = _sha256_of_file(resolved)
        report["actual_size_bytes"] = resolved.stat().st_size
    except OSError as exc:
        report["status"] = "missing"
        report["detail"] = str(exc)
        return report
    report["status"] = "unchanged" if report["actual_sha256"] == entry["sha256"] else "changed"
    if report["status"] == "changed":
        report["detail"] = "File content no longer matches the recorded hash."
    return report


@dataclass(slots=True)
class SessionRecord:
    name: str
    context: dict[str, Any]
    saved_at: str
    schema_version: int = SCHEMA_VERSION
    created_at: str | None = None
    canarchy_version: str = __version__
    provenance_available: bool = True
    inputs: list[dict[str, Any]] = field(default_factory=list)
    invocations: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    annotations: list[dict[str, Any]] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        # `name`, `context`, and `saved_at` stay at the top level so older
        # readers (and `export session:<name>`) keep working unchanged.
        return {
            "name": self.name,
            "context": self.context,
            "saved_at": self.saved_at,
            "schema_version": self.schema_version,
            "created_at": self.created_at or self.saved_at,
            "canarchy_version": self.canarchy_version,
            "provenance_available": self.provenance_available,
            "inputs": self.inputs,
            "invocations": self.invocations,
            "artifacts": self.artifacts,
            "annotations": self.annotations,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> SessionRecord:
        schema_version = int(payload.get("schema_version", LEGACY_SCHEMA_VERSION))
        return cls(
            name=payload["name"],
            context=payload.get("context", {}),
            saved_at=payload["saved_at"],
            schema_version=schema_version,
            created_at=payload.get("created_at", payload["saved_at"]),
            canarchy_version=payload.get("canarchy_version", "unknown"),
            provenance_available=bool(
                payload.get("provenance_available", schema_version >= SCHEMA_VERSION)
            ),
            inputs=list(payload.get("inputs", [])),
            invocations=list(payload.get("invocations", [])),
            artifacts=list(payload.get("artifacts", [])),
            annotations=list(payload.get("annotations", [])),
        )

    def entry_ids(self) -> set[str]:
        return {str(entry["input_id"]) for entry in self.inputs} | {
            str(entry["artifact_id"]) for entry in self.artifacts
        }


class SessionStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.cwd() / ".canarchy"
        self.sessions_dir = self.root / "sessions"
        self.active_session_path = self.root / "active_session.json"

    # -- store base ---------------------------------------------------------

    @property
    def store_base(self) -> Path:
        """The project directory that store-relative paths are anchored to."""
        return self.root.parent.resolve()

    def files_dir(self, name: str) -> Path:
        return self.sessions_dir / f"{name}.files"

    # -- commands -----------------------------------------------------------

    def save(
        self,
        name: str,
        context: dict[str, Any],
        *,
        arguments: dict[str, Any] | None = None,
        command: str = "session save",
        notes: list[str] | None = None,
        artifacts: list[str] | None = None,
    ) -> SessionRecord:
        """Create or refresh a session, recording provenance for its inputs.

        Re-saving an existing session keeps its creation timestamp, artifacts,
        annotations, and earlier invocations: a research record accumulates
        rather than being replaced.
        """
        self._ensure_paths()
        existing = self._read_session_if_present(name)
        now = _utc_now()

        record = SessionRecord(
            name=name,
            context=context,
            saved_at=now,
            created_at=existing.created_at if existing else now,
            inputs=self._record_inputs(context),
            invocations=list(existing.invocations) if existing else [],
            artifacts=list(existing.artifacts) if existing else [],
            annotations=list(existing.annotations) if existing else [],
        )
        record.invocations.append(
            self._build_invocation(
                record,
                command=command,
                arguments=arguments if arguments is not None else dict(context),
                source="session_command",
            )
        )
        for note in notes or []:
            record.annotations.append(self._build_annotation(record, note, ()))
        for artifact_path in artifacts or []:
            self._append_artifact(
                record,
                artifact_path,
                kind="analysis_output",
                derived_from=[str(entry["input_id"]) for entry in record.inputs],
                produced_by=record.invocations[-1]["invocation_id"],
                embed=False,
            )
        self._write_session(record)
        return record

    def load(self, name: str) -> SessionRecord:
        record = self._read_session(name)
        self._ensure_paths()
        self._write_json(self.active_session_path, record.to_payload())
        return record

    def show(self) -> dict[str, Any]:
        sessions: list[dict[str, Any]] = []
        if self.sessions_dir.exists():
            for session_path in sorted(self.sessions_dir.glob("*.json")):
                payload = self._read_json(session_path)
                record = SessionRecord.from_payload(payload)
                sessions.append(
                    {
                        "name": record.name,
                        "saved_at": record.saved_at,
                        "context": record.context,
                        "schema_version": record.schema_version,
                        "provenance_available": record.provenance_available,
                        "input_count": len(record.inputs),
                        "artifact_count": len(record.artifacts),
                        "annotation_count": len(record.annotations),
                    }
                )

        active = None
        if self.active_session_path.exists():
            active = self._read_json(self.active_session_path)

        return {
            "active_session": active,
            "sessions": sessions,
        }

    def verify(self, name: str, *, root: Path | None = None) -> dict[str, Any]:
        """Re-hash every recorded input and artifact without running anything."""
        record = self._read_session(name)
        if not record.provenance_available:
            raise SessionError(
                code="SESSION_PROVENANCE_UNAVAILABLE",
                message=(
                    f"Session '{name}' was saved before input provenance was recorded "
                    f"(schema version {record.schema_version})."
                ),
                hint=(
                    f"Re-run `canarchy session save {name}` with the interface, DBC, and "
                    "capture inputs to upgrade it to a verifiable record."
                ),
            )

        relocation_root = root.expanduser().resolve() if root is not None else None
        store_base = self.store_base
        inputs = [
            _verify_entry(entry, id_key="input_id", store_base=store_base, root=relocation_root)
            for entry in record.inputs
        ]
        artifacts = [
            _verify_entry(entry, id_key="artifact_id", store_base=store_base, root=relocation_root)
            for entry in record.artifacts
        ]

        blocked_ids = {
            str(entry["input_id"])
            for entry in inputs
            if entry["status"] in {"missing", "changed", "unverifiable"}
        }
        invocations = []
        for invocation in record.invocations:
            blocked = sorted(blocked_ids & set(invocation.get("inputs", [])))
            invocations.append(
                {
                    "invocation_id": invocation.get("invocation_id"),
                    "command": invocation.get("command"),
                    "source": invocation.get("source"),
                    "recorded_at": invocation.get("recorded_at"),
                    "reproduce_command": invocation.get("reproduce_command")
                    or invocation.get("command"),
                    "inputs": list(invocation.get("inputs", [])),
                    "status": "blocked" if blocked else "reproducible",
                    "blocked_by": blocked,
                }
            )

        summary = {
            "inputs_total": len(inputs),
            "artifacts_total": len(artifacts),
        }
        for label, entries in (("inputs", inputs), ("artifacts", artifacts)):
            for status in ("unchanged", "changed", "missing", "unverifiable"):
                summary[f"{label}_{status}"] = sum(1 for e in entries if e["status"] == status)

        # `incomplete` keeps "nothing is known to be wrong" distinct from
        # "everything checked out": an entry recorded without a hash cannot
        # support a claim either way.
        entries = (*inputs, *artifacts)
        if any(entry["status"] in {"changed", "missing"} for entry in entries):
            status = "degraded"
        elif any(entry["status"] == "unverifiable" for entry in entries):
            status = "incomplete"
        else:
            status = "verified"
        return {
            "session": record.to_payload(),
            "verification": {
                "status": status,
                "checked_at": _utc_now(),
                "root": str(relocation_root) if relocation_root else None,
                "inputs": inputs,
                "artifacts": artifacts,
                "invocations": invocations,
                "summary": summary,
                "required_actions": _required_actions(inputs, artifacts, relocation_root),
            },
        }

    def annotate(
        self, name: str, text: str, targets: list[str] | None = None
    ) -> tuple[SessionRecord, dict[str, Any]]:
        record = self._read_session(name)
        self._require_known_ids(record, targets or [], flag="--target")
        annotation = self._build_annotation(record, text, tuple(targets or ()))
        record.annotations.append(annotation)
        record.saved_at = _utc_now()
        self._write_session(record)
        return record, annotation

    def attach(
        self,
        name: str,
        artifact_path: str,
        *,
        kind: str = "analysis_output",
        derived_from: list[str] | None = None,
        command: str | None = None,
        embed: bool = False,
    ) -> tuple[SessionRecord, dict[str, Any]]:
        record = self._read_session(name)
        self._require_known_ids(record, derived_from or [], flag="--derived-from")

        produced_by = None
        if command:
            invocation = self._build_invocation(
                record,
                command=command,
                arguments={"declared": command},
                source="operator_declared",
                inputs=derived_from or [entry["input_id"] for entry in record.inputs],
                reproduce_command=command,
            )
            record.invocations.append(invocation)
            produced_by = invocation["invocation_id"]

        artifact = self._append_artifact(
            record,
            artifact_path,
            kind=kind,
            derived_from=list(derived_from or []),
            produced_by=produced_by,
            embed=embed,
        )
        record.saved_at = _utc_now()
        self._write_session(record)
        return record, artifact

    def bundle(self, name: str, output: Path) -> dict[str, Any]:
        """Write a portable copy of a session: manifest plus every file it names."""
        record = self._read_session(name)
        destination = output.expanduser()
        if destination.exists():
            raise SessionError(
                code="SESSION_BUNDLE_EXISTS",
                message=f"Bundle destination '{destination}' already exists.",
                hint="Choose a new path or remove the existing bundle first.",
            )

        as_zip = destination.suffix.lower() == ".zip"
        with tempfile.TemporaryDirectory() as staging_dir:
            staging = Path(staging_dir) / "bundle"
            staging.mkdir(parents=True)
            payload = record.to_payload()
            warnings: list[str] = []
            copied = 0

            for section, id_key, folder in (
                ("inputs", "input_id", "inputs"),
                ("artifacts", "artifact_id", "artifacts"),
            ):
                rewritten = []
                for entry in payload[section]:
                    entry = dict(entry)
                    if entry.get("embedded"):
                        rewritten.append(entry)
                        continue
                    source = _resolve_entry_path(entry, store_base=self.store_base, root=None)
                    entry_id = str(entry.get(id_key))
                    if not source.exists():
                        entry["status"] = "missing"
                        entry["detail"] = "File was not available when the bundle was written."
                        warnings.append(
                            f"SESSION_BUNDLE_INCOMPLETE: {entry_id} ({entry.get('path')}) "
                            "was not found and is referenced by hash only."
                        )
                        rewritten.append(entry)
                        continue
                    relative = f"{folder}/{entry_id}/{source.name}"
                    target = staging / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    copied += 1
                    entry["path"] = relative
                    entry["relative_path"] = relative
                    entry["absolute_path"] = None
                    entry["bundle_path"] = relative
                    rewritten.append(entry)
                payload[section] = rewritten

            payload["bundle"] = {
                "bundle_version": 1,
                "created_at": _utc_now(),
                "canarchy_version": __version__,
                "source_store": str(self.store_base),
            }
            self._write_json(staging / "manifest.json", payload)

            if as_zip:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
                    for path in sorted(staging.rglob("*")):
                        if path.is_file():
                            archive.write(path, path.relative_to(staging).as_posix())
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(staging, destination)

        return {
            "name": record.name,
            "bundle_path": str(destination),
            "bundle_format": "zip" if as_zip else "directory",
            "file_count": copied,
            "input_count": len(record.inputs),
            "artifact_count": len(record.artifacts),
            "warnings": warnings,
        }

    def import_bundle(self, source: Path, *, name: str | None = None) -> SessionRecord:
        """Install a bundle into this store, rewriting paths to the local copies."""
        origin = source.expanduser()
        if not origin.exists():
            raise SessionError(
                code="SESSION_BUNDLE_INVALID",
                message=f"Bundle '{origin}' was not found.",
                hint="Pass the directory or .zip file written by `canarchy session bundle`.",
            )

        with tempfile.TemporaryDirectory() as staging_dir:
            staging = Path(staging_dir)
            bundle_root = self._materialize_bundle(origin, staging)
            manifest_path = bundle_root / "manifest.json"
            if not manifest_path.exists():
                raise SessionError(
                    code="SESSION_BUNDLE_INVALID",
                    message=f"Bundle '{origin}' does not contain a manifest.json.",
                    hint="Re-create the bundle with `canarchy session bundle <name> --output`.",
                )
            payload = self._read_json(manifest_path)
            payload.pop("bundle", None)
            session_name = name or str(payload.get("name", ""))
            if not session_name:
                raise SessionError(
                    code="SESSION_BUNDLE_INVALID",
                    message="Bundle manifest does not name a session.",
                    hint="Pass `--name <name>` to import it under an explicit name.",
                )
            self._ensure_paths()
            if (self.sessions_dir / f"{session_name}.json").exists():
                raise SessionError(
                    code="SESSION_EXISTS",
                    message=f"Session '{session_name}' already exists in this store.",
                    hint="Pass `--name <other-name>` to import the bundle alongside it.",
                )

            files_dir = self.files_dir(session_name)
            for section, id_key in (("inputs", "input_id"), ("artifacts", "artifact_id")):
                rewritten = []
                for entry in payload.get(section, []):
                    entry = dict(entry)
                    bundle_path = entry.pop("bundle_path", None)
                    if not bundle_path or entry.get("embedded"):
                        rewritten.append(entry)
                        continue
                    staged = self._safe_bundle_member(bundle_root, str(bundle_path))
                    if not staged.exists():
                        entry["status"] = "missing"
                        entry["detail"] = "Bundle did not carry this file."
                        rewritten.append(entry)
                        continue
                    target = files_dir / bundle_path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(staged, target)
                    resolved = target.resolve()
                    entry["path"] = str(resolved)
                    entry["absolute_path"] = str(resolved)
                    entry["relative_path"] = _relative_to(resolved, self.store_base)
                    entry["status"] = entry.get("status", "recorded")
                    rewritten.append(entry)
                payload[section] = rewritten

            payload["name"] = session_name
            record = SessionRecord.from_payload(payload)
            self._write_session(record)
            return record

    # -- internals ----------------------------------------------------------

    def _record_inputs(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        inputs: list[dict[str, Any]] = []
        for role in ("capture", "dbc"):
            raw_path = context.get(role)
            if not raw_path:
                continue
            input_id = _stable_id("in", role, str(raw_path))
            record = _record_file(input_id, str(raw_path), store_base=self.store_base)
            provider = None
            if role == "dbc" and record.absolute_path:
                provider = _provider_metadata(Path(record.absolute_path))
            inputs.append(
                _input_payload(input_id=input_id, role=role, record=record, provider=provider)
            )
        return inputs

    def _build_invocation(
        self,
        record: SessionRecord,
        *,
        command: str,
        arguments: dict[str, Any],
        source: str,
        inputs: list[str] | None = None,
        reproduce_command: str | None = None,
    ) -> dict[str, Any]:
        sanitized, redacted = _sanitize_config(arguments)
        return {
            "invocation_id": f"inv-{len(record.invocations) + 1:04d}",
            "command": command,
            "arguments": sanitized,
            "redacted_argument_keys": redacted,
            "effective_config": effective_config(),
            "environment": environment_snapshot(),
            "canarchy_version": __version__,
            "recorded_at": _utc_now(),
            "source": source,
            "inputs": list(inputs)
            if inputs is not None
            else [e["input_id"] for e in record.inputs],
            "reproduce_command": reproduce_command,
        }

    def _build_annotation(
        self, record: SessionRecord, text: str, targets: tuple[str, ...]
    ) -> dict[str, Any]:
        return {
            "annotation_id": f"note-{len(record.annotations) + 1:04d}",
            "created_at": _utc_now(),
            "text": text,
            "targets": list(targets),
        }

    def _append_artifact(
        self,
        record: SessionRecord,
        raw_path: str,
        *,
        kind: str,
        derived_from: list[str],
        produced_by: str | None,
        embed: bool,
    ) -> dict[str, Any]:
        artifact_id = _stable_id("art", kind, raw_path)
        file_record = _record_file(artifact_id, raw_path, store_base=self.store_base)
        if file_record.status == "unreadable":
            raise SessionError(
                code="SESSION_ARTIFACT_UNREADABLE",
                message=f"Artifact '{raw_path}' could not be read: {file_record.detail}",
                hint="Pass a readable file path to record as session evidence.",
            )

        artifact: dict[str, Any] = {
            "artifact_id": artifact_id,
            "kind": kind,
            **file_record.to_payload(),
            "produced_by": produced_by,
            "derived_from": list(derived_from),
            "recorded_at": _utc_now(),
            "embedded": None,
        }
        if embed:
            artifact["embedded"] = self._embed_payload(Path(file_record.absolute_path or raw_path))
        # Re-attaching the same artifact refreshes it rather than duplicating it.
        record.artifacts = [
            entry for entry in record.artifacts if entry.get("artifact_id") != artifact_id
        ]
        record.artifacts.append(artifact)
        return artifact

    def _embed_payload(self, path: Path) -> dict[str, Any]:
        payload = path.read_bytes()
        if len(payload) > _MAX_EMBED_BYTES:
            raise SessionError(
                code="SESSION_ARTIFACT_UNREADABLE",
                message=(
                    f"Artifact '{path}' is {len(payload)} bytes; --embed is limited to "
                    f"{_MAX_EMBED_BYTES} bytes."
                ),
                hint="Attach the artifact without --embed to reference it by hash instead.",
            )
        media_type = _media_type_for(path)
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            return {
                "media_type": media_type,
                "encoding": "base64",
                "content": base64.b64encode(payload).decode("ascii"),
            }
        return {"media_type": media_type, "encoding": "utf-8", "content": text}

    def _require_known_ids(self, record: SessionRecord, ids: list[str], *, flag: str) -> None:
        known = record.entry_ids()
        unknown = [entry_id for entry_id in ids if entry_id not in known]
        if unknown:
            raise SessionError(
                code="SESSION_INPUT_UNKNOWN",
                message=f"Session '{record.name}' has no entry {', '.join(sorted(unknown))}.",
                hint=(
                    f"Run `canarchy session verify {record.name} --json` to list recorded "
                    f"identifiers before passing {flag}."
                ),
            )

    def _materialize_bundle(self, origin: Path, staging: Path) -> Path:
        if origin.is_dir():
            return origin
        try:
            with zipfile.ZipFile(origin) as archive:
                for member in archive.namelist():
                    # Reject traversal before writing anything to disk.
                    self._safe_bundle_member(staging, member)
                archive.extractall(staging)
        except zipfile.BadZipFile as exc:
            raise SessionError(
                code="SESSION_BUNDLE_INVALID",
                message=f"Bundle '{origin}' is not a readable zip archive: {exc}",
                hint="Pass the directory or .zip file written by `canarchy session bundle`.",
            ) from exc
        return staging

    def _safe_bundle_member(self, base: Path, member: str) -> Path:
        candidate = (base / member).resolve()
        if not _is_within(candidate, base.resolve()):
            raise SessionError(
                code="SESSION_BUNDLE_INVALID",
                message=f"Bundle entry '{member}' would be written outside the destination.",
                hint="Re-create the bundle with `canarchy session bundle <name> --output`.",
            )
        return candidate

    def _read_session_if_present(self, name: str) -> SessionRecord | None:
        session_path = self.sessions_dir / f"{name}.json"
        if not session_path.exists():
            return None
        return self._parse_session(self._read_json(session_path), name=name)

    def _read_session(self, name: str) -> SessionRecord:
        session_path = self.sessions_dir / f"{name}.json"
        if not session_path.exists():
            raise SessionError(
                code="SESSION_NOT_FOUND",
                message=f"Session '{name}' was not found.",
                hint="Save the session first or inspect `session show` for available sessions.",
            )
        return self._parse_session(self._read_json(session_path), name=name)

    def _parse_session(self, payload: dict[str, Any], *, name: str) -> SessionRecord:
        schema_version = int(payload.get("schema_version", LEGACY_SCHEMA_VERSION))
        if schema_version > SCHEMA_VERSION:
            raise SessionError(
                code="SESSION_SCHEMA_UNSUPPORTED",
                message=(
                    f"Session '{name}' uses manifest schema version {schema_version}; this "
                    f"CANarchy records version {SCHEMA_VERSION}."
                ),
                hint="Upgrade CANarchy to read this session record.",
            )
        return SessionRecord.from_payload(payload)

    def _write_session(self, record: SessionRecord) -> None:
        self._ensure_paths()
        payload = record.to_payload()
        self._write_json(self.sessions_dir / f"{record.name}.json", payload)
        self._write_json(self.active_session_path, payload)

    def _ensure_paths(self) -> None:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _read_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text())

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        """Publish a complete JSON file; an interrupted write leaves the old one."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".pending-", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(self._to_json(payload) + "\n")
        try:
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _to_json(self, payload: dict[str, Any]) -> str:
        return json.dumps(payload, sort_keys=True)


def _required_actions(
    inputs: list[dict[str, Any]], artifacts: list[dict[str, Any]], root: Path | None
) -> list[str]:
    """Say what an operator must restore before the analysis can be reproduced."""
    actions: list[str] = []
    for entry in inputs:
        label = f"{entry.get('role', 'input')} input {entry['input_id']} ({entry.get('path')})"
        if entry["status"] == "missing":
            hint = (
                "restore it at that path"
                if root is None
                else f"place it under the relocation root {root}"
            )
            actions.append(
                f"Missing {label}: {hint}, or re-run verification with "
                f"`--root <directory>` pointing at the relocated inputs. "
                f"Expected sha256 {entry['expected_sha256']}."
            )
        elif entry["status"] == "changed":
            actions.append(
                f"Changed {label}: recorded sha256 {entry['expected_sha256']} but found "
                f"{entry['actual_sha256']}. Recover the original bytes; analysis run against "
                "the current file is not the recorded analysis."
            )
        elif entry["status"] == "unverifiable":
            actions.append(
                f"Unverifiable {label}: {entry.get('detail') or 'no content hash was recorded'}. "
                "Re-save the session to record one."
            )
    for entry in artifacts:
        label = f"artifact {entry['artifact_id']} ({entry.get('path')})"
        if entry["status"] == "missing":
            actions.append(
                f"Missing {label}: the recorded result is gone. Reproduce it from the inputs "
                "or re-attach it with `session attach --embed` to keep it inside the record."
            )
        elif entry["status"] == "changed":
            actions.append(
                f"Changed {label}: recorded sha256 {entry['expected_sha256']} but found "
                f"{entry['actual_sha256']}."
            )
    return actions


def build_session_context(args: Any) -> dict[str, Any]:
    context: dict[str, Any] = {}
    for key in ("interface", "dbc", "capture"):
        value = getattr(args, key, None)
        if value is not None:
            context[key] = value
    return context


def session_arguments(args: Any) -> dict[str, Any]:
    """Collect the command arguments worth recording for reproduction.

    Argparse namespaces carry front-end plumbing (`--json`, log level) that says
    nothing about the analysis, so only analysis-relevant values are recorded,
    and `_sanitize_config` still strips anything secret-looking.
    """
    recorded: dict[str, Any] = {}
    for key in (
        "name",
        "interface",
        "dbc",
        "capture",
        "note",
        "kind",
        "root",
        "target",
        "derived_from",
        "embed",
    ):
        value = getattr(args, key, None)
        if value not in (None, False, [], ()):
            recorded[key] = value
    return recorded
