# Test Spec: `gateway` Command

## Coverage goals

- Unidirectional frame forwarding (src → dst)
- Bidirectional frame forwarding (src ↔ dst)
- `--count` terminates the stream after N total forwarded frames
- `--src-backend` and `--dst-backend` are passed to the correct buses
- Scaffold backend raises `GATEWAY_LIVE_BACKEND_REQUIRED`
- Unreachable channel raises `TRANSPORT_UNAVAILABLE`
- `--count 0` returns a structured user error
- JSON output contains frame events with correct `source` direction label
- Table output prints a gateway header and candump-style frame lines

## Test cases

### Unidirectional forward

**Setup:** Two in-process virtual buses on the same channel using threads.  
**Action:** Send 2 frames on the source bus.  
**Assert:** Both frames arrive on the destination bus with correct arbitration IDs and data.

### Bidirectional forward

**Setup:** Two in-process virtual buses on distinct channels.  
**Action:** Send 1 frame src→dst and 1 frame dst→src.  
**Assert:** Both frames are forwarded; events carry the correct direction label.

### Count limit stops forwarding

**Setup:** Virtual buses; more frames available than `--count`.  
**Action:** Run gateway with `--count 2`; send 5 frames on the source.  
**Assert:** Gateway stops after exactly 2 forwarded frames and exits cleanly.

### Scaffold backend error

**Setup:** Default scaffold backend (no `CANARCHY_TRANSPORT_BACKEND` env var).  
**Action:** Run `canarchy gateway src dst --json`.  
**Assert:** Exit code 2; `errors[0].code == "GATEWAY_LIVE_BACKEND_REQUIRED"`.

### Invalid count

**Setup:** python-can backend.  
**Action:** Run `canarchy gateway src dst --count 0 --json`.  
**Assert:** Exit code 1; `errors[0].code == "INVALID_COUNT"`.

### JSON output structure

**Setup:** Virtual buses; `--count 1`.  
**Action:** Forward one frame with `--json`.  
**Assert:** Payload contains `ok: true`, `command: "gateway"`, `events` list with one frame event, `source` field is `"gateway.src->dst"`.

### Table output header

**Setup:** Virtual buses; `--count 1`.  
**Action:** Forward one frame with `--table`.  
**Assert:** Output contains `gateway:` header line with src and dst channels; at least one candump-style frame line.

## Fixtures

No new fixture files are required. Tests use in-process python-can virtual buses.

## What is not tested

- Physical hardware adapters (pcan, slcan, socketcan) — environment-dependent.
- Cross-process gateway validation — covered by the `test_virtual_bus_is_process_local` and `test_udp_multicast_backend_round_trips_frame_across_processes` tests in `test_transport.py`.
- Indefinite streaming (no `--count`) — not suitable for unit tests; covered by the demo docs.
