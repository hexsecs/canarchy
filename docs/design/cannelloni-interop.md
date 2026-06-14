# Design Spec: cannelloni CAN-over-UDP Interop

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy cannelloni decode`, `canarchy cannelloni send` |
| Primary area | Core, CLI, transport |

## Goal

Speak the [cannelloni](https://github.com/mguentner/cannelloni) UDP datagram
wire format so CANarchy can send captures to, and decode captures from,
cannelloni endpoints — notably the UTHP / TCAT heavy-vehicle appliances'
remote-bus setups. This is frame-format interop, not a new hardware backend.

## User-Facing Motivation

cannelloni is the de-facto CAN-over-Ethernet tunnel for remote-bus access on
truck-assessment appliances. Without it, an operator using CANarchy alongside
such an appliance cannot exchange frames over the tunnel.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-CAN-01` | Ubiquitous | The system shall provide a pure codec that encodes a list of CAN frames into cannelloni wire-format (version 2) UDP datagrams and decodes datagrams back into CAN frames, opening no live hardware. |
| `REQ-CAN-02` | Ubiquitous | The codec shall round-trip classic CAN, extended-ID, remote (RTR), error, and CAN FD frames (including BRS / ESI flags), carrying the SocketCAN EFF / RTR / ERR flag bits in the `can_id`. |
| `REQ-CAN-03` | Event-driven | When `cannelloni decode --file <path>` is invoked, the system shall decode one or more concatenated cannelloni datagrams from the file into canonical `frame` events. |
| `REQ-CAN-04` | Event-driven | When `cannelloni send <host:port> --file <capture>` is invoked, the system shall encode the capture into cannelloni datagrams (at most `--max-count` frames each, default 64, and at most `--mtu` encoded bytes each, default 1500, so a stock peer's MTU is not overrun by CAN FD frames; `--mtu 0` disables the byte cap) and transmit them over UDP to the endpoint, paced by `--rate` datagrams per second. |
| `REQ-CAN-05` | Ubiquitous | `cannelloni send` shall be an active-transmit command honouring the active-transmit safety model (`--ack-active`, `YES` confirmation, `[safety].require_active_ack`); `--dry-run` shall plan the datagrams (returned as hex in the envelope) without opening a socket. |
| `REQ-CAN-06` | Unwanted behaviour | If the target is not `<host>:<port>` or the port is out of range, the system shall return a structured error with code `CANNELLONI_INVALID_TARGET` and exit code 1. |
| `REQ-CAN-07` | Unwanted behaviour | If a datagram is truncated or uses an unsupported version, the decoder shall raise a structured error (`CANNELLONI_TRUNCATED` / `CANNELLONI_VERSION_UNSUPPORTED`); if a UDP send fails, `cannelloni send` shall return `CANNELLONI_SEND_FAILED` (exit code 2). |
| `REQ-CAN-08` | Ubiquitous | `cannelloni decode` shall be exposed as the MCP tool `cannelloni_decode`; `cannelloni send` shall be a documented MCP exclusion (active UDP egress to an arbitrary host). |
| `REQ-CAN-09` | Unwanted behaviour | If a datagram declares a non-truncated but out-of-range DLC (a classic frame > 8 bytes or a CAN FD frame > 64 bytes), the decoder shall raise `CANNELLONI_INVALID_DLC` so the CLI/MCP path returns a structured error rather than crashing. |

## Command Surface

```text
canarchy cannelloni decode --file <payload> [--json|--jsonl|--text]
canarchy cannelloni send <host:port> --file <capture> [--seq-no <n>] [--max-count <n>] [--mtu <bytes>] \
    [--rate <hz>] [--ack-active] [--dry-run] [--offset <n>] [--max-frames <n>] [--seconds <s>] \
    [--json|--jsonl|--text]
```

## Wire Format (version 2)

All multi-byte integers big-endian.

```text
datagram = header frame*
header   = version(1) op_code(1) seq_no(1) count(2)
frame    = can_id(4) len(1) [flags(1) if CAN FD] data(dlc bytes unless RTR)
```

`can_id` carries the Linux SocketCAN flag bits (`CAN_EFF_FLAG`, `CAN_RTR_FLAG`,
`CAN_ERR_FLAG`) in its high bits. The `len` byte's `0x80` bit marks a CAN FD
frame, followed by a one-byte flags field (`CANFD_BRS` / `CANFD_ESI`).

## Responsibilities And Boundaries

In scope:

* a pure codec (`src/canarchy/cannelloni.py`) plus a thin UDP socket sender
* file-backed decode and active-transmit UDP send, both testable over loopback
* active-transmit safety on the send path

Out of scope (v1):

* TCP / SCTP transports (cannelloni also supports these; UDP is the common case)
* a live `cannelloni receive` capture loop (decode of captured payloads covers
  consuming inbound traffic)
* ACK/NACK reliability handshakes (the UDP `OP_DATA` path only)

## Error Codes

| Code | Trigger | Exit code |
|------|---------|-----------|
| `CANNELLONI_INVALID_TARGET` | `send` target not `host:port` / bad port | 1 |
| `CANNELLONI_FILE_UNREADABLE` | `decode` payload file cannot be read | 2 |
| `CANNELLONI_TRUNCATED` | datagram ends mid-frame | 2 |
| `CANNELLONI_VERSION_UNSUPPORTED` | datagram version != 2 | 2 |
| `CANNELLONI_INVALID_DLC` | declared DLC exceeds the classic (8) / FD (64) maximum | 2 |
| `CANNELLONI_SEND_FAILED` | UDP send raised `OSError` | 2 |
| `CANNELLONI_TOO_MANY_FRAMES` / `CANNELLONI_INVALID_MAX_COUNT` | codec bounds violated | 1 |
