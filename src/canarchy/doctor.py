"""Environment health checks exposed via ``canarchy doctor``.

The doctor command returns a canonical envelope so both human operators
and agents can use it for triage. Each check produces a ``{name, status,
detail, hint}`` block; ``status`` is one of ``ok``, ``warn``, or ``fail``.

Checks are intentionally cheap (no network, no live bus). They cover the
local environment, dependencies, configuration, and cache state.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from canarchy import __version__

CheckPayload = dict[str, Any]


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _ok(name: str, detail: str) -> CheckPayload:
    return {"name": name, "status": "ok", "detail": detail, "hint": None}


def _warn(name: str, detail: str, hint: str) -> CheckPayload:
    return {"name": name, "status": "warn", "detail": detail, "hint": hint}


def _fail(name: str, detail: str, hint: str) -> CheckPayload:
    return {"name": name, "status": "fail", "detail": detail, "hint": hint}


def _check_python_version() -> CheckPayload:
    major, minor, micro = sys.version_info[:3]
    version = f"Python {major}.{minor}.{micro}"
    if (major, minor) >= (3, 12):
        return _ok("python_version", version)
    return _fail(
        "python_version",
        f"{version} is below the required 3.12 baseline",
        "Install Python 3.12 or newer and re-run `canarchy doctor`.",
    )


def _check_python_can() -> CheckPayload:
    try:
        import can  # type: ignore[import-untyped]
    except ImportError as exc:
        return _fail(
            "python_can",
            f"python-can is not importable: {exc}",
            "Re-install canarchy or `pip install python-can` in the active environment.",
        )
    version = getattr(can, "__version__", "unknown")
    return _ok("python_can", f"python-can {version} importable")


def _check_transport_backend() -> CheckPayload:
    backend = (os.environ.get("CANARCHY_TRANSPORT_BACKEND") or "python-can").strip().lower()
    if backend == "scaffold":
        return _ok("transport_backend", "scaffold (deterministic offline)")
    if backend == "python-can":
        try:
            import can  # type: ignore[import-untyped]  # noqa: F401
        except ImportError:
            return _fail(
                "transport_backend",
                "configured as python-can but the library is not importable",
                "Install python-can or set CANARCHY_TRANSPORT_BACKEND=scaffold for offline use.",
            )
        interface = os.environ.get("CANARCHY_PYTHON_CAN_INTERFACE", "<unset>")
        return _ok("transport_backend", f"python-can interface={interface}")
    return _warn(
        "transport_backend",
        f"unknown backend '{backend}'",
        "Set CANARCHY_TRANSPORT_BACKEND to 'python-can' or 'scaffold'.",
    )


def _config_path() -> Path:
    return Path.home() / ".canarchy" / "config.toml"


def _check_config_file() -> CheckPayload:
    path = _config_path()
    if not path.exists():
        return _ok("config_file", f"{path} not present (defaults in use)")
    try:
        import tomllib
    except ImportError:  # Python < 3.11 — guarded by python_version check
        return _warn(
            "config_file",
            "Cannot parse TOML — Python is missing the tomllib module.",
            "Upgrade to Python 3.12 or newer.",
        )
    try:
        with path.open("rb") as handle:
            tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return _fail(
            "config_file",
            f"{path} present but failed to parse: {exc}",
            "Open the file and fix the TOML syntax, then re-run `canarchy doctor`.",
        )
    return _ok("config_file", f"{path} parses cleanly")


def _cache_root_for(module_name: str) -> Path | None:
    try:
        module = __import__(module_name, fromlist=["cache_root"])
    except ImportError:
        return None
    cache_root = getattr(module, "cache_root", None)
    if cache_root is None:
        return None
    try:
        return Path(cache_root())
    except Exception:  # pragma: no cover — defensive
        return None


def _check_cache_dirs() -> CheckPayload:
    roots: list[tuple[str, Path]] = []
    for module_name in (
        "canarchy.dbc_cache",
        "canarchy.dataset_cache",
        "canarchy.skills_cache",
    ):
        root = _cache_root_for(module_name)
        if root is not None:
            roots.append((module_name.rsplit(".", 1)[1], root))

    if not roots:
        return _warn(
            "cache_dirs",
            "no cache modules expose a cache_root() helper",
            "This usually means a partial install; reinstall canarchy.",
        )

    failures: list[str] = []
    for label, root in roots:
        try:
            root.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(prefix="doctor-", dir=root) as _handle:
                pass
        except OSError as exc:
            failures.append(f"{label}={root}: {exc}")

    if failures:
        return _fail(
            "cache_dirs",
            "; ".join(failures),
            "Fix permissions on the listed cache directory or set HOME to a writable location.",
        )
    return _ok("cache_dirs", "all caches writable")


def _check_opendbc_cache() -> CheckPayload:
    try:
        from canarchy import dbc_cache
    except ImportError as exc:
        return _warn(
            "opendbc_cache",
            f"dbc_cache module not importable: {exc}",
            "Reinstall canarchy.",
        )

    cache_root = Path(dbc_cache.cache_root()) / "opendbc"
    if not cache_root.exists():
        return _warn(
            "opendbc_cache",
            f"{cache_root} not present",
            "Run `canarchy dbc cache refresh --provider opendbc` to populate it.",
        )

    files = list(cache_root.rglob("*.dbc"))
    if not files:
        return _warn(
            "opendbc_cache",
            f"{cache_root} exists but contains no .dbc files",
            "Run `canarchy dbc cache refresh --provider opendbc` to rebuild the cache.",
        )
    return _ok("opendbc_cache", f"{len(files)} cached DBC files at {cache_root}")


def _check_mcp_server() -> CheckPayload:
    try:
        import canarchy.mcp_server as mcp_server
    except ImportError as exc:
        return _fail(
            "mcp_server",
            f"canarchy.mcp_server is not importable: {exc}",
            "Reinstall canarchy with the MCP extra.",
        )
    if not hasattr(mcp_server, "run_server"):
        return _fail(
            "mcp_server",
            "canarchy.mcp_server is missing the run_server entry point",
            "Reinstall canarchy; the MCP server contract has drifted.",
        )
    return _ok("mcp_server", "stdio server constructable")


def _check_version_consistency() -> CheckPayload:
    try:
        from importlib.metadata import PackageNotFoundError, version as installed_version
    except ImportError:  # pragma: no cover — Python 3.12+ has importlib.metadata
        return _warn(
            "version_consistency",
            "importlib.metadata not available",
            "Upgrade to Python 3.12 or newer.",
        )
    try:
        installed = installed_version("canarchy")
    except PackageNotFoundError:
        return _warn(
            "version_consistency",
            "canarchy is not installed via a package manager (editable workspace?)",
            "Run `uv tool install --editable .` or `pipx install canarchy` to register the package.",
        )
    if installed != __version__:
        return _warn(
            "version_consistency",
            f"installed package reports {installed} but src/canarchy/__init__.py is {__version__}",
            "Run `uv sync` to reinstall the editable package against the current source.",
        )
    return _ok("version_consistency", f"package and source agree on {installed}")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def doctor_payload() -> dict[str, Any]:
    """Return the canonical ``data`` payload for ``canarchy doctor``.

    The caller wraps the dict in a :class:`~canarchy.cli.CommandResult`.
    """

    checks = [
        _check_python_version(),
        _check_python_can(),
        _check_transport_backend(),
        _check_config_file(),
        _check_cache_dirs(),
        _check_opendbc_cache(),
        _check_mcp_server(),
        _check_version_consistency(),
    ]
    ok_count = sum(1 for c in checks if c["status"] == "ok")
    warn_count = sum(1 for c in checks if c["status"] == "warn")
    fail_count = sum(1 for c in checks if c["status"] == "fail")
    summary = f"{ok_count} ok, {warn_count} warning(s), {fail_count} failed"
    return {
        "checks": checks,
        "ok_count": ok_count,
        "warn_count": warn_count,
        "fail_count": fail_count,
        "summary": summary,
    }
