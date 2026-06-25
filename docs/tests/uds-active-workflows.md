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
| `REQ-UDS-ACT-07` | `test_uds_services_returns_catalog`, `TEST-UDS-ACT-CLI-01` |
| `REQ-UDS-ACT-08` | `TEST-UDS-ACT-UNIT-05`, `TEST-UDS-ACT-UNIT-06` |
| `REQ-UDS-ACT-09` | `TEST-UDS-ACT-CLI-10`, `TEST-UDS-ACT-CLI-11`, `TEST-UDS-ACT-UNIT-07` |
| `REQ-UDS-ACT-10` | `TEST-UDS-ACT-CLI-05` |
| `REQ-UDS-ACT-11` | `TEST-UDS-ACT-CLI-07`, `TEST-UDS-ACT-UNIT-08` |
| `REQ-UDS-ACT-12` | `TEST-UDS-ACT-UNIT-01` |
| `REQ-UDS-ACT-14` | `test_every_cli_command_is_exposed_or_documented` |

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
