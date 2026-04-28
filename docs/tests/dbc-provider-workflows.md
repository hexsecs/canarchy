# Test Spec: Provider-Backed DBC Workflows

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Related design spec | `docs/design/dbc-provider-workflows.md` |
| Primary test area | CLI, DBC |

## Test Objectives

Validate the shipped provider-backed DBC workflow from provider discovery and cache management through provider-ref resolution and provenance reporting in DBC-backed commands.

## Coverage Requirements

* provider registry listing
* provider-backed search and fetch flows
* cache list, prune, and refresh behavior
* provider-ref normalization and resolution
* `dbc_source` provenance for local and provider-backed decode, encode, and inspect paths
* `auto_refresh` cold-cache behavior and failure handling
* structured provider and cache errors

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-DBCP-01` | `TEST-DBCP-01`, `TEST-DBCP-02`, `TEST-DBCP-03`, `TEST-DBCP-04`, `TEST-DBCP-05`, `TEST-DBCP-06` |
| `REQ-DBCP-02` | `TEST-DBCP-01` |
| `REQ-DBCP-03` | `TEST-DBCP-02` |
| `REQ-DBCP-04` | `TEST-DBCP-03` |
| `REQ-DBCP-05` | `TEST-DBCP-04` |
| `REQ-DBCP-06` | `TEST-DBCP-05` |
| `REQ-DBCP-07` | `TEST-DBCP-06` |
| `REQ-DBCP-08` | `TEST-DBCP-07`, `TEST-DBCP-08`, `TEST-DBCP-09` |
| `REQ-DBCP-09` | `TEST-DBCP-07`, `TEST-DBCP-08`, `TEST-DBCP-09`, `TEST-DBCP-10` |
| `REQ-DBCP-10` | `TEST-DBCP-10` |
| `REQ-DBCP-11` | `TEST-DBCP-12`, `TEST-DBCP-13` |
| `REQ-DBCP-12` | `TEST-DBCP-11` |
| `REQ-DBCP-13` | `TEST-DBCP-14` |
| `REQ-DBCP-14` | `TEST-DBCP-15` |

## Representative Test Cases

### `TEST-DBCP-01` — Provider list returns registered providers

```gherkin
Given  the default provider registry is available
When   the operator runs `canarchy dbc provider list --json`
Then   the system shall return a provider list including the local provider
```

**Fixture:** default provider registry.

---

### `TEST-DBCP-02` — Provider-backed search returns structured results

```gherkin
Given  a mocked `opendbc` provider returns a catalog search result
When   the operator runs `canarchy dbc search toyota --provider opendbc --json`
Then   the system shall return one or more structured search results
And    each result shall include provider, name, version, and source-ref fields
```

**Fixture:** mocked provider registry.

---

### `TEST-DBCP-03` — Provider-backed fetch resolves to a cached local file

```gherkin
Given  a mocked provider registry can resolve `opendbc:toyota_tnga_k_pt_generated`
When   the operator runs `canarchy dbc fetch opendbc:toyota_tnga_k_pt_generated --json`
Then   the system shall return the resolved provider, DBC name, version, local path, and cache status
```

**Fixture:** mocked provider registry and fixture-backed local DBC path.

---

### `TEST-DBCP-04` — Cache list returns manifest entries

```gherkin
Given  the DBC cache contains a saved provider manifest
When   the operator runs `canarchy dbc cache list --json`
Then   the system shall return one or more cache entries with provider and DBC-count metadata
```

**Fixture:** temporary cache manifest.

---

### `TEST-DBCP-05` — Cache prune removes stale snapshot paths

```gherkin
Given  the DBC cache contains stale and current provider snapshot directories
When   the operator runs `canarchy dbc cache prune --json`
Then   the system shall return the removed stale paths
And    the current pinned snapshot shall remain available
```

**Fixture:** temporary cache directory.

---

### `TEST-DBCP-06` — Cache refresh returns refreshed provider metadata

```gherkin
Given  a mocked provider registry can refresh the `opendbc` catalog
When   the operator runs `canarchy dbc cache refresh --provider opendbc --json`
Then   the system shall return the refreshed provider name
And    the response shall include the refreshed DBC count
```

**Fixture:** mocked provider registry.

---

### `TEST-DBCP-07` — Decode resolves provider ref and reports provenance

```gherkin
Given  a mocked provider registry can resolve a provider-backed DBC ref
When   the operator runs `canarchy decode --file tests/fixtures/sample.candump --dbc opendbc:toyota_tnga_k_pt_generated --json`
Then   the system shall decode using the resolved local DBC path
And    `data.dbc_source` shall include provider, logical DBC name, version, and path
```

**Fixture:** `tests/fixtures/sample.candump`, mocked provider registry, `tests/fixtures/sample.dbc`.

---

### `TEST-DBCP-08` — Encode resolves provider ref and reports provenance

```gherkin
Given  a mocked provider registry can resolve a provider-backed DBC ref
When   the operator runs `canarchy encode --dbc opendbc:toyota_tnga_k_pt_generated EngineStatus1 CoolantTemp=55 OilTemp=65 Load=40 LampState=1 --json`
Then   the system shall encode using the resolved local DBC path
And    `data.dbc_source` shall include provider-backed provenance metadata
```

**Fixture:** mocked provider registry and `tests/fixtures/sample.dbc`.

---

### `TEST-DBCP-09` — Inspect resolves provider ref and reports provenance

```gherkin
Given  a mocked provider registry can resolve a provider-backed DBC ref
When   the operator runs `canarchy dbc inspect opendbc:toyota_tnga_k_pt_generated --json`
Then   the system shall inspect the resolved local DBC path
And    `data.dbc_source` shall include provider-backed provenance metadata
```

**Fixture:** mocked provider registry and `tests/fixtures/sample.dbc`.

---

### `TEST-DBCP-10` — Provider alias normalization and local provenance split

```gherkin
Given  the provider registry supports both provider-backed and local DBC resolution
When   the operator resolves `comma:<name>` and a direct local DBC path through DBC-backed commands
Then   the system shall normalize `comma:` to the `opendbc` provider
And    local-path resolution shall report `provider` as `local` with `version` set to `null`
```

**Fixture:** mocked provider registry and `tests/fixtures/sample.dbc`.

---

### `TEST-DBCP-11` — Cache refresh rejects unknown providers cleanly

```gherkin
Given  the requested provider name is not registered
When   the operator runs `canarchy dbc cache refresh --provider unknown_provider --json`
Then   the command shall exit with code `3`
And    `errors[0].code` shall equal `"DBC_PROVIDER_NOT_FOUND"`
```

**Fixture:** default provider registry.

---

### `TEST-DBCP-12` — Auto-refresh resolves a cold cache when enabled

```gherkin
Given  the provider cache is cold and `[dbc.providers.opendbc].auto_refresh` is enabled
When   a provider-backed DBC ref is resolved
Then   the system shall refresh the provider manifest automatically
And    the resolution shall succeed without requiring a manual refresh step
```

**Fixture:** mocked provider refresh and temporary cache path.

---

### `TEST-DBCP-13` — Auto-refresh failure returns a clean error

```gherkin
Given  the provider cache is cold and auto-refresh is enabled but refresh fails
When   a provider-backed DBC ref is resolved
Then   the system shall return a structured DBC error
And    the command path shall not crash while handling the refresh failure
```

**Fixture:** mocked provider refresh failure.

---

### `TEST-DBCP-14` — Unknown provider-backed DBC name returns not found

```gherkin
Given  the selected provider catalog does not contain the requested DBC name
When   the operator runs `canarchy dbc fetch opendbc:does_not_exist --json`
Then   the command shall exit with code `3`
And    `errors[0].code` shall equal `"DBC_NOT_FOUND"`
```

**Fixture:** mocked provider registry.

---

### `TEST-DBCP-15` — Cold-cache provider resolution returns cache-miss guidance by default

```gherkin
Given  the provider cache is cold and auto-refresh is disabled
When   a provider-backed DBC ref is resolved
Then   the system shall return a structured `DBC_CACHE_MISS` error
And    the error shall guide the operator to run `canarchy dbc cache refresh --provider opendbc`
```

**Fixture:** mocked provider manifest miss.

---

## Fixtures And Environment

Coverage uses:

* `tests/fixtures/sample.candump`
* `tests/fixtures/sample.dbc`
* mocked provider registries and mocked `opendbc` provider descriptors
* temporary cache roots and manifests for cache list/prune behavior

## Explicit Non-Coverage

* network-level end-to-end provider refresh against live GitHub APIs
* additional provider implementations beyond the current local plus `opendbc` model
* eager full-catalog DBC-file download during manifest refresh

## Traceability

This spec maps to the current provider registry, cache, and CLI coverage in `tests/test_dbc_provider.py`.
