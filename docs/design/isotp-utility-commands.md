# Design Spec: Standalone ISO-TP Utility Commands

## Document Control

| Field | Value |
|-------|-------|
| Status | Planned |
| Command surface | `canarchy isotp reassemble`, `canarchy isotp send` |
| Primary area | CLI, protocol, transport, active-transmit safety |
| Related specs | `docs/design/uds-transaction-workflows.md`, `docs/design/j1939-expanded-workflows.md`, `docs/design/active-transmit-safety.md` |
| Issue | #328 |

## Goal

Expose ISO 15765-2 transport utilities as standalone CLI commands so analysts can reassemble or transmit arbitrary ISO-TP messages without routing the workflow through UDS-specific commands.

## User-Facing Motivation

CAN captures often contain diagnostic or vendor-specific ISO-TP exchanges that are not strictly UDS, or where the operator wants transport-layer evidence before protocol interpretation. A standalone `isotp` command group gives agents and human analysts a protocol-neutral path for message reconstruction, malformed-sequence triage, and safe single-message transmit planning.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-ISOTP-01` | Ubiquitous | The system shall provide an `isotp` command group with `reassemble` and `send` subcommands. |
| `REQ-ISOTP-02` | Event-driven | When `isotp reassemble --file <capture>` is invoked, the system shall read CAN frames from the capture and emit reassembled ISO-TP messages with source metadata. |
| `REQ-ISOTP-03` | Optional feature | Where `--source <id>` is specified for `isotp reassemble`, the system shall include only ISO-TP frames whose arbitration ID matches the source ID. |
| `REQ-ISOTP-04` | Optional feature | Where `--target <id>` is specified for `isotp reassemble`, the system shall use target ID metadata to classify request/response direction and flow-control relationships. |
| `REQ-ISOTP-05` | Event-driven | When a complete single-frame or multi-frame ISO-TP message is observed, the system shall emit exactly one `isotp_message` event with `complete` equal to `true`. |
| `REQ-ISOTP-06` | Unwanted behaviour | If a multi-frame ISO-TP message is truncated, out of order, or interrupted by a new first frame on the same arbitration ID, the system shall emit an `isotp_message` event with `complete` equal to `false` and preserve the partial payload bytes observed before the error. |
| `REQ-ISOTP-07` | Event-driven | When ISO-TP flow-control frames appear in captured traffic, the system shall include them in per-message flow-control metadata without emitting them as standalone reassembled messages. |
| `REQ-ISOTP-08` | Unwanted behaviour | If an ISO-TP frame has an unsupported or malformed protocol-control-information nibble, the system shall return or report a structured error with code `ISOTP_MALFORMED_SEQUENCE`. |
| `REQ-ISOTP-09` | Event-driven | When `isotp send <interface> --source <id> --target <id> --data <hex>` is invoked, the system shall segment the payload as needed and transmit the ISO-TP frame sequence on the target interface. |
| `REQ-ISOTP-10` | Optional feature | Where `--dry-run` is specified for `isotp send`, the system shall return the planned frame sequence without opening a transport. |
| `REQ-ISOTP-11` | State-driven | While `isotp send` is running without `--dry-run`, the system shall enforce active-transmit safety controls before any CAN frame is transmitted. |
| `REQ-ISOTP-12` | Unwanted behaviour | If `isotp send` does not receive required flow-control permission before a consecutive-frame timeout, the system shall return a structured error with code `ISOTP_FLOW_CONTROL_TIMEOUT`. |
| `REQ-ISOTP-13` | Ubiquitous | The system shall honor the canonical CANarchy envelope for `--json`, one event per line for `--jsonl`, and protocol-aware summaries for `--text`. |
| `REQ-ISOTP-14` | Ubiquitous | The system shall reuse the existing ISO-TP reassembly helpers proven by UDS workflows and avoid duplicating reassembly logic in CLI handlers. |

## Command Surface

```text
canarchy isotp reassemble --file <capture> [--source <id>] [--target <id>]
                         [--offset N] [--max-frames N] [--seconds T]
                         [--json] [--jsonl] [--text]

canarchy isotp send <interface> --source <id> --target <id> --data <hex>
                   [--dry-run] [--ack-active]
                   [--json] [--jsonl] [--text]
```

`<id>`, `--source`, and `--target` accept decimal or hex arbitration IDs. `isotp send` is an active-transmit command. `isotp reassemble` is passive and never opens a live transport.

## Responsibilities And Boundaries

In scope:

* file-backed ISO-TP reassembly from candump and any capture formats already supported by file-backed analysis commands
* source-ID filtering and target-ID metadata for request/response pairing
* single-frame and multi-frame message reconstruction
* incomplete-message reporting for malformed or truncated sequences
* flow-control metadata observed in captures
* single ISO-TP message transmission with active-transmit safety and dry-run planning

Out of scope:

* UDS service decoding; operators should pipe or correlate with `uds` workflows when UDS semantics are needed
* J1939 transport-protocol reassembly, which remains under `j1939 tp`
* ISO-TP extended addressing, mixed addressing, CAN FD payload sizing, and block-size tuning until separately specified
* long-running ISO-TP client sessions, retries beyond one message, and ECU-specific diagnostic behavior

## Data Model

`isotp reassemble` emits `isotp_message` events. Each event payload includes:

| Field | Description |
|-------|-------------|
| `arbitration_id` | CAN ID carrying the ISO-TP payload frame sequence |
| `source_id` | Matched source ID when known, otherwise the observed arbitration ID |
| `target_id` | Target ID supplied by the operator, or null |
| `direction` | `request`, `response`, or `unknown` when source/target metadata is insufficient |
| `payload` | Reassembled application payload as lowercase hex |
| `payload_length` | Number of bytes in `payload` |
| `declared_length` | ISO-TP first-frame total length for multi-frame messages, otherwise payload length |
| `complete` | Whether the payload reached the declared length without sequence errors |
| `frame_count` | Number of data-bearing CAN frames consumed by the message |
| `flow_control_count` | Number of related flow-control frames observed |
| `sequence_error` | Sequence error description, or null |
| `timestamp_start` | Timestamp of the first data-bearing frame, or null |
| `timestamp_end` | Timestamp of the last related frame, or null |

`isotp send --dry-run` returns a `frames` array with CAN frame payloads in send order. Active sends return the same planned frames plus `mode`, `interface`, `source_id`, `target_id`, `payload`, `frame_count`, and active-transmit event metadata.

## Output Contracts

`--json` returns the standard CANarchy envelope:

```json
{
  "ok": true,
  "command": "isotp reassemble",
  "data": {
    "message_count": 1,
    "messages": [
      {
        "event_type": "isotp_message",
        "payload": {
          "arbitration_id": 2024,
          "source_id": 2024,
          "target_id": 2016,
          "direction": "response",
          "payload": "62f190574457313233343536373839",
          "payload_length": 15,
          "declared_length": 15,
          "complete": true,
          "frame_count": 3,
          "flow_control_count": 1,
          "sequence_error": null,
          "timestamp_start": 0.0,
          "timestamp_end": 0.012
        }
      }
    ]
  },
  "warnings": [],
  "errors": []
}
```

`--jsonl` emits one `isotp_message` event per line for `reassemble` and one planned/sent frame event per line for `send`. `--text` summarizes each message as source, target, direction, completeness, payload length, and payload hex.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `CAPTURE_SOURCE_UNAVAILABLE` | `--file` path is missing or unreadable | 1 |
| `CAPTURE_PARSE_FAILED` | capture contains lines/records the existing capture reader cannot parse | 1 |
| `INVALID_CAN_ID` | `--source`, `--target`, or positional send IDs are malformed or outside the supported 11-bit range for the planned first slice | 1 |
| `INVALID_HEX_PAYLOAD` | `--data` is not valid hex or exceeds the planned payload limit | 1 |
| `ISOTP_MALFORMED_SEQUENCE` | PCI nibble, length field, consecutive-frame sequence, or frame length is invalid | 3 |
| `ISOTP_FLOW_CONTROL_TIMEOUT` | `isotp send` waits for flow-control permission and the timeout expires | 2 |
| `ACTIVE_ACK_REQUIRED` | active acknowledgement is required but omitted for live `isotp send` | 1 |
| `ACTIVE_CONFIRMATION_DECLINED` | active-transmit confirmation is declined for live `isotp send` | 1 |
| `TRANSPORT_UNAVAILABLE` | live send target interface cannot be opened | 2 |

Malformed sequences found during passive reassembly should be represented as incomplete `isotp_message` events when useful payload bytes were recovered. Fatal `ISOTP_MALFORMED_SEQUENCE` errors are reserved for inputs that cannot be associated with a coherent message event.

## Active-Transmit Safety

`isotp send` shall be added to `ACTIVE_TRANSMIT_COMMANDS` when implemented. Live mode requires the same preflight warning, configurable `--ack-active` enforcement, and MCP-side safety posture as other active transmitters. `--dry-run` is the safe default expected for any future MCP mirror and must not open a transport.

## Deferred Decisions

* Whether `isotp send` should wait for observed flow-control frames by default or offer an explicit `--assume-flow-control` dry lab mode.
* Whether extended, mixed, or normal-fixed addressing should be represented as flags or profile names.
* Whether CAN FD ISO-TP segmentation should be introduced with a `--can-fd` flag and configurable data length.
* Whether standalone ISO-TP utilities should be exposed through MCP in the first implementation slice or deferred until active-send behavior is stable.
