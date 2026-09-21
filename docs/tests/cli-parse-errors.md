# Test Spec: CLI Parse-Error Output

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/cli-parse-errors.md` |
| Test file | `tests/test_cli_entry_point.py` |
| Primary test area | CLI, output contract |

## Test Objectives

Prove that argument-parsing failures honour the requested output format **through the installed `canarchy` console script**, which is the only route that exercises the `argv=None` entry path. Every test in this spec runs the console script as a real subprocess; calling `canarchy.cli.main([...])` in-process passes an explicit argument list and cannot observe the defect this spec guards (#519).

## Coverage Requirements

* each parse-failure class — unrecognised option, unknown subcommand, missing required argument, invalid typed value — emits a canonical JSON envelope when `--json` is requested
* `--jsonl` emits the same envelope as a single JSONL record
* conflicting output flags resolve by fixed precedence, in either order
* text output stays human-readable and is not valid JSON
* successful commands and runtime (post-parse) errors are unchanged
* every parse failure exits 1

## Requirement Traceability

| Requirement ID | Description summary | Covered by test IDs |
|----------------|---------------------|---------------------|
| `REQ-CLIERR-01` | resolve argv before detecting output format | `TEST-CLIERR-01`, `TEST-CLIERR-02`, `TEST-CLIERR-03`, `TEST-CLIERR-04`, `TEST-CLIERR-05` |
| `REQ-CLIERR-02` | `--json` parse-failure envelope | `TEST-CLIERR-01`, `TEST-CLIERR-02`, `TEST-CLIERR-03`, `TEST-CLIERR-04` |
| `REQ-CLIERR-03` | `--jsonl` parse-failure envelope | `TEST-CLIERR-05` |
| `REQ-CLIERR-04` | all parse-failure classes covered | `TEST-CLIERR-01`, `TEST-CLIERR-02`, `TEST-CLIERR-03`, `TEST-CLIERR-04` |
| `REQ-CLIERR-05` | exit code 1 for parse failures | `TEST-CLIERR-01`, `TEST-CLIERR-02`, `TEST-CLIERR-03`, `TEST-CLIERR-04`, `TEST-CLIERR-05`, `TEST-CLIERR-06`, `TEST-CLIERR-07` |
| `REQ-CLIERR-06` | text mode stays readable | `TEST-CLIERR-07` |
| `REQ-CLIERR-07` | fixed precedence for conflicting output flags | `TEST-CLIERR-06` |
| `REQ-CLIERR-08` | successful output unchanged | `TEST-CLIERR-08`, `TEST-CLIERR-09` |

## Test Cases

### `TEST-CLIERR-01` — Unrecognised option honours `--json`

```gherkin
Given  the `canarchy` console script is installed for the test interpreter
When   the operator runs `canarchy stats --unknown-option --json` as a subprocess
Then   the system shall exit with code 1
And    stdout shall parse as a single JSON object with `ok` false and `command` `"cli"`
And    the first error shall have code `INVALID_ARGUMENTS` and a non-empty hint
And    the error message shall contain `unrecognized arguments: --unknown-option`
```

**Fixture:** none.

---

### `TEST-CLIERR-02` — Unknown subcommand honours `--json`

```gherkin
Given  the `canarchy` console script is installed for the test interpreter
When   the operator runs `canarchy bogus-subcommand --json` as a subprocess
Then   the system shall exit with code 1
And    stdout shall parse as a JSON error envelope with code `INVALID_ARGUMENTS`
And    the error message shall contain `invalid choice: 'bogus-subcommand'`
```

**Fixture:** none.

---

### `TEST-CLIERR-03` — Missing required argument honours `--json`

```gherkin
Given  the `canarchy` console script is installed for the test interpreter
When   the operator runs `canarchy decode --json` as a subprocess
Then   the system shall exit with code 1
And    stdout shall parse as a JSON error envelope with code `INVALID_ARGUMENTS`
And    the error message shall contain `the following arguments are required: --dbc`
```

**Fixture:** none.

---

### `TEST-CLIERR-04` — Invalid typed value honours `--json`

```gherkin
Given  the `canarchy` console script is installed and `tests/fixtures/sample.candump` is present
When   the operator runs `canarchy stats --file sample.candump --top notanint --json` as a subprocess
Then   the system shall exit with code 1
And    stdout shall parse as a JSON error envelope with code `INVALID_ARGUMENTS`
And    the error message shall contain `argument --top: invalid int value: 'notanint'`
```

**Fixture:** `tests/fixtures/sample.candump`.

---

### `TEST-CLIERR-05` — Parse failure honours `--jsonl`

```gherkin
Given  the `canarchy` console script is installed for the test interpreter
When   the operator runs `canarchy stats --unknown-option --jsonl` as a subprocess
Then   the system shall exit with code 1
And    stdout shall contain exactly one non-empty line
And    that line shall parse as the canonical `INVALID_ARGUMENTS` error envelope
```

**Fixture:** none.

---

### `TEST-CLIERR-06` — Conflicting output flags use fixed precedence

```gherkin
Given  the `canarchy` console script is installed for the test interpreter
When   the operator runs `canarchy stats --unknown-option` with `--json --jsonl`, `--jsonl --json`, or `--text --json`
Then   the system shall exit with code 1
And    stdout shall parse as a JSON error envelope with code `INVALID_ARGUMENTS`
And    the error message shall report that the second output flag is not allowed with the first
```

**Fixture:** none.

---

### `TEST-CLIERR-07` — Text mode stays readable

```gherkin
Given  the `canarchy` console script is installed for the test interpreter
When   the operator runs `canarchy stats --unknown-option` with no output flag or with `--text`
Then   the system shall exit with code 1
And    stdout shall begin with `command: cli`
And    stdout shall contain the `error: INVALID_ARGUMENTS: ...` and `hint: ` lines
And    stdout shall not parse as JSON
```

**Fixture:** none.

---

### `TEST-CLIERR-08` — Successful command output is unchanged

```gherkin
Given  the `canarchy` console script is installed and `tests/fixtures/sample.candump` is present
When   the operator runs `canarchy stats --file sample.candump --json` as a subprocess
Then   the system shall exit with code 0
And    stdout shall parse as a JSON result envelope with `ok` true and `command` `"stats"`
And    `data.total_frames` shall be greater than zero
```

**Fixture:** `tests/fixtures/sample.candump`.

---

### `TEST-CLIERR-09` — Runtime error envelope is unchanged

```gherkin
Given  the `canarchy` console script is installed and the capture path does not exist
When   the operator runs `canarchy stats --file <missing> --json` as a subprocess
Then   the system shall exit with a nonzero code
And    stdout shall parse as a JSON error envelope with `command` `"stats"`
```

**Fixture:** a temporary directory providing a path that does not exist.

## Fixtures And Environment

* `tests/fixtures/sample.candump` — small candump capture used by the typed-value and success cases.
* The console script is located next to `sys.executable`; if it is absent (a source checkout run without installing the project) the tests skip rather than fall back to an in-process call, because an in-process call would not exercise the behaviour under test.
* The suite-wide isolation fixtures in `tests/conftest.py` redirect `HOME` and strip `CANARCHY_*` from the environment, and the subprocesses inherit that environment, so no operator configuration reaches these runs.

## Not Tested

* argparse's `--help` and `--version` output, which argparse prints and exits 0 for before any CANarchy code runs.
* The wording of argparse's failure messages — they are passed through verbatim and are a Python implementation detail.
* The in-process `execute_command` path used by the REPL and TUI: it always receives an explicit argument list, and its parse-failure envelope is covered in `tests/test_cli.py`.
