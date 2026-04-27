# Test Spec: Skills Provider Workflows

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/skills-provider-workflows.md` |
| Test file | `tests/test_skills_provider.py` |

## Requirement Traceability

| REQ ID | Description summary | TEST IDs |
|--------|--------------------|----------|
| `REQ-SKILLPROV-01` | Skills provider command family exists | `TEST-SKILLPROV-01`, `TEST-SKILLPROV-02`, `TEST-SKILLPROV-03` |
| `REQ-SKILLPROV-02` | Provider abstraction exists independently of execution | `TEST-SKILLPROV-04`, `TEST-SKILLPROV-05` |
| `REQ-SKILLPROV-03` | `skills provider list` reports registered providers | `TEST-SKILLPROV-01` |
| `REQ-SKILLPROV-04` | `skills search` returns structured manifest-derived results | `TEST-SKILLPROV-02`, `TEST-SKILLPROV-05` |
| `REQ-SKILLPROV-05` | `skills fetch` resolves cached files and reports provenance fields | `TEST-SKILLPROV-03`, `TEST-SKILLPROV-06` |
| `REQ-SKILLPROV-06` | `skills cache list` reports cached provider entries | `TEST-SKILLPROV-07` |
| `REQ-SKILLPROV-07` | `skills cache refresh` refreshes provider catalogs | `TEST-SKILLPROV-04` |
| `REQ-SKILLPROV-08` | Auto-refresh behavior is available for future cold-cache resolution | Deferred |
| `REQ-SKILLPROV-09` | Unknown providers return structured error | `TEST-SKILLPROV-08` |
| `REQ-SKILLPROV-10` | Missing skill names return structured error | `TEST-SKILLPROV-06` |
| `REQ-SKILLPROV-11` | Cold cache returns structured cache miss | Deferred |
| `REQ-SKILLPROV-12` | Invalid manifests are rejected | `TEST-SKILLPROV-04` |

## Test Cases

### TEST-SKILLPROV-01 — Provider list reports registered skills providers

```gherkin
Given  a skills provider registry is available
When   the operator runs `canarchy skills provider list --json`
Then   the system shall return a structured list of registered skills providers
```

**Fixture:** mocked registry.

---

### TEST-SKILLPROV-02 — Search returns manifest-derived skill metadata

```gherkin
Given  a provider search returns at least one manifest-derived skill descriptor
When   the operator runs `canarchy skills search <query> --json`
Then   the system shall return provider, skill name, publisher, version, and provider-facing skill ref
And    the result may include manifest-derived tags in metadata
```

**Fixture:** mocked descriptor result.

---

### TEST-SKILLPROV-03 — Fetch reports local manifest and entry paths

```gherkin
Given  a provider resolution returns local cached manifest and entry paths
When   the operator runs `canarchy skills fetch <provider>:<skill> --json`
Then   the system shall return the local manifest path, local entry path, and cache status
```

**Fixture:** mocked resolution result.

---

### TEST-SKILLPROV-04 — Refresh rejects invalid manifests

```gherkin
Given  a repository-backed manifest is missing required schema fields
When   the provider refresh path parses that manifest
Then   the system shall reject it with `SKILL_MANIFEST_INVALID`
```

**Fixture:** `tests/fixtures/skills/invalid_missing_entry.skill.yaml`.

---

### TEST-SKILLPROV-05 — Refresh builds a catalog from valid manifests

```gherkin
Given  repository-backed skill manifest files are available
When   the provider refresh path inspects those manifests
Then   the system shall build a manifest-derived provider catalog
And    the provider search path shall be able to return those descriptors later
```

**Fixture:** `tests/fixtures/skills/j1939_compare_triage.skill.yaml`, `tests/fixtures/skills/uds_trace_minimal.skill.yaml`.

---

### TEST-SKILLPROV-06 — Resolve fetches cached files for a valid skill

```gherkin
Given  a cached provider catalog contains a valid skill entry
When   the provider resolve path is asked for that skill name
Then   the system shall fetch or reuse the local manifest and entry files
And    the returned resolution shall include provider-facing provenance fields
```

**Fixture:** mocked catalog entry and downloaded files.

---

### TEST-SKILLPROV-07 — Cache list reports cached skill counts

```gherkin
Given  a provider manifest is stored in the local skills cache
When   the operator runs `canarchy skills cache list --json`
Then   the system shall report the provider name and cached skill count
```

**Fixture:** temporary cache manifest.

---

### TEST-SKILLPROV-08 — Unknown provider returns structured error

```gherkin
Given  the requested skills provider is not registered
When   the operator runs `canarchy skills cache refresh --provider missing --json`
Then   the system shall exit with code `3`
And    the response shall contain an error with code `"SKILL_PROVIDER_NOT_FOUND"`
```

**Fixture:** mocked registry without the requested provider.

## Fixtures And Environment

* `tests/fixtures/skills/j1939_compare_triage.skill.yaml`
* `tests/fixtures/skills/uds_trace_minimal.skill.yaml`
* `tests/fixtures/skills/invalid_missing_entry.skill.yaml`
* temporary cache directories for cache-list and resolution tests
* mocked provider registry and mocked GitHub transport helpers for deterministic refresh/resolve flows

## Explicit Non-Coverage

* MCP exposure of skills commands, which belongs to `#167`
* actual skill execution semantics, which are out of scope for this issue
* non-GitHub provider implementations
