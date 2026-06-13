# Test Spec: Web Dashboard (`web serve`)

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/web-serve.md` |
| Test file | `tests/test_web.py` |

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-WEB-01` | `TEST-WEB-02`, `TEST-WEB-06` |
| `REQ-WEB-02` | `TEST-WEB-04` |
| `REQ-WEB-03` | `TEST-WEB-03` |
| `REQ-WEB-04` | `TEST-WEB-01`, `TEST-WEB-03` |
| `REQ-WEB-05` | `TEST-WEB-02` |
| `REQ-WEB-06` | `TEST-WEB-05`, `TEST-WEB-06` |
| `REQ-WEB-07` | `TEST-WEB-03`, `TEST-WEB-05` |
| `REQ-WEB-08` | `TEST-WEB-06` |

## Representative Test Cases

### `TEST-WEB-01` — Dashboard events carry the canonical envelope content

```gherkin
Given  a J1939 fixture capture
When   `build_dashboard_events` runs (optionally with a DBC)
Then   `frame` and `j1939_pgn` events shall be emitted, the latter annotated with `pgn_label` and `source_address_name`
And    `decoded_message` events with a `signals` map shall appear when a DBC is supplied
And    a capture containing an ISO-TP request/response pair shall yield a `uds_transaction` event
And    events shall be ordered by timestamp
```

**Fixture:** `tests/fixtures/j1939_heavy_vehicle.candump`, `tests/fixtures/j1939_sample.dbc`, synthetic UDS capture.

---

### `TEST-WEB-02` — Server startup serves the SPA and status against a fixture capture

```gherkin
Given  a `WebDashboardServer` started on an ephemeral port with fixture events
When   `GET /` and `GET /api/status` are requested
Then   the bundled SPA HTML shall be returned
And    the status JSON shall report `read_only: true`, the event count, and client count
And    `GET` on an unknown path shall return 404
```

**Fixture:** `tests/fixtures/j1939_heavy_vehicle.candump`.

---

### `TEST-WEB-03` — WebSocket smoke: envelope events stream to a raw client

```gherkin
Given  a running dashboard and a raw-socket RFC 6455 client handshake
When   the client reads text frames from `/ws`
Then   the upgrade response shall carry the correct `Sec-WebSocket-Accept` key
And    `frame`, `j1939_pgn`, and `decoded_message` events shall arrive as JSON envelope objects
And    the stream shall end with an `alert` event carrying `STREAM_COMPLETE` and a close frame
```

**Fixture:** `tests/fixtures/j1939_heavy_vehicle.candump` + `j1939_sample.dbc`.

---

### `TEST-WEB-04` — Read-only surface rejects write methods

```gherkin
Given  a running dashboard
When   POST, PUT, DELETE, or PATCH is sent to any path
Then   the response shall be HTTP 405 with error code `WEB_READ_ONLY`
```

**Fixture:** none.

---

### `TEST-WEB-05` — Bind validation and WS framing round-trip

```gherkin
Given  malformed bind strings (missing port, non-integer, out of range)
When   `parse_bind` is called
Then   a structured `WEB_BIND_INVALID` error shall be raised
And    encoded server text frames of 7/16/64-bit payload lengths shall round-trip through the frame reader
```

**Fixture:** none.

---

### `TEST-WEB-06` — CLI startup envelope and structured file errors

```gherkin
Given  `canarchy web serve --file <missing> --json`
Then   a structured error envelope shall be emitted with a non-zero exit code
Given  `canarchy web serve --file <fixture> --bind 127.0.0.1:0 --json` with the serve loop stubbed
Then   the startup envelope shall report the resolved `url`, `read_only: true`, and a positive `event_count`
And    a read-only warning shall be present
```

**Fixture:** `tests/fixtures/j1939_heavy_vehicle.candump`.
