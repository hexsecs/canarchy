"""Helpers for `canarchy mcp install`.

Pure path-resolution and config-merge logic for writing the canarchy MCP
server block into a client configuration file. All disk I/O and the
interactive confirmation live in the CLI handler; this module only
computes *what* to write so it can be unit-tested without touching the
filesystem.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

CANARCHY_SERVER_KEY = "canarchy"


class McpInstallError(Exception):
    """Structured failure while planning an MCP install."""

    def __init__(self, code: str, message: str, hint: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


def default_server_block(command: str = "canarchy") -> dict[str, object]:
    """Return the `mcpServers.canarchy` entry for ``command``."""
    return {"command": command, "args": ["mcp", "serve"]}


def resolve_config_path(client: str, *, override: str | None = None) -> Path:
    """Resolve the client config path, honouring an explicit ``override``."""
    if override:
        return Path(override).expanduser()
    if client == "claude-desktop":
        return _claude_desktop_path()
    if client == "claude-code":
        # Project-scoped MCP config in the current working directory — the
        # least-surprise, self-contained location for Claude Code.
        return Path.cwd() / ".mcp.json"
    raise ValueError(f"unknown client: {client!r}")


def _claude_desktop_path() -> Path:
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Claude"
            / "claude_desktop_config.json"
        )
    if os.name == "nt" or sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


@dataclass(slots=True, frozen=True)
class InstallPlan:
    action: str  # "create" | "update" | "unchanged"
    config: dict[str, object]
    block: dict[str, object]


def plan_install(existing_text: str | None, *, command: str = "canarchy") -> InstallPlan:
    """Compute the merged config to write.

    ``existing_text`` is the current file contents, or ``None`` when the
    file does not yet exist. The canarchy block is merged into
    ``mcpServers`` without disturbing any other entry. Raises
    ``McpInstallError`` when the existing file is not a usable MCP config
    or already contains a *different* canarchy entry.
    """
    block = default_server_block(command)

    if existing_text is None or not existing_text.strip():
        return InstallPlan("create", {"mcpServers": {CANARCHY_SERVER_KEY: block}}, block)

    try:
        config = json.loads(existing_text)
    except json.JSONDecodeError as exc:
        raise McpInstallError(
            "MCP_INSTALL_INVALID_CONFIG",
            "The existing client config is not valid JSON.",
            "Fix or remove the file, then re-run; use --dry-run to preview.",
        ) from exc

    if not isinstance(config, dict):
        raise McpInstallError(
            "MCP_INSTALL_INVALID_CONFIG",
            "The existing client config is not a JSON object.",
            "Point --config-path at a JSON object with an `mcpServers` map.",
        )

    servers = config.get("mcpServers", {})
    if servers in (None, {}):
        servers = {}
    elif not isinstance(servers, dict):
        raise McpInstallError(
            "MCP_INSTALL_INVALID_CONFIG",
            "The existing config has a non-object `mcpServers` value.",
            "Repair `mcpServers` to be a JSON object before installing.",
        )

    existing_entry = servers.get(CANARCHY_SERVER_KEY)
    if existing_entry is not None:
        if existing_entry == block:
            return InstallPlan("unchanged", config, block)
        raise McpInstallError(
            "MCP_INSTALL_CONFLICT",
            "A different `mcpServers.canarchy` entry already exists.",
            "Remove or edit the existing entry, or pass --command to match it, then re-run.",
        )

    merged_servers = dict(servers)
    merged_servers[CANARCHY_SERVER_KEY] = block
    merged_config = dict(config)
    merged_config["mcpServers"] = merged_servers
    return InstallPlan("update", merged_config, block)
