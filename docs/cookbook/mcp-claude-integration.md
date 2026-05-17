# Wire CANarchy into Claude Desktop or Claude Code

## Goal

Run `canarchy` as an MCP server so an agent can call CANarchy commands
directly. This is the quick-start; see [MCP Install](../mcp_install.md)
for the canonical reference with OS-specific paths, generic-client
configuration, and troubleshooting.

## Prerequisites

* CANarchy installed and on your `PATH` (`canarchy --version` works).
* Claude Desktop or Claude Code installed.

## Verify the MCP server runs

```bash
canarchy mcp serve --help
```

You should see the standard CLI envelope describing the MCP stdio
server. The server speaks Model Context Protocol over stdin and stdout;
do not run it interactively unless you are piping JSON-RPC into it.

## Claude Desktop

Add the following block to your `claude_desktop_config.json`. On macOS
this is `~/Library/Application Support/Claude/claude_desktop_config.json`;
on Windows it is `%AppData%/Claude/claude_desktop_config.json`.

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

Restart Claude Desktop. The CANarchy tools should appear in the tool
picker.

## Claude Code

Add CANarchy as an MCP server via the project or user-scoped MCP
configuration. The exact location depends on the Claude Code version;
the config block has the same shape as above:

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

## Verify from an agent

Ask the agent to call `canarchy capture-info` against an in-tree
fixture:

> Run `canarchy capture-info` on `tests/fixtures/j1939_heavy_vehicle.candump`
> and summarise the result.

The agent should invoke the MCP tool and return the canonical envelope.

## Where to go next

* [MCP Install](../mcp_install.md) — full install reference (other clients, troubleshooting)
* [Agent Guide](../agents.md)
* [Command Spec — mcp serve](../command_spec.md)
