# Design Spec: Skills Agent MCP Integration

## Document Control

| Field | Value |
|-------|-------|
| Status | Planned |
| Command surface | `canarchy skills provider list`, `skills search`, `skills fetch`, `skills cache list`, `skills cache refresh`; `canarchy mcp serve` |
| Primary area | agent integration, MCP, skills provider |
| Related specs | `docs/design/skill-manifest-schema.md`, `docs/design/skills-provider-workflows.md`, `docs/design/mcp-server.md` |

## Goal

Define the first-phase integration model between CANarchy skills, agent workflows, and the MCP surface so agents can discover and reference repository-backed skills consistently without treating skills as executable MCP tools yet.

## User-Facing Motivation

Operators and agents need a repeatable way to select the right CANarchy skill for a capture or protocol task. The first integration phase should make skill identity, provenance, compatibility, required context, and expected outputs inspectable while preserving the CLI as the contract and avoiding premature runtime skill execution semantics.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-SKILLAGENT-01` | Ubiquitous | The system shall treat CANarchy skills as repository-backed workflow descriptors in phase 1 rather than executable MCP tools. |
| `REQ-SKILLAGENT-02` | Ubiquitous | The system shall keep skill discovery, fetch, and cache operations on the CLI surface in phase 1. |
| `REQ-SKILLAGENT-03` | Ubiquitous | The system shall communicate skill identity using the provider-qualified reference `<provider>:<skill>`. |
| `REQ-SKILLAGENT-04` | Ubiquitous | The system shall communicate skill provenance using manifest-derived provider, source reference, revision, version, manifest path, and local cache paths where available. |
| `REQ-SKILLAGENT-05` | Ubiquitous | The system shall communicate skill compatibility using manifest-derived CANarchy version constraints, MCP compatibility flags, required tools, accepted artifacts, and domain tags where available. |
| `REQ-SKILLAGENT-06` | Event-driven | When an agent needs to select a skill, the agent workflow shall search skills by protocol domain, fetch the selected provider-qualified skill, inspect the cached manifest and entry file, and then run the referenced CANarchy CLI or MCP tools explicitly. |
| `REQ-SKILLAGENT-07` | Event-driven | When a skill manifest sets `compatibility.mcp` to `false`, the agent workflow shall not assume that the skill or its referenced commands are callable as MCP tools. |
| `REQ-SKILLAGENT-08` | Ubiquitous | The MCP server shall remain a curated command execution surface in phase 1 and shall not expose skills as MCP tools, resources, or prompts. |
| `REQ-SKILLAGENT-09` | Optional feature | Where an agent can call MCP tools and the fetched skill references MCP-exposed commands, the agent may use those MCP tools after selecting the skill through the CLI provider workflow. |
| `REQ-SKILLAGENT-10` | Unwanted behaviour | If a skill requires context, tools, or artifact types that are missing from the current analysis task, the agent workflow shall report the incompatibility instead of silently applying the skill. |

## Command Surface

```text
canarchy skills provider list [--json] [--jsonl] [--text]
canarchy skills search <query> [--provider <name>] [--limit <n>] [--json] [--jsonl] [--text]
canarchy skills fetch <provider>:<skill> [--json] [--jsonl] [--text]
canarchy skills cache list [--json] [--jsonl] [--text]
canarchy skills cache refresh [--provider <name>] [--json] [--jsonl] [--text]
canarchy mcp serve
```

No new phase-1 command is introduced. Agents use existing `skills` CLI commands for discovery and existing CLI or MCP command execution surfaces for protocol work.

## Responsibilities And Boundaries

In scope:

* phase-1 agent workflow for discovering, fetching, and referencing skills
* MCP exposure decision for phase 1
* skill identity, provenance, compatibility, required context, and output contract fields an agent should inspect
* an end-to-end example of selecting a skill and running canonical CANarchy commands

Out of scope:

* exposing skills as MCP tools, resources, or prompts
* runtime skill execution inside CANarchy
* automatic skill selection by CANarchy
* trust policy, signature validation, or repository authentication beyond the provider/cache workflow
* converting skill manifests into plugin registrations

## Data Model

Agents should treat the fetched manifest and provider resolution payload as the integration contract.

### Identity

Skill identity is provider-qualified:

* `provider`
* `name`
* `source_ref`
* provider-qualified reference `<provider>:<skill>`

The provider-qualified reference is the stable handle an agent should record in notes, reports, and reproduced workflows.

### Provenance

Agents should preserve provenance fields in analysis notes and generated reports:

* `provider`
* `source_ref`
* `revision`
* `version`
* `manifest_path`
* `local_manifest_path`
* `local_entry_path`

### Compatibility

Agents should inspect manifest compatibility before applying a skill:

* `compatibility.canarchy`
* `compatibility.mcp`
* `compatibility.platforms`
* `required_tools`
* `inputs.requires_context`
* `inputs.accepted_artifacts`
* `outputs.expected_artifacts`
* `outputs.response_style`
* `skill.domains`
* `skill.tags`

`compatibility.mcp` describes whether the skill was authored with MCP-assisted use in mind. It does not make the skill itself an MCP tool.

## Agent Workflow

Phase-1 agents should follow this sequence:

1. Run `canarchy skills search <domain-or-task> --json` to find candidate skills.
2. Select a provider-qualified reference from the results, such as `github:j1939_compare_triage`.
3. Run `canarchy skills fetch <provider>:<skill> --json` to cache the manifest and entry file locally.
4. Read the cached manifest and entry file paths returned by the fetch result.
5. Check compatibility, required tools, required context, accepted artifacts, and expected outputs.
6. Execute the required CANarchy CLI commands or MCP tools explicitly.
7. Record the provider-qualified skill reference and provenance in the final analysis output.

Example:

```bash
canarchy skills search j1939 --provider github --json
canarchy skills fetch github:j1939_compare_triage --json
canarchy j1939 summary --file baseline.candump --json
canarchy j1939 compare --file baseline.candump --file after-start.candump --json
```

If MCP is available and the selected skill references an MCP-exposed command, the agent may use the MCP equivalent for that command. For example, an agent may call `j1939_summary` through MCP for `canarchy j1939 summary`, but it still discovers and fetches the skill through the CLI in phase 1.

## MCP Exposure Decision

MCP exposure is out of scope for skills in phase 1.

The MCP server remains a curated command execution surface. Skills are not exposed as:

* MCP tools
* MCP resources
* MCP prompts
* an MCP-specific discovery surface

This avoids presenting workflow descriptors as executable protocol commands before the project defines skill runtime semantics. Future MCP exposure can be added after skill execution, prompt/resource mapping, trust policy, and compatibility validation are designed.

## Output Contracts

Skills provider commands continue to return the standard CANarchy result envelope for JSON output. Agent workflows should consume the same fields documented by `docs/design/skills-provider-workflows.md` and the manifest schema documented by `docs/design/skill-manifest-schema.md`.

MCP command outputs continue to return one JSON text block containing the canonical command result envelope. Skills do not add a new MCP output shape in phase 1.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `SKILL_PROVIDER_NOT_FOUND` | requested provider is not registered | 3 |
| `SKILL_NOT_FOUND` | requested skill name is not present in the selected provider catalog | 3 |
| `SKILL_CACHE_MISS` | provider-backed resolution is requested with no usable provider manifest or cache snapshot | 3 |
| `SKILL_MANIFEST_INVALID` | repository-backed manifest is missing required schema fields or resolves outside the cache subtree | 3 |
| `SKILL_FETCH_FAILED` | a skill manifest or entry file could not be downloaded during fetch | 3 |

Agent-level compatibility failures are not a new CANarchy CLI error code in phase 1. Agents should report those failures in their own response when a fetched manifest does not match the available artifacts, tools, or MCP surface.

## Deferred Decisions

* whether skills should later appear as MCP resources, prompts, tools, or a separate discovery capability
* whether CANarchy should implement a `skills inspect` command for cached manifests
* whether CANarchy should implement a `skills run` command with explicit runtime semantics
* whether skill compatibility should be validated automatically by CANarchy or remain an agent responsibility
* how signed or trusted skill repositories should be represented
