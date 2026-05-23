# Test Spec: `canarchy send --dbc` — DBC-Aware Signal Transmit

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Covers | `docs/design/send-dbc-command.md` |
| Issue | #360 |

## Scenarios

```gherkin
Feature: DBC-aware signal transmit via `send --dbc`

  Background:
    Given the scaffold transport backend is configured
    And the sample.dbc fixture is available

  Scenario: Dry-run returns encoded frame without transmitting
    Given a valid DBC file with message "EngineStatus1"
    When the user runs `send can0 --dbc sample.dbc --message EngineStatus1 --signals CoolantTemp=80 OilTemp=90 Load=50 LampState=0 --dry-run --json`
    Then the exit code is 0
    And the envelope data.mode is "dry_run"
    And the envelope data.message is "EngineStatus1"
    And the envelope data.signals.CoolantTemp is 80
    And the envelope data.frame contains an arbitration_id
    And the envelope data.events is empty

  Scenario: Dry-run requires no interface
    When the user runs `send --dbc sample.dbc --message EngineStatus1 --signals ... --dry-run --json`
    Then the exit code is 0
    And the envelope data.mode is "dry_run"

  Scenario: Active transmit sends frame and emits events
    When the user runs `send can0 --dbc sample.dbc --message EngineStatus1 --signals ... --json`
    Then the exit code is 0
    And the envelope data.mode is "active"
    And a preflight warning is written to stderr
    And the envelope data.events is non-empty

  Scenario: --count N sends frame N times
    Given transport.send_events is monitored
    When the user runs `send can0 --dbc sample.dbc --message EngineStatus1 --signals ... --count 3 --json`
    Then the exit code is 0
    And transport.send_events was called exactly 3 times

  Scenario: Missing --message returns MISSING_MESSAGE error
    When the user runs `send can0 --dbc sample.dbc --signals CoolantTemp=80 --json`
    Then the exit code is 3
    And the envelope errors[0].code is "MISSING_MESSAGE"

  Scenario: Malformed signal assignment returns INVALID_SIGNAL_ASSIGNMENT error
    When the user runs `send can0 --dbc sample.dbc --message EngineStatus1 --signals CoolantTemp --json`
    Then the exit code is 3
    And the envelope errors[0].code is "INVALID_SIGNAL_ASSIGNMENT"

  Scenario: Non-positive --count returns INVALID_COUNT error
    When the user runs `send can0 --dbc sample.dbc --message EngineStatus1 --count 0 --json`
    Then the exit code is 3
    And the envelope errors[0].code is "INVALID_COUNT"

  Scenario: Non-positive --rate returns INVALID_RATE error
    When the user runs `send can0 --dbc sample.dbc --message EngineStatus1 --signals ... --rate -1 --json`
    Then the exit code is 3
    And the envelope errors[0].code is "INVALID_RATE"

  Scenario: Raw send is backwards-compatible
    When the user runs `send can0 0x123 11223344 --json`
    Then the exit code is 0
    And the envelope data.frame.arbitration_id is 0x123
```

## Traceability

| Scenario | Requirement |
|----------|-------------|
| Dry-run returns encoded frame | REQ-SEND-DBC-03 |
| Dry-run requires no interface | REQ-SEND-DBC-07 |
| Active transmit sends frame | REQ-SEND-DBC-02, REQ-SEND-DBC-06 |
| --count N sends N times | REQ-SEND-DBC-04 |
| Missing --message error | REQ-SEND-DBC-08 |
| Malformed signal assignment error | REQ-SEND-DBC-09 |
| Invalid --count error | REQ-SEND-DBC-11 |
| Invalid --rate error | REQ-SEND-DBC-10 |
| Raw send backwards-compatible | REQ-SEND-DBC-14 |
