# CANarchy Specification Template

All design specs (`docs/design/`) and test specs (`docs/tests/`) follow this template.

---

## Standards

### Requirements — EARS + IEEE 29148

Requirements use the **Easy Approach to Requirements Syntax (EARS)** sentence templates combined with **IEEE 29148:2018** modal verbs.

**Modal hierarchy**

| Keyword | Meaning |
|---------|---------|
| `shall` | Mandatory — testable requirement |
| `should` | Recommended but not mandatory |
| `may` | Permitted but optional |

**EARS sentence templates**

| Type | Template | Use when |
|------|----------|----------|
| Ubiquitous | `The <system> shall <response>.` | Always-true invariants, capability declarations |
| Event-driven | `When <trigger>, the <system> shall <response>.` | Command invocations, received inputs |
| State-driven | `While <system state>, the <system> shall <response>.` | Active modes, sustained conditions |
| Unwanted behaviour | `If <precondition>, the <system> shall <response>.` | Error paths, guard conditions, failure modes |
| Optional feature | `Where <feature is included>, the <system> shall <response>.` | Conditional capabilities, flags |

Every requirement in a design spec must use one of these five templates. The requirement ID table includes a **Type** column to make the template choice explicit.

**Examples**

```
Ubiquitous:
  The system shall provide a `canarchy capture <interface>` command.

Event-driven:
  When `capture <interface>` is invoked, the system shall stream frame events
  through the live capture path for all output formats.

State-driven:
  While the scaffold backend is active, the system shall use deterministic
  fixture frames rather than a live CAN interface.

Unwanted behaviour:
  If the transport interface is unavailable, the system shall return a
  structured error with code `TRANSPORT_UNAVAILABLE` and exit code 2.

Optional feature:
  Where `--stdin` is specified, the system shall read JSONL frame events from
  stdin instead of a `--file` capture source.
```

---

### Test Cases — Gherkin (Given / When / Then)

Test cases use **Gherkin-style** structure. Each step starts on its own line, aligned for readability.

```gherkin
Given  <precondition or fixture state>
When   <the operator invokes a command or action>
Then   the system shall <primary observable outcome>
And    <additional assertion>
```

- `Given` — establishes the precondition (backend, fixture file, env var, prior state).
- `When` — the single triggering action (command invocation or API call).
- `Then` — the primary assertion, always phrased as `the system shall ...`.
- `And` — additional assertions chained from `Then`.

**Example**

```gherkin
Given  the scaffold backend is active and `sample.candump` is present
When   the operator runs `canarchy replay --file sample.candump --rate 0 --json`
Then   the system shall exit with code 1
And    the response shall contain an error with code `"INVALID_RATE"`
```

---

## Design Spec Template

```markdown
# Design Spec: <Feature Name>

## Document Control

| Field | Value |
|-------|-------|
| Status | Draft / Planned / Implemented / Partial |
| Command surface | `canarchy <commands>` |
| Primary area | CLI, transport, protocol, analysis, etc. |
| Related specs | links to related design docs |

## Goal

One paragraph: what this feature does and why it exists.

## User-Facing Motivation

Why an analyst or agent needs this capability.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-<AREA>-01` | Ubiquitous | The system shall ... |
| `REQ-<AREA>-02` | Event-driven | When ..., the system shall ... |
| `REQ-<AREA>-03` | Unwanted behaviour | If ..., the system shall ... |
| `REQ-<AREA>-04` | State-driven | While ..., the system shall ... |
| `REQ-<AREA>-05` | Optional feature | Where ..., the system shall ... |

## Command Surface

\```text
canarchy <command> <args> [--json] [--jsonl] [--table] [--raw]
\```

## Responsibilities And Boundaries

In scope: ...
Out of scope: ...

## Data Model

Key fields and structures returned by this command.

## Output Contracts

How each output mode (`--json`, `--jsonl`, `--table`, `--raw`) behaves.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `ERROR_CODE` | when this happens | N |

## Deferred Decisions

Things explicitly not decided yet.
```

---

## Test Spec Template

```markdown
# Test Spec: <Feature Name>

## Document Control

| Field | Value |
|-------|-------|
| Status | Draft / Planned / Implemented / Partial |
| Design doc | `docs/design/<filename>.md` |
| Test file | `tests/test_<module>.py` |

## Requirement Traceability

| REQ ID | Description summary | TEST IDs |
|--------|--------------------|---------||
| `REQ-<AREA>-01` | brief description | `TEST-<AREA>-01`, `TEST-<AREA>-02` |

## Test Cases

### TEST-<AREA>-01 — <Title>

\```gherkin
Given  <precondition>
When   <invocation>
Then   the system shall <assertion>
And    <additional assertion>
\```

**Fixture:** description of any required fixture file or state.

---

### TEST-<AREA>-02 — <Title>

\```gherkin
Given  <precondition>
When   <invocation>
Then   the system shall <assertion>
\```

**Fixture:** none.

## Fixtures And Environment

Summary of fixture files and environment setup required across all tests.

## Explicit Non-Coverage

What is deliberately not tested and why.
```
