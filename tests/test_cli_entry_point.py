"""Regression coverage for the installed `canarchy` console entry point (#519).

These tests invoke the real console script as a subprocess instead of calling
`canarchy.cli.main([...])` in-process. That distinction is the whole point: the
console script calls `main()` with no argv, and the parse-error path used to
resolve the requested output format from `None` — so every argparse failure
printed text even when the caller asked for `--json`/`--jsonl`. In-process
tests pass an explicit argv list and never see it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_CAPTURE = FIXTURES / "sample.candump"


def _console_script() -> Path:
    """Locate the installed `canarchy` console script for this interpreter."""
    bin_dir = Path(sys.executable).parent
    for name in ("canarchy", "canarchy.exe"):
        candidate = bin_dir / name
        if candidate.exists():
            return candidate
    pytest.skip("`canarchy` console script is not installed for this interpreter")


def run_console(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the installed console script with the isolated test environment."""
    return subprocess.run(
        [str(_console_script()), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def assert_parse_error_envelope(payload: dict, *, message_contains: str) -> None:
    assert payload["ok"] is False
    assert payload["command"] == "cli"
    assert payload["data"] == {}
    assert payload["warnings"] == []
    error = payload["errors"][0]
    assert error["code"] == "INVALID_ARGUMENTS"
    assert message_contains in error["message"]
    assert error["hint"]


# --- TEST-CLIERR-01..04: parse failures honour --json -----------------------


@pytest.mark.parametrize(
    ("argv", "message_contains"),
    [
        pytest.param(
            ("stats", "--unknown-option", "--json"),
            "unrecognized arguments: --unknown-option",
            id="unknown-option",
        ),
        pytest.param(
            ("bogus-subcommand", "--json"),
            "invalid choice: 'bogus-subcommand'",
            id="unknown-subcommand",
        ),
        pytest.param(
            ("decode", "--json"),
            "the following arguments are required: --dbc",
            id="missing-required-argument",
        ),
        pytest.param(
            ("stats", "--file", str(SAMPLE_CAPTURE), "--top", "notanint", "--json"),
            "argument --top: invalid int value: 'notanint'",
            id="invalid-typed-value",
        ),
    ],
)
def test_parse_failure_emits_json_envelope(argv: tuple[str, ...], message_contains: str) -> None:
    result = run_console(*argv)

    assert result.returncode == 1, result.stdout
    payload = json.loads(result.stdout)
    assert_parse_error_envelope(payload, message_contains=message_contains)


# --- TEST-CLIERR-05: parse failures honour --jsonl --------------------------


def test_parse_failure_emits_jsonl_envelope() -> None:
    result = run_console("stats", "--unknown-option", "--jsonl")

    assert result.returncode == 1, result.stdout
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1
    assert_parse_error_envelope(
        json.loads(lines[0]), message_contains="unrecognized arguments: --unknown-option"
    )


# --- TEST-CLIERR-06: conflicting output flags -------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(("stats", "--unknown-option", "--json", "--jsonl"), id="json-first"),
        pytest.param(("stats", "--unknown-option", "--jsonl", "--json"), id="jsonl-first"),
        pytest.param(("stats", "--unknown-option", "--text", "--json"), id="text-first"),
    ],
)
def test_conflicting_output_flags_use_fixed_precedence(argv: tuple[str, ...]) -> None:
    """`--json` wins over `--jsonl` and `--text`, whatever the argv order."""
    result = run_console(*argv)

    assert result.returncode == 1, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "INVALID_ARGUMENTS"
    assert "not allowed with argument" in payload["errors"][0]["message"]


# --- TEST-CLIERR-07: text mode stays readable -------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(("stats", "--unknown-option"), id="default"),
        pytest.param(("stats", "--unknown-option", "--text"), id="explicit-text"),
    ],
)
def test_parse_failure_text_output_stays_readable(argv: tuple[str, ...]) -> None:
    result = run_console(*argv)

    assert result.returncode == 1
    assert result.stdout.startswith("command: cli")
    assert "error: INVALID_ARGUMENTS: unrecognized arguments: --unknown-option" in result.stdout
    assert "hint: " in result.stdout
    with pytest.raises(json.JSONDecodeError):
        json.loads(result.stdout)


# --- TEST-CLIERR-08: successful invocations are unchanged -------------------


def test_successful_command_still_emits_json_through_console_script() -> None:
    result = run_console("stats", "--file", str(SAMPLE_CAPTURE), "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["command"] == "stats"
    assert payload["data"]["total_frames"] > 0


# --- TEST-CLIERR-09: runtime errors keep their own exit code ----------------


def test_runtime_error_envelope_unchanged(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-capture.log"
    result = run_console("stats", "--file", str(missing), "--json")

    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["command"] == "stats"
