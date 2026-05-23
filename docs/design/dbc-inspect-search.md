# Design Spec: `dbc inspect --search` and `dbc signals`

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy dbc inspect`, `canarchy dbc signals` |
| Primary area | CLI, DBC, MCP |
| Issue | #361 |

## Goal

Allow operators to search within a DBC file for signals and messages by keyword or regex, eliminating the manual full-table scan when looking for a specific signal (e.g. `L_MIL`, `VehicleSpeed`, `OilTemp`) across a file with hundreds of messages and thousands of signals.

## User-Facing Motivation

DBCs routinely have 50–200+ messages and 500–3000+ signals. Finding the signal you want is currently a full-table scan of `dbc inspect` output. A `--search` flag turns that into a single filtered command, and the new `dbc signals` subcommand provides a signal-centric shorthand.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-DBC-SEARCH-01` | Ubiquitous | The system shall accept a `--search <pattern>` flag on `canarchy dbc inspect`. |
| `REQ-DBC-SEARCH-02` | Ubiquitous | The system shall provide a `canarchy dbc signals` command with `--search` and `--message` flags. |
| `REQ-DBC-SEARCH-03` | Event-driven | When `--search <pattern>` is supplied to `dbc inspect` (without `--signals-only`), the system shall return only messages whose name matches, or messages that contain at least one matching signal; within each retained message only matching signals are included. |
| `REQ-DBC-SEARCH-04` | Event-driven | When `--search <pattern>` is supplied together with `--signals-only`, the system shall filter the flat signals list to those whose name or message name matches. |
| `REQ-DBC-SEARCH-05` | Event-driven | When `dbc signals [--search <pattern>]` is invoked, the system shall return a signal-centric list equivalent to `dbc inspect --signals-only [--search <pattern>]`. |
| `REQ-DBC-SEARCH-06` | Ubiquitous | Pattern matching shall be case-insensitive. |
| `REQ-DBC-SEARCH-07` | Ubiquitous | The pattern shall be treated as a Python `re` regex; if the pattern is not a valid regex the system shall fall back to a literal substring match. |
| `REQ-DBC-SEARCH-08` | Ubiquitous | `--search` shall be additive with the existing `--message` flag. |
| `REQ-DBC-SEARCH-09` | Unwanted behaviour | If `--search` matches no messages or signals, the system shall return an empty `messages` or `signals` list with exit code 0. |
| `REQ-DBC-SEARCH-10` | Ubiquitous | The `dbc_inspect` MCP tool shall accept an optional `search` parameter. |
| `REQ-DBC-SEARCH-11` | Ubiquitous | A new `dbc_signals` MCP tool shall expose `dbc`, `message`, and `search` parameters. |

## Command Surface

```text
canarchy dbc inspect <dbc> [--message <name>] [--signals-only] [--search <pattern>]
canarchy dbc signals <dbc> [--message <name>] [--search <pattern>]
```

## Responsibilities And Boundaries

In scope:

* Case-insensitive regex/substring filtering on message names and signal names
* Additive composition with `--message` and `--signals-only`
* Signal-centric `dbc signals` shorthand
* MCP `search` parameter on `dbc_inspect` and new `dbc_signals` tool

Out of scope:

* Fuzzy / approximate matching
* Filtering on signal metadata (unit, range, bit position)
* Persistent saved searches

## Data Model

The filter is applied post-serialization to the `to_payload()` output from `DatabaseInspection`. For the message-level view, retained messages include only the matching subset of their signals and an updated `signal_count`. The database-level totals (`database.message_count`, `database.signal_count`) reflect the unfiltered database.

## Output Contracts

`dbc signals` returns the same payload shape as `dbc inspect --signals-only`. The `format_dbc_table` text renderer renders both commands using the same signal-row path.
