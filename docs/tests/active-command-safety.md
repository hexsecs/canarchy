# Test Spec: Active Command Safety

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/active-command-safety.md` |
| Test file | `tests/test_cli.py` |

## Requirement Traceability

| REQ ID | Description summary | TEST IDs |
|--------|--------------------|---------|
| `REQ-ACTIVE-SAFE-01` | active transmit command set is defined | `TEST-ACTIVE-SAFE-01`, `TEST-ACTIVE-SAFE-02` |
| `REQ-ACTIVE-SAFE-02` | preflight warning is emitted before transmission | `TEST-ACTIVE-SAFE-01`, `TEST-ACTIVE-SAFE-04` |
| `REQ-ACTIVE-SAFE-03` | `--ack-active` triggers a confirmation prompt | `TEST-ACTIVE-SAFE-03`, `TEST-ACTIVE-SAFE-04` |
| `REQ-ACTIVE-SAFE-04` | config can require explicit acknowledgement flag | `TEST-ACTIVE-SAFE-02`, `TEST-ACTIVE-SAFE-03` |
| `REQ-ACTIVE-SAFE-05` | missing acknowledgement fails before transport send | `TEST-ACTIVE-SAFE-02` |
| `REQ-ACTIVE-SAFE-06` | declined confirmation fails before transport send | `TEST-ACTIVE-SAFE-04` |
| `REQ-ACTIVE-SAFE-07` | stdout avoids duplicated safety warnings | `TEST-ACTIVE-SAFE-03`, `TEST-ACTIVE-SAFE-05` |
| `REQ-ACTIVE-SAFE-08` | config show reports require_active_ack | `TEST-ACTIVE-SAFE-06` |

## Test Cases

### TEST-ACTIVE-SAFE-01 — Preflight warning precedes send transport call

```gherkin
Given  the scaffold transport backend is active and the send transport path is patched
When   the operator runs `canarchy send can0 0x123 11223344 --json`
Then   the system shall emit an active-command warning on `stderr`
And    the patched transport send path shall observe that warning before transmission begins
```

**Fixture:** scaffold backend with patched `LocalTransport.send_events`.

---

### TEST-ACTIVE-SAFE-02 — Missing acknowledgement blocks active send

```gherkin
Given  `CANARCHY_REQUIRE_ACTIVE_ACK` is enabled through config
When   the operator runs `canarchy send can0 0x123 11223344 --json` without `--ack-active`
Then   the system shall exit with code `1`
And    the response shall contain an error with code `"ACTIVE_ACK_REQUIRED"`
```

**Fixture:** scaffold backend with patched `LocalTransport.send_events` to verify it is not called.

---

### TEST-ACTIVE-SAFE-03 — Confirmation allows active send

```gherkin
Given  `CANARCHY_REQUIRE_ACTIVE_ACK` is enabled through config
When   the operator runs `canarchy send can0 0x123 11223344 --ack-active --json` and replies `YES`
Then   the system shall succeed
And    the structured result shall not duplicate the safety prompt in `warnings`
```

**Fixture:** scaffold backend.

---

### TEST-ACTIVE-SAFE-04 — Declined confirmation blocks active send

```gherkin
Given  the scaffold transport backend is active
When   the operator runs `canarchy send can0 0x123 11223344 --ack-active --json` and replies `no`
Then   the system shall exit with code `1`
And    the response shall contain an error with code `"ACTIVE_CONFIRMATION_DECLINED"`
```

**Fixture:** scaffold backend with patched `LocalTransport.send_events` to verify it is not called.

---

### TEST-ACTIVE-SAFE-05 — Structured active commands keep stdout machine-readable

```gherkin
Given  the scaffold transport backend is active
When   the operator runs `canarchy uds scan can0 --jsonl`
Then   the system shall emit only structured transaction lines on `stdout`
And    the active safety prompt shall not be emitted as an extra JSONL warning line
```

**Fixture:** scaffold backend.

---

### TEST-ACTIVE-SAFE-06 — Config show reports active acknowledgement setting

```gherkin
Given  `CANARCHY_REQUIRE_ACTIVE_ACK=true` is present in file-backed config
When   the operator runs `canarchy config show --json`
Then   the system shall report `require_active_ack` as `true`
And    the reported source for `require_active_ack` shall be `"file"`
```

**Fixture:** patched `_load_user_config` return value.

## Fixtures And Environment

Shared coverage uses the scaffold backend plus targeted transport patching for send-path ordering checks.

## Explicit Non-Coverage

No coverage is included for TTY-only prompt styling differences because the confirmation flow is validated through stdin/stdout redirection in CLI tests.
