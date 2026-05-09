# Test Spec: J1939 Monitor Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/j1939-monitor-command.md` |
| Test file | `tests/test_cli.py` |

## Requirement Traceability

| REQ ID | Description summary | TEST IDs |
|--------|--------------------|----------|
| `REQ-J1939MON-01` | Command exists with the documented CLI surface | `TEST-J1939MON-01`, `TEST-J1939MON-02`, `TEST-J1939MON-03`, `TEST-J1939MON-04` |
| `REQ-J1939MON-02` | Monitor without an interface uses the sample/reference provider | `TEST-J1939MON-01` |
| `REQ-J1939MON-03` | Monitor with an interface uses the transport-backed path | `TEST-J1939MON-02` |
| `REQ-J1939MON-04` | `--pgn` filters the observation set and is echoed in the result | `TEST-J1939MON-03`, `TEST-J1939MON-04` |
| `REQ-J1939MON-05` | Structured output is observation-first rather than raw-frame-only | `TEST-J1939MON-01`, `TEST-J1939MON-02`, `TEST-J1939MON-03` |
| `REQ-J1939MON-06` | Standard output modes remain supported | `TEST-J1939MON-04`, `TEST-J1939MON-05` |

## Test Cases

### TEST-J1939MON-01 — Monitor without interface uses sample provider

```gherkin
Given  no interface argument is provided
When   the operator runs `canarchy j1939 monitor --json`
Then   the system shall return a passive J1939 result envelope
And    the result shall report the sample/reference provider implementation
And    the first emitted event shall be a J1939 PGN observation
```

**Fixture:** built-in sample/reference provider.

---

### TEST-J1939MON-02 — Monitor with interface uses transport-backed path

```gherkin
Given  the scaffold transport backend is configured
When   the operator runs `canarchy j1939 monitor can0 --json`
Then   the system shall return a passive J1939 result envelope
And    the result shall include `interface="can0"`
And    the result shall report the transport-backed implementation
```

**Fixture:** mocked transport config selecting the scaffold backend.

---

### TEST-J1939MON-03 — PGN filter reduces the observation set

```gherkin
Given  the sample/reference provider emits more than one J1939 observation
When   the operator runs `canarchy j1939 monitor --pgn 65262 --json`
Then   the system shall echo `pgn_filter=65262` in the result
And    the returned observations shall only report PGN `65262`
```

**Fixture:** built-in sample/reference provider.

---

### TEST-J1939MON-04 — Text output remains protocol-first

```gherkin
Given  a PGN filter is supplied
When   the operator runs `canarchy j1939 monitor --pgn 65262 --text`
Then   the system shall print the command header
And    the text output shall include the active PGN filter and protocol-first observation fields
```

**Fixture:** built-in sample/reference provider.

## Fixtures And Environment

* built-in sample/reference J1939 provider
* mocked scaffold transport configuration for the live-path test

## Explicit Non-Coverage

* transport backend failure paths, which are covered by generic transport and CLI error handling
* DBC enrichment, because `j1939 monitor` does not currently expose that surface
