# Install the CANarchy MCP server in an agent client

`canarchy mcp serve` exposes the CLI as an [MCP](https://modelcontextprotocol.io/)
stdio server. Any MCP-capable client can call CANarchy tools the same
way it calls its own built-in tools. This page covers the canonical
install paths.

For the agent-side workflows themselves (which tools to call, the
event-stream contract, security guidance), see the
[Agent Guide](agents.md) and the [Command Spec](command_spec.md).

## Prerequisites

Confirm `canarchy` is on your `PATH` and the MCP server starts cleanly:

```bash
canarchy --version
canarchy mcp serve --help
```

If either fails, follow the
[Getting Started](getting_started.md#install-and-sync) install steps
first. A clean `canarchy doctor --text` run is a fast way to verify the
local environment before wiring it into a client.

## Claude Desktop

Edit Claude Desktop's MCP config file:

| Platform | Config path |
|----------|-------------|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

Add a `canarchy` entry under `mcpServers`:

```json
{
  "mcpServers": {
    "canarchy": {
      "command": "canarchy",
      "args": ["mcp", "serve"]
    }
  }
}
```

If `canarchy` is installed inside a project venv rather than on the
system `PATH`, give the absolute path to the binary:

```json
{
  "mcpServers": {
    "canarchy": {
      "command": "/path/to/.venv/bin/canarchy",
      "args": ["mcp", "serve"]
    }
  }
}
```

Restart Claude Desktop. The CANarchy tools will appear in the tool
picker.

## Claude Code

Claude Code reads MCP server entries from project-scoped or user-scoped
configuration. The block shape is the same as Claude Desktop:

```json
{
  "mcpServers": {
    "canarchy": {
      "command": "canarchy",
      "args": ["mcp", "serve"]
    }
  }
}
```

Drop the block into the appropriate Claude Code config file. The CLI
also accepts MCP servers via:

```bash
claude mcp add canarchy canarchy mcp serve
```

(Refer to the Claude Code documentation for the current command surface
of your installed version.)

## Other MCP clients

Any client that speaks MCP over stdio can run CANarchy with the same
command. A generic configuration looks like:

```yaml
mcp_servers:
  canarchy:
    command: canarchy
    args:
      - mcp
      - serve
```

Cursor, Continue, Cline, and similar editor integrations follow the
same pattern. The only requirement is that the client launches
`canarchy mcp serve` as a subprocess and speaks JSON-RPC on stdio.

## Verify the integration

Ask the agent to call CANarchy against one of the in-repo fixtures:

> Run `canarchy capture-info` on
> `tests/fixtures/j1939_heavy_vehicle.candump` and summarise the result.

A correctly wired-up client invokes the `capture_info` MCP tool and
returns the canonical envelope. The `doctor` tool is the fastest
end-to-end smoke check because it requires no fixture:

> Run `canarchy doctor` and report any warnings.

## Configuration tips

* **Per-project canarchy with uv.** If the agent should always pick up a
  specific project's editable install, point `command` at `uv` and pass
  `["run", "canarchy", "mcp", "serve"]` as `args`, with `cwd` set to
  the project root. Some clients support `cwd` directly; otherwise wrap
  in a small launcher script.
* **Active-transmit safety.** Active commands such as `send` and
  `gateway` already require `--ack-active`. Agents must surface the
  confirmation explicitly. See
  [`SECURITY.md`](https://github.com/hexsecs/canarchy/blob/main/SECURITY.md).
* **Logging.** The MCP server logs to stderr. The agent client typically
  surfaces stderr in its diagnostics pane; check there first when a
  tool call misbehaves.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Tools never appear in the client | Wrong `command` path | Run `which canarchy` and use the absolute path in the config. |
| `INVALID_ARGUMENTS` for known-good calls | Client passes wrong argv shape | Compare against the MCP tool inputSchema; `canarchy mcp serve --help` documents the bridging contract. |
| Tools error with `DBC_CACHE_MISS` | opendbc cache empty | Run `canarchy dbc cache refresh --provider opendbc` once locally; the agent then has cached data to read. |
| `python-can` import errors at startup | Missing optional dependency | Re-run `uv sync` in the project, or `pipx install canarchy` for a global install. |

`canarchy doctor` is the canonical first stop for environment problems;
each non-ok check ships a copy-pasteable remediation hint.

## Where to go next

* [Agent Guide](agents.md) — agent-side workflows and policies.
* [Command Spec](command_spec.md) — every CLI command, mirrored as MCP tools where applicable.
* [Cookbook: Wire CANarchy into Claude Desktop or Claude Code](cookbook/mcp-claude-integration.md) — the short version of this page.
