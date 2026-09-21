# Design Spec: Session Workflows

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy session save`, `load`, `show`, `verify`, `annotate`, `attach`, `bundle`, `import` |
| Primary area | CLI, session |

## Goal

Provide session persistence that doubles as a reproducible research record: operators can save, restore, and inspect working context, and the saved record establishes *which bytes and settings* produced a result.

## User-Facing Motivation

Operators reuse the same interface, DBC, and capture context across commands, and later need to answer "was this finding produced from this capture, with this DBC, on this version of CANarchy?" Paths alone cannot answer that — captures and DBC databases change, and tool versions, parameters, outputs, and analyst notes are lost.

A session therefore records content hashes for its inputs, the invocations that consumed them, the analysis artifacts they produced, and the operator's annotations, so the record can be verified offline and moved to another directory or machine.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-SESSION-01` | Ubiquitous | The system shall provide `session save`, `session load`, and `session show` commands for named session persistence. |
| `REQ-SESSION-02` | Event-driven | When `session save <name>` is invoked, the system shall persist a named session record with the supplied interface, DBC, and capture context. |
| `REQ-SESSION-03` | Event-driven | When `session load <name>` is invoked, the system shall restore the named session and update the active session state. |
| `REQ-SESSION-04` | Event-driven | When `session show` is invoked, the system shall return the current active session and the list of all saved sessions. |
| `REQ-SESSION-05` | Unwanted behaviour | If `session load` is invoked with a name that does not exist, the system shall return a structured error with code `SESSION_NOT_FOUND` and exit code 1. |
| `REQ-SESSION-06` | Unwanted behaviour | If a session name contains a path separator or is `.` or `..`, the system shall return a structured error with code `INVALID_SESSION_NAME` and exit code 1. |
| `REQ-SESSION-07` | Ubiquitous | The session record shall carry a manifest `schema_version`, the recording CANarchy version, creation and save timestamps, and the recorded invocations that produced it. |
| `REQ-SESSION-08` | Event-driven | When a capture or DBC input is recorded, the system shall store its SHA-256 content hash, size in bytes, modification timestamp, the path as supplied, an absolute path, and a store-relative path when the file lives under the session store's project directory. |
| `REQ-SESSION-09` | Event-driven | When a recorded DBC input resolves inside the DBC provider cache, the system shall retain the provider name, repository, commit, and ref from that provider's cache manifest. |
| `REQ-SESSION-10` | Event-driven | When an input cannot be read at record time, the system shall record it with status `unreadable` and a detail string rather than failing the save. |
| `REQ-SESSION-11` | Ubiquitous | Each recorded invocation shall carry the command, its sanitised arguments, the effective configuration that applied, an environment snapshot, and the CANarchy version. |
| `REQ-SESSION-12` | Event-driven | When `session attach <name> --artifact <path>` is invoked, the system shall record the artifact with a content hash, size, the invocation it was produced by when `--command` is supplied, and the input identifiers named by `--derived-from`. |
| `REQ-SESSION-13` | Event-driven | When `session attach` is invoked with `--embed`, the system shall store the artifact's content inside the manifest so the result survives deletion of the original file. |
| `REQ-SESSION-14` | Event-driven | When `session annotate <name> --note <text>` is invoked, the system shall append a timestamped annotation, optionally targeting recorded input or artifact identifiers. |
| `REQ-SESSION-15` | Event-driven | When `session verify <name>` is invoked, the system shall re-hash every recorded input and artifact offline and report each as `unchanged`, `changed`, `missing`, or `unverifiable`. |
| `REQ-SESSION-16` | Event-driven | When `session verify` finds any changed or missing input or artifact, the system shall report status `degraded` and return a structured error with code `SESSION_VERIFICATION_FAILED`, exit code 1, and a report listing the required actions to reproduce the analysis. |
| `REQ-SESSION-16a` | Event-driven | When `session verify` finds no changed or missing entry but some entry carries no recorded hash, the system shall report status `incomplete` with exit code 0 and name those entries in the required actions. |
| `REQ-SESSION-17` | Event-driven | When `session verify --root <dir>` is invoked, the system shall resolve store-relative input and artifact paths against `<dir>` before verifying them, so a relocated session can be verified without its original absolute paths. |
| `REQ-SESSION-18` | Ubiquitous | The `session verify` report shall list, per recorded invocation, the command to re-run and the identifiers of any inputs that block reproduction. |
| `REQ-SESSION-19` | Event-driven | When `session bundle <name> --output <path>` is invoked, the system shall write a portable bundle containing the manifest and copies of every available input and artifact, addressed by bundle-relative paths, as a directory or, when `<path>` ends in `.zip`, a zip archive. |
| `REQ-SESSION-20` | Event-driven | When `session import <path>` is invoked, the system shall install the bundled session into the local store, copy its files into the store, and rewrite the manifest paths to the imported copies. |
| `REQ-SESSION-21` | Unwanted behaviour | If a bundle entry would extract outside the destination directory, the system shall return a structured error with code `SESSION_BUNDLE_INVALID` and exit code 1. |
| `REQ-SESSION-22` | Event-driven | When a session saved by an earlier schema version is loaded, the system shall load it successfully, report `provenance_available: false`, and emit a `SESSION_PROVENANCE_UNAVAILABLE` warning naming the command that upgrades it. |
| `REQ-SESSION-23` | Unwanted behaviour | If `session verify` is invoked for a session without recorded provenance, the system shall return a structured error with code `SESSION_PROVENANCE_UNAVAILABLE` and exit code 1. |
| `REQ-SESSION-24` | Ubiquitous | The session record shall not serialize credentials or environment variables outside the documented allowlist; configuration keys whose names look secret shall be omitted and listed under `redacted_keys`. |
| `REQ-SESSION-25` | Ubiquitous | `session load`, `session show`, and `session verify` shall not execute recorded commands, open a transport, or transmit frames. |

## Command Surface

```text
canarchy session save <name> [--interface <name>] [--dbc <file>] [--capture <file>]
                             [--note <text>] [--artifact <file>]... [--json|--jsonl|--text]
canarchy session load <name> [--json|--jsonl|--text]
canarchy session show [--json|--jsonl|--text]
canarchy session verify <name> [--root <dir>] [--json|--jsonl|--text]
canarchy session annotate <name> --note <text> [--target <id>]... [--json|--jsonl|--text]
canarchy session attach <name> --artifact <file> [--kind <kind>] [--command <text>]
                               [--derived-from <input-id>]... [--embed] [--json|--jsonl|--text]
canarchy session bundle <name> --output <path> [--json|--jsonl|--text]
canarchy session import <path> [--name <name>] [--json|--jsonl|--text]
```

`session save` on an existing name refreshes the context, inputs, and effective configuration while preserving that session's creation timestamp, annotations, artifacts, and earlier invocations. Input identifiers are derived from the role and supplied path, so re-saving the same input keeps artifact relationships intact.

## Responsibilities And Boundaries

In scope:

* named session record persistence
* input provenance: content hashes, sizes, provider references
* recorded invocations, analysis artifacts, and operator annotations
* offline verification and portable relocation of a session record

Out of scope:

* multi-user session coordination and collaboration services
* cloud storage or remote session synchronisation
* executing recorded commands on the operator's behalf
* reproducing live ECU behaviour: only deterministic offline analysis is reproducible from a record, and live bus interaction is environment-dependent

## Data Model

The manifest is a single JSON object per session under `.canarchy/sessions/<name>.json`:

| Field | Meaning |
|-------|---------|
| `schema_version` | manifest version; `2` for records carrying provenance |
| `name`, `created_at`, `saved_at` | identity and lifecycle timestamps |
| `canarchy_version` | the CANarchy version that wrote the record |
| `provenance_available` | `false` for records restored from schema version 1 |
| `context` | the legacy interface/DBC/capture context, retained unchanged |
| `inputs[]` | `input_id`, `role`, `path`, `absolute_path`, `relative_path`, `sha256`, `size_bytes`, `modified_at`, `status`, `provider` |
| `invocations[]` | `invocation_id`, `command`, `arguments`, `effective_config`, `environment`, `canarchy_version`, `recorded_at`, `source` |
| `artifacts[]` | `artifact_id`, `kind`, path fields and hash as for inputs, `produced_by`, `derived_from[]`, `embedded` |
| `annotations[]` | `annotation_id`, `created_at`, `text`, `targets[]` |

`effective_config` holds the allowlisted `[transport]`, `[dbc]`, `[safety]`, `[fuzz]`, and `[j1939]` sections of `~/.canarchy/config.toml` plus the allowlisted `CANARCHY_*` variables that change analysis behaviour. Secret-looking keys and every variable outside the allowlist — `CANARCHY_SERVER_KEY` among them — are omitted, and the omitted key names are listed under `effective_config.redacted_keys`.

`embedded` artifacts carry `{media_type, encoding, content}` where `encoding` is `utf-8` for text or `base64` for binary content.

## Output Contracts

`--json` returns the standard CANarchy result envelope. Because current session commands do not emit event streams, `--jsonl` also returns a single result object line, except `session show`, which emits one saved session per line.

`session verify` returns a `verification` block with per-input and per-artifact status, a summary count block, one `reproduce_command` per recorded invocation, and a `required_actions` list. `verification.status` is `verified` when every entry matched its hash, `incomplete` when nothing is known to be wrong but an entry carries no hash, and `degraded` when an entry changed or went missing. A `verified` or `incomplete` run exits 0; a `degraded` one exits 1 with the same report attached to the error envelope.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `SESSION_NOT_FOUND` | requested session does not exist | 1 |
| `INVALID_SESSION_NAME` | session name contains path separators or is `.` / `..` | 1 |
| `SESSION_VERIFICATION_FAILED` | an input or artifact is missing or its content changed | 1 |
| `SESSION_PROVENANCE_UNAVAILABLE` | verification requested for a record without provenance | 1 |
| `SESSION_ARTIFACT_UNREADABLE` | `session attach` cannot read the artifact path | 1 |
| `SESSION_INPUT_UNKNOWN` | `--derived-from` or `--target` names an identifier the session does not hold | 1 |
| `SESSION_BUNDLE_INVALID` | bundle is unreadable, malformed, or contains a traversing path | 1 |
| `SESSION_BUNDLE_EXISTS` | bundle output path already exists | 1 |
| `SESSION_EXISTS` | `session import` target name already exists in the store | 1 |
| `SESSION_SCHEMA_UNSUPPORTED` | manifest schema version is newer than this build records | 1 |

## Migration And Version Compatibility

* Records written before this change carry no `schema_version` and are treated as version 1.
* Version 1 records load unchanged from disk. The loaded payload reports `schema_version: 1` and `provenance_available: false`, and `session load` emits a `SESSION_PROVENANCE_UNAVAILABLE` warning.
* Loading never rewrites a version 1 record: the upgrade to version 2 happens only when the operator re-runs `session save <name>` with the inputs to record, which is the command named in the warning and in the `session verify` error hint.
* A version 2 record consumed by an older CANarchy build still exposes `name`, `context`, and `saved_at` at the top level, so `session load`, `session show`, and `export session:<name>` keep working.
* Manifests with a `schema_version` newer than this build report `SESSION_SCHEMA_UNSUPPORTED` rather than being partially interpreted.

## Relocation And Portability

Every input and artifact stores the path as supplied, an absolute path, and — when the file lives under the session store's project directory — a store-relative path.

* Within the same checkout, verification resolves the absolute path first.
* After relocation, `session verify --root <dir>` resolves store-relative paths against `<dir>`.
* Across machines, `session bundle` copies the files next to the manifest under bundle-relative paths, and `session import` installs them into `<store>/sessions/<name>.files/`, rewriting the manifest to the imported copies. Neither step depends on the original absolute paths.

## Deferred Decisions

* session deletion and lifecycle management commands
* recording invocations automatically from arbitrary analysis commands rather than by explicit `session attach --command`
* content-addressed storage shared between sessions
