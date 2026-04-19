"""Local filesystem DBC provider."""

from __future__ import annotations

from pathlib import Path

from canarchy.dbc import DbcError
from canarchy.dbc_provider import DbcDescriptor, DbcResolution


class LocalDbcProvider:
    name = "local"

    def search(self, query: str, limit: int = 20) -> list[DbcDescriptor]:
        # Local provider resolves explicit paths only; no catalog to search.
        return []

    def resolve(self, ref: str) -> DbcResolution:
        path = Path(ref)
        if not path.exists():
            raise DbcError(
                code="DBC_NOT_FOUND",
                message=f"DBC file '{ref}' was not found.",
                hint="Pass a readable DBC file path with `--dbc`.",
            )
        if not path.is_file():
            raise DbcError(
                code="DBC_NOT_FOUND",
                message=f"'{ref}' is not a file.",
                hint="Pass a path to a .dbc file.",
            )
        descriptor = DbcDescriptor(
            provider="local",
            name=path.name,
            version=None,
            source_ref=ref,
            cache_path=None,
            sha256=None,
        )
        return DbcResolution(descriptor=descriptor, local_path=path.resolve(), is_cached=False)

    def refresh(self, ref: str | None = None) -> list[DbcDescriptor]:
        return []
