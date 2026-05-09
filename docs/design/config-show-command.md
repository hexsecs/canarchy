# Design Spec: Config Show Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy config show` |
| Primary area | CLI, transport, configuration |
| Related specs | `docs/design/active-command-safety.md`, `docs/design/mcp-server.md`, `docs/design/transport-core-commands.md` |

## Goal

Define the current implemented behavior of `config show` so operators and agents can inspect the effective transport configuration, the provenance of each setting, and the config-file discovery state through a stable command contract.

## User-Facing Motivation

Operators need an inspectable way to answer basic configuration questions such as which backend is active, whether settings came from defaults, the config file, or environment variables, and whether a J1939 DBC default is configured.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-CONFIG-01` | Ubiquitous | The system shall provide a `canarchy config show` command for inspecting the effective transport configuration. |
| `REQ-CONFIG-02` | Event-driven | When `config show` is invoked, the system shall return the effective values for transport backend, interface, capture limit, capture timeout, active-ack safety, and default J1939 DBC configuration. |
| `REQ-CONFIG-03` | Ubiquitous | The `config show` result shall include a `sources` map that records whether each effective value came from the environment, the config file, or the built-in defaults. |
| `REQ-CONFIG-04` | Optional feature | Where an environment variable overrides a config-file value, the system shall use the environment value and mark its source as `env`. |
| `REQ-CONFIG-05` | Optional feature | Where a value is set in the config file and not overridden by the environment, the system shall use the config-file value and mark its source as `file`. |
| `REQ-CONFIG-06` | State-driven | While no environment or config-file override exists for a supported setting, the system shall use the built-in default and mark its source as `default`. |
| `REQ-CONFIG-07` | Ubiquitous | The `config show` result shall report the resolved config-file path and whether that file currently exists. |
| `REQ-CONFIG-08` | Ubiquitous | `config show` shall preserve the standard output modes (`--json`, `--jsonl`, `--text`, `--raw`) with command-specific formatting over the same configuration payload. |

## Command Surface

```text
canarchy config show [--json] [--jsonl] [--text] [--raw]
```

## Responsibilities And Boundaries

In scope:

* effective transport/backend configuration reporting
* source precedence reporting across defaults, file config, and environment variables
* config-file path and existence metadata

Out of scope:

* validating that every configured path or backend is usable for a later command invocation
* editing or writing configuration files
* command-specific runtime state beyond the effective configuration snapshot

## Data Model

The top-level `data` payload includes:

* `backend`
* `interface`
* `capture_limit`
* `capture_timeout`
* `require_active_ack`
* `j1939_dbc`
* `sources`
* `config_file`
* `config_file_found`

The `sources` object includes one source entry for each effective configuration field and uses the values `env`, `file`, or `default`.

## Output Contracts

### JSON

`--json` emits the standard CANarchy result envelope with the configuration snapshot under `data`.

### JSONL

`--jsonl` emits a single CANarchy result object because `config show` returns a structured payload rather than an event stream.

### Table

`--text` renders a human-readable configuration summary that shows each effective value together with its source annotation and ends with the config-file path plus its found/not-found status.

### Raw

`--raw` prints `config show` on success.

## Error Contracts

No command-specific error codes are defined for `config show`. Generic CLI and configuration parsing errors apply if underlying configuration loading fails.

## Deferred Decisions

* whether future config domains beyond transport and J1939 defaults should appear in this command
* whether secrets or credential-bearing config fields will require redaction rules if they are ever added
