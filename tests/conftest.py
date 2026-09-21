"""Default isolation for the CANarchy test suite (#531).

Running the tests must not read, write, or transmit anything belonging to the
person running them. Two autouse fixtures enforce that, and both are on by
default so a contributor gets isolation without having to remember it:

``isolate_canarchy_state``
    Redirects ``Path.home()`` and the ``CANARCHY_*`` environment at a
    per-test temporary directory, so config, caches, sessions, plugin state,
    metadata overrides, and fuzz findings all resolve somewhere disposable.

``forbid_real_can_bus``
    Fails a test that reaches ``python_can.Bus`` -- the single point where a
    real CAN interface is opened.

Why both. Isolation alone is not enough: the default transport backend is
``python-can`` on ``socketcan`` (see ``transport_backend_config``), so a
suite run on a machine that *has* a live interface would happily open it
even with no configuration present. Isolation removes the usual route to a
bus; the guard catches whatever is left and names the test that did it.

And a guard alone is not enough either: before this existed, a full suite run
left two fuzz campaign directories in the operator's real
``~/.canarchy/findings`` every time, and a config with
``interface = "udp_multicast"`` made the suite open a real multicast socket.

What this deliberately does **not** do is hide configuration-sensitivity.
Tests that care about config precedence still set a configured default
interface explicitly through their own fixtures -- see the `uds services`
regressions from #530, which exist precisely because a test inherited real
configuration and failed. Isolation makes that behaviour *deliberate* rather
than dependent on the developer's machine; it does not make it untestable.

Opting out: mark a test ``@pytest.mark.integration`` to keep the real
environment and permit a real bus. Those are excluded from the default run
(see ``addopts`` in ``pyproject.toml``) and require explicit selection with
``-m integration``.
"""

from __future__ import annotations

import contextlib
import os

import pytest

#: Module-level constants that captured ``Path.home()`` at import time, so
#: patching ``Path.home`` alone would not move them. Each entry is
#: (module, attribute, path relative to the fake home).
_IMPORT_TIME_HOME_PATHS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("canarchy.dbc_cache", "_CACHE_ROOT", (".canarchy", "cache", "dbc")),
    ("canarchy.dbc_cache", "_CONFIG_PATH", (".canarchy", "config.toml")),
    ("canarchy.skills_cache", "_CACHE_ROOT", (".canarchy", "cache", "skills")),
    ("canarchy.skills_cache", "_CONFIG_PATH", (".canarchy", "config.toml")),
    ("canarchy.j1587_metadata", "_PID_OVERRIDES_DEFAULT", (".canarchy", "j1587_pids.json")),
    ("canarchy.j1939_metadata", "_SPN_OVERRIDES_DEFAULT", (".canarchy", "j1939_spns.json")),
    ("canarchy.j2497_metadata", "_MID_OVERRIDES_DEFAULT", (".canarchy", "j2497_mids.json")),
)


def _is_integration(request: pytest.FixtureRequest) -> bool:
    return request.node.get_closest_marker("integration") is not None


@pytest.fixture(autouse=True)
def isolate_canarchy_state(request: pytest.FixtureRequest, tmp_path_factory, monkeypatch):
    """Point every CANarchy state location at a disposable directory."""
    if _is_integration(request):
        yield
        return

    home = tmp_path_factory.mktemp("canarchy-home")

    # Redirect via the environment rather than by patching `Path.home`.
    # `Path.home()` resolves `~` through HOME (POSIX) / USERPROFILE (Windows),
    # so this moves it for in-process code *and* for subprocess-based tests
    # like the stdio MCP server, which inherit the environment. Patching
    # `Path.home` to a fixed value would instead override a test that sets up
    # its own HOME (`test_session.py::workspace` does exactly that), silently
    # pointing the code under test somewhere the test never wrote to.
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    # A developer's real CANARCHY_* settings must not steer the suite. Tests
    # that want one set it themselves.
    for key in [k for k in os.environ if k.startswith("CANARCHY_")]:
        monkeypatch.delenv(key, raising=False)

    for module_name, attribute, parts in _IMPORT_TIME_HOME_PATHS:
        with contextlib.suppress(ImportError, AttributeError):
            module = __import__(module_name, fromlist=["_"])
            monkeypatch.setattr(module, attribute, home.joinpath(*parts))

    yield


@pytest.fixture(autouse=True)
def forbid_real_can_bus(request: pytest.FixtureRequest, monkeypatch):
    """Fail loudly if a test opens a real CAN interface.

    Tests that legitimately exercise the python-can backend patch
    ``PythonCanBackend._open_bus`` and never reach this, so the guard costs
    them nothing.
    """
    if _is_integration(request):
        yield
        return

    from canarchy import transport

    if getattr(transport, "python_can", None) is None:
        yield
        return

    real_bus = transport.python_can.Bus

    def _guarded_bus(*args, **kwargs):
        # python-can's `virtual` interface is an in-process message queue: no
        # socket, no hardware, nothing outside this process. It is the CAN
        # equivalent of the localhost web server the web tests bind, so it is
        # allowed. Every other interface (socketcan, udp_multicast, pcan,
        # vector, kvaser, ...) reaches a real bus or the network.
        if kwargs.get("interface") == "virtual":
            return real_bus(*args, **kwargs)
        raise AssertionError(
            f"{request.node.nodeid} tried to open a real CAN bus via "
            f"python_can.Bus(args={args!r}, kwargs={kwargs!r}). Unit tests must not "
            "touch a real interface: patch `PythonCanBackend._open_bus`, select the "
            "scaffold backend, use the in-process `virtual` interface, or mark the "
            "test `@pytest.mark.integration` if it genuinely needs hardware."
        )

    monkeypatch.setattr(transport.python_can, "Bus", _guarded_bus)
    yield
