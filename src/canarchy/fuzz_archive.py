"""Durable, independently inspectable guided-fuzz campaign evidence."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from canarchy import __version__
from canarchy.fuzz_guided import Finding


def _write_record(path: Path, payload: dict[str, Any]) -> None:
    """Publish a complete JSON record; an interrupted write leaves no partial JSON."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".pending-", delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, sort_keys=True, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        # POSIX directory fsync also persists the published filename. Windows
        # does not expose this operation; complete-file replacement still applies.
        if os.name == "posix":
            fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    except (ValueError, TypeError) as exc:
        raise OSError(f"Cannot serialize evidence record {path}: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class FindingArchive:
    """One fresh directory per campaign; no corpus file is used as evidence."""

    def __init__(self, root: str | Path, config: dict[str, Any], seeds: list[bytes]):
        self.campaign_id = uuid4().hex
        self.path = Path(root).expanduser().resolve() / self.campaign_id
        self.path.mkdir(parents=True, exist_ok=False)
        _write_record(
            self.path / "campaign.json",
            {
                "schema_version": 1,
                "campaign_id": self.campaign_id,
                "created_at": datetime.now(UTC).isoformat(),
                "canarchy_version": __version__,
                "config": config,
                "initial_seeds": [
                    {"seed_id": f"s{i}", "data": seed.hex()} for i, seed in enumerate(seeds)
                ],
            },
        )
        self.count = 0

    def save(self, finding: Finding) -> None:
        _write_record(
            self.path / f"finding-{finding.iteration:08d}.json",
            {
                "schema_version": 1,
                "recorded_at": datetime.now(UTC).isoformat(),
                **finding.to_payload(),
            },
        )
        self.count += 1
