# Test Spec: J1939 Map Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/j1939-map-command.md` |
| Test file | `tests/test_cli.py`, `tests/test_mcp.py` |

## Requirement Traceability

| REQ ID | Description summary | TEST IDs |
|--------|--------------------|----------|
| `REQ-J1939MAP-01` | `j1939 map` command exists | `TEST-J1939MAP-01`, `TEST-J1939MAP-02` |
| `REQ-J1939MAP-02` | One node per source address with name and frame count | `TEST-J1939MAP-01` |
| `REQ-J1939MAP-03` | Address Claimed NAME fields decoded onto nodes | `TEST-J1939MAP-01` |
| `REQ-J1939MAP-04` | Identification strings attached to nodes | `TEST-J1939MAP-01` |
| `REQ-J1939MAP-05` | Edges aggregate observed PGN flows with frame counts | `TEST-J1939MAP-01` |
| `REQ-J1939MAP-06` | PDU1 global-address traffic reported as broadcast | `TEST-J1939MAP-01` |
| `REQ-J1939MAP-07` | Map derived purely from captured frames (passive) | `TEST-J1939MAP-01` |
| `REQ-J1939MAP-08` | Map respects bounded-analysis controls | shared bounded-analysis coverage |
| `REQ-J1939MAP-09` | Empty capture warns instead of erroring | `TEST-J1939MAP-03` |
| `REQ-J1939MAP-10` | JSON field names remain stable | `TEST-J1939MAP-01`, `TEST-J1939MAP-04` |

## Test Cases

### TEST-J1939MAP-01 — Map builds nodes and edges from a capture

```gherkin
Given  a J1939 capture fixture contains Address Claimed messages, broadcast PGNs, and a directed PDU1 request
When   the operator runs `canarchy j1939 map --file <capture> --json`
Then   the system shall emit one node per source address with the resolved name, frame count, decoded Address Claimed NAME fields, and identification strings
And    the system shall emit edges aggregating repeated frames into per-(source, destination, PGN) flows with frame counts
And    the directed PDU1 request shall appear as a non-broadcast edge with a destination address
And    broadcast and PDU1 global-address traffic shall appear as broadcast edges
And    the JSON field names shall remain stable for automation
```

**Fixture:** `tests/fixtures/j1939_map.candump`.

---

### TEST-J1939MAP-02 — Text output remains operator-friendly

```gherkin
Given  a J1939 capture fixture with address claims and PGN flows
When   the operator runs `canarchy j1939 map --file <capture> --text`
Then   the output shall show the node list with source addresses, decoded NAME summaries, and identification strings
And    the output shall show the edge list with source, destination (or broadcast), and PGN
```

**Fixture:** `tests/fixtures/j1939_map.candump`.

---

### TEST-J1939MAP-03 — Empty capture warns instead of erroring

```gherkin
Given  an empty capture file
When   the operator runs `canarchy j1939 map --file <capture> --json`
Then   the system shall return exit code 0 with zero nodes and zero edges
And    the warnings shall include a "No J1939 network map" message
```

**Fixture:** generated empty capture file.

---

### TEST-J1939MAP-04 — MCP exposes the j1939_map tool

```gherkin
Given  the CANarchy MCP server tool catalog
When   the j1939_map tool argv is built with a file and a frame limit
Then   the argv shall invoke `j1939 map --file <file>` with `--max-frames` and `--json`
And    the tool schema shall expose the max_frames and seconds frame-limit parameters
```

## Fixtures And Environment

* `tests/fixtures/j1939_map.candump`
* generated empty capture file (created within the test)

## Explicit Non-Coverage

* graph rendering or layout output (DOT/GraphML)
* active probing or address-claim solicitation behavior
* OEM-specific identification heuristics beyond inventory's existing extraction
