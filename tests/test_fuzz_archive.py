"""Durability regressions for #503; all responders and transport calls are local fakes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from canarchy.fuzz_archive import FindingArchive, _write_record
from canarchy.fuzz_feedback import ResponseObservation
from canarchy.fuzz_guided import load_corpus, run_guided_fuzz, save_corpus
from canarchy.models import CanFrame
from canarchy.transport import LocalTransport, TransportError
from test_fuzz_guided import run_cli


def response(code):
    return CanFrame(arbitration_id=0x7E8, data=bytes([3, 0x7F, 0x27, code]), timestamp=1.0)


def test_pruned_findings_survive_corpus_reload_and_new_campaign(tmp_path):
    archive = FindingArchive(tmp_path / "corpus" / "findings", {"seed": 7}, [b"\x00"])
    mutations = iter([b"\x35extra", b"\x36extra"])
    transmitted = []

    def responder(data):
        transmitted.append(data)
        return ResponseObservation(frames=(response(data[0]),), elapsed=0.002)

    result = run_guided_fuzz(
        [b"\x00"],
        responder,
        mutate=lambda *_: next(mutations),
        max_payload=1,
        max_iterations=3,
        max_corpus=1,
        signals=("nrc",),
        campaign_id=archive.campaign_id,
        on_finding=archive.save,
    )
    assert transmitted == [b"\x00", b"\x35", b"\x36"]
    assert [s.seed_id for s in result.seeds] == ["s1"]  # s2 is pruned immediately.
    save_corpus(tmp_path / "corpus", result.seeds)
    assert load_corpus(tmp_path / "corpus") == [b"\x35"]
    records = [json.loads(p.read_text()) for p in sorted(archive.path.glob("finding-*.json"))]
    assert [r["data"] for r in records] == ["35", "36"]
    assert records[1]["seed_id"] == "s2"
    assert records[1]["parent_data"] == "35"
    assert records[1]["observation"]["frames"][0]["data"] == "037f2736"
    assert records[1]["observation"]["elapsed"] == 0.002
    assert records[1]["new_markers"] == ["nrc:27:36"]
    assert records[1]["finding_id"] == f"{archive.campaign_id}:s2"
    # New process/run uses a new campaign namespace, even though seed IDs restart.
    another = FindingArchive(tmp_path / "corpus" / "findings", {}, load_corpus(tmp_path / "corpus"))
    assert another.path != archive.path
    assert len(list(archive.path.glob("finding-*.json"))) == 2
    assert (
        json.loads((another.path / "campaign.json").read_text())["initial_seeds"][0]["seed_id"]
        == "s0"
    )


@pytest.mark.parametrize("failure", [KeyboardInterrupt(), RuntimeError("transport failed")])
def test_completed_evidence_survives_interruption(tmp_path, failure):
    archive = FindingArchive(tmp_path, {}, [b"\x00"])
    calls = 0

    def responder(data):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise failure
        return ResponseObservation(frames=(response(calls),))

    with pytest.raises(type(failure)):
        run_guided_fuzz(
            [b"\x00"],
            responder,
            max_iterations=5,
            campaign_id=archive.campaign_id,
            on_finding=archive.save,
        )
    assert archive.count == 1
    record = json.loads(next(archive.path.glob("finding-*.json")).read_text())
    assert record["iteration"] == 2
    assert record["observation"]["frames"][0]["data"] == "037f2702"


def test_failed_publication_keeps_previous_records_and_stops_sends(tmp_path):
    archive = FindingArchive(tmp_path, {}, [b"\x00"])
    calls = 0
    real_replace = os.replace

    def fail_second_finding(src, dst):
        if Path(dst).name == "finding-00000003.json":
            raise OSError("disk full")
        real_replace(src, dst)

    def responder(data):
        nonlocal calls
        calls += 1
        return ResponseObservation(frames=(response(calls),))

    with patch("canarchy.fuzz_archive.os.replace", side_effect=fail_second_finding):
        with pytest.raises(OSError, match="disk full"):
            run_guided_fuzz(
                [b"\x00"],
                responder,
                max_iterations=10,
                campaign_id=archive.campaign_id,
                on_finding=archive.save,
            )
    assert calls == 3
    assert archive.count == 1
    assert len(list(archive.path.glob("finding-*.json"))) == 1
    assert not list(archive.path.glob(".pending-*"))
    json.loads(next(archive.path.glob("finding-*.json")).read_text())


def test_serialization_failure_leaves_no_partial_json(tmp_path):
    with pytest.raises(OSError):
        _write_record(tmp_path / "record.json", {"bad": float("nan")})
    assert not list(tmp_path.iterdir())


def active_cli(tmp_path, *extra):
    with patch.dict(
        os.environ,
        {"CANARCHY_TRANSPORT_BACKEND": "scaffold", "CANARCHY_MCP_NONINTERACTIVE_ACK": "1"},
    ):
        return run_cli(
            "fuzz",
            "guided",
            "vcan0",
            "--id",
            "0x123",
            "--ack-active",
            "--max-iterations",
            "3",
            "--findings-dir",
            str(tmp_path),
            "--json",
            *extra,
        )


def test_cli_manifest_and_output(tmp_path):
    with patch.object(
        LocalTransport, "transaction", side_effect=[[], [response(1)], [response(2)]]
    ):
        code, stdout, _ = active_cli(tmp_path)
    assert code == 0
    data = json.loads(stdout)["data"]
    directory = Path(data["archive_path"])
    manifest = json.loads((directory / "campaign.json").read_text())
    assert manifest["schema_version"] == 1
    assert manifest["canarchy_version"]
    assert manifest["config"]["arbitration_id"] == 0x123
    assert manifest["config"]["max_payload"] == 8
    assert manifest["config"]["transport_backend"] == "scaffold"
    assert manifest["config"]["feedback_weights"]["nrc"] == 5
    assert manifest["config"]["pace_seconds"] == 0.01
    assert manifest["config"]["target_firmware"] is None
    assert data["archived_finding_count"] == len(data["findings"]) == 2
    assert data["findings"][0]["campaign_id"] == manifest["campaign_id"]
    from canarchy.cli import CommandResult, format_fuzz_guided_table

    rendered = "\n".join(format_fuzz_guided_table(CommandResult(command="fuzz guided", data=data)))
    assert f"archive_path: {directory}" in rendered
    assert "archived_findings: 2" in rendered


@pytest.mark.parametrize(
    "failure,expected",
    [
        (
            TransportError("TRANSPORT_UNAVAILABLE", "broken", "check bus"),
            "FUZZ_GUIDED_TRANSPORT_FAILED",
        ),
        (KeyboardInterrupt(), "FUZZ_GUIDED_INTERRUPTED"),
    ],
)
def test_cli_partial_error_reports_archive(tmp_path, failure, expected):
    with patch.object(LocalTransport, "transaction", side_effect=[[], [response(1)], failure]):
        code, stdout, _ = active_cli(tmp_path)
    payload = json.loads(stdout)
    assert code != 0
    assert payload["errors"][0]["code"] == expected
    assert payload["data"]["archived_finding_count"] == 1
    assert len(list(Path(payload["data"]["archive_path"]).glob("finding-*.json"))) == 1


def test_cli_storage_failure_before_transmit(tmp_path):
    with patch("canarchy.fuzz_archive._write_record", side_effect=OSError("read only")):
        with patch.object(LocalTransport, "transaction") as transaction:
            code, stdout, _ = active_cli(tmp_path)
    assert code == 2
    assert json.loads(stdout)["errors"][0]["code"] == "FUZZ_GUIDED_PERSISTENCE_FAILED"
    transaction.assert_not_called()


def test_dry_run_does_not_create_archive_or_transmit(tmp_path):
    with patch.object(LocalTransport, "transaction") as transaction:
        code, _, _ = active_cli(tmp_path / "absent", "--dry-run")
    assert code == 0
    assert not (tmp_path / "absent").exists()
    transaction.assert_not_called()


def test_mcp_findings_directory_preserves_safety_default():
    from canarchy.mcp_server import _build_argv

    argv = _build_argv(
        "fuzz_guided", {"id": "0x123", "ack_active": True, "findings_dir": "evidence"}
    )
    assert argv[argv.index("--findings-dir") + 1] == "evidence"
    assert "--dry-run" in argv


def test_final_corpus_save_failure_preserves_archive(tmp_path):
    with patch.object(
        LocalTransport, "transaction", side_effect=[[], [response(1)], [response(2)]]
    ):
        with patch("canarchy.fuzz_guided.save_corpus", side_effect=OSError("disk full")):
            code, stdout, _ = active_cli(
                tmp_path / "evidence", "--corpus", str(tmp_path / "corpus")
            )
    payload = json.loads(stdout)
    assert code == 2
    assert payload["errors"][0]["code"] == "FUZZ_GUIDED_PERSISTENCE_FAILED"
    assert payload["data"]["archived_finding_count"] == 2
    assert len(list(Path(payload["data"]["archive_path"]).glob("finding-*.json"))) == 2


def test_cli_record_failure_stops_campaign_and_reports_previous_evidence(tmp_path):
    real_write = _write_record

    def write(path, payload):
        if path.name == "finding-00000003.json":
            raise OSError("disk full")
        real_write(path, payload)

    with patch("canarchy.fuzz_archive._write_record", side_effect=write):
        with patch.object(
            LocalTransport, "transaction", side_effect=[[], [response(1)], [response(2)]]
        ) as tx:
            code, stdout, _ = active_cli(tmp_path, "--max-iterations", "10")
    payload = json.loads(stdout)
    assert code == 2
    assert tx.call_count == 3
    assert payload["errors"][0]["code"] == "FUZZ_GUIDED_PERSISTENCE_FAILED"
    assert payload["data"]["archived_finding_count"] == 1
    assert len(list(Path(payload["data"]["archive_path"]).glob("finding-*.json"))) == 1
