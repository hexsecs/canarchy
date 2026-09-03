# Full-Screen TUI Test Specification

## Document Control

| Field | Value |
|---|---|
| Status | Implemented |
| Related design spec | `docs/design/tui-shell.md` |
| Test modules | `tests/test_tui.py`, `tests/test_tui_app.py`, `tests/test_tui_capture.py`, `tests/test_transport.py` |

## Test Cases

### TEST-TUI-01: TTY Gate

```gherkin
Given the TUI command is launched without an interactive terminal
When command validation runs
Then the command fails with TUI_REQUIRES_TTY and an actionable hint
```

**Fixture:** Patched non-TTY standard streams.

### TEST-TUI-02: Full-Screen Layout And Shared Commands

```gherkin
Given the Textual TUI is running
When commands and structured command results are submitted
Then the expected panes are mounted and shared state is rendered without nested front ends
```

**Fixture:** Textual test pilot and deterministic command executor.

### TEST-TUI-03: Background Capture And Stop

```gherkin
Given a capture session is consuming a live event iterator
When stop is requested with a 250 millisecond join budget
Then the stop event reaches the transport and the worker terminates within the budget
And a worker that exceeds the budget reports CAPTURE_STOP_TIMEOUT and blocks replacement
```

**Fixture:** Deterministic cancellable and stubborn capture doubles.

### TEST-TUI-04: Idle Python-CAN Cancellation

```gherkin
Given a python-can bus is idle and recv returns no frame
When the capture stop event is set
Then capture iteration exits after bounded receive polling and the bus is shut down
```

**Fixture:** Fake python-can bus recording receive timeouts and shutdown.

### TEST-TUI-05: Finite Stream Drain

```gherkin
Given a finite capture source produces 1000 events before the first UI drain
When the capture producer finishes
Then the TUI retains the session and renders all 1000 events before releasing it
```

**Fixture:** Textual test pilot with a 1000-event burst transport.

### TEST-TUI-06: Paused Completion

```gherkin
Given presentation is paused while a finite capture source completes
When timer drains run and presentation later resumes
Then no buffered events are consumed while paused and all are rendered after resume
```

**Fixture:** Textual test pilot with a finite burst transport.

### TEST-TUI-07: Overflow Telemetry

```gherkin
Given capture produces more events than the bounded queue can hold
When the producer evicts old events and the TUI drains the queue
Then received, drained, dropped, depth, and high-water counts are exact and loss is visible in status
```

**Fixture:** Two-item capture queue with a ten-event producer.

### TEST-TUI-08: Capture Errors

```gherkin
Given the transport raises a structured or unexpected error
When the capture worker handles the failure
Then the error is queued for the TUI with a stable code, message, and hint
```

**Fixture:** Failing transport doubles.

### TEST-TUI-09: Explicit Stop Drain

```gherkin
Given a live capture worker has buffered more than one UI drain batch
When the operator stops capture
Then the worker exits and every buffered event is rendered before the session is released
```

**Fixture:** Textual test pilot with a stoppable 600-event burst transport.

## Traceability

| Requirement | Tests |
|---|---|
| REQ-TUI-01 | TEST-TUI-01 |
| REQ-TUI-02 | TEST-TUI-02 |
| REQ-TUI-03 | TEST-TUI-02 |
| REQ-TUI-04 | TEST-TUI-02 |
| REQ-TUI-05 | TEST-TUI-03, TEST-TUI-05 |
| REQ-TUI-06 | TEST-TUI-03, TEST-TUI-04, TEST-TUI-09 |
| REQ-TUI-07 | TEST-TUI-03, TEST-TUI-08 |
| REQ-TUI-08 | TEST-TUI-05, TEST-TUI-08, TEST-TUI-09 |
| REQ-TUI-09 | TEST-TUI-06 |
| REQ-TUI-10 | TEST-TUI-07 |
| REQ-TUI-11 | TEST-TUI-07 |
| REQ-TUI-12 | TEST-TUI-02, TEST-TUI-05, TEST-TUI-06 |

## Not Tested

Real adapter shutdown timing is hardware-dependent and is not exercised in CI. The tests enforce the polling contract and worker lifecycle with deterministic fake buses; operator validation remains necessary for each physical backend.
