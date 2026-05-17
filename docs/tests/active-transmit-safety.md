# Test Spec: Active-Transmit Safety Model

## Document Control

| Field | Value |
|-------|-------|
| Status | Planned |
| Design doc | [`docs/design/active-transmit-safety.md`](../design/active-transmit-safety.md) |
| Test file | `tests/test_active_transmit_safety.py` plus `tests/test_fuzz.py`, `tests/test_fuzz_cli.py`, `tests/test_mcp.py` |

## Requirement Traceability

| REQ ID | Description summary | TEST IDs |
|--------|---------------------|----------|
| `REQ-ATS-01` | active-transmit set | `TEST-ATS-01` |
| `REQ-ATS-02` | existing ack gate still applies | `TEST-ATS-02` |
| `REQ-ATS-03` | `--ack-active` is sufficient when stdin is not a TTY | `TEST-ATS-03` |
| `REQ-ATS-04` | `run_id` stamped on every emitted event | `TEST-ATS-04` |
| `REQ-ATS-05` | rate cap enforced | `TEST-ATS-05`, `TEST-ATS-06` |
| `REQ-ATS-06` | `ACTIVE_TRANSMIT_RATE_EXCEEDED` returned when violated | `TEST-ATS-06` |
| `REQ-ATS-07` | target allowlist file loaded and honoured | `TEST-ATS-07`, `TEST-ATS-08` |
| `REQ-ATS-08` | `ACTIVE_TRANSMIT_TARGET_BLOCKED` returned for off-list IDs | `TEST-ATS-08` |
| `REQ-ATS-09` | kill switch on SIGINT and stdin EOF | `TEST-ATS-09`, `TEST-ATS-10` |
| `REQ-ATS-10` | `--dry-run` plans but does not transmit | `TEST-ATS-11` |
| `REQ-ATS-11` | MCP requires `ack_active=true` | `TEST-ATS-12` |
| `REQ-ATS-12` | `ACTIVE_TRANSMIT_REQUIRES_ACK` from MCP without ack | `TEST-ATS-12` |
| `REQ-ATS-13` | MCP defaults `dry_run=true` | `TEST-ATS-13` |
| `REQ-ATS-14` | stdout never carries duplicated safety prompts | `TEST-ATS-14` |
| `REQ-ATS-15` | `config show` exposes safety attribution | `TEST-ATS-15` |

## Test Cases

### TEST-ATS-01 — Active-transmit set is exhaustive

```gherkin
Given  the build_parser() returns the canonical command tree
When   the test enumerates every command flagged as active-transmit
Then   the system shall include exactly {send, generate, gateway, replay,
       uds scan, fuzz payload, fuzz replay, fuzz arbitration-id}
And    the system shall include no passive command in that set
```

**Fixture:** none.

### TEST-ATS-02 — Existing ack gate still applies

```gherkin
Given  `[safety].require_active_ack = true` in `~/.canarchy/config.toml`
When   the operator runs `canarchy send vcan0 0x123 1122 --json`
Then   the system shall return an error with code `ACTIVE_ACK_REQUIRED`
And    the system shall exit with code 1
And    the system shall not open the transport
```

**Fixture:** a temporary config file under `tmp_path`.

### TEST-ATS-03 — `--ack-active` is sufficient when stdin is not a TTY

```gherkin
Given  stdin is not a TTY (test harness pipe)
When   the operator runs `canarchy send vcan0 0x123 1122 --ack-active --dry-run --json`
Then   the system shall accept the flag as acknowledgement
And    the system shall not block waiting for a `YES` prompt
And    the response shall include `data.run_id`
```

**Fixture:** scaffold backend.

### TEST-ATS-04 — `run_id` is stamped on every emitted event

```gherkin
Given  a dry-run invocation of `canarchy generate vcan0 --count 5 --rate 100 --ack-active --jsonl`
When   the command completes
Then   the system shall include the same `run_id` on every emitted JSONL event
And    the value shall match the UUID echoed in the final envelope `data.run_id`
```

**Fixture:** scaffold backend; `--dry-run` keeps the test offline.

### TEST-ATS-05 — Rate cap honoured when within limit

```gherkin
Given  `[safety.rate_cap].fuzz_payload_hz = 100` and `--rate 50` requested
When   the operator runs `canarchy fuzz payload vcan0 --id 0x100 --strategy bitflip --rate 50 --max 10 --ack-active --dry-run --json`
Then   the system shall plan exactly 10 frames
And    the response shall include `data.rate_hz = 50`
And    the system shall not return a rate-cap error
```

**Fixture:** scaffold backend.

### TEST-ATS-06 — Rate cap rejection above ceiling

```gherkin
Given  `[safety.rate_cap].maximum_hz = 500` and `--rate 1000` requested
When   the operator runs `canarchy fuzz payload vcan0 --id 0x100 --strategy bitflip --rate 1000 --max 100 --ack-active --json`
Then   the system shall return an error with code `ACTIVE_TRANSMIT_RATE_EXCEEDED`
And    the system shall exit with code 1
And    the system shall not open the transport
```

**Fixture:** scaffold backend.

### TEST-ATS-07 — Target allowlist loads and matches

```gherkin
Given  `targets.toml` lists `ids = ["0x100", "0x200-0x2FF"]`
And    `--targets targets.toml` is supplied
When   the operator runs `canarchy send vcan0 0x250 1122 --ack-active --dry-run --json`
Then   the system shall accept the frame
And    the response shall include `data.targets_path` and `data.targets_matched = "0x200-0x2FF"`
```

**Fixture:** a temporary `targets.toml` under `tmp_path`.

### TEST-ATS-08 — Target allowlist blocks off-list ID

```gherkin
Given  `targets.toml` lists `ids = ["0x100"]`
And    `--targets targets.toml` is supplied
When   the operator runs `canarchy send vcan0 0x500 1122 --ack-active --json`
Then   the system shall return an error with code `ACTIVE_TRANSMIT_TARGET_BLOCKED`
And    `errors[0].detail.blocked_ids` shall contain `["0x500"]`
And    the system shall exit with code 1
```

**Fixture:** temporary `targets.toml`.

### TEST-ATS-09 — Kill switch on SIGINT

```gherkin
Given  `canarchy generate vcan0 --count 10000 --rate 200 --ack-active --jsonl` is running
When   the harness sends SIGINT to the process
Then   the system shall stop transmission cleanly
And    emit a final `alert` event with `payload.reason = "KILL_SWITCH_TRIGGERED"`
And    exit with code 4
```

**Fixture:** scaffold backend; subprocess harness so SIGINT is real.

### TEST-ATS-10 — Kill switch on stdin EOF

```gherkin
Given  `canarchy fuzz payload vcan0 --id 0x100 --strategy bitflip --rate 100 --ack-active --jsonl` is running
And    the command is reading from a piped stdin
When   the upstream pipe closes (EOF)
Then   the system shall stop transmission cleanly
And    emit a final `alert` event with `payload.reason = "KILL_SWITCH_TRIGGERED"`
And    exit with code 4
```

**Fixture:** scaffold backend; subprocess harness.

### TEST-ATS-11 — `--dry-run` plans without opening the transport

```gherkin
Given  the scaffold backend is active
When   the operator runs `canarchy fuzz payload vcan0 --id 0x100 --strategy bitflip --rate 100 --max 5 --ack-active --dry-run --jsonl`
Then   the system shall emit exactly 5 JSONL events with `payload.frame.dry_run = true`
And    the response shall include `warnings = ["ACTIVE_TRANSMIT_DRY_RUN: 5 frames planned; no transport opened."]`
And    the system shall not open a transport (no calls to `transport.send`)
```

**Fixture:** scaffold backend; mock on `transport.send` to assert it is not invoked.

### TEST-ATS-12 — MCP rejects active call without `ack_active=true`

```gherkin
Given  the MCP server is constructable
When   an agent calls the `fuzz_payload` tool with `ack_active` omitted
Then   the system shall return an error with code `ACTIVE_TRANSMIT_REQUIRES_ACK`
And    the system shall not invoke the underlying CLI command
```

**Fixture:** mock `_run_cli` to assert non-invocation.

### TEST-ATS-13 — MCP defaults `dry_run=true`

```gherkin
Given  the MCP server is constructable
When   an agent calls the `fuzz_payload` tool with `ack_active=true` and `dry_run` omitted
Then   the system shall invoke the CLI with `--dry-run`
And    the response shall include `data.dry_run = true`
```

**Fixture:** mock subprocess invocation; capture argv.

### TEST-ATS-14 — stdout is free of duplicated safety prompts

```gherkin
Given  `--ack-active` triggers the preflight warning on stderr
When   the operator runs `canarchy generate vcan0 --count 1 --rate 50 --ack-active --json`
Then   the system shall produce stdout JSON that does not contain the preflight warning string
And    the warning string shall appear on stderr only
```

**Fixture:** scaffold backend.

### TEST-ATS-15 — `config show` exposes safety attribution

```gherkin
Given  `[safety].targets_file = "~/labs.toml"` is set in `~/.canarchy/config.toml`
When   the operator runs `canarchy config show --json`
Then   the response shall include `data.safety.targets_file = "~/labs.toml"`
And    the response shall include `data.sources.safety.targets_file = "config"`
And    the response shall include `data.safety.rate_cap.default_hz` with a `sources.safety.rate_cap.default_hz` attribution
```

**Fixture:** temporary config file.

## Fixtures And Environment

* The full suite runs against the scaffold transport backend; no live CAN interface is required.
* `--dry-run` is used wherever possible to avoid exercising the transport at all.
* Subprocess-driven tests are used for SIGINT and stdin EOF; in-process tests are used for everything else.
* Two temporary file fixtures recur: a minimal config file and a target allowlist file. Both are produced under `tmp_path` per pytest test.

## Explicit Non-Coverage

* Hardware bus behaviour. The model defines what the CLI does; what the bus does in response is out of scope.
* Performance benchmarks of the rate cap itself. The cap is enforced at the engine layer; benchmarking it is a follow-up.
* The fuzz payload generator's mutation quality. That belongs to `src/canarchy/fuzzing.py` and its own tests (`tests/test_fuzz.py`).
* Interaction with hypothetical future commands beyond the listed set. New active commands must extend this spec rather than skip it.
