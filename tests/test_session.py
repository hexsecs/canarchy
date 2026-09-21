"""Tests for session research records: provenance, verification, portability.

Covers `docs/tests/session-workflows.md` `TEST-SESSION-03` … `TEST-SESSION-13`.
The round-trip and missing-session cases (`TEST-SESSION-01`, `TEST-SESSION-02`)
live in `test_cli.py` next to the rest of the CLI surface tests.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from canarchy import __version__
from canarchy.cli import EXIT_OK, EXIT_USER_ERROR, main

FIXTURES = Path(__file__).parent / "fixtures"


def run_cli(*argv: str) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


def run_json(*argv: str) -> tuple[int, dict]:
    exit_code, stdout, stderr = run_cli(*argv)
    assert stderr == ""
    return exit_code, json.loads(stdout)


@contextlib.contextmanager
def working_directory(path: Path) -> Iterator[None]:
    original = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """An isolated project directory with its own `.canarchy/` store and HOME.

    HOME is redirected so a developer's real `~/.canarchy/config.toml` cannot
    leak into a recorded manifest — or change the assertions.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    project = tmp_path / "project"
    project.mkdir()
    shutil.copy(FIXTURES / "sample.candump", project / "sample.candump")
    shutil.copy(FIXTURES / "sample.dbc", project / "sample.dbc")
    with working_directory(project):
        yield project


def save_session(name: str = "lab-a", *extra: str) -> dict:
    exit_code, payload = run_json(
        "session",
        "save",
        name,
        "--interface",
        "can0",
        "--dbc",
        "sample.dbc",
        "--capture",
        "sample.candump",
        *extra,
        "--json",
    )
    assert exit_code == EXIT_OK
    return payload["data"]["session"]


def input_by_role(session: dict, role: str) -> dict:
    return next(entry for entry in session["inputs"] if entry["role"] == role)


# --- TEST-SESSION-03: provenance is recorded -------------------------------


def test_save_records_input_hashes_versions_and_invocation(workspace: Path) -> None:
    session = save_session()

    assert session["schema_version"] == 2
    assert session["provenance_available"] is True
    assert session["canarchy_version"] == __version__
    assert session["created_at"] and session["saved_at"]
    # The legacy context stays where older readers expect it.
    assert session["context"] == {
        "interface": "can0",
        "dbc": "sample.dbc",
        "capture": "sample.candump",
    }

    capture = input_by_role(session, "capture")
    expected = hashlib.sha256((workspace / "sample.candump").read_bytes()).hexdigest()
    assert capture["sha256"] == expected
    assert capture["size_bytes"] == (workspace / "sample.candump").stat().st_size
    assert capture["absolute_path"] == str(workspace / "sample.candump")
    assert capture["relative_path"] == "sample.candump"
    assert capture["status"] == "recorded"
    assert capture["modified_at"]

    (invocation,) = session["invocations"]
    assert invocation["command"] == "session save"
    assert invocation["canarchy_version"] == __version__
    assert invocation["arguments"]["capture"] == "sample.candump"
    assert invocation["environment"]["python_version"]
    assert "python_can" in invocation["environment"]["backends"]
    assert set(invocation["inputs"]) == {entry["input_id"] for entry in session["inputs"]}


def test_unreadable_input_is_recorded_rather_than_failing_the_save(workspace: Path) -> None:
    exit_code, payload = run_json(
        "session", "save", "lab-a", "--capture", "does-not-exist.candump", "--json"
    )
    assert exit_code == EXIT_OK
    (capture,) = payload["data"]["session"]["inputs"]
    assert capture["status"] == "unreadable"
    assert capture["sha256"] is None
    assert capture["detail"]


# --- TEST-SESSION-04/05: verification of unchanged and modified inputs ------


def test_verify_reports_unchanged_inputs(workspace: Path) -> None:
    save_session()
    exit_code, payload = run_json("session", "verify", "lab-a", "--json")

    assert exit_code == EXIT_OK
    verification = payload["data"]["verification"]
    assert verification["status"] == "verified"
    assert verification["summary"]["inputs_unchanged"] == 2
    assert verification["required_actions"] == []
    assert all(entry["status"] == "reproducible" for entry in verification["invocations"])


def test_verify_flags_a_modified_input_and_blocks_its_invocation(workspace: Path) -> None:
    session = save_session()
    capture_id = input_by_role(session, "capture")["input_id"]
    (workspace / "sample.candump").write_text("(0.0) can0 123#DEADBEEF\n")

    exit_code, payload = run_json("session", "verify", "lab-a", "--json")

    assert exit_code == EXIT_USER_ERROR
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "SESSION_VERIFICATION_FAILED"
    verification = payload["data"]["verification"]
    assert verification["status"] == "degraded"
    capture = next(e for e in verification["inputs"] if e["input_id"] == capture_id)
    assert capture["status"] == "changed"
    assert capture["actual_sha256"] != capture["expected_sha256"]
    assert any(capture_id in action for action in verification["required_actions"])
    (invocation,) = verification["invocations"]
    assert invocation["status"] == "blocked"
    assert invocation["blocked_by"] == [capture_id]


def test_verify_reports_a_missing_input(workspace: Path) -> None:
    save_session()
    (workspace / "sample.candump").unlink()

    exit_code, payload = run_json("session", "verify", "lab-a", "--json")

    assert exit_code == EXIT_USER_ERROR
    verification = payload["data"]["verification"]
    assert verification["summary"]["inputs_missing"] == 1
    capture = next(e for e in verification["inputs"] if e["role"] == "capture")
    assert capture["status"] == "missing"
    assert capture["expected_sha256"]
    assert any("Missing capture input" in action for action in verification["required_actions"])


def test_verify_reports_incomplete_when_an_input_was_never_hashed(workspace: Path) -> None:
    """An input recorded as unreadable cannot support a claim either way."""
    exit_code, _ = run_json(
        "session", "save", "lab-a", "--capture", "does-not-exist.candump", "--json"
    )
    assert exit_code == EXIT_OK

    exit_code, payload = run_json("session", "verify", "lab-a", "--json")

    assert exit_code == EXIT_OK
    verification = payload["data"]["verification"]
    assert verification["status"] == "incomplete"
    assert verification["summary"]["inputs_unverifiable"] == 1
    assert any("Unverifiable" in action for action in verification["required_actions"])


# --- TEST-SESSION-06: artifacts and annotations ----------------------------


def test_attach_links_an_artifact_to_the_inputs_that_produced_it(workspace: Path) -> None:
    session = save_session()
    capture_id = input_by_role(session, "capture")["input_id"]
    exit_code, stdout, _ = run_cli("j1939", "summary", "--file", "sample.candump", "--json")
    assert exit_code == EXIT_OK
    (workspace / "summary.json").write_text(stdout)

    exit_code, payload = run_json(
        "session",
        "attach",
        "lab-a",
        "--artifact",
        "summary.json",
        "--command",
        "canarchy j1939 summary --file sample.candump --json",
        "--derived-from",
        capture_id,
        "--json",
    )

    assert exit_code == EXIT_OK
    artifact = payload["data"]["artifact"]
    assert artifact["kind"] == "analysis_output"
    assert artifact["derived_from"] == [capture_id]
    assert artifact["sha256"] == hashlib.sha256(stdout.encode()).hexdigest()
    invocation = payload["data"]["session"]["invocations"][-1]
    assert artifact["produced_by"] == invocation["invocation_id"]
    assert invocation["source"] == "operator_declared"
    assert invocation["reproduce_command"] == "canarchy j1939 summary --file sample.candump --json"


def test_missing_artifact_is_reported_by_verification(workspace: Path) -> None:
    save_session()
    (workspace / "summary.json").write_text('{"ok": true}')
    exit_code, _ = run_json("session", "attach", "lab-a", "--artifact", "summary.json", "--json")
    assert exit_code == EXIT_OK
    (workspace / "summary.json").unlink()

    exit_code, payload = run_json("session", "verify", "lab-a", "--json")

    assert exit_code == EXIT_USER_ERROR
    verification = payload["data"]["verification"]
    assert verification["summary"]["artifacts_missing"] == 1
    assert verification["artifacts"][0]["status"] == "missing"
    assert any("Missing artifact" in action for action in verification["required_actions"])


def test_embedded_artifact_survives_deletion_of_the_original_file(workspace: Path) -> None:
    save_session()
    (workspace / "summary.json").write_text('{"ok": true}')
    exit_code, payload = run_json(
        "session", "attach", "lab-a", "--artifact", "summary.json", "--embed", "--json"
    )
    assert exit_code == EXIT_OK
    assert payload["data"]["artifact"]["embedded"]["content"] == '{"ok": true}'
    (workspace / "summary.json").unlink()

    exit_code, payload = run_json("session", "verify", "lab-a", "--json")

    assert exit_code == EXIT_OK
    artifact = payload["data"]["verification"]["artifacts"][0]
    assert artifact["status"] == "unchanged"
    assert artifact["source"] == "embedded"


def test_annotations_accumulate_and_may_target_recorded_entries(workspace: Path) -> None:
    session = save_session("lab-a", "--note", "baseline capture")
    capture_id = input_by_role(session, "capture")["input_id"]
    assert session["annotations"][0]["text"] == "baseline capture"

    exit_code, payload = run_json(
        "session",
        "annotate",
        "lab-a",
        "--note",
        "retarder PGN looks wrong",
        "--target",
        capture_id,
        "--json",
    )

    assert exit_code == EXIT_OK
    annotations = payload["data"]["session"]["annotations"]
    assert [entry["text"] for entry in annotations] == [
        "baseline capture",
        "retarder PGN looks wrong",
    ]
    assert annotations[1]["targets"] == [capture_id]
    assert annotations[1]["created_at"]


def test_unknown_target_id_is_a_structured_error(workspace: Path) -> None:
    save_session()
    exit_code, payload = run_json(
        "session", "annotate", "lab-a", "--note", "x", "--target", "in-deadbeef", "--json"
    )
    assert exit_code == EXIT_USER_ERROR
    assert payload["errors"][0]["code"] == "SESSION_INPUT_UNKNOWN"


def test_resaving_preserves_evidence_and_keeps_input_identifiers_stable(
    workspace: Path,
) -> None:
    first = save_session("lab-a", "--note", "first pass")
    capture_id = input_by_role(first, "capture")["input_id"]
    (workspace / "summary.json").write_text('{"ok": true}')
    run_json("session", "attach", "lab-a", "--artifact", "summary.json", "--json")

    second = save_session()

    assert input_by_role(second, "capture")["input_id"] == capture_id
    assert second["created_at"] == first["created_at"]
    assert second["saved_at"] != first["saved_at"]
    assert [entry["text"] for entry in second["annotations"]] == ["first pass"]
    assert len(second["artifacts"]) == 1
    assert second["artifacts"][0]["derived_from"] == []
    assert [entry["invocation_id"] for entry in second["invocations"]] == ["inv-0001", "inv-0002"]


# --- TEST-SESSION-07: relocation -------------------------------------------


def test_relocated_session_verifies_against_a_relocation_root(
    tmp_path: Path, workspace: Path
) -> None:
    save_session()
    relocated = tmp_path / "relocated"
    relocated.mkdir()
    shutil.copytree(workspace / ".canarchy", relocated / ".canarchy")
    for name in ("sample.candump", "sample.dbc"):
        shutil.copy(workspace / name, relocated / name)
        (workspace / name).unlink()

    with working_directory(relocated):
        # The recorded absolute paths are gone; `--root` re-anchors the
        # store-relative paths onto the new checkout.
        exit_code, payload = run_json(
            "session", "verify", "lab-a", "--root", str(relocated), "--json"
        )

    assert exit_code == EXIT_OK
    verification = payload["data"]["verification"]
    assert verification["status"] == "verified"
    assert verification["root"] == str(relocated)
    assert all(
        entry["resolved_path"].startswith(str(relocated)) for entry in verification["inputs"]
    )


# --- TEST-SESSION-08: legacy records ---------------------------------------


LEGACY_PAYLOAD = {
    "name": "legacy",
    "context": {"interface": "can0", "capture": "sample.candump"},
    "saved_at": "2025-01-01T00:00:00+00:00",
}


def write_legacy_session(workspace: Path) -> Path:
    sessions_dir = workspace / ".canarchy" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    path = sessions_dir / "legacy.json"
    path.write_text(json.dumps(LEGACY_PAYLOAD, sort_keys=True) + "\n")
    return path


def test_legacy_session_loads_and_reports_missing_provenance(workspace: Path) -> None:
    path = write_legacy_session(workspace)

    exit_code, payload = run_json("session", "load", "legacy", "--json")

    assert exit_code == EXIT_OK
    session = payload["data"]["session"]
    assert session["schema_version"] == 1
    assert session["provenance_available"] is False
    assert session["context"] == LEGACY_PAYLOAD["context"]
    assert session["inputs"] == []
    assert any("SESSION_PROVENANCE_UNAVAILABLE" in warning for warning in payload["warnings"])
    # Loading must not silently rewrite a record the operator saved earlier.
    assert json.loads(path.read_text()) == LEGACY_PAYLOAD


def test_legacy_session_verification_explains_the_upgrade(workspace: Path) -> None:
    write_legacy_session(workspace)

    exit_code, payload = run_json("session", "verify", "legacy", "--json")

    assert exit_code == EXIT_USER_ERROR
    assert payload["errors"][0]["code"] == "SESSION_PROVENANCE_UNAVAILABLE"
    assert "session save legacy" in payload["errors"][0]["hint"]


def test_resaving_a_legacy_session_upgrades_it(workspace: Path) -> None:
    write_legacy_session(workspace)

    exit_code, payload = run_json(
        "session", "save", "legacy", "--capture", "sample.candump", "--json"
    )

    assert exit_code == EXIT_OK
    assert payload["warnings"] == []
    session = payload["data"]["session"]
    assert session["schema_version"] == 2
    assert session["provenance_available"] is True
    assert session["inputs"][0]["sha256"]
    assert run_json("session", "verify", "legacy", "--json")[0] == EXIT_OK


def test_future_schema_version_is_refused_rather_than_partially_read(workspace: Path) -> None:
    sessions_dir = workspace / ".canarchy" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    (sessions_dir / "future.json").write_text(
        json.dumps({**LEGACY_PAYLOAD, "name": "future", "schema_version": 99})
    )

    exit_code, payload = run_json("session", "load", "future", "--json")

    assert exit_code == EXIT_USER_ERROR
    assert payload["errors"][0]["code"] == "SESSION_SCHEMA_UNSUPPORTED"


# --- TEST-SESSION-09: portable bundles -------------------------------------


def test_bundle_and_import_move_a_session_without_its_original_paths(
    tmp_path: Path, workspace: Path
) -> None:
    save_session("lab-a", "--note", "baseline")
    bundle_path = tmp_path / "lab-a-bundle.zip"

    exit_code, payload = run_json(
        "session", "bundle", "lab-a", "--output", str(bundle_path), "--json"
    )
    assert exit_code == EXIT_OK
    bundle = payload["data"]["bundle"]
    assert bundle["bundle_format"] == "zip"
    assert bundle["file_count"] == 2
    with zipfile.ZipFile(bundle_path) as archive:
        names = set(archive.namelist())
    assert "manifest.json" in names
    assert any(name.startswith("inputs/") for name in names)

    # Another machine: a fresh store, and none of the recorded paths resolve.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    for name in ("sample.candump", "sample.dbc"):
        (workspace / name).unlink()
    shutil.rmtree(workspace / ".canarchy")
    with working_directory(elsewhere):
        exit_code, payload = run_json("session", "import", str(bundle_path), "--json")
        assert exit_code == EXIT_OK
        session = payload["data"]["session"]
        assert session["name"] == "lab-a"
        assert [entry["text"] for entry in session["annotations"]] == ["baseline"]
        for entry in session["inputs"]:
            assert Path(entry["absolute_path"]).is_file()
            assert entry["absolute_path"].startswith(str(elsewhere))

        exit_code, payload = run_json("session", "verify", "lab-a", "--json")

    assert exit_code == EXIT_OK
    assert payload["data"]["verification"]["status"] == "verified"


def test_bundle_directory_round_trips_under_a_new_name(tmp_path: Path, workspace: Path) -> None:
    save_session()
    bundle_path = tmp_path / "lab-a-bundle"
    assert run_json("session", "bundle", "lab-a", "--output", str(bundle_path), "--json")[0] == (
        EXIT_OK
    )
    assert (bundle_path / "manifest.json").is_file()

    exit_code, payload = run_json(
        "session", "import", str(bundle_path), "--name", "lab-a-copy", "--json"
    )

    assert exit_code == EXIT_OK
    assert payload["data"]["session"]["name"] == "lab-a-copy"
    assert run_json("session", "verify", "lab-a-copy", "--json")[0] == EXIT_OK


def test_importing_over_an_existing_session_is_refused(tmp_path: Path, workspace: Path) -> None:
    save_session()
    bundle_path = tmp_path / "bundle"
    run_json("session", "bundle", "lab-a", "--output", str(bundle_path), "--json")

    exit_code, payload = run_json("session", "import", str(bundle_path), "--json")

    assert exit_code == EXIT_USER_ERROR
    assert payload["errors"][0]["code"] == "SESSION_EXISTS"


def test_bundle_refuses_an_existing_destination(tmp_path: Path, workspace: Path) -> None:
    save_session()
    destination = tmp_path / "taken"
    destination.mkdir()

    exit_code, payload = run_json(
        "session", "bundle", "lab-a", "--output", str(destination), "--json"
    )

    assert exit_code == EXIT_USER_ERROR
    assert payload["errors"][0]["code"] == "SESSION_BUNDLE_EXISTS"


def test_bundle_with_a_traversing_entry_is_rejected(tmp_path: Path, workspace: Path) -> None:
    hostile = tmp_path / "hostile.zip"
    with zipfile.ZipFile(hostile, "w") as archive:
        archive.writestr("manifest.json", json.dumps({**LEGACY_PAYLOAD, "schema_version": 2}))
        archive.writestr("../escaped.txt", "nope")

    exit_code, payload = run_json("session", "import", str(hostile), "--json")

    assert exit_code == EXIT_USER_ERROR
    assert payload["errors"][0]["code"] == "SESSION_BUNDLE_INVALID"
    assert not (tmp_path / "escaped.txt").exists()


# --- TEST-SESSION-10: deterministic offline reproduction -------------------


def test_recorded_analysis_reproduces_byte_for_byte_from_the_record(workspace: Path) -> None:
    """The record alone is enough to re-run the analysis and match the result."""
    session = save_session()
    capture_id = input_by_role(session, "capture")["input_id"]
    argv = ("j1939", "summary", "--file", "sample.candump", "--json")
    exit_code, original_stdout, _ = run_cli(*argv)
    assert exit_code == EXIT_OK
    (workspace / "summary.json").write_text(original_stdout)
    run_json(
        "session",
        "attach",
        "lab-a",
        "--artifact",
        "summary.json",
        "--command",
        "canarchy " + " ".join(argv),
        "--derived-from",
        capture_id,
        "--json",
    )
    (workspace / "summary.json").unlink()

    # What an analyst gets from the record: verified inputs plus the command.
    exit_code, payload = run_json("session", "verify", "lab-a", "--json")
    assert exit_code == EXIT_USER_ERROR  # the artifact file is gone, the inputs are not
    verification = payload["data"]["verification"]
    assert verification["summary"]["inputs_unchanged"] == 2
    recorded = next(
        entry
        for entry in verification["invocations"]
        if entry["source"] != "session_command"
        if entry.get("reproduce_command")
    )
    assert recorded["status"] == "reproducible"

    replay_argv = tuple(recorded["reproduce_command"].split()[1:])
    exit_code, replayed_stdout, _ = run_cli(*replay_argv)

    assert exit_code == EXIT_OK
    assert replayed_stdout == original_stdout
    artifact = next(entry for entry in payload["data"]["session"]["artifacts"])
    assert hashlib.sha256(replayed_stdout.encode()).hexdigest() == artifact["sha256"]


# --- TEST-SESSION-11: secrets and side effects -----------------------------


def test_record_omits_credentials_and_unrelated_environment(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = Path(os.environ["HOME"]) / ".canarchy"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.toml").write_text(
        "[transport]\n"
        'default_interface = "can0"\n'
        'api_token = "super-secret-token"\n'
        "\n"
        "[dbc]\n"
        'default_provider = "local"\n'
        'password = "hunter2"\n'
    )
    monkeypatch.setenv("CANARCHY_SERVER_KEY", "server-key-value")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-secret-value")
    monkeypatch.setenv("CANARCHY_DEFAULT_INTERFACE", "can1")

    session = save_session()

    serialized = json.dumps(session)
    assert "super-secret-token" not in serialized
    assert "hunter2" not in serialized
    assert "server-key-value" not in serialized
    assert "aws-secret-value" not in serialized

    config = session["invocations"][0]["effective_config"]
    assert config["sections"]["transport"]["default_interface"] == "can0"
    assert config["sections"]["dbc"]["default_provider"] == "local"
    assert config["redacted_keys"] == ["dbc.password", "transport.api_token"]
    assert config["environment_variables"] == {"CANARCHY_DEFAULT_INTERFACE": "can1"}


def test_load_and_verify_do_not_open_a_transport(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Restoring a research record must never touch the bus."""
    import canarchy.transport as transport

    def explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("session commands must not open a transport")

    monkeypatch.setattr(transport, "open_bus", explode, raising=False)
    save_session()

    assert run_json("session", "load", "lab-a", "--json")[0] == EXIT_OK
    assert run_json("session", "verify", "lab-a", "--json")[0] == EXIT_OK
    assert run_json("session", "show", "--json")[0] == EXIT_OK


# --- TEST-SESSION-12/13: inspection surface --------------------------------


def test_show_summarizes_provenance_per_session(workspace: Path) -> None:
    save_session("lab-a", "--note", "baseline")
    write_legacy_session(workspace)

    exit_code, payload = run_json("session", "show", "--json")

    assert exit_code == EXIT_OK
    sessions = {entry["name"]: entry for entry in payload["data"]["sessions"]}
    assert sessions["lab-a"]["schema_version"] == 2
    assert sessions["lab-a"]["input_count"] == 2
    assert sessions["lab-a"]["annotation_count"] == 1
    assert sessions["legacy"]["provenance_available"] is False
    assert sessions["legacy"]["input_count"] == 0


def test_session_name_validation_covers_the_new_subcommands(workspace: Path) -> None:
    for argv in (
        ("session", "verify", "bad/name", "--json"),
        ("session", "annotate", "bad/name", "--note", "x", "--json"),
        ("session", "attach", "..", "--artifact", "sample.dbc", "--json"),
        ("session", "bundle", "bad/name", "--output", "out", "--json"),
    ):
        exit_code, payload = run_json(*argv)
        assert exit_code == EXIT_USER_ERROR, argv
        assert payload["errors"][0]["code"] == "INVALID_SESSION_NAME", argv


def test_text_output_renders_the_verification_report(workspace: Path) -> None:
    save_session()
    exit_code, stdout, _ = run_cli("session", "verify", "lab-a", "--text")

    assert exit_code == EXIT_OK
    assert "verification:" in stdout
    assert "status: verified" in stdout
