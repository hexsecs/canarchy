# Test Spec: Skills Agent MCP Integration

## Document Control

| Field | Value |
|-------|-------|
| Status | Planned |
| Design doc | `docs/design/skills-agent-mcp-integration.md` |
| Test file | documentation review; existing command coverage in `tests/test_skills_provider.py` and `tests/test_mcp_server.py` |

## Requirement Traceability

| REQ ID | Description summary | TEST IDs |
|--------|--------------------|----------|
| `REQ-SKILLAGENT-01` | Skills are phase-1 workflow descriptors, not executable MCP tools | `TEST-SKILLAGENT-01`, `TEST-SKILLAGENT-05` |
| `REQ-SKILLAGENT-02` | Discovery, fetch, and cache stay on the CLI surface | `TEST-SKILLAGENT-02` |
| `REQ-SKILLAGENT-03` | Skill identity uses `<provider>:<skill>` refs | `TEST-SKILLAGENT-02`, `TEST-SKILLAGENT-04` |
| `REQ-SKILLAGENT-04` | Provenance is manifest-derived and preserved | `TEST-SKILLAGENT-03`, `TEST-SKILLAGENT-04` |
| `REQ-SKILLAGENT-05` | Compatibility fields are visible to agents | `TEST-SKILLAGENT-03` |
| `REQ-SKILLAGENT-06` | Agent selection flow searches, fetches, inspects, then executes explicit commands | `TEST-SKILLAGENT-04` |
| `REQ-SKILLAGENT-07` | `compatibility.mcp=false` prevents assuming MCP invocation | `TEST-SKILLAGENT-05` |
| `REQ-SKILLAGENT-08` | MCP does not expose skills as tools, resources, or prompts in phase 1 | `TEST-SKILLAGENT-01` |
| `REQ-SKILLAGENT-09` | Agents may use MCP for command execution after CLI skill selection | `TEST-SKILLAGENT-06` |
| `REQ-SKILLAGENT-10` | Agents report missing context or tools instead of silently applying a skill | `TEST-SKILLAGENT-07` |

## Test Cases

### TEST-SKILLAGENT-01 - MCP surface excludes skills

```gherkin
Given  the MCP server design and agent guide are current
When   an agent reviews the phase-1 MCP tool surface
Then   the system shall document that skills are not exposed as MCP tools, resources, or prompts
And    the documentation shall preserve `skills search` and `skills fetch` as MCP exclusions
```

**Fixture:** `docs/design/mcp-server.md`, `docs/agents.md`.

---

### TEST-SKILLAGENT-02 - CLI remains the skills discovery surface

```gherkin
Given  a repository-backed skills provider is available
When   the operator runs `canarchy skills search j1939 --json`
Then   the system shall return candidate skills with provider and name fields
And    the agent workflow shall use those fields to form `<provider>:<skill>` references
```

**Fixture:** existing skills provider fixtures under `tests/fixtures/skills/`.

---

### TEST-SKILLAGENT-03 - Fetched skills expose provenance and compatibility

```gherkin
Given  a selected provider-qualified skill reference exists
When   the operator runs `canarchy skills fetch <provider>:<skill> --json`
Then   the system shall return local manifest and entry paths
And    the cached manifest shall expose provenance and compatibility metadata for agent inspection
```

**Fixture:** `tests/fixtures/skills/j1939_compare_triage.skill.yaml`.

---

### TEST-SKILLAGENT-04 - Agent workflow records selected skill provenance

```gherkin
Given  an agent has selected and fetched `github:j1939_compare_triage`
When   the agent completes a J1939 comparison workflow
Then   the agent shall record the provider-qualified skill reference in its final analysis
And    the agent shall include provider, revision, version, and local manifest provenance when available
```

**Fixture:** `docs/design/skills-agent-mcp-integration.md` example workflow.

---

### TEST-SKILLAGENT-05 - MCP-incompatible skills are not invoked through MCP

```gherkin
Given  a fetched skill manifest sets `compatibility.mcp` to `false`
When   an agent applies the skill to an analysis task
Then   the agent shall not assume the skill is callable through MCP
And    the agent shall use explicit CLI commands unless individual required commands are known MCP tools
```

**Fixture:** `tests/fixtures/skills/j1939_compare_triage.skill.yaml`.

---

### TEST-SKILLAGENT-06 - MCP may execute referenced commands after skill selection

```gherkin
Given  an agent has selected a skill through the CLI provider workflow
When   the skill references a command exposed by the MCP server
Then   the agent may call the equivalent MCP tool for that command
And    the MCP response shall preserve the canonical CANarchy result envelope
```

**Fixture:** `docs/design/mcp-server.md`, `docs/agents.md`.

---

### TEST-SKILLAGENT-07 - Missing context blocks skill application

```gherkin
Given  a fetched skill manifest requires capture files as context
When   the current task does not include a compatible capture artifact
Then   the agent shall report that the skill cannot be applied
And    the agent shall not silently continue as though the skill requirements were met
```

**Fixture:** `tests/fixtures/skills/j1939_compare_triage.skill.yaml`.

## Fixtures And Environment

The integration contract uses the existing skills provider fixtures and MCP documentation. Future automated tests can reuse `tests/test_skills_provider.py` for provider resolution assertions and `tests/test_mcp_server.py` for MCP exclusion assertions.

## Explicit Non-Coverage

Phase 1 does not test runtime skill execution, MCP resources, MCP prompts, automatic skill selection, trust policy, signed repositories, or a `skills run` command because those behaviors are explicitly deferred by the design.
