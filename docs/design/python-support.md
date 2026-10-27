# Design Spec: Supported Python Runtimes

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | Packaging and `canarchy doctor` |
| Primary area | Packaging, diagnostics, CI |
| Related specs | `docs/tests/python-support.md` |

## Goal

CANarchy shall be installable and continuously validated on supported CPython
versions without weakening the package metadata or relying on development-only
installation workarounds.

## Requirements

| ID | Type | Requirement |
| --- | --- | --- |
| REQ-PYTHON-01 | Ubiquitous | The package shall declare Python 3.11 as its minimum supported runtime. |
| REQ-PYTHON-02 | Ubiquitous | The package shall advertise Python 3.11, 3.12, and 3.13 classifiers. |
| REQ-PYTHON-03 | Event-driven | When `canarchy doctor` runs on Python 3.11 or newer, it shall report the Python-version check as successful. |
| REQ-PYTHON-04 | Unwanted behaviour | If `canarchy doctor` runs on Python older than 3.11, it shall report a failed Python-version check with an upgrade hint. |
| REQ-PYTHON-05 | Ubiquitous | Continuous integration shall run the default test suite on Python 3.11, 3.12, and 3.13. |
| REQ-PYTHON-06 | Ubiquitous | The packaging workflow shall build both wheel and sdist artifacts and install the wheel on Python 3.11 without bypassing `Requires-Python`. |

## Validation

The packaging smoke job runs the installed wheel's version, offline doctor,
scaffold capture, and fixture-backed DBC decode commands.
