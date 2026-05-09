# Test Spec: Config Show Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/config-show-command.md` |
| Test file | `tests/test_cli.py`, `tests/test_mcp.py` |

## Requirement Traceability

| REQ ID | Description summary | TEST IDs |
|--------|--------------------|----------|
| `REQ-CONFIG-01` | Command exists with the documented CLI surface | `TEST-CONFIG-01`, `TEST-CONFIG-04` |
| `REQ-CONFIG-02` | Effective transport values are reported | `TEST-CONFIG-01`, `TEST-CONFIG-05`, `TEST-CONFIG-06`, `TEST-CONFIG-07` |
| `REQ-CONFIG-03` | Per-field source reporting is present | `TEST-CONFIG-01`, `TEST-CONFIG-02`, `TEST-CONFIG-03`, `TEST-CONFIG-05`, `TEST-CONFIG-06`, `TEST-CONFIG-07` |
| `REQ-CONFIG-04` | Environment variables override file config | `TEST-CONFIG-03` |
| `REQ-CONFIG-05` | File config overrides defaults when env vars are absent | `TEST-CONFIG-02`, `TEST-CONFIG-05`, `TEST-CONFIG-06`, `TEST-CONFIG-07` |
| `REQ-CONFIG-06` | Defaults are reported when no overrides exist | `TEST-CONFIG-01` |
| `REQ-CONFIG-07` | Config-file path and existence are reported | `TEST-CONFIG-01`, `TEST-CONFIG-04` |
| `REQ-CONFIG-08` | Standard output modes remain supported | `TEST-CONFIG-04`, `TEST-CONFIG-08` |

## Test Cases

### TEST-CONFIG-01 — Defaults are reported with default provenance

```gherkin
Given  no relevant config-file entries or environment variables are present
When   the operator runs `canarchy config show --json`
Then   the system shall return the effective default transport configuration
And    each reported source shall be marked as `default`
```

**Fixture:** mocked empty config file state and cleared environment.

---

### TEST-CONFIG-02 — File config overrides defaults

```gherkin
Given  the config file defines transport backend and interface values
When   the operator runs `canarchy config show --json`
Then   the system shall return those file-backed values
And    the affected source entries shall be marked as `file`
```

**Fixture:** mocked config file values with no environment overrides.

---

### TEST-CONFIG-03 — Environment variables override file config

```gherkin
Given  both the config file and environment define overlapping transport settings
When   the operator runs `canarchy config show --json`
Then   the system shall prefer the environment values
And    the overridden source entries shall be marked as `env`
```

**Fixture:** mocked file config plus environment-variable overrides.

---

### TEST-CONFIG-04 — Config-file discovery state is explicit

```gherkin
Given  the default config-file path does not exist
When   the operator runs `canarchy config show --json`
Then   the system shall include the resolved config-file path
And    the result shall report `config_file_found=false`
```

**Fixture:** mocked home directory path and missing config file.

---

### TEST-CONFIG-05 — Capture controls can come from the config file

```gherkin
Given  the config file defines capture-limit and capture-timeout values
When   the operator runs `canarchy config show --json`
Then   the system shall report those effective values
And    both source entries shall be marked as `file`
```

**Fixture:** mocked config file values.

---

### TEST-CONFIG-06 — Active-ack safety can come from the config file

```gherkin
Given  the config file enables active-command acknowledgement
When   the operator runs `canarchy config show --json`
Then   the system shall report `require_active_ack=true`
And    the source entry shall be marked as `file`
```

**Fixture:** mocked config file values.

---

### TEST-CONFIG-07 — Default J1939 DBC can come from the config file

```gherkin
Given  the config file defines `CANARCHY_J1939_DBC`
When   the operator runs `canarchy config show --json`
Then   the system shall report the configured J1939 DBC path
And    the source entry shall be marked as `file`
```

**Fixture:** mocked config file values.

---

### TEST-CONFIG-08 — Text output includes source annotations

```gherkin
Given  the configuration snapshot is available
When   the operator runs `canarchy config show --text`
Then   the system shall render a human-readable configuration summary
And    the output shall include source annotations and config-file status text
```

**Fixture:** mocked empty config file state and cleared environment.

## Fixtures And Environment

* mocked config-file dictionaries returned by `_load_user_config`
* patched environment-variable state
* patched home-directory lookup for the missing-config-file case

## Explicit Non-Coverage

* malformed config-file parsing failures, which are covered by generic configuration loading behavior
* future non-transport config domains that are not yet surfaced by `config show`
