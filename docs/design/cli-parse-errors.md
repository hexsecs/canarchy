# Design Spec: CLI Parse-Error Output

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | every `canarchy` command (argument parsing layer) |
| Primary area | CLI, output contract |
| Related specs | `docs/design/transport-core-commands.md`, `docs/design/composition.md` |

## Goal

Guarantee that argument-parsing failures obey the same machine-readable output contract as every other CANarchy failure: when the operator asks for `--json` or `--jsonl`, the parse-error envelope is JSON, whatever route the CLI was entered through.

## User-Facing Motivation

An agent driving CANarchy needs exactly one error parser. Before this spec, the installed `canarchy` console script printed a text error block for argparse failures even when `--json` was on the command line, because the console script calls `main()` with no argv and the requested output mode was detected from `None` rather than from `sys.argv[1:]`. A caller had to special-case usage errors — which are the failures an automated caller hits most often (#519).

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-CLIERR-01` | Ubiquitous | The system shall resolve the effective argument vector (`sys.argv[1:]` when the entry point supplies no explicit list) before detecting the requested output format, and shall parse that same vector. |
| `REQ-CLIERR-02` | Event-driven | When argument parsing fails and `--json` is present on the effective argument vector, the system shall emit the canonical JSON error envelope with `ok: false`, `command: "cli"`, and an error of code `INVALID_ARGUMENTS`. |
| `REQ-CLIERR-03` | Event-driven | When argument parsing fails and `--jsonl` is present on the effective argument vector, the system shall emit the canonical error envelope as a single JSONL record. |
| `REQ-CLIERR-04` | Ubiquitous | The system shall apply requirements `REQ-CLIERR-02` and `REQ-CLIERR-03` to every class of parse failure, including an unrecognised option, an unknown command or subcommand, a missing required argument, and a value that fails its argument type conversion. |
| `REQ-CLIERR-05` | Event-driven | When argument parsing fails, the system shall exit with code 1 regardless of the selected output format. |
| `REQ-CLIERR-06` | State-driven | While no output flag is present, or while `--text` or `--table` is the only output flag present, the system shall emit the human-readable `command:` / `error:` / `hint:` text block for parse failures. |
| `REQ-CLIERR-07` | Unwanted behaviour | If more than one output flag is present on the effective argument vector, the system shall select the error output format by the fixed precedence `--json` > `--jsonl` > `--text` > `--table`, independent of the order of the flags on the command line. |
| `REQ-CLIERR-08` | Ubiquitous | The system shall leave the output of successfully parsed commands unchanged by the argument-vector resolution described in `REQ-CLIERR-01`. |

## Command Surface

No new commands or flags. The contract applies to the existing global output flags on every command:

```text
canarchy <command> [<args> ...] [--json] [--jsonl] [--text]
```

## Responsibilities And Boundaries

In scope:

* resolution of the effective argument vector inside `canarchy.cli.main`
* the output format used for the `INVALID_ARGUMENTS` envelope produced by the parse-failure path
* precedence between conflicting output flags for that envelope

Out of scope:

* the wording of argparse's own failure messages — they are passed through verbatim as the envelope `message`
* `--help` and `--version`, which argparse handles by printing to stdout and exiting 0
* runtime (post-parse) failures, which already resolve their format from the parsed namespace
* the in-process `execute_command` helper used by the REPL and TUI, which always receives an explicit argument list

## Data Model

The parse-failure path emits the standard `CommandResult` error envelope with `command` set to the literal `"cli"` — the failure happened before a command could be identified.

## Output Contracts

`--json`

```json
{
  "ok": false,
  "command": "cli",
  "data": {},
  "warnings": [],
  "errors": [
    {
      "code": "INVALID_ARGUMENTS",
      "message": "unrecognized arguments: --unknown-option",
      "hint": "Run `canarchy --help` to inspect the available commands and flags."
    }
  ]
}
```

`--jsonl` — the same envelope as a single JSON record on one line.

`--text` (also the default)

```text
command: cli
error: INVALID_ARGUMENTS: unrecognized arguments: --unknown-option
hint: Run `canarchy --help` to inspect the available commands and flags.
```

Conflicting output flags are themselves a parse failure, because the output flags form a mutually exclusive argparse group. The envelope reporting that failure is rendered using the precedence in `REQ-CLIERR-07`, so `canarchy stats --file capture.log --jsonl --json` exits 1 with a JSON envelope whose message is `argument --json: not allowed with argument --jsonl`. The precedence matches the one already applied to successfully parsed invocations, so the two paths can never disagree.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `INVALID_ARGUMENTS` | any argparse failure: unrecognised option, unknown command or subcommand, missing required argument, invalid typed value, conflicting output flags | 1 |

## Deferred Decisions

* Output-flag detection for the parse-failure path is a literal scan of the argument vector, so a flag-like *value* (for example `--file --json`) is read as a format request. Argparse would reject such an invocation anyway; a token-aware scan is not warranted.
* Argparse's `--help` output stays plain text. A machine-readable command inventory belongs to the MCP tool listing and `canarchy completion`, not to `--help`.
