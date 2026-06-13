# Design Spec: Web Dashboard (`web serve`)

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy web serve` |
| Primary area | CLI, presentation |

## Goal

Add a presentation tier that streams the existing JSONL event envelope to a
small browser-based dashboard. The CLI remains the contract; the web layer is
a view, like the TUI.

## User-Facing Motivation

Operators triaging a capture want a live, glanceable view — frame stream, bus
status, decoded signals, J1939 activity, UDS transactions — without leaving
the structured-output model or installing a heavy GUI.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-WEB-01` | Ubiquitous | The system shall provide a `canarchy web serve --file <capture> [--dbc <ref>] [--bind <host:port>] [--rate <x>] [--loop]` command that starts an HTTP + WebSocket server streaming the capture as canonical envelope events. |
| `REQ-WEB-02` | Ubiquitous | The server shall be read-only: it shall expose no active-transmit endpoints, and every non-GET HTTP request shall be rejected with status 405 and a structured `WEB_READ_ONLY` error body. |
| `REQ-WEB-03` | Event-driven | When a WebSocket client connects to `/ws`, the system shall stream the capture's events in timestamp order, paced by inter-event timestamp deltas divided by `--rate` (gaps capped at 1 s; `--rate 0` disables pacing), and shall mark end-of-stream with an `alert` event carrying code `STREAM_COMPLETE` followed by a close frame, unless `--loop` restarts the stream. |
| `REQ-WEB-04` | Ubiquitous | The streamed events shall be the canonical envelope objects: `frame` per frame; `j1939_pgn` per 29-bit frame annotated with the bundled PGN label/name and source-address name; `decoded_message` where a `--dbc` database decodes the frame; and `uds_transaction` for transactions reassembled from the capture — each carrying `event_type`, `payload`, `source`, and `timestamp`. |
| `REQ-WEB-05` | Ubiquitous | `GET /` shall serve the bundled dependency-light single-file SPA (`canarchy/resources/web/index.html`, vanilla JS, no frontend framework) rendering the live frame stream, bus status, decoded signals, J1939 PGN/source-address activity, and recent UDS transactions. `GET /api/status` shall return server status JSON including `read_only`, `event_count`, `clients`, and source metadata. |
| `REQ-WEB-06` | Unwanted behaviour | If the bind address is malformed or the port cannot be bound, the system shall return a structured error with code `WEB_BIND_INVALID` / `WEB_BIND_FAILED` and exit code 1; if the capture file is missing or invalid, the existing transport error codes apply with exit code 2. |
| `REQ-WEB-07` | Ubiquitous | The WebSocket implementation shall be a minimal RFC 6455 server (handshake accept key, unmasked server→client text frames with 7/16/64-bit lengths, masked client-frame reads, ping→pong, close handling) with no third-party dependency. |
| `REQ-WEB-08` | Ubiquitous | On startup the CLI shall emit a canonical envelope reporting the dashboard `url`, `read_only: true`, source metadata, and `event_count`, then serve until interrupted; `web serve` shall not be exposed as an MCP tool (long-running front end, like `shell`/`tui`). |

## Command Surface

```text
canarchy web serve --file <capture> [--dbc <path|provider:ref>] \
    [--bind <host:port>] [--rate <multiplier>] [--loop] \
    [--offset <n>] [--max-frames <n>] [--seconds <s>] \
    [--json|--jsonl|--text]
```

Default bind: `127.0.0.1:8474`. Port `0` selects an ephemeral port (the
startup envelope reports the resolved URL).

## Responsibilities And Boundaries

In scope:

* file-backed capture streaming over WebSocket with timestamp pacing
* DBC-decoded signal events, J1939 PGN/source-address annotation, UDS
  transaction reassembly — all reusing the existing engine helpers
* a bundled, dependency-light SPA served from package resources
* read-only HTTP surface with structured errors

Out of scope (v1):

* live interface streaming (capture files are the source; live follows later)
* any active-transmit endpoint, regardless of flags
* authentication/TLS — bind defaults to loopback; operators exposing the
  dashboard beyond localhost own the transport security

## Architecture

* `src/canarchy/web.py` — `build_dashboard_events` (engine → envelope
  events), minimal RFC 6455 helpers, and `WebDashboardServer`
  (`ThreadingHTTPServer` subclass; `/`, `/api/status`, `/ws`).
* `src/canarchy/resources/web/index.html` — single-file vanilla-JS SPA.
* `emit_web_serve` in `cli.py` — argument handling, structured startup
  envelope, serve loop.

## Error Codes

| Code | Trigger | Exit code |
|------|---------|-----------|
| `WEB_BIND_INVALID` | `--bind` not in `<host>:<port>` form or port out of range | 1 |
| `WEB_BIND_FAILED` | Port already in use / cannot bind | 1 |
| `WEB_READ_ONLY` | Non-GET HTTP request (HTTP 405 body, not a CLI exit) | — |
| `CAPTURE_SOURCE_*` | Existing transport errors for missing/invalid captures | 2 |
