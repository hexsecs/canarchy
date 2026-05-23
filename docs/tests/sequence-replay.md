# Test Spec: `canarchy sequence replay` — YAML/JSON multi-message coordinated transmit

## Feature: Sequence file loading and encoding

### Scenario: Dry-run returns a structured plan
```gherkin
Given a valid JSON sequence file with 2 steps and 3 total frames
When I run `canarchy sequence replay --file <seq> --dry-run --json`
Then the exit code is 0
And `data.step_count` is 2
And `data.frame_count` is 3
And `data.rate` is 1.0
And `data.loop` is false
And `warnings[0]` contains "ACTIVE_TRANSMIT_DRY_RUN"
```

### Scenario: Events contain one sequence_step per step
```gherkin
Given a valid JSON sequence file
When I run with `--dry-run --json`
Then `data.events` has length equal to the number of steps
And each event has `event_type == "sequence_step"`
And each event payload contains `step`, `delay_ms`, `frame_count`, `frames`
```

### Scenario: Frames are DBC-encoded
```gherkin
Given a sequence file referencing EngineStatus1 (id=0x18FEEE31)
When I run with `--dry-run --json`
Then the first frame in the first step has `frame_id == 0x18FEEE31`
And `message_name == "EngineStatus1"`
And `data` is a non-empty hex string
```

### Scenario: JSONL output emits one line per step
```gherkin
Given a sequence file with 2 steps
When I run with `--dry-run --jsonl`
Then stdout contains exactly 2 lines with `event_type == "sequence_step"`
```

## Feature: Transmission modes

### Scenario: No interface → plan mode
```gherkin
Given a sequence file
When I run `canarchy sequence replay --file <seq> --json` (no --interface)
Then `data.mode` is "plan"
And `data` does not contain "interface"
```

### Scenario: Interface + dry-run → dry_run mode
```gherkin
Given a sequence file
When I run with `--interface vcan0 --dry-run --json`
Then `data.mode` is "dry_run"
And `data.interface` is "vcan0"
```

### Scenario: Live transmit → active mode
```gherkin
Given the scaffold transport backend
And a sequence file
When I run with `--interface vcan0 --ack-active --json` and confirm YES
Then exit code is 0
And `data.mode` is "active"
And `data.interface` is "vcan0"
And `data.frame_count` is 3
```

## Feature: Active-transmit safety

### Scenario: Live transmit requires ack when configured
```gherkin
Given `active_ack_required()` returns True
And I run with `--interface vcan0 --json` (no --ack-active)
Then exit code is EXIT_USER_ERROR
And `errors[0].code` is "ACTIVE_ACK_REQUIRED"
```

## Feature: Validation

### Scenario: Zero rate is rejected
```gherkin
When I run with `--rate 0 --json`
Then exit code is EXIT_USER_ERROR
And `errors[0].code` is "INVALID_RATE"
```

### Scenario: Missing file is rejected
```gherkin
When I run with `--file /tmp/no-such-sequence.json --json`
Then exit code is EXIT_USER_ERROR
And `errors[0].code` is "SEQUENCE_LOAD_ERROR"
```

## Feature: Rate scaling

### Scenario: Rate is reflected in output
```gherkin
When I run with `--rate 2.0 --dry-run --json`
Then `data.rate` is 2.0
```

## Feature: MCP tool

### Scenario: sequence_replay requires ack_active
```gherkin
When the MCP tool `sequence_replay` is called without `ack_active=true`
Then the response contains `ACTIVE_TRANSMIT_REQUIRES_ACK`
```

### Scenario: sequence_replay argv builder includes all flags
```gherkin
Given ack_active=true, dry_run=true, rate=2.0, loop=true
When _tool_to_argv("sequence_replay", args) is called
Then argv contains ["sequence", "replay", "--file", ..., "--rate", "2.0", "--loop", "--ack-active", "--dry-run", "--json"]
```
