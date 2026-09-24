# Design Spec: TUI Identifier Explorer

## Document Control

| Field | Value |
|---|---|
| Status | Implemented |
| Command surface | `canarchy tui`; `canarchy filter <expression>` |
| Primary area | Shared frame analysis and TUI presentation |
| Related specs | `docs/design/tui-shell.md`, `docs/design/transport-core-commands.md` |

## Goal

Make the Traffic workspace an investigation surface: group frames by bus and typed CAN identifier, keep a chronological event log available, and let an operator inspect a stable frame while capture continues.

## User-Facing Motivation

A fixed append-only table makes repeated IDs hard to compare, scrolls away from inspected evidence, and hides byte changes. The operator needs a bounded, keyboard-driven summary and a complete, non-color-dependent detail view without changing the CLI's command contract.

## Requirements

| ID | Type | Requirement |
|---|---|---|
| REQ-TUIX-01 | Event-driven | When frame or decoded-message events with embedded frames arrive, the system shall group them by `(interface or source, arbitration_id, is_extended_id)` and keep standard/extended IDs and buses distinct. |
| REQ-TUIX-02 | Ubiquitous | The system shall show each retained identifier's count, recent rate, age, last payload, changed-byte offsets, and activity plot, and shall provide a separate chronological event-log mode. |
| REQ-TUIX-03 | Event-driven | When the operator selects an identifier or historical event, the system shall freeze its inspector independently of capture and show incoming and dropped counts with a return-to-live action that advances the log cursor to the newest visible event. |
| REQ-TUIX-04 | State-driven | While inspection is frozen, the system shall preserve the selected key and detail snapshot across arrivals, sorts, filters, workspace switches, and backlog eviction. |
| REQ-TUIX-05 | Ubiquitous | The system shall show raw timestamp, identifier type and flags, complete payload hex and bits, decoded signals when present, and bounded recent history; changed bytes shall use zero-based offsets and a textual caret legend. |
| REQ-TUIX-06 | Event-driven | When an operator filters traffic by ID, PGN, or J1939 source address, the system shall apply the same frame predicate used by `canarchy filter`, with `sa==` matching extended frames only; while following live traffic, hidden frames shall not replace the inspector selection. |
| REQ-TUIX-07 | Unwanted behaviour | If an operator requests an unknown sort field or invalid typed filter, the system shall show a diagnostic and leave the previous sort or filter unchanged. |
| REQ-TUIX-08 | Ubiquitous | The system shall sort identifier counts, rates, age, and IDs by underlying numeric values and event-log time by the underlying timestamp rather than formatted cells. |
| REQ-TUIX-09 | Ubiquitous | The system shall bound retained frame observations by the configured backlog cap, resize that cap in both directions, and keep rate/change analysis outside Textual. |

## Command Surface

```text
canarchy tui
  v                       switch identifier summary / chronological event log
  F4                      freeze inspection / return live
  Enter                   inspect the selected identifier or event
  /filter traffic <expr>  apply shared frame filter grammar to traffic
  /sort traffic <column>  sort the active traffic view

canarchy filter 'sa==0x31' --file capture.log --json
```

`/filter traffic` still accepts a plain substring for legacy text filtering. Expressions beginning with a supported filter atom use the canonical frame predicate; invalid typed expressions are reported rather than silently treated as text. `sa==` is also available in the non-interactive CLI filter command. It accepts decimal, `0x`-prefixed hex, or bare hex source addresses in the 0–255 range, supports `&&`/`||`, and never matches standard frames.

## Responsibilities And Boundaries

`canarchy.tui_explorer` owns frame grouping, bounded history, rate, change offsets, activity plots, and detail text. It accepts raw `frame` events and `decoded_message` events with embedded frames, correlating child `signal` events by source, frame index, and message name. It uses `CanFrame` and the shared J1939 identifier decomposition. `canarchy.transport._compile_filter` owns the CLI/TUI filter predicate. `canarchy.tui_app` owns only keyboard actions, table rendering, focus, follow state, and status labels. The app continues to consume canonical event envelopes and the same command executor as CLI/REPL. No new transmit path or output schema is introduced.

## Data Model

`IdentifierKey` contains `bus`, numeric `arbitration_id`, and `is_extended_id`. `FrameObservation` contains a monotonic sequence, its source event index, the key, a `CanFrame`, arrival time, and optional decoded signal text. `IdentifierActivity` retains the recent observations for a key, a count while that key remains in the bounded backlog, latest payload, and offsets changed from the previous payload. `TrafficExplorer` keeps at most `backlog_cap` observations globally; an identifier with no retained observations is evicted. Selecting an event-log row snapshots that exact observation rather than the latest frame for its ID. The inspector holds the detail snapshot while frozen, even after its backing history is evicted.

The rate is `(n - 1) / (last - first)` over at most the latest 16 observations for an identifier, using frame timestamps when increasing and arrival times otherwise. Age uses monotonic arrival time. The plot shows eight buckets of recent activity. A byte is changed when its value or presence differs from the previous payload; the first observation has no change baseline.

## Output Contracts

The identifier summary is a human-only table: `bus`, `id`, `type`, `count`, `Hz`, `age`, `last data`, `Δ byte`, `activity`. The inspector includes the complete raw payload and a `^ changed since previous payload` legend. The status band shows `LIVE` or `INSPECTING`, incoming frames since freeze, capture drops, and `v`/`F4` controls. CLI `filter --json`/`--jsonl`/`--text` retain their existing schemas; `sa==` only adds an accepted expression.

## Error Contracts

| Code or diagnostic | Trigger | Exit code |
|---|---|---|
| `INVALID_FILTER_EXPRESSION` | Invalid CLI `sa==` or other filter atom | 2 |
| `/filter traffic: INVALID_FILTER_EXPRESSION` | Invalid typed TUI filter | None; existing filter retained |
| `/sort traffic: unknown column` | Unknown TUI sort field | None; existing sort retained |

## Deferred Decisions

Persistent identifier counts after all history for a key is evicted, richer DBC linkage across separately invoked commands, and ECU-specific signal inference are outside this bounded live view. Hardware timing is not benchmarked in CI.
