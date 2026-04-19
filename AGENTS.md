# AGENTS.md

## Project

**CANarchy** is a CLI-first CAN security research toolkit with optional REPL and TUI front ends.

The implementation language is Python, and the project uses `uv` for dependency management, virtual environments, and packaging workflows.

The core design rule is simple:

> The CLI is the contract. The REPL and TUI are views over the same engine.

The project is focused on:

* CAN and CAN FD workflows
* J1939-first heavy vehicle workflows
* security research and protocol exploration
* automation-friendly use by coding agents
* automation-friendly development by coding agents
* structured outputs suitable for pipelines and machine parsing

---

## Project planning

GitHub Issues are the source of truth for project planning and task tracking.

### Every change must be associated with an issue

**This is a hard rule, not a suggestion.**

* Before starting any new feature, bug fix, or non-trivial refactor, check whether an open issue already covers it.
* If no issue exists, create one with a clear title, description, and acceptance criteria before writing code.
* Every commit that implements or fixes something must reference the relevant issue number using `closes #N`, `fixes #N`, or `refs #N` in the commit message.
* Do not merge or push code changes that have no associated issue.
* Bug fixes discovered incidentally (e.g. while working on a different issue) get their own issue opened first, then fixed.

The only exceptions are:
* typo/whitespace-only changes in docs or comments
* changes to `.gitignore` or other non-functional config

### Changelog policy

`CHANGELOG.md` follows the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format. Every non-trivial change must be recorded in the `[Unreleased]` section before or alongside the commit that introduces it.

**This is a hard rule, not a suggestion.**

* Every new feature, bug fix, behaviour change, or significant documentation update must have a corresponding `CHANGELOG.md` entry under `[Unreleased]`.
* Group entries under the standard headings: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`, or `Documentation`.
* Write entries from the operator's perspective — describe what changed and why it matters, not what files were edited.
* Changelog entries must be committed in the same commit or PR as the change they describe. Do not leave the changelog update for a separate follow-up.
* When a release is cut, the `[Unreleased]` section is promoted to a versioned heading. Do not manually create versioned headings outside of the release workflow.
* The only exceptions are: typo/whitespace-only changes in docs or comments, changes to `.gitignore` or other non-functional config, and MkDocs nav or theme-only changes.

### Other issue rules

* Use GitHub Issues to track planned work rather than ad hoc task lists in docs.
* When starting or completing work that relates to an issue, update the issue with progress or implementation notes.
* Commit and push the relevant code changes before closing an issue so the issue state matches the remote repository state.
* Close an issue when its scope and acceptance criteria have been satisfied.
* When creating a new issue, always include explicit acceptance criteria that define what must be true to close it.
* If code changes only partially satisfy an issue, leave the issue open and note the remaining work.
* If work for an issue is complete locally but has not yet been committed and pushed, explicitly offer to the user to commit and push the changes and then close or update the issue.
* After completing issue-scoped work, summarize what was implemented, recommend the most sensible next steps, and present those next steps as a concise multiple-choice menu the user can select from.

### Recommended completion handoff when issue-scoped work is done locally

1. State that the issue work is complete locally.
2. Summarize the shipped changes and verification results.
3. Offer to commit and push the changes if that has not happened yet.
4. If commit/push is already done, offer to close or update the issue if still needed.
5. Recommend the next 2–4 highest-value follow-up tasks.
6. Present the next steps as a multiple-choice menu, for example:

   A. commit, push, and close the issue
   B. start the next recommended issue
   C. refine docs or tests around the completed work
   D. inspect or review the implementation before moving on

---

## Primary goals

1. Build a stable, scriptable command surface for CAN security research.
2. Make common analyst workflows easy from the terminal.
3. Support agentic use through deterministic commands, structured output, and explicit error handling.
4. Keep protocol logic in the core engine, not in the UI.
5. Preserve parity across CLI, REPL, and TUI wherever practical.

---

## Non-goals for the first versions

Do not try to do all of these immediately:

* Full OEM-specific protocol coverage
* Deep GUI-first workflows
* Large-scale cloud architecture
* Automatic “AI magic” without clear, inspectable outputs
* Feature parity with every existing CAN tool before the core model is stable

---

## Product shape

CANarchy should be implemented as three layers:

### 1. Core engine

Responsible for:

* transport backends
* frame ingest and transmit
* decode/encode pipelines
* protocol state tracking
* replay and mutation
* analysis and reverse engineering helpers
* event generation

### 2. Command layer

Responsible for:

* canonical commands and subcommands
* validation of arguments
* output formatting modes
* exit codes
* scripting compatibility

### 3. Front ends

Responsible for presentation only:

* CLI
* REPL shell
* TUI

Front ends must not contain business logic that cannot also be reached through the CLI.

---

## Front-end rules

### CLI

The CLI is the authoritative interface.

Every important workflow must be reachable as a non-interactive command.

Examples:

* `canarchy capture can0 --jsonl`
* `canarchy decode capture.log --dbc truck.dbc --json`
* `canarchy j1939 monitor --pgn 65262 --json`
* `canarchy uds scan can0 --json`
* `canarchy replay drive.log --rate 0.5`

### REPL

The REPL is a convenience layer for human operators.

The REPL should:

* reuse the same command parser where possible
* preserve context like active bus, loaded decode database, and session artifacts
* expose the same operations as the CLI with minimal drift

### TUI

The TUI is a state and visualization surface over the same engine.

The TUI should:

* consume the same event stream model used by CLI/REPL
* trigger the same underlying commands/actions
* avoid introducing unique features that cannot be expressed as commands

---

## Initial capability priorities

### P0

* CAN / CAN FD capture
* transmit/send
* replay
* filtering
* stats
* structured export (`json`, `jsonl`)
* DBC-backed decode and encode
* J1939 monitor / decode / PGN-first workflows
* clear exit codes and error schema

### P1

* UDS scan and trace support
* session save/load
* SQLite export
* remote backends
* mutation/fuzzing primitives
* reverse engineering helpers

### P2

* TUI dashboard
* plugin SDK
* additional output sinks such as MQTT/Kafka/webhooks
* advanced anomaly detection and signal inference

---

## Security research focus

CANarchy is intended for defensive research, protocol analysis, lab experimentation, red-team style validation, and tool-assisted reverse engineering.

When implementing features, prefer:

* reproducibility
* evidence capture
* traceability
* safe defaults
* explicit operator intent for active transmission and fuzzing

Suggested safeguards:

* make active transmit/fuzz commands obviously distinct from passive commands
* support dry-run modes where possible
* log enough metadata for lab replay and reporting

---

## Architectural principles

### 1. Structured events over raw text

Internally, the system should model events such as:

* frame
* decoded message
* signal value
* J1939 PGN/SPN observation
* UDS request/response transaction
* anomaly
* replay action
* fuzz action
* alert

Prefer typed event objects over free-form strings.

### 2. Human output must never break machine output

Every command should support explicit output modes:

* `--json`
* `--jsonl`
* `--table`
* `--raw`

Do not mix human decoration into JSON output.

### 3. Deterministic behavior matters

Commands should behave predictably.

Avoid:

* hidden prompts in non-interactive mode
* unstable field names
* ambiguous time formats
* random output ordering unless explicitly requested

### 4. Stable command grammar

Prefer a command layout like:

* `<domain> <action>`
* or `<action> <object>` only when very obvious

Examples:

* `j1939 monitor`
* `j1939 decode`
* `uds scan`
* `re signals`
* `session save`

### 5. Protocol semantics are first-class

Do not force users to stay at the raw-frame layer when protocol-aware workflows exist.

Examples:

* allow PGN/SPN-first commands for J1939
* allow request/response transaction views for UDS
* allow decode-aware filtering

---

## Coding guidelines

### General

* Favor readability and explicitness over cleverness.
* Keep modules small and focused.
* Add tests for protocol parsing, decode logic, and CLI behavior.
* Prefer pure functions for transforms and protocol analysis.
* Keep transport adapters separate from semantic layers.

### Error handling

All errors should be actionable.

At minimum, errors should communicate:

* category
* message
* likely cause
* retry or corrective hint when appropriate

Prefer structured errors internally and in JSON output.

### Logging

* Use structured logging internally.
* Keep logs useful for replay and debugging.
* Avoid noisy logs in default CLI usage.

### Configuration

* Prefer explicit CLI flags first.
* Add config files only where they reduce repetition without hiding behavior.
* Make the effective configuration inspectable.

---

## Output and exit code conventions

Suggested exit codes:

* `0` success
* `1` user/input/usage error
* `2` backend or transport error
* `3` decode/schema/plugin error
* `4` partial result / partial success

Suggested JSON result shape:

```json
{
  "ok": true,
  "command": "j1939 monitor",
  "data": {},
  "warnings": [],
  "errors": []
}
```

Suggested JSON error shape:

```json
{
  "ok": false,
  "command": "decode",
  "errors": [
    {
      "code": "DBC_LOAD_FAILED",
      "message": "Failed to parse DBC file.",
      "hint": "Validate file format and line endings."
    }
  ]
}
```

---

## Proposed initial command tree

```text
canarchy
  capture
  send
  replay
  filter
  stats
  decode
  encode
  export
  session
    save
    load
    show
  j1939
    monitor
    decode
    pgn
    spn
    tp
    dm1
  uds
    scan
    trace
    services
  re
    signals
    counters
    entropy
    correlate
  fuzz
    replay
    mutate
    id
  shell
  tui
```

This tree is a starting point, not a lock.

---

## J1939 expectations

J1939 should be treated as a first-class workflow, not an afterthought.

Priorities:

* PGN-first filtering
* SPN presentation where decode data is available
* source address tracking
* TP/BAM reassembly support
* DM message visibility
* ECU/node activity summaries

The user should not be forced to manually reason from raw 29-bit IDs for common J1939 tasks.

---

## Reverse engineering expectations

Reverse engineering features should be evidence-driven and explainable.

Good early features:

* field entropy ranking
* likely counter detection
* likely checksum detection
* correlation against known external series
* changing-bit analysis
* signal boundary suggestions

Do not present guesses as facts.
Always expose confidence and rationale where possible.

---

## TUI expectations

The TUI should be useful for live analysis, demos, and triage.

Good initial panes:

* bus/interface status
* live traffic table
* decoded signals
* J1939 PGN/SPN activity
* node list
* alerts/events
* command entry area

The TUI should subscribe to the same event model used elsewhere.

---

## Testing expectations

At minimum, cover:

* frame parsing and formatting
* J1939 ID decomposition
* DBC-backed decode behavior
* replay timing behavior
* CLI argument validation
* JSON output stability
* error schema behavior

Where possible, use fixtures for:

* representative CAN logs
* representative J1939 traces
* malformed inputs
* edge cases like extended IDs, CAN FD, transport protocol fragmentation

---

## Documentation expectations

Documentation should be written for three audiences:

### 1. Operators

Show practical commands and workflows.

### 2. Developers

Explain architecture, module responsibilities, and extension points.

### 3. Agents

Keep command help, output schemas, and command behavior explicit and stable.

Prefer example-heavy docs.

---

## Design and architecture documents

CANarchy maintains living specification documents alongside the code. These documents are the authoritative record of how the system is designed to work.

### Document types

**Architecture documents** (`docs/architecture/`)

Describe the overall structure and module responsibilities. Each document should cover:

* the problem the component solves
* its boundaries and responsibilities
* how it interacts with adjacent components
* key design decisions and the reasons for them
* what is intentionally out of scope

**Software design specs** (`docs/design/`)

Describe the intended behavior of a specific feature or subsystem before or during implementation. Each spec should include:

* document control metadata including current status and affected command surface
* the goal and user-facing motivation
* explicit requirement IDs in a stable format such as `REQ-<AREA>-NN`
* the proposed command surface or API shape
* data models and event types involved
* output format definitions (JSON schema or representative examples)
* error cases and expected error codes
* open questions or deferred decisions

**Test specs** (`docs/tests/`)

Describe the test strategy and coverage expectations for a component or feature. Each test spec should include:

* document control metadata including the related design spec
* explicit test case IDs in a stable format such as `TEST-<AREA>-NN`
* what behaviors must be covered
* requirement-to-test traceability mapping back to the design spec requirement IDs
* representative test cases including happy path, edge cases, and failure modes
* fixture requirements
* what is explicitly not tested and why

### Spec language standard

All design specs and test specs must use the formats defined in [`docs/spec-template.md`](spec-template.md).

**Design specs** shall write requirements using EARS (Easy Approach to Requirements Syntax):

| EARS type | Template |
|-----------|----------|
| Ubiquitous | The system shall … |
| Event-driven | When \<trigger\>, the system shall … |
| State-driven | While \<state\>, the system shall … |
| Optional feature | Where \<feature\> is specified, the system shall … |
| Unwanted behaviour | If \<condition\>, the system shall … |

Each requirement row in the table shall include a `Type` column identifying which EARS pattern applies.

**Test specs** shall write test cases using Gherkin Given/When/Then syntax inside a fenced `gherkin` block, followed by a `**Fixture:**` line naming the required files or environment.

### Rules for agents

* When implementing a new feature or command, check `docs/design/` for an existing spec before writing code. If a spec exists, implement against it. If it conflicts with the code, flag the conflict rather than silently diverging.
* When no spec exists for a significant new feature, create one in `docs/design/` before or alongside the implementation. Follow `docs/spec-template.md` for the required sections, requirement IDs (`REQ-<AREA>-NN`), and EARS language.
* When adding new protocol logic, transport backends, or output formats, update or create the relevant architecture document in `docs/architecture/`.
* After implementing a feature, verify the test spec in `docs/tests/` matches what was actually tested, includes test IDs (`TEST-<AREA>-NN`), uses Gherkin Given/When/Then, and traces back to the design-spec requirement IDs. Update it if coverage changed.
* Specs are living documents. Update them when the implementation changes rather than letting them drift.
* Do not create specs for trivial changes (single-function fixes, minor output tweaks). Reserve them for features that affect the command surface, data model, or module boundaries.

---

## Preferred development style for agents

When proposing code changes or new modules, agents should:

* preserve CLI stability
* avoid leaking UI logic into core modules
* prefer structured outputs over formatted prose
* add tests with new behavior
* document new commands and output fields
* keep protocol-specific logic in well-named modules
* avoid unnecessary dependencies in the core runtime

When uncertain, agents should optimize for:

1. CLI reliability
2. output stability
3. protocol correctness
4. architecture clarity
5. UI polish

---

## Initial implementation suggestion

A reasonable first milestone is:

* core frame/event model
* SocketCAN capture/send/replay
* JSON/JSONL output modes
* DBC decode pipeline
* basic J1939 decomposition and monitor command
* simple session model
* shell scaffolding

Only after the command and event model feel stable should the project invest heavily in TUI and plugin work.

---

## Working summary

CANarchy should become:

> A CLI-first CAN security research environment with structured outputs, protocol-aware workflows, and shared core logic across CLI, REPL, and TUI.

When making design choices, preserve the following order of importance:

* command clarity
* structured outputs
* protocol correctness
* session reproducibility
* front-end parity
* visual polish

```
```
