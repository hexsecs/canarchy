"""Tab completion and command history for the CANarchy shell and TUI."""

from __future__ import annotations

import atexit
import glob
import os
import shlex
from typing import Optional

try:
    import readline
except ImportError:  # pragma: no cover — Windows without pyreadline
    readline = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Command tree
# ---------------------------------------------------------------------------

# Top-level commands available inside the shell/TUI prompt (no "canarchy" prefix).
# "shell" and "tui" are intentionally excluded — they are rejected when entered
# inside an interactive session anyway.
TOP_LEVEL_COMMANDS: list[str] = [
    "capture",
    "config",
    "dbc",
    "decode",
    "encode",
    "export",
    "filter",
    "fuzz",
    "gateway",
    "generate",
    "j1939",
    "re",
    "replay",
    "send",
    "session",
    "stats",
    "uds",
    "exit",
    "quit",
]

# Group commands whose second token is a subcommand.
SUBCOMMANDS: dict[str, list[str]] = {
    "config": ["show"],
    "dbc": ["inspect"],
    "session": ["load", "save", "show"],
    "j1939": ["decode", "dm1", "monitor", "pgn", "spn", "tp"],
    "uds": ["scan", "services", "trace"],
    "re": ["correlate", "counters", "entropy", "signals"],
    "fuzz": ["id", "mutate", "replay"],
}

# Output format flags shared by every command.
_OUTPUT = ["--json", "--jsonl", "--raw", "--table"]
_J1939_FILE_BOUNDS = ["--offset", "--max-frames", "--seconds"]

# Per-command (or per-subcommand) flag lists.
# Keys for subcommand groups use the "group subcommand" form.
FLAGS: dict[str, list[str]] = {
    "capture": ["--candump"] + _OUTPUT,
    "capture-info": ["--file"] + _OUTPUT,
    "config show": _OUTPUT,
    "dbc inspect": ["--message", "--signals-only"] + _OUTPUT,
    "decode": ["--dbc", "--file"] + _OUTPUT,
    "encode": ["--dbc"] + _OUTPUT,
    "export": _OUTPUT,
    "filter": ["--file", "--compact"] + _OUTPUT,
    "gateway": [
        "--ack-active",
        "--bidirectional",
        "--count",
        "--dst-backend",
        "--src-backend",
    ] + _OUTPUT,
    "generate": [
        "--ack-active",
        "--count",
        "--data",
        "--dlc",
        "--extended",
        "--gap",
        "--id",
    ] + _OUTPUT,
    "j1939 decode": ["--dbc", "--file"] + _J1939_FILE_BOUNDS + _OUTPUT,
    "j1939 dm1": ["--dbc", "--file"] + _J1939_FILE_BOUNDS + _OUTPUT,
    "j1939 inventory": ["--file"] + _J1939_FILE_BOUNDS + _OUTPUT,
    "j1939 monitor": ["--pgn"] + _OUTPUT,
    "j1939 pgn": ["--dbc", "--file"] + _J1939_FILE_BOUNDS + _OUTPUT,
    "j1939 spn": ["--dbc", "--file"] + _J1939_FILE_BOUNDS + _OUTPUT,
    "j1939 summary": ["--file"] + _J1939_FILE_BOUNDS + _OUTPUT,
    "j1939 tp": ["--file"] + _J1939_FILE_BOUNDS + _OUTPUT,
    "re correlate": _OUTPUT,
    "re counters": _OUTPUT,
    "re entropy": _OUTPUT,
    "re signals": _OUTPUT,
    "fuzz id": _OUTPUT,
    "fuzz mutate": _OUTPUT,
    "fuzz replay": _OUTPUT,
    "replay": ["--file", "--rate"] + _OUTPUT,
    "send": ["--ack-active"] + _OUTPUT,
    "session load": _OUTPUT,
    "session save": ["--capture", "--dbc", "--interface"] + _OUTPUT,
    "session show": _OUTPUT,
    "stats": ["--file"] + _OUTPUT,
    "uds scan": ["--ack-active"] + _OUTPUT,
    "uds services": _OUTPUT,
    "uds trace": _OUTPUT,
}

# Flags whose next token should be completed as a filesystem path.
_FILE_FLAGS: frozenset[str] = frozenset(["--capture", "--dbc", "--file"])


# ---------------------------------------------------------------------------
# Completer
# ---------------------------------------------------------------------------


class CanarchyCompleter:
    """Context-aware tab completer for the CANarchy interactive prompt.

    Registered with :func:`install_completion` so that pressing Tab inside
    ``canarchy shell`` or ``canarchy tui`` offers:

    * Top-level command names on the first token.
    * Subcommand names (``j1939 <tab>``, ``session <tab>``, …) on the second token.
    * Flag names (``--json``, ``--dbc``, …) once a command is recognised.
    * Filesystem paths after file-expecting flags such as ``--dbc`` and ``--file``,
      and for tokens that look like paths (start with ``/``, ``~``, or ``.``).
    """

    def __init__(self) -> None:
        self._matches: list[str] = []

    # readline calls complete(text, state) with state = 0, 1, 2, … until None.
    def complete(self, text: str, state: int) -> Optional[str]:
        if state == 0:
            self._matches = self._get_completions(text)
        if state < len(self._matches):
            return self._matches[state]
        return None

    def _get_completions(self, text: str) -> list[str]:
        if readline is None:
            return []
        line: str = readline.get_line_buffer()

        # Split tokens that have already been confirmed (i.e. everything before
        # the current partial word).  If the line ends with whitespace the user
        # is starting a brand-new token; otherwise the last shlex token is the
        # one being completed and we drop it from the "confirmed" list.
        try:
            all_tokens = shlex.split(line) if line.strip() else []
        except ValueError:
            all_tokens = line.split()

        if line and not line[-1].isspace():
            # The last token is partial — don't count it as confirmed.
            confirmed = all_tokens[:-1]
        else:
            confirmed = all_tokens

        # ── After a file-expecting flag → path completion ───────────────────
        if confirmed and confirmed[-1] in _FILE_FLAGS:
            return self._complete_path(text)

        # ── First token → top-level command names ───────────────────────────
        if not confirmed:
            return [c + " " for c in TOP_LEVEL_COMMANDS if c.startswith(text)]

        first = confirmed[0]

        # ── Second token for a group command → subcommand names ─────────────
        if first in SUBCOMMANDS and len(confirmed) == 1:
            return [s + " " for s in SUBCOMMANDS[first] if s.startswith(text)]

        # ── Determine the flag key ──────────────────────────────────────────
        if first in SUBCOMMANDS and len(confirmed) >= 2:
            cmd_key = f"{first} {confirmed[1]}"
        else:
            cmd_key = first

        flags = FLAGS.get(cmd_key, _OUTPUT)
        already_used = set(confirmed)

        # ── Explicit path-looking token → filesystem completion ─────────────
        if text and text[0] in ("/", "~", "."):
            return self._complete_path(text)

        # ── Partial flag → flag completion ───────────────────────────────────
        if text.startswith("-"):
            return [f + " " for f in flags if f.startswith(text) and f not in already_used]

        # ── Empty text or positional → offer unused flags ────────────────────
        return [f + " " for f in flags if f.startswith(text) and f not in already_used]

    @staticmethod
    def _complete_path(text: str) -> list[str]:
        """Return filesystem path completions matching *text*."""
        pattern = os.path.expanduser(text) + "*" if text else "*"
        matches = glob.glob(pattern)
        result: list[str] = []
        for match in sorted(matches):
            result.append(match + "/" if os.path.isdir(match) else match)
        return result


# ---------------------------------------------------------------------------
# Public installation helper
# ---------------------------------------------------------------------------

_HISTORY_FILE = "~/.canarchy/history"


def install_completion() -> None:
    """Enable tab completion and persistent command history for ``input()``.

    Safe to call on platforms where ``readline`` is unavailable — the function
    degrades silently rather than raising.

    History is loaded from and saved to ``~/.canarchy/history`` so commands
    persist across shell and TUI sessions.
    """
    if readline is None:
        return

    completer = CanarchyCompleter()
    readline.set_completer(completer.complete)

    # Delimiters: only split on whitespace so that paths and flag names with
    # hyphens complete as a unit.
    readline.set_completer_delims(" \t\n")

    # macOS ships Python with libedit rather than GNU readline; the key-binding
    # syntax differs between the two.
    doc = getattr(readline, "__doc__", "") or ""
    if "libedit" in doc:
        readline.parse_and_bind("bind ^I rl_complete")
    else:
        readline.parse_and_bind("tab: complete")

    # Persistent history.
    history_path = os.path.expanduser(_HISTORY_FILE)
    os.makedirs(os.path.dirname(history_path), exist_ok=True)
    try:
        readline.read_history_file(history_path)
    except FileNotFoundError:
        pass
    except OSError:
        pass

    readline.set_history_length(500)
    atexit.register(_save_history, history_path)


def _save_history(path: str) -> None:
    try:
        readline.write_history_file(path)
    except Exception:  # noqa: BLE001
        pass
