# Test Spec: `re suggest` — Signal-Name Suggestions

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/re-suggest.md` |
| Test file | `tests/test_re_suggest.py` |

## Requirement Traceability

| REQ ID | Description summary | TEST IDs |
|--------|--------------------|----------|
| `REQ-SUG-01` | Ranks candidates and attaches names offline | `TEST-SUG-05`, `TEST-SUG-06` |
| `REQ-SUG-02` | Each suggestion has source + confidence; top reported | `TEST-SUG-01`, `TEST-SUG-04` |
| `REQ-SUG-03` | `--reference-dbc` cross-reference | `TEST-SUG-02` |
| `REQ-SUG-04` | J1939 SPN overlap + PGN fallback | `TEST-SUG-01`, `TEST-SUG-03` |
| `REQ-SUG-05` | `--llm` enrichment + envelope note | `TEST-SUG-08` |
| `REQ-SUG-06` | Declined confirmation error | `TEST-SUG-07` |
| `REQ-SUG-07` | Unsupported provider error | `TEST-SUG-09` |
| `REQ-SUG-08` | Metadata-only to the provider | `TEST-SUG-08` |
| `REQ-SUG-09` | MCP heuristic-only exposure | `TEST-SUG-10` |

## Test Cases

### TEST-SUG-01 — SPN overlap names a J1939 field

```gherkin
Given  a candidate covering bits 24..31 of PGN 61444 (EEC1)
When   suggestions are built
Then   the top suggestion shall be "Engine Speed" from source spn
```

**Fixture:** none (constructed candidate).

---

### TEST-SUG-02 — Reference DBC suggests a message signal

```gherkin
Given  a candidate on a message id present in a reference DBC mapping
When   suggestions are built with that mapping
Then   a dbc-sourced suggestion with the DBC signal name shall be present and top
```

**Fixture:** none (in-test signal mapping).

---

### TEST-SUG-03 — PGN fallback when no SPN overlaps

```gherkin
Given  a J1939 candidate whose bit range overlaps no decodable SPN
When   suggestions are built
Then   no spn suggestion shall be present and a heuristic template shall be included
```

**Fixture:** none.

---

### TEST-SUG-04 — Heuristic template is always available

```gherkin
Given  a candidate with no J1939 annotation and no reference DBC
When   suggestions are built
Then   the suggested source shall be heuristic with a behaviour-derived name
```

**Fixture:** none.

---

### TEST-SUG-05 — `re suggest` CLI names candidates offline

```gherkin
Given  an EEC1 capture fixture
When   `canarchy re suggest <fixture> --json` is invoked
Then   the envelope shall report passive mode, name a candidate "Engine Speed" via spn, and carry no external_enrichment
```

**Fixture:** `tests/fixtures/re_suggest_eec1.candump`.

---

### TEST-SUG-06 — `--file` flag form and `--limit`

```gherkin
Given  the EEC1 fixture
When   `canarchy re suggest --file <fixture> --limit 5 --json` is invoked
Then   the candidate count shall be at most 5
```

**Fixture:** `tests/fixtures/re_suggest_eec1.candump`.

---

### TEST-SUG-07 — Declined LLM confirmation sends nothing

```gherkin
Given  `--llm anthropic` with a non-YES reply and no bypass
When   `canarchy re suggest <fixture> --llm anthropic --json` is invoked
Then   the system shall exit 1 with `LLM_CONFIRMATION_DECLINED`
```

**Fixture:** `tests/fixtures/re_suggest_eec1.candump`.

---

### TEST-SUG-08 — LLM enrichment with a mocked client

```gherkin
Given  a mocked LLM client and `CANARCHY_LLM_NONINTERACTIVE=1`
When   `canarchy re suggest <fixture> --llm anthropic --json` is invoked
Then   the top suggestion shall be the LLM-proposed name from source llm
And    the envelope shall carry external_enrichment and an EXTERNAL_SERVICE_CALLED warning
```

**Fixture:** `tests/fixtures/re_suggest_eec1.candump`; provider client patched.

---

### TEST-SUG-09 — Unsupported provider returns a structured error

```gherkin
Given  `--llm nope` with confirmation bypassed
When   `canarchy re suggest <fixture> --llm nope --json` is invoked
Then   the system shall exit 1 with `LLM_PROVIDER_UNSUPPORTED`
```

**Fixture:** `tests/fixtures/re_suggest_eec1.candump`.

---

### TEST-SUG-10 — MCP tool is heuristic-only

```gherkin
Given  the MCP tool registry
Then   `re_suggest` shall be a registered tool whose schema has no `llm` property
And    `_build_argv("re_suggest", {...})` shall map to the heuristic CLI argv
```

**Fixture:** none.

## Fixtures And Environment

`tests/fixtures/re_suggest_eec1.candump` is a synthetic EEC1 (PGN 61444) capture
whose byte 3/4 fields change at a mid-band rate so the analyzer surfaces
candidates over the Engine Speed bit region. The LLM tests patch the provider
client (`_build_client`) so no network call occurs.

## Explicit Non-Coverage

* Real external-LLM requests (the network client is patched in tests).
* Writing accepted suggestions back into a DBC.
