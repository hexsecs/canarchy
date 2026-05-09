# Design Spec: Skills Provider Workflows

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy skills provider list`, `skills search`, `skills fetch`, `skills cache list`, `skills cache refresh` |
| Primary area | CLI, agent integration, provider/cache |
| Related specs | `docs/design/skill-manifest-schema.md`, `docs/design/dbc-provider-workflows.md`, `docs/design/mcp-server.md` |

## Goal

Provide a first-phase provider-backed skills workflow that lets operators discover, cache, resolve, and inspect repository-backed CANarchy skills through a stable CLI surface before any MCP execution or runtime skill invocation behavior is added.

## User-Facing Motivation

Operators and future agents need a local, inspectable skill catalog with reproducible provenance. Before higher-level skill execution can be designed cleanly, CANarchy needs commands that answer basic workflow questions: which skills providers are registered, what skills are available, where a fetched skill came from, and what is already cached locally.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-SKILLPROV-01` | Ubiquitous | The system shall provide `skills provider list`, `skills search`, `skills fetch`, `skills cache list`, and `skills cache refresh` commands for provider-backed skill workflows. |
| `REQ-SKILLPROV-02` | Ubiquitous | The system shall define a skills provider abstraction that is separate from command execution and separate from MCP tool exposure. |
| `REQ-SKILLPROV-03` | Event-driven | When `skills provider list` is invoked, the system shall return the registered skills providers and their operator-facing names. |
| `REQ-SKILLPROV-04` | Event-driven | When `skills search <query>` is invoked, the system shall return ranked skill matches including provider, skill name, publisher, version, provider-facing skill ref, and manifest-derived metadata. |
| `REQ-SKILLPROV-05` | Event-driven | When `skills fetch <provider>:<skill>` is invoked, the system shall resolve that skill to local cached files and return provider, skill name, publisher, version, local manifest path, local entry path, and cache status. |
| `REQ-SKILLPROV-06` | Event-driven | When `skills cache list` is invoked, the system shall return cached provider-manifest entries including provider identity, pinned commit, generation timestamp, and cached skill count. |
| `REQ-SKILLPROV-07` | Event-driven | When `skills cache refresh` is invoked, the system shall refresh the selected provider catalog and return the refreshed provider name and skill count. |
| `REQ-SKILLPROV-08` | Optional feature | Where a provider cache is cold and provider auto-refresh is enabled, the provider resolution path shall refresh the catalog automatically before retrying skill resolution. |
| `REQ-SKILLPROV-09` | Unwanted behaviour | If a requested skills provider is not registered, the system shall return a structured error with code `SKILL_PROVIDER_NOT_FOUND` and exit code 3. |
| `REQ-SKILLPROV-10` | Unwanted behaviour | If a requested skill name is not present in the selected provider catalog, the system shall return a structured error with code `SKILL_NOT_FOUND` and exit code 3. |
| `REQ-SKILLPROV-11` | Unwanted behaviour | If a provider-backed skill resolution is requested while the provider cache is missing and auto-refresh is disabled or unavailable, the system shall return a structured error with code `SKILL_CACHE_MISS` and exit code 3. |
| `REQ-SKILLPROV-12` | Unwanted behaviour | If a repository-backed manifest is missing required schema fields, the system shall return a structured error with code `SKILL_MANIFEST_INVALID` and exit code 3 rather than accepting the malformed catalog entry. |
| `REQ-SKILLPROV-13` | Unwanted behaviour | If repository-backed skill files cannot be downloaded during fetch or refresh, the system shall return structured provider/cache errors instead of surfacing an uncaught exception. |
| `REQ-SKILLPROV-14` | Unwanted behaviour | If a manifest-controlled cache path escapes the provider cache subtree, the system shall reject that manifest or fetch request with `SKILL_MANIFEST_INVALID`. |

## Command Surface

```text
canarchy skills provider list [--json] [--jsonl] [--text] [--raw]
canarchy skills search <query> [--provider <name>] [--limit <n>] [--json] [--jsonl] [--text] [--raw]
canarchy skills fetch <ref> [--json] [--jsonl] [--text] [--raw]
canarchy skills cache list [--json] [--jsonl] [--text] [--raw]
canarchy skills cache refresh [--provider <name>] [--json] [--jsonl] [--text] [--raw]
```

## Responsibilities And Boundaries

In scope:

* provider discovery and catalog search
* catalog refresh and local cache inspection
* provider-ref resolution for fetched skills
* provenance metadata for cached skill content

Out of scope:

* skill execution semantics
* MCP tool, resource, or prompt exposure for skills
* interactive skill invocation UX
* repository authentication and trust policy beyond the current provider config

## Data Model

The skills provider workflow uses manifest-derived skill descriptors and local resolutions layered above the future execution path.

### Descriptor fields

Search and refresh results may include:

* `provider`
* `name`
* `publisher`
* `version`
* `source_ref`
* `metadata`

### Resolution fields

Fetch results include:

* `provider`
* `name`
* `publisher`
* `version`
* `local_manifest_path`
* `local_entry_path`
* `is_cached`

### Cache entry fields

`skills cache list` returns entries including:

* `provider`
* `repo`
* `commit`
* `generated_at`
* `skill_count`
* `cache_dir`

## Output Contracts

### JSON

Provider and cache commands return the standard CANarchy result envelope with structured result objects under `data`.

### JSONL

Provider and cache commands emit a single result object line because they do not stream canonical transport events.

### Table

`skills provider list`, `skills search`, `skills fetch`, `skills cache list`, and `skills cache refresh` use compact provider-specific summaries.

### Raw

Skills provider and cache workflows emit the command name on success or the first error message on failure.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `SKILL_PROVIDER_NOT_FOUND` | requested provider is not registered | 3 |
| `SKILL_NOT_FOUND` | requested skill name is not present in the selected provider catalog | 3 |
| `SKILL_CACHE_MISS` | provider-backed resolution is requested with no usable provider manifest or cache snapshot | 3 |
| `SKILL_MANIFEST_INVALID` | repository-backed manifest is missing required schema fields | 3 |
| `SKILL_FETCH_FAILED` | a skill manifest or entry file could not be downloaded during fetch | 3 |

## Deferred Decisions

* whether additional provider implementations beyond GitHub should ship in the first stable series
* whether cache management should later include prune or eager prefetch commands
* whether future provider metadata should expose trust or signature information
* whether a later phase should expose skills through MCP tools, resources, prompts, or a dedicated discovery capability
