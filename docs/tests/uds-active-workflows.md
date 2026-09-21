# Test Spec: Active UDS Diagnostic Workflows

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Related design spec | `docs/design/uds-active-workflows.md` |
| Primary test area | CLI, protocol, safety |
| Test modules | `tests/test_uds_active.py`, `tests/test_cli.py` |

## Test Objectives

Validate that the active UDS workflows build correct single-frame requests,
classify responses (positive / negative-with-NRC / no-response), apply bounded
defaults, gate active transmission, emit deterministic dry-run plans, and
produce stable structured output — all without live hardware.

## Coverage Requirements

* single-frame request construction and bounds (empty / oversize / extended id);
* response selection that skips the request echo and `0x78` response-pending;
* service and subfunction support classification;
* single-shot services (ECU reset, TesterPresent) request encoding;
* SecurityAccess seed collection and even-level rejection;
* DID dumping with present/absent detection and `--limit` capping;
* memory request encoding, chunk planning, oversize rejection, and data assembly;
* `auto` discovery + service/DID probing over a bounded id range;
* CLI: active probe paths through a patched live `transaction()`, dry-run plans, acknowledgement gating, and bounds errors.

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-UDS-ACT-01` | `TEST-UDS-ACT-CLI-01`..`07` |
| `REQ-UDS-ACT-02` | `TEST-UDS-ACT-CLI-01` |
| `REQ-UDS-ACT-03` | `TEST-UDS-ACT-CLI-09` |
| `REQ-UDS-ACT-04` | `TEST-UDS-ACT-CLI-08` |
| `REQ-UDS-ACT-05` | `TEST-UDS-ACT-CLI-03` |
| `REQ-UDS-ACT-06` | `TEST-UDS-ACT-UNIT-02`, `TEST-UDS-ACT-CLI-01` |
| `REQ-UDS-ACT-07` | `test_uds_services_returns_catalog`, `TEST-UDS-ACT-CLI-01`, `TEST-UDS-ACT-REF-05` |
| `REQ-UDS-ACT-08` | `TEST-UDS-ACT-UNIT-05`, `TEST-UDS-ACT-UNIT-06` |
| `REQ-UDS-ACT-09` | `TEST-UDS-ACT-CLI-10`, `TEST-UDS-ACT-CLI-11`, `TEST-UDS-ACT-UNIT-07` |
| `REQ-UDS-ACT-10` | `TEST-UDS-ACT-CLI-05` |
| `REQ-UDS-ACT-11` | `TEST-UDS-ACT-CLI-07`, `TEST-UDS-ACT-UNIT-08` |
| `REQ-UDS-ACT-12` | `TEST-UDS-ACT-UNIT-01` |
| `REQ-UDS-ACT-14` | `test_every_cli_command_is_exposed_or_documented` |
| `REQ-UDS-ACT-15` | `TEST-UDS-ACT-REF-01`, `TEST-UDS-ACT-REF-02`, `TEST-UDS-ACT-REF-06` |
| `REQ-UDS-ACT-16` | `TEST-UDS-ACT-REF-03`, `TEST-UDS-ACT-REF-04`, `TEST-UDS-ACT-REF-07` |
| `REQ-UDS-ACT-17` | `TEST-UDS-ACT-REF-08`, `TEST-UDS-ACT-REF-09`, `TEST-UDS-ACT-REF-10` |

## Representative Test Cases

### `TEST-UDS-ACT-UNIT-01` — single-frame request construction
`tests/test_uds_active.py::SingleFrameRequestTest` — padded single frame,
extended-id flagging, and empty/oversize rejection.

### `TEST-UDS-ACT-UNIT-02` — response selection
`tests/test_uds_active.py::TransportClientTest` — reassembles a single-frame
response, ignores the request echo, reports `no_response`, and prefers a settled
response over a `0x78` response-pending placeholder.

### `TEST-UDS-ACT-UNIT-03/04` — service / subfunction classification
`ServiceEnumerationTest`, `SubserviceEnumerationTest` — supported when positive
or negative with a non-"not supported" NRC; unsupported when silent or
`ServiceNotSupported` / `SubFunctionNotSupported`.

### `TEST-UDS-ACT-UNIT-05` — seed collection
`SecuritySeedTest` — collects N seeds for an explicit session/level and rejects
even request levels.

### `TEST-UDS-ACT-UNIT-06/07` — DID dump and memory
`DumpDidsTest`, `ReadMemoryTest` — present/absent DID detection, `--limit`
capping, ALFID/request encoding, chunk planning, oversize rejection, and data
assembly.

### `TEST-UDS-ACT-UNIT-08` — auto recon
`AutoReconTest` — discovers the live responder over a bounded id range and
probes services / a bounded DID range.

### `TEST-UDS-ACT-CLI-01`..`11` — CLI integration (`tests/test_cli.py`)
Active probe paths driven through a patched live `transaction()`
(`services`, `subservices`, `ecu-reset`, `dump-dids`, `read-memory` with output
file, `auto`), the `dump-dids --dry-run` plan, acknowledgement gating
(`ACTIVE_ACK_REQUIRED`), oversize memory rejection, and even-level rejection.

### `TEST-UDS-ACT-REF-01`..`10` — reference mode is not promoted by configuration (#530)

The defect: `prepare_args` applied the default-interface fallback before the
`uds services` reference exception, so a configured default supplied a target
and the command probed the bus. Reached through MCP `uds_services`, which has
no acknowledgement parameter, that was unacknowledged active transmission.

```gherkin
Scenario: TEST-UDS-ACT-REF-01 — a config-file default does not trigger probing
  Given `[transport].default_interface` is set to "vcan7"
  When  `canarchy uds services --json` is run with no interface argument
  Then  data.mode shall be "reference"
  And   data shall contain no "probe_count" or "interface"
  And   stderr shall be empty

Scenario: TEST-UDS-ACT-REF-02 — an environment default does not trigger probing
  Given CANARCHY_DEFAULT_INTERFACE is set to "vcan7" and no config file sets one
  When  `canarchy uds services --json` is run with no interface argument
  Then  data.mode shall be "reference"

Scenario: TEST-UDS-ACT-REF-03 — the catalog answers under either ack setting
  Given a configured default interface and CANARCHY_REQUIRE_ACTIVE_ACK is true
  When  `canarchy uds services --json` is run with no interface argument
  Then  the exit code shall be 0
  And   data.mode shall be "reference"

Scenario: TEST-UDS-ACT-REF-04 — the reference path builds no transport
  Given a configured default interface
  And   `canarchy.cli.LocalTransport` raises if it is constructed
  When  `canarchy uds services --json` is run with no interface argument
  Then  the catalog shall be returned without the constructor being reached

Scenario: TEST-UDS-ACT-REF-05 — explicit CLI intent still probes
  Given a configured default interface of "vcan7"
  When  `canarchy uds services can0 --json` is run
  Then  data.mode shall be "active"
  And   data.interface shall be "can0"
  And   stderr shall contain the active-transmit preflight warning

Scenario: TEST-UDS-ACT-REF-06 — MCP tool ignores the configured default
  Given a configured default interface, under each CANARCHY_REQUIRE_ACTIVE_ACK setting
  When  `handle_call_tool("uds_services", {})` is called
  Then  data.mode shall be "reference"
  And   data shall contain no "probe_count" or "interface"

Scenario: TEST-UDS-ACT-REF-07 — MCP tool builds no transport
  Given a configured default interface
  And   `canarchy.cli.LocalTransport` raises if it is constructed
  When  `handle_call_tool("uds_services", {})` is called
  Then  the catalog shall be returned without the constructor being reached

Scenario: TEST-UDS-ACT-REF-08 — the server fails closed on a non-reference argv
  Given the argv builder is made to emit `uds services vcan7 --json`
  When  `handle_call_tool("uds_services", {})` is called
  Then  ok shall be false
  And   errors[0].code shall be "REFERENCE_ONLY_TOOL_VIOLATION"
  And   no command shall have been executed

Scenario: TEST-UDS-ACT-REF-09 — reference-only tools expose no transport surface
  Given the registry of reference-only MCP tools
  When  each tool's input schema is inspected
  Then  it shall declare no "interface", "ack_active", or "dry_run" property
  And   it shall not appear in the active-transmit tool set

Scenario: TEST-UDS-ACT-REF-10 — end to end over a real stdio MCP session
  Given a server subprocess started with HOME pointing at a config that sets
        default_interface = "vcan7"
  When  an MCP client initialises over stdio and calls `uds_services` with {}
  Then  data.mode shall be "reference"
  And   data shall contain no "probe_count"
```

**Fixture:** none on disk. The config-file cases patch
`canarchy.transport._load_user_config`; the environment cases patch
`os.environ`; `TEST-UDS-ACT-REF-10` writes a temporary `~/.canarchy/config.toml`
under a `tmp_path` HOME and runs the server as a subprocess with the scaffold
backend, so no real interface is ever opened.

Implemented in `tests/test_cli.py` (`REF-01`..`05`) and `tests/test_mcp.py`
(`REF-06`..`10`). Each was confirmed to fail against the pre-fix source.
