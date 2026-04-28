# Design Spec: Skill Manifest Schema

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy skills provider list`, `skills search`, `skills fetch`, `skills cache list`, `skills cache refresh` consume this manifest contract |
| Primary area | agent integration, MCP, documentation |
| Related specs | `docs/design/mcp-server.md`, `docs/design/dbc-provider-workflows.md`, `docs/design/plugin-model.md` |

## Goal

Define a stable, versioned manifest schema for CANarchy skills so repository-backed skill providers, cache workflows, and future MCP or agent integration all build against one inspectable contract instead of repository-specific conventions.

## User-Facing Motivation

Operators and agents need skills to be discoverable and reproducible. A provider should be able to answer basic questions without fetching arbitrary content: what the skill is called, which provider published it, what revision it came from, what files form the skill body, what domains it applies to, and what context or tools it expects.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-SKILLMAN-01` | Ubiquitous | The system shall define a versioned manifest schema for CANarchy skills. |
| `REQ-SKILLMAN-02` | Ubiquitous | The manifest schema shall distinguish identity fields, provenance fields, and content-entry fields. |
| `REQ-SKILLMAN-03` | Ubiquitous | Each manifest shall identify one skill with a stable provider-facing reference composed from provider identity and skill name. |
| `REQ-SKILLMAN-04` | Ubiquitous | Each manifest shall describe at minimum the skill name, summary, content entry file, domain tags, compatibility metadata, and provenance metadata needed for repository-backed provider workflows. |
| `REQ-SKILLMAN-05` | Optional feature | Where optional metadata is included, the manifest schema shall allow examples, dependencies, supported capture types, required tools, and deprecation metadata without changing the meaning of the required core fields. |
| `REQ-SKILLMAN-06` | Unwanted behaviour | If a manifest omits required identity, provenance, compatibility, or content-entry fields, the provider validation path shall reject it as invalid rather than guessing missing metadata. |
| `REQ-SKILLMAN-07` | Ubiquitous | The schema shall be suitable for repository-backed providers, catalog search, fetch/cache provenance reporting, and future MCP or agent discovery workflows without exposing provider-specific runtime objects. |
| `REQ-SKILLMAN-08` | State-driven | While provider validation is available, the project shall provide canonical example manifests that provider and schema-validation tests can exercise. |

## Command Surface

```text
No direct manifest-only CLI command is introduced in this phase.
This schema is consumed by the `skills` provider/catalog/fetch/cache workflows.
```

## Responsibilities And Boundaries

In scope:

* a versioned manifest format for one skill per manifest
* required versus optional field definitions
* a clear split between identity, provenance, compatibility, and content-entry metadata
* example manifests suitable for provider and validation tests

Out of scope:

* runtime skill execution or MCP tool exposure
* repository authentication or trust policy
* plugin execution semantics outside the skill metadata contract

## Data Model

The canonical manifest format for phase 1 is YAML.

### Top-level fields

Required fields:

* `schema_version`
* `skill`
* `provider`
* `provenance`
* `compatibility`
* `entry`

Optional fields:

* `inputs`
* `outputs`
* `examples`
* `dependencies`
* `required_tools`
* `supported_capture_types`
* `deprecation`
* `metadata`

### Identity fields

The `skill` object defines what the skill is independent of where it was fetched from.

Required identity fields:

* `skill.name`
* `skill.summary`
* `skill.description`
* `skill.tags`

Optional identity fields:

* `skill.domains`
* `skill.capabilities`

### Provider fields

The `provider` object identifies the source namespace expected to publish the skill.

Required provider fields:

* `provider.name`
* `provider.kind`

Phase-1 allowed provider kinds:

* `repository`

### Provenance fields

The `provenance` object answers where this specific manifest revision came from.

Required provenance fields:

* `provenance.source_ref`
* `provenance.revision`
* `provenance.manifest_path`

Optional provenance fields:

* `provenance.version`
* `provenance.published_at`
* `provenance.sha256`

### Compatibility fields

The `compatibility` object describes whether a future CANarchy runtime or agent client should consider the skill usable.

Required compatibility fields:

* `compatibility.canarchy`

Optional compatibility fields:

* `compatibility.mcp`
* `compatibility.platforms`
* `compatibility.python`

### Content-entry fields

The `entry` object identifies the local content file that represents the skill body.

Required content-entry fields:

* `entry.path`
* `entry.format`

Phase-1 allowed entry formats:

* `markdown`

### Inputs and outputs

The schema supports summary-level workflow expectations without encoding a full executable interface.

Suggested input/output fields:

* `inputs.requires_context`
* `inputs.accepted_artifacts`
* `outputs.expected_artifacts`
* `outputs.response_style`

## Output Contracts

No manifest-only CLI output mode is introduced in this phase. Provider and cache commands surface manifest-derived metadata through the standard CANarchy result envelope.

## Error Contracts

Provider workflows reject invalid manifests through structured errors rather than silently tolerating missing required fields.

Validation codes:

| Code | Trigger | Exit code |
|------|---------|-----------|
| `SKILL_MANIFEST_INVALID` | required manifest fields are missing or malformed | 3 |
| `SKILL_SCHEMA_UNSUPPORTED` | manifest `schema_version` is unsupported | 3 |
| `SKILL_ENTRY_UNSUPPORTED` | manifest `entry.format` is unsupported | 3 |

## Example Manifest

```yaml
schema_version: "canarchy.skill.v1"
skill:
  name: "j1939_compare_triage"
  summary: "Compare multiple J1939 captures for PGN, source-address, and fault drift."
  description: "Guides an analyst through multi-capture J1939 triage using the canonical compare workflow."
  tags: ["j1939", "triage", "heavy-vehicle"]
  domains: ["j1939", "reverse-engineering"]
  capabilities: ["file-analysis", "comparison"]
provider:
  name: "canarchy-labs"
  kind: "repository"
provenance:
  source_ref: "github:hexsecs/canarchy-skills"
  revision: "4f2a9c1"
  manifest_path: "skills/j1939_compare_triage/skill.yaml"
  version: "0.1.0"
compatibility:
  canarchy: ">=0.5.0"
  mcp: false
entry:
  path: "skills/j1939_compare_triage/SKILL.md"
  format: "markdown"
inputs:
  requires_context: ["capture_files"]
  accepted_artifacts: ["candump"]
outputs:
  expected_artifacts: ["triage_summary"]
  response_style: "structured_markdown"
required_tools: ["j1939_compare", "j1939_summary"]
examples:
  - prompt: "Compare two captures from before and after engine start."
```

## Deferred Decisions

* whether multiple entry files should be supported in one manifest
* whether provider kinds beyond `repository` should be standardized in v1
* whether compatibility metadata should include model-family or agent-family targeting
* whether a future JSON Schema artifact should be generated mechanically from this document or maintained separately
