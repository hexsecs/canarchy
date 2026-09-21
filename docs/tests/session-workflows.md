# Test Spec: Session Workflows

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Related design spec | `docs/design/session-workflows.md` |
| Primary test area | CLI, session |

## Test Objectives

Validate session round-trip persistence, structured missing-session error handling, and the research-record behaviour layered on top of it: recorded input provenance, offline verification of unchanged, modified, and missing inputs and artifacts, relocation, portable bundles, legacy-record compatibility, deterministic offline reproduction, and the exclusion of credentials.

## Coverage Requirements

* save/load/show round trip with representative context
* missing-session error handling
* recorded hashes, sizes, versions, effective configuration, and invocation metadata
* verification of unchanged, modified, and missing inputs and artifacts
* relocation through `--root` and through bundle/import
* legacy (schema version 1) records: load, warn, refuse verification, upgrade on re-save
* deterministic offline reproduction of a recorded analysis
* credentials and unrelated environment variables never reaching the record
* no transport opened by load, show, or verify

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-SESSION-01` | `TEST-SESSION-01`, `TEST-SESSION-02` |
| `REQ-SESSION-02` | `TEST-SESSION-01`, `TEST-SESSION-03` |
| `REQ-SESSION-03` | `TEST-SESSION-01` |
| `REQ-SESSION-04` | `TEST-SESSION-01`, `TEST-SESSION-12` |
| `REQ-SESSION-05` | `TEST-SESSION-02` |
| `REQ-SESSION-06` | `TEST-SESSION-13` |
| `REQ-SESSION-07` | `TEST-SESSION-03` |
| `REQ-SESSION-08` | `TEST-SESSION-03` |
| `REQ-SESSION-09` | `TEST-SESSION-03` |
| `REQ-SESSION-10` | `TEST-SESSION-03` |
| `REQ-SESSION-11` | `TEST-SESSION-03`, `TEST-SESSION-11` |
| `REQ-SESSION-12` | `TEST-SESSION-06` |
| `REQ-SESSION-13` | `TEST-SESSION-06` |
| `REQ-SESSION-14` | `TEST-SESSION-06` |
| `REQ-SESSION-15` | `TEST-SESSION-04`, `TEST-SESSION-05` |
| `REQ-SESSION-16` | `TEST-SESSION-05` |
| `REQ-SESSION-16a` | `TEST-SESSION-05` |
| `REQ-SESSION-17` | `TEST-SESSION-07` |
| `REQ-SESSION-18` | `TEST-SESSION-04`, `TEST-SESSION-05`, `TEST-SESSION-10` |
| `REQ-SESSION-19` | `TEST-SESSION-09` |
| `REQ-SESSION-20` | `TEST-SESSION-09` |
| `REQ-SESSION-21` | `TEST-SESSION-09` |
| `REQ-SESSION-22` | `TEST-SESSION-08` |
| `REQ-SESSION-23` | `TEST-SESSION-08` |
| `REQ-SESSION-24` | `TEST-SESSION-11` |
| `REQ-SESSION-25` | `TEST-SESSION-11` |

## Representative Test Cases

### `TEST-SESSION-01` — Session round trip

```gherkin
Given  a temporary working directory with an isolated `.canarchy/` store
And    the files `tests/fixtures/sample.candump` and `tests/fixtures/sample.dbc` are available
When   the operator saves a named session with interface, DBC, and capture context
And    then loads the saved session
And    then runs `canarchy session show --json`
Then   the saved context shall be preserved
And    `session show` shall report both the active and saved session entries
```

**Fixture:** `tests/fixtures/sample.candump`, `tests/fixtures/sample.dbc`, temporary session directory.

---

### `TEST-SESSION-02` — Missing session error

```gherkin
Given  no session named `missing` exists in the session store
When   the operator runs `canarchy session load missing --json`
Then   the command shall exit with code `1`
And    `errors[0].code` shall equal `"SESSION_NOT_FOUND"`
```

**Fixture:** temporary session directory (empty).

---

### `TEST-SESSION-03` — Recorded input provenance

```gherkin
Given  an isolated project directory holding a capture and a DBC file
When   the operator saves a session naming both files
Then   the record shall carry `schema_version: 2`, the CANarchy version, and creation and save timestamps
And    each input shall carry its SHA-256 hash, size, modification time, absolute path, and store-relative path
And    the recorded invocation shall carry the command, its arguments, the effective configuration, and an environment snapshot
And    an input that cannot be read shall be recorded with status `unreadable` instead of failing the save
```

**Fixture:** `tests/fixtures/sample.candump`, `tests/fixtures/sample.dbc`, temporary project directory and HOME.

---

### `TEST-SESSION-04` — Verification of unchanged inputs

```gherkin
Given  a saved session whose inputs are untouched
When   the operator runs `canarchy session verify <name> --json`
Then   the command shall exit with code `0`
And    `verification.status` shall equal `"verified"`
And    every recorded invocation shall be reported as `reproducible`
And    `verification.required_actions` shall be empty
```

---

### `TEST-SESSION-05` — Modified and missing inputs

```gherkin
Given  a saved session
When   a recorded capture is edited and the session is verified
Then   the command shall exit with code `1` with `errors[0].code` `"SESSION_VERIFICATION_FAILED"`
And    that input shall be reported as `changed` with the recorded and observed hashes
And    the invocation that consumed it shall be reported as `blocked` by that input id
And    `verification.required_actions` shall name what must be restored
And    deleting the input instead shall report it as `missing`
When   a session records an input that could not be hashed and nothing else is wrong
Then   verification shall exit with code `0`, report status `incomplete`, and name that entry in the required actions
```

---

### `TEST-SESSION-06` — Artifacts and annotations

```gherkin
Given  a saved session with a recorded capture
When   the operator attaches an analysis output with `--command` and `--derived-from <input-id>`
Then   the artifact shall carry its content hash, the declared invocation as `produced_by`, and that input in `derived_from`
And    an artifact attached with `--embed` shall verify as `unchanged` after its file is deleted
And    an artifact attached without `--embed` shall verify as `missing` after its file is deleted
And    annotations shall accumulate in order with timestamps and optional targets
And    `--target` or `--derived-from` naming an unknown id shall fail with `"SESSION_INPUT_UNKNOWN"`
And    re-saving the session shall keep its annotations, artifacts, input identifiers, and creation timestamp
```

---

### `TEST-SESSION-07` — Relocation

```gherkin
Given  a saved session whose inputs and `.canarchy/` store are copied to another directory
And    the original input files are deleted
When   the operator runs `canarchy session verify <name> --root <new-directory> --json`
Then   the command shall exit with code `0`
And    every input shall resolve under the relocation root and verify as `unchanged`
```

---

### `TEST-SESSION-08` — Legacy records

```gherkin
Given  a session file written without a `schema_version`
When   the operator loads it
Then   the command shall succeed, report `schema_version: 1` and `provenance_available: false`
And    warn with `SESSION_PROVENANCE_UNAVAILABLE`
And    the stored file shall be left byte-identical
When   the operator verifies it
Then   the command shall exit with code `1` with `errors[0].code` `"SESSION_PROVENANCE_UNAVAILABLE"`
When   the operator re-saves it with its inputs
Then   the record shall become `schema_version: 2` and verify successfully
And    a record whose `schema_version` is newer than this build shall fail with `"SESSION_SCHEMA_UNSUPPORTED"`
```

---

### `TEST-SESSION-09` — Portable bundles

```gherkin
Given  a saved session with recorded inputs and an annotation
When   the operator bundles it to a `.zip` destination
Then   the archive shall contain `manifest.json` and a copy of each input
When   the bundle is imported into a fresh store in another directory, with the original paths removed
Then   the imported session shall resolve every input inside the new store and verify as `verified`
And    a bundle imported under an existing name shall fail with `"SESSION_EXISTS"`
And    a bundle written to an existing destination shall fail with `"SESSION_BUNDLE_EXISTS"`
And    a bundle entry that would extract outside the destination shall fail with `"SESSION_BUNDLE_INVALID"` and write nothing
```

---

### `TEST-SESSION-10` — Deterministic offline reproduction

```gherkin
Given  a saved session recording a capture and an attached `j1939 summary` artifact with its producing command
And    the artifact file has since been deleted
When   the operator verifies the session and re-runs the recorded `reproduce_command`
Then   verification shall report the inputs as `unchanged` and the invocation as `reproducible`
And    the replayed output shall be byte-identical to the original output
And    its SHA-256 shall equal the recorded artifact hash
```

---

### `TEST-SESSION-11` — Secrets and side effects

```gherkin
Given  a configuration file containing `api_token` and `password` values
And    `CANARCHY_SERVER_KEY` and `AWS_SECRET_ACCESS_KEY` set in the environment
When   the operator saves a session
Then   none of those values shall appear anywhere in the record
And    `effective_config.redacted_keys` shall name the omitted configuration keys
And    `effective_config.environment_variables` shall contain only allowlisted `CANARCHY_*` variables
And    `session load`, `session show`, and `session verify` shall succeed with transport access patched to raise
```

---

### `TEST-SESSION-12` — Inspection surface

```gherkin
Given  a session with provenance and a legacy session in the same store
When   the operator runs `canarchy session show --json`
Then   each entry shall report its manifest version, provenance availability, and input, artifact, and annotation counts
And    `canarchy session verify <name> --text` shall render the verification report as readable text
```

---

### `TEST-SESSION-13` — Session name validation

```gherkin
Given  any session subcommand that takes a session name
When   the name contains a path separator or is `.` / `..`
Then   the command shall exit with code `1` and `errors[0].code` `"INVALID_SESSION_NAME"`
```

---

## Fixtures And Environment

* temporary working directories for isolated `.canarchy/` session storage
* a temporary `HOME` so the developer's own `~/.canarchy/config.toml` cannot reach a recorded manifest
* `tests/fixtures/sample.candump`
* `tests/fixtures/sample.dbc`

## Explicit Non-Coverage

* concurrent session access
* session deletion lifecycle
* reproduction of live ECU behaviour, which is environment-dependent rather than deterministic

## Traceability

`TEST-SESSION-01` and `TEST-SESSION-02` are implemented in `test_cli.py`; `TEST-SESSION-03` through `TEST-SESSION-13` are implemented in `test_session.py`.
