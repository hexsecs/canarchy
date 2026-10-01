"""The publish workflow must refuse to upload anything but a tagged release.

Dispatched from `main` while cutting 0.10.0, `publish.yml` built the
development commit and uploaded 0.10.1.dev0 to PyPI (issue #559). PyPI never
accepts a version twice, so the guard has to stop the run before the build.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_release_ref.py"
WORKFLOW = ROOT / ".github" / "workflows" / "publish.yml"


def _load_guard():
    spec = importlib.util.spec_from_file_location("check_release_ref", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load_guard()


def test_the_incident_is_refused() -> None:
    """The exact dispatch that published 0.10.1.dev0: branch `main`, dev version."""
    problems = guard.check("pypi", "branch", "main", "0.10.1.dev0")
    assert len(problems) == 2
    assert any("not a tag" in p and "'main'" in p for p in problems)
    assert any("not a final release" in p and "0.10.1.dev0" in p for p in problems)


def test_matching_tag_with_final_version_is_allowed() -> None:
    assert guard.check("pypi", "tag", "v0.10.0", "0.10.0") == []


def test_branch_is_refused_even_with_a_final_version() -> None:
    """A release commit reached through a branch is still not the tag."""
    problems = guard.check("pypi", "branch", "main", "0.10.0")
    assert len(problems) == 1
    assert "not a tag" in problems[0]


def test_tag_that_does_not_match_the_version_is_refused() -> None:
    problems = guard.check("pypi", "tag", "v0.9.2", "0.10.0")
    assert problems == ["tag 'v0.9.2' does not match the package version; expected 'v0.10.0'"]


def test_unprefixed_tag_is_refused() -> None:
    """Release tags carry a `v` prefix; a bare `0.10.0` tag is not the release tag."""
    assert guard.check("pypi", "tag", "0.10.0", "0.10.0")


@pytest.mark.parametrize(
    "version",
    ["0.10.1.dev0", "0.11.0rc1", "0.11.0a1", "0.11.0b2", "0.10.0.post1", "0.10.0+local"],
)
def test_non_final_versions_are_refused_even_from_a_matching_tag(version: str) -> None:
    problems = guard.check("pypi", "tag", f"v{version}", version)
    assert len(problems) == 1
    assert "not a final release" in problems[0]


def test_testpypi_is_not_restricted() -> None:
    """TestPyPI is the runbook's sandbox for rehearsing workflow changes."""
    assert guard.check("testpypi", "branch", "main", "0.10.1.dev0") == []


def test_reads_the_same_version_hatch_builds() -> None:
    from canarchy import __version__

    assert guard.read_version() == __version__


def test_read_version_rejects_a_file_without_one(tmp_path: Path) -> None:
    empty = tmp_path / "__init__.py"
    empty.write_text('__all__ = ["x"]\n', encoding="utf-8")
    with pytest.raises(ValueError):
        guard.read_version(empty)


def _run(target: str, ref_type: str, ref_name: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "GITHUB_REF_TYPE": ref_type, "GITHUB_REF_NAME": ref_name}
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--target", target],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_cli_fails_from_a_branch_with_annotations() -> None:
    result = _run("pypi", "branch", "main")
    assert result.returncode == 1
    assert result.stdout.startswith("::error::")
    assert "not a tag" in result.stdout


def test_cli_passes_from_the_matching_tag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The success path, run in-process against a release-shaped version file.

    `main` normally carries a `.dev` version, so exercising the real package
    file here would only ever test refusal.
    """
    version_file = tmp_path / "__init__.py"
    version_file.write_text('__version__ = "0.10.0"\n', encoding="utf-8")
    monkeypatch.setattr(guard, "VERSION_FILE", version_file)
    monkeypatch.setenv("GITHUB_REF_TYPE", "tag")
    monkeypatch.setenv("GITHUB_REF_NAME", "v0.10.0")

    assert guard.main(["--target", "pypi"]) == 0
    assert "release ref OK" in capsys.readouterr().out


def test_cli_does_not_restrict_testpypi() -> None:
    assert _run("testpypi", "branch", "main").returncode == 0


def test_workflow_runs_the_guard_before_building() -> None:
    """The guard is only useful if it runs, and runs before the upload can happen."""
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    steps = jobs["build"]["steps"]
    names = [step.get("name", "") for step in steps]
    guard_index = names.index("Verify release ref")
    assert guard_index < names.index("Build distribution artifacts")
    guard_step = steps[guard_index]
    assert "scripts/check_release_ref.py" in guard_step["run"]
    assert guard_step["env"]["PUBLISH_TARGET"] == "${{ inputs.repository }}"
    # Both publish jobs depend on build, so a refused build uploads nothing.
    assert jobs["publish-pypi"]["needs"] == "build"
    assert jobs["publish-testpypi"]["needs"] == "build"
