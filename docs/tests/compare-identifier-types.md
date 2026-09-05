# Test Spec: Comparison Identifier Types

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/compare-identifier-types.md` |
| Test files | `tests/test_compare.py`, `tests/test_mcp.py` |

## Requirement Traceability

| REQ ID | Description summary | TEST IDs |
|--------|---------------------|----------|
| REQ-COMPARE-ID-01 | Independent metrics and flags | TEST-COMPARE-ID-01, TEST-COMPARE-ID-02 |
| REQ-COMPARE-ID-02 | Typed rows and pair counts | TEST-COMPARE-ID-01, TEST-COMPARE-ID-02 |
| REQ-COMPARE-ID-03 | Complete typed summaries, numeric compatibility | TEST-COMPARE-ID-01, TEST-COMPARE-ID-02, TEST-COMPARE-ID-03 |
| REQ-COMPARE-ID-04 | Ranking, tie order, top cap | TEST-COMPARE-ID-01, TEST-COMPARE-ID-02 |
| REQ-COMPARE-ID-05 | Standard rows lack J1939 metadata | TEST-COMPARE-ID-01 |
| REQ-COMPARE-ID-06 | CLI/MCP parity | TEST-COMPARE-ID-02, TEST-COMPARE-ID-04 |

## Test Cases

### TEST-COMPARE-ID-01 — Independent metrics

```gherkin
Given two captures containing standard and extended identifiers with numeric value 0x123
And only the extended stream changes rate, cycle time, and entropy
When the captures are compared
Then the system shall report independent counts, rates, timing, entropy, and flags
And the standard row shall have no flags or J1939 annotation
And the extended row shall rank first and appear in the typed change summaries
```

**Fixture:** Temporary candump files in `test_colliding_identifier_types_keep_independent_metrics`.

### TEST-COMPARE-ID-02 — Identifier type switch through CLI

```gherkin
Given a standard-only baseline and extended-only comparison with the same numeric ID
When the CLI compares them with top set to one
Then the system shall report two identifier pairs and one returned row
And the standard dropped row shall win the equal-score tie
And the uncapped summary shall identify the extended message as new and standard message as dropped
And the result shall not claim that no changes crossed the thresholds
```

**Fixture:** Temporary candump files in `test_identifier_type_switch_is_new_and_dropped_through_cli`.

### TEST-COMPARE-ID-03 — Numeric compatibility

```gherkin
Given both forms of numeric ID 0x123 are new relative to the baseline
When the captures are compared
Then the system shall list 0x123 once in new_ids
And new_identifiers shall contain both types sorted standard before extended
```

**Fixture:** Temporary candump files in `test_numeric_summary_deduplicates_colliding_new_identifiers`.

### TEST-COMPARE-ID-04 — MCP result

```gherkin
Given a standard-only baseline and extended-only comparison with the same numeric ID
When the MCP compare tool is invoked
Then the system shall return separate typed rows with new and dropped flags
And its typed summaries shall preserve both identities
```

**Fixture:** Temporary candump files in `test_call_tool_compare_preserves_identifier_type`.

## Fixtures And Environment

All tests use local temporary files and require no CAN hardware or external network.

## Explicit Non-Coverage

No changes to channel identity, other analysis commands, or live transport behavior are covered by this fix.
