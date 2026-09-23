# Full-Screen TUI Test Specification

## Document Control

| Field | Value |
|---|---|
| Status | Implemented |
| Related design spec | `docs/design/tui-shell.md` |
| Test modules | `tests/test_tui_snapshots.py`, `tests/test_tui_app.py`, `tests/test_tui_capture.py`, `tests/test_transport.py` |

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

### TEST-TUI-10: Help Retains Pane Data

```gherkin
Given the TUI has folded a command result into the traffic and J1939 panes
When the operator submits `/help` through the command input
Then the system shall keep every displayed row and every retained row store entry
And the hotkey table shall appear in the alerts log without a `panes cleared` alert
And pane filters shall be unchanged and a filter round-trip shall restore every row
And `/clear` shall still empty both the tables and the row stores
```

**Fixture:** Textual test pilot with the scaffold capture factory; fold-layer assertion on `_handle_hotkey` dispositions (`/help` → `LOCAL`, `/clear` → `CLEARED`).

### TEST-TUI-11: Help During Capture And While Paused

```gherkin
Given a live capture session is running and has rendered its frames
When the operator submits `/help` while capturing and again while presentation is paused
Then the system shall retain the same capture session in the running state
And displayed rows, retained row stores, and the paused flag shall be unchanged
```

**Fixture:** Textual test pilot with a capture transport that parks on the stop event so the session stays live.

### TEST-TUI-12: Malformed Slash Quoting

```gherkin
Given a live capture session is running and the traffic pane holds rendered rows
When the operator submits `/capture "` and then `/capture vcan0\` through the real Input event
Then the system shall report each parse failure in the alerts log without raising out of the app
And the running capture session and the displayed rows shall be unchanged
And a subsequent valid command shall still execute and populate its pane
```

**Fixture:** Textual test pilot with a capture transport that parks on the stop event.

### TEST-TUI-13: Capture Argument Validation

```gherkin
Given a live capture session is running on `vcan0`
When the operator submits `/capture ""`, `/capture vcan1 --candump`, and `/capture`
Then the system shall reject each form with its own alerts diagnostic
And the capture factory shall not be invoked again
And the running session, its interface, and the displayed rows shall be unchanged
```

**Fixture:** Textual test pilot with a recording capture factory over a parked capture transport.

### TEST-TUI-14: Stop Argument Validation

```gherkin
Given a capture is running and traffic rows are displayed
When  the operator submits `/stop "`
Then  the alerts log shall report the parse failure
And   the capture shall still be running
When  the operator submits `/stop now`
Then  the alerts log shall state that /stop takes no arguments
And   the capture shall still be running
And   the displayed rows shall be unchanged
When  the operator submits a bare `/stop`
Then  the capture shall stop
```

**Fixture:** Textual test pilot over a parked capture transport.

### TEST-TUI-15: Raw-Text Slash Arguments

```gherkin
Given the TUI is running
When  the operator submits `/filter traffic "`
Then  the traffic filter shall be the literal quote character
And   no parse-failure diagnostic shall be reported
When  the operator submits `/sort "`
Then  the alerts log shall show the /sort usage hint
```

**Fixture:** Textual test pilot. Guards the scoping of REQ-TUI-15: tokenising
every slash command would make this filter needle unusable.

### TEST-TUI-16: Command Result Visibility

```gherkin
Given the TUI has event rows and is running in an 80-column terminal
When the operator runs stats, DBC inspection, doctor, config, or PGN/SPN reference lookups
Then the answer appears in a scrollable, selectable result view
And F2 and Esc return to the panes without losing event rows or filters
```

**Fixture:** Textual test pilot, sample capture, and complex DBC.

### TEST-TUI-17: Help, Version, And Error Output

```gherkin
Given the full-screen TUI is running
When the operator submits --help, --version, or an invalid command
Then the text appears in the result view instead of leaking behind the screen
And the operator can close the view and continue using the panes
```

**Fixture:** Textual test pilot at 80 by 24 cells.

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
| REQ-TUI-13 | TEST-TUI-10, TEST-TUI-11 |
| REQ-TUI-14 | TEST-TUI-10, TEST-TUI-11 |
| REQ-TUI-15 | TEST-TUI-12, TEST-TUI-14 |
| REQ-TUI-16 | TEST-TUI-13 |
| REQ-TUI-17 | TEST-TUI-14 |
| REQ-TUI-18 | TEST-TUI-15 |
| REQ-TUI-19 | TEST-TUI-16, TEST-TUI-17 |
| REQ-TUI-20 | TEST-TUI-16, TEST-TUI-17 |

## Not Tested

Real adapter shutdown timing is hardware-dependent and is not exercised in CI. The tests enforce the polling contract and worker lifecycle with deterministic fake buses; operator validation remains necessary for each physical backend.
