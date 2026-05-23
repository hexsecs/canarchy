# Test Spec: `dbc inspect --search` and `dbc signals`

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Covers | `docs/design/dbc-inspect-search.md` |
| Issue | #361 |

## Scenarios

```gherkin
Feature: DBC keyword search via `dbc inspect --search` and `dbc signals`

  Background:
    Given the sample.dbc fixture is available with messages EngineStatus1 and EngineStatus2

  Scenario: --search filters messages to those containing matching signals
    When the user runs `dbc inspect sample.dbc --search coolant --json`
    Then the exit code is 0
    And data.messages contains exactly 1 message
    And that message contains signal "CoolantTemp"
    And that message does not contain signal "OilTemp"

  Scenario: --search with --signals-only filters the flat signal list
    When the user runs `dbc inspect sample.dbc --signals-only --search temp --json`
    Then the exit code is 0
    And data.signals contains "CoolantTemp" and "OilTemp"
    And data.signals does not contain "Load"

  Scenario: --search with no matches returns empty list
    When the user runs `dbc inspect sample.dbc --search nonexistentsignal --json`
    Then the exit code is 0
    And data.messages is an empty list

  Scenario: dbc signals returns signal-centric output
    When the user runs `dbc signals sample.dbc --json`
    Then the exit code is 0
    And data.signal_count equals 6
    And data.signals has 6 entries

  Scenario: dbc signals --search filters signal list
    When the user runs `dbc signals sample.dbc --search coolant --json`
    Then the exit code is 0
    And data.signals contains only "CoolantTemp"

  Scenario: dbc signals text output renders signal rows
    When the user runs `dbc signals sample.dbc --search temp`
    Then the exit code is 0
    And stdout contains "CoolantTemp"
    And stdout contains "OilTemp"
    And stdout does not contain "Load"

  Scenario: --search is case-insensitive
    When the user runs `dbc inspect sample.dbc --search COOLANT --json`
    And the user runs `dbc inspect sample.dbc --search coolant --json`
    Then both return identical data.messages arrays
```

## Traceability

| Scenario | Requirement |
|----------|-------------|
| --search filters messages | REQ-DBC-SEARCH-03 |
| --search with --signals-only | REQ-DBC-SEARCH-04 |
| No matches returns empty | REQ-DBC-SEARCH-09 |
| dbc signals returns signal-centric output | REQ-DBC-SEARCH-05 |
| dbc signals --search | REQ-DBC-SEARCH-04, REQ-DBC-SEARCH-05 |
| dbc signals text output | REQ-DBC-SEARCH-05 |
| Case-insensitive | REQ-DBC-SEARCH-06 |
