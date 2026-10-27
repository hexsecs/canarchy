# Test Spec: Supported Python Runtimes

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/python-support.md` |
| Test file | `tests/test_cli.py`, `.github/workflows/test.yml` |

## Requirement Traceability

| ID | Requirement | Coverage |
| --- | --- | --- |
| TEST-PYTHON-01 | REQ-PYTHON-01, REQ-PYTHON-02 | Inspect package metadata and lockfile constraints. |
| TEST-PYTHON-02 | REQ-PYTHON-03 | Patch the doctor runtime version to Python 3.11 and expect `ok`. |
| TEST-PYTHON-03 | REQ-PYTHON-04 | Patch the doctor runtime version to Python 3.10 and expect `fail` with an upgrade hint. |
| TEST-PYTHON-04 | REQ-PYTHON-05, REQ-PYTHON-06 | Run the CI matrix and Python 3.11 packaging smoke job. |

## TEST-PYTHON-02 — Python 3.11 is accepted

```gherkin
Given the doctor runtime reports Python 3.11
When the Python-version check runs
Then the check status is "ok"
```

**Fixture:** `tests/test_cli.py`

## TEST-PYTHON-03 — Older Python is rejected

```gherkin
Given the doctor runtime reports Python 3.10
When the Python-version check runs
Then the check status is "fail"
And the check includes an upgrade hint
```

**Fixture:** `tests/test_cli.py`

## TEST-PYTHON-04 — The Python 3.11 wheel smoke test

```gherkin
Given a wheel and sdist built from the repository
When the wheel is installed in a clean Python 3.11 environment
Then the installed CLI reports its version
And offline doctor, scaffold capture, and fixture-backed DBC decode succeed
```

**Fixture:** `.github/workflows/test.yml`, `tests/fixtures/sample.candump`, `tests/fixtures/sample.dbc`
