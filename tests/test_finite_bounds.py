"""Non-finite limits must fail before command dispatch, with strict JSON (#523)."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
from unittest.mock import patch

import pytest

from canarchy.cli import CommandError, build_parser, main, prepare_args
from canarchy.doip import DoipError, discover_entities, parse_doip_target


def strict_json(text):
    def reject(value):
        raise AssertionError(f"Non-standard JSON constant: {value}")

    return json.loads(text, parse_constant=reject)


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
@pytest.mark.parametrize("output", ["--json", "--jsonl"])
@pytest.mark.parametrize(
    "argv,option,code",
    [
        (["stats", "--file", "missing.candump"], "seconds", "INVALID_ANALYSIS_SECONDS"),
        (
            ["j1939", "tp", "sessions", "--file", "missing.candump"],
            "seconds",
            "INVALID_ANALYSIS_SECONDS",
        ),
        (["re", "corpus", "missing.candump"], "seconds", "INVALID_ANALYSIS_SECONDS"),
        (
            ["replay", "--interface", "can0", "--file", "missing.candump", "--dry-run"],
            "rate",
            "INVALID_RATE",
        ),
        (["generate", "can0", "--dry-run"], "gap", "INVALID_GAP"),
        (["generate", "can0"], "gap", "INVALID_GAP"),
        (
            ["simulate", "can0", "--profile", "heavy-truck", "--dry-run"],
            "duration",
            "INVALID_DURATION",
        ),
        (
            ["fuzz", "payload", "can0", "--id", "0x123", "--strategy", "bitflip", "--dry-run"],
            "rate",
            "INVALID_RATE",
        ),
        (["doip", "discovery"], "timeout", "INVALID_TIMEOUT"),
        (["uds", "dump-dids", "can0", "--dry-run"], "max-duration", "INVALID_MAX_DURATION"),
        (["web", "serve", "--file", "missing.candump"], "rate", "INVALID_RATE"),
    ],
)
def test_nonfinite_options_fail_before_dispatch(argv, option, code, output, value):
    stdout = io.StringIO()
    with (
        patch("canarchy.cli.execute_command") as execute,
        patch("canarchy.cli.LocalTransport") as transport,
        patch("canarchy.cli.emit_web_serve") as web,
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        assert main([*argv, f"--{option}={value}", output]) == 1
    execute.assert_not_called()
    transport.assert_not_called()
    web.assert_not_called()
    payload = strict_json(stdout.getvalue())
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == code


def float_actions(parser):
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for child in action.choices.values():
                yield from float_actions(child)
        elif action.type is float:
            yield action


def test_every_float_option_has_an_early_finiteness_guard():
    # Covers future numeric options as well as timing and analytical thresholds.
    for action in float_actions(build_parser()):
        for value in (float("nan"), float("inf"), float("-inf")):
            with pytest.raises(CommandError) as error:
                prepare_args(argparse.Namespace(command="audit", **{action.dest: value}))
            strict_json(json.dumps(error.value.data))
        for value in (0.0, 0.25):
            args = argparse.Namespace(command="audit", **{action.dest: value})
            prepare_args(args)
            assert getattr(args, action.dest) == value


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_doip_timeout_rejected_before_network(value):
    with pytest.raises(DoipError, match="finite"):
        parse_doip_target(f"doip://localhost?logical_address=0x123&timeout={value}")
    with patch("canarchy.doip._udp_identification_sender") as sender:
        with pytest.raises(DoipError, match="finite"):
            discover_entities(timeout=value)
        sender.assert_not_called()


@pytest.mark.parametrize("value", ["0", "0.1"])
def test_valid_file_seconds_preserve_zero_and_finite_semantics(value):
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
        assert (
            main(["stats", "--file", "tests/fixtures/sample.candump", "--seconds", value, "--json"])
            == 0
        )
    assert strict_json(stdout.getvalue())["ok"] is True
