# Design Spec: Provider-Backed DBC Workflows

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy dbc provider list`, `dbc search`, `dbc fetch`, `dbc cache list`, `dbc cache prune`, `dbc cache refresh`, `decode --dbc <ref>`, `encode --dbc <ref>`, `dbc inspect <ref>` |
| Primary area | CLI, DBC |
| Related specs | `docs/design/dbc-command-workflows.md`, `docs/design/dbc-inspect-command.md`, `docs/design/reverse-engineering-helpers.md` |

## Goal

Provide a provider-backed DBC workflow that lets operators discover, cache, resolve, and use DBC files from a configured catalog without manually managing local schema files.

## User-Facing Motivation

Operators often have a capture before they have the matching DBC on disk. CANarchy should let them search a provider catalog, fetch the likely schema, and use provider refs directly with decode, encode, and inspection commands while preserving reproducibility through cache state and provenance metadata.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-DBCP-01` | Ubiquitous | The system shall provide `dbc provider list`, `dbc search`, `dbc fetch`, `dbc cache list`, `dbc cache prune`, and `dbc cache refresh` commands for provider-backed DBC workflows. |
| `REQ-DBCP-02` | Event-driven | When `dbc provider list` is invoked, the system shall return the registered DBC providers and their operator-facing metadata. |
| `REQ-DBCP-03` | Event-driven | When `dbc search <query>` is invoked, the system shall return ranked provider-catalog matches including provider name, logical DBC name, version, source ref, and provider metadata where available. |
| `REQ-DBCP-04` | Event-driven | When `dbc fetch <ref>` is invoked with a provider ref, the system shall resolve that ref to a local cached file and return the resolved provider, logical DBC name, version, local path, and cache status. |
| `REQ-DBCP-05` | Event-driven | When `dbc cache list` is invoked, the system shall return cached provider-manifest entries including provider identity, pinned commit, and DBC count. |
| `REQ-DBCP-06` | Event-driven | When `dbc cache prune` is invoked, the system shall remove stale provider snapshot directories and return the removed paths. |
| `REQ-DBCP-07` | Event-driven | When `dbc cache refresh` is invoked, the system shall refresh the selected provider catalog and return the refreshed provider name and DBC count. |
| `REQ-DBCP-08` | Event-driven | When `decode`, `encode`, or `dbc inspect` is invoked with a provider ref such as `opendbc:<name>`, the system shall resolve that ref through the provider registry before loading the local DBC runtime file. |
| `REQ-DBCP-09` | Event-driven | When a DBC-backed command resolves a local path or provider ref, the system shall attach `data.dbc_source` describing the provider, logical DBC name, pinned version, and resolved local path used for that command. |
| `REQ-DBCP-10` | Optional feature | Where the `comma:<name>` alias is specified, the system shall normalize it to the `opendbc` provider before resolution. |
| `REQ-DBCP-11` | Optional feature | Where `[dbc.providers.opendbc].auto_refresh = true` is configured and the provider cache is cold, the system shall refresh the provider manifest automatically before retrying resolution. |
| `REQ-DBCP-12` | Unwanted behaviour | If a requested provider is not registered, the system shall return a structured error with code `DBC_PROVIDER_NOT_FOUND` and exit code 3. |
| `REQ-DBCP-13` | Unwanted behaviour | If a requested DBC name is not present in the selected provider catalog, the system shall return a structured error with code `DBC_NOT_FOUND` and exit code 3. |
| `REQ-DBCP-14` | Unwanted behaviour | If provider-backed resolution is requested while the required provider manifest is missing and auto-refresh is disabled or unavailable, the system shall return a structured error with code `DBC_CACHE_MISS` and exit code 3. |

## Command Surface

```text
canarchy dbc provider list [--json] [--jsonl] [--text] [--raw]
canarchy dbc search <query> [--provider <name>] [--limit <n>] [--json] [--jsonl] [--text] [--raw]
canarchy dbc fetch <ref> [--json] [--jsonl] [--text] [--raw]
canarchy dbc cache list [--json] [--jsonl] [--text] [--raw]
canarchy dbc cache prune [--provider <name>] [--json] [--jsonl] [--text] [--raw]
canarchy dbc cache refresh [--provider <name>] [--json] [--jsonl] [--text] [--raw]
canarchy decode --file <file> --dbc <path|provider-ref> [--json] [--jsonl] [--text] [--raw]
canarchy decode --stdin --dbc <path|provider-ref> [--json] [--jsonl] [--text] [--raw]
canarchy encode --dbc <path|provider-ref> <message> <signal=value>... [--json] [--jsonl] [--text] [--raw]
canarchy dbc inspect <path|provider-ref> [--message <name>] [--signals-only] [--json] [--jsonl] [--text] [--raw]
```

## Responsibilities And Boundaries

In scope:

* provider discovery and catalog search
* cached manifest refresh and stale snapshot pruning
* provider-ref resolution for DBC-backed commands
* provenance metadata for resolved DBC usage

Out of scope:

* editing provider-hosted DBC files
* synchronizing every upstream DBC file eagerly on refresh
* non-DBC schema catalogs beyond the current provider model

## Data Model

The provider-backed DBC workflow uses provider descriptors and resolutions layered above the runtime codec path.

### Provider descriptor fields

Search and refresh results may include:

* `provider`
* `name`
* `version`
* `source_ref`
* `metadata`

### Resolution fields

Fetch and DBC-backed command resolution include:

* `provider`
* `name`
* `version`
* `local_path`
* `is_cached`

### Provenance fields

`data.dbc_source` includes:

* `provider`
* `name`
* `version`
* `path`

For local file refs, `provider` is `local` and `version` is `null`. For provider-backed refs, `version` is the pinned provider version or commit-derived identifier.

## Output Contracts

### JSON

Provider and cache commands return the standard CANarchy result envelope with structured result objects under `data`.

### JSONL

Provider and cache commands emit a single result object line because they do not stream canonical transport events.

### Table

`dbc provider list` and `dbc search` use DBC-specific table helpers. Cache and fetch workflows return compact key/value summaries.

### Raw

Provider and cache workflows emit the command name on success or the first error message on failure.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `DBC_PROVIDER_NOT_FOUND` | requested provider is not registered | 3 |
| `DBC_NOT_FOUND` | requested DBC name is not present in the selected provider catalog | 3 |
| `DBC_CACHE_MISS` | provider-backed resolution is requested with no usable provider manifest or cache snapshot | 3 |

## Deferred Decisions

* whether additional provider implementations beyond `opendbc` should ship in the first stable series
* whether provider search ranking should grow beyond the current provider-native ordering
* whether cache refresh should support forced eager DBC-file download in addition to manifest refresh
