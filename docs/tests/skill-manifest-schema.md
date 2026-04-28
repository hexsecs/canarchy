# Test Spec: Skill Manifest Schema

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/skill-manifest-schema.md` |
| Test file | `tests/test_skills_provider.py`; fixtures live under `tests/fixtures/skills/` |

## Requirement Traceability

| REQ ID | Description summary | TEST IDs |
|--------|--------------------|----------|
| `REQ-SKILLMAN-01` | Schema is versioned | `TEST-SKILLMAN-01`, `TEST-SKILLMAN-02` |
| `REQ-SKILLMAN-02` | Identity, provenance, and content-entry fields are distinct | `TEST-SKILLMAN-01` |
| `REQ-SKILLMAN-03` | Each manifest identifies one skill with provider-facing identity | `TEST-SKILLMAN-01` |
| `REQ-SKILLMAN-04` | Required core metadata is present | `TEST-SKILLMAN-01`, `TEST-SKILLMAN-02` |
| `REQ-SKILLMAN-05` | Optional metadata can be present without redefining required fields | `TEST-SKILLMAN-01`, `TEST-SKILLMAN-03` |
| `REQ-SKILLMAN-06` | Missing required fields are rejected by provider validation | `TEST-SKILLMAN-02` |
| `REQ-SKILLMAN-07` | Schema is suitable for provider/catalog/cache and future MCP workflows | `TEST-SKILLMAN-01`, `TEST-SKILLMAN-03` |
| `REQ-SKILLMAN-08` | Canonical example manifests support provider validation tests | `TEST-SKILLMAN-01`, `TEST-SKILLMAN-03` |

## Test Cases

### TEST-SKILLMAN-01 — Canonical manifest fixture expresses the full core contract

```gherkin
Given  a canonical example skill manifest fixture exists
When   the manifest is inspected against the documented schema
Then   the system shall expose a schema version
And    the manifest shall include distinct identity, provider, provenance, compatibility, and content-entry sections
And    optional workflow metadata may also be present without changing the required core fields
```

**Fixture:** `tests/fixtures/skills/j1939_compare_triage.skill.yaml`.

---

### TEST-SKILLMAN-02 — Invalid manifest fixture demonstrates required-field rejection targets

```gherkin
Given  an intentionally incomplete skill manifest fixture exists
When   the provider validation path checks that manifest
Then   the system shall reject the manifest as invalid
And    the failure shall be attributable to missing required identity, provenance, compatibility, or content-entry fields rather than inferred defaults
```

**Fixture:** `tests/fixtures/skills/invalid_missing_entry.skill.yaml`.

---

### TEST-SKILLMAN-03 — Minimal manifest fixture remains provider-friendly

```gherkin
Given  a minimal valid skill manifest fixture exists
When   the manifest is inspected against the documented schema
Then   the system shall expose enough metadata for provider catalog listing and fetch provenance
And    optional metadata such as examples or dependencies may be absent without invalidating the manifest
```

**Fixture:** `tests/fixtures/skills/uds_trace_minimal.skill.yaml`.

## Fixtures And Environment

Current fixtures for this issue are provider-validation artifacts:

* `tests/fixtures/skills/j1939_compare_triage.skill.yaml`
* `tests/fixtures/skills/uds_trace_minimal.skill.yaml`
* `tests/fixtures/skills/invalid_missing_entry.skill.yaml`

Provider refresh and fetch paths validate manifest shape before accepting catalog entries.

## Explicit Non-Coverage

* MCP or agent execution behavior, which belongs to `#167`
* standalone manifest linting outside provider refresh/fetch workflows
