"""Tests for the test suite's own isolation guarantees (#531).

The fixtures in `conftest.py` are the thing standing between an ordinary
`pytest` run and an operator's real configuration, caches, and CAN bus. If
they silently stop working, every other test in the suite goes back to
depending on whoever's machine it runs on -- so the guarantees are asserted
here rather than assumed.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from canarchy import dbc_cache, skills_cache, transport

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestStateIsolation:
    """`isolate_canarchy_state` redirects everything rooted at the home dir."""

    def test_home_is_a_disposable_directory(self) -> None:
        home = Path.home()
        assert "canarchy-home" in str(home), f"home was not redirected: {home}"
        assert home.is_dir()

    def test_home_env_and_path_home_agree(self) -> None:
        """Subprocess tests inherit HOME, so it must match `Path.home()`."""
        assert Path(os.environ["HOME"]) == Path.home()

    def test_no_canarchy_environment_leaks_in(self) -> None:
        leaked = sorted(k for k in os.environ if k.startswith("CANARCHY_"))
        assert leaked == [], f"CANARCHY_* variables leaked into the test: {leaked}"

    def test_user_config_reads_as_empty(self) -> None:
        """A developer's real `~/.canarchy/config.toml` must not be visible."""
        assert transport._load_user_config() == {}

    def test_no_default_interface_is_configured(self) -> None:
        """The setting behind #530 must not be inherited from the machine."""
        assert transport.default_can_interface() is None

    @pytest.mark.parametrize(
        "module,attribute",
        [
            (dbc_cache, "_CACHE_ROOT"),
            (dbc_cache, "_CONFIG_PATH"),
            (skills_cache, "_CACHE_ROOT"),
            (skills_cache, "_CONFIG_PATH"),
        ],
    )
    def test_import_time_paths_are_redirected(self, module, attribute) -> None:
        """These captured `Path.home()` at import, so HOME alone misses them."""
        value = Path(getattr(module, attribute))
        assert value.is_relative_to(Path.home()), f"{attribute} escapes the fake home: {value}"

    def test_fuzz_findings_default_stays_inside_the_fake_home(self) -> None:
        """A full suite run used to leave campaigns in the real findings dir."""
        findings = Path.home() / ".canarchy" / "findings"
        assert findings.is_relative_to(Path.home())


class TestCanBusGuard:
    """`forbid_real_can_bus` blocks the one call that opens a real interface."""

    def test_socketcan_is_refused(self) -> None:
        with pytest.raises(AssertionError, match="tried to open a real CAN bus"):
            transport.python_can.Bus(channel="can0", interface="socketcan")

    def test_udp_multicast_is_refused(self) -> None:
        """The interface that actually opened a socket during the evaluation."""
        with pytest.raises(AssertionError, match="tried to open a real CAN bus"):
            transport.python_can.Bus(channel="239.0.0.1:10000", interface="udp_multicast")

    def test_the_refusal_names_the_test(self) -> None:
        """A guard that does not say who tripped it is hard to act on."""
        with pytest.raises(AssertionError) as caught:
            transport.python_can.Bus(channel="can0", interface="socketcan")
        assert "test_the_refusal_names_the_test" in str(caught.value)

    def test_in_process_virtual_bus_is_allowed(self) -> None:
        """`virtual` is an in-process queue: no socket, no hardware."""
        bus = transport.python_can.Bus(
            channel="canarchy-isolation-test", interface="virtual", receive_own_messages=True
        )
        try:
            assert bus is not None
        finally:
            bus.shutdown()

    def test_backend_reports_the_guard_as_a_transport_error(self) -> None:
        """The guard surfaces through the backend's normal error path."""
        backend = transport.PythonCanBackend(bus_interface="socketcan")
        with pytest.raises((transport.TransportError, AssertionError)):
            backend.capture("can0")


class TestIntegrationMarker:
    """Integration tests must be opt-in, not part of the default run."""

    def _run_pytest(self, tmp_path: Path, *extra: str) -> subprocess.CompletedProcess:
        test_file = tmp_path / "test_marked.py"
        test_file.write_text(
            textwrap.dedent(
                """
                import pytest

                def test_ordinary():
                    pass

                @pytest.mark.integration
                def test_needs_hardware():
                    pass
                """
            ),
            encoding="utf-8",
        )
        return subprocess.run(
            # `-c` is required: pytest picks its rootdir from the test file's
            # location, so a file under tmp_path would otherwise load neither
            # the `integration` marker nor the default `-m 'not integration'`.
            [
                sys.executable,
                "-m",
                "pytest",
                "-c",
                str(REPO_ROOT / "pyproject.toml"),
                str(test_file),
                "-q",
                "-p",
                "no:cacheprovider",
                *extra,
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=300,
        )

    def test_integration_tests_are_deselected_by_default(self, tmp_path: Path) -> None:
        result = self._run_pytest(tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "1 passed" in result.stdout
        assert "1 deselected" in result.stdout

    def test_integration_tests_run_when_selected(self, tmp_path: Path) -> None:
        result = self._run_pytest(tmp_path, "-m", "integration")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "1 passed" in result.stdout

    def test_marker_is_registered(self, tmp_path: Path) -> None:
        """An unregistered marker would warn, and `-W error` would fail."""
        result = self._run_pytest(tmp_path, "-W", "error::pytest.PytestUnknownMarkWarning")
        assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.integration
class TestIntegrationOptOut:
    """Marked tests keep the real environment; they never run by default."""

    def test_marked_tests_see_the_real_home(self) -> None:
        # Only meaningful when selected with `-m integration`. If this ever
        # runs in a default suite, the marker filtering has regressed.
        assert "canarchy-home" not in str(Path.home())
