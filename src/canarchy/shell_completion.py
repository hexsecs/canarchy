"""Shell completion scripts emitted by ``canarchy completion <shell>``.

These scripts are intended to be sourced from the user's shell rcfile
(or dropped into the appropriate completion directory). They cover:

* the top-level ``canarchy`` subcommands
* the most common flags (``--json``, ``--jsonl``, ``--text``, ``--file``,
  ``--dbc``, ``--max-frames``, ``--seconds``, ``--offset``, ``--ack-active``,
  ``--log-level``, ``--quiet``, ``--help``, ``--version``)
* file-path completion after ``--file``

Provider refs such as ``opendbc:<name>`` are not enumerated here because
the available names depend on a populated DBC provider cache; users can
rely on substring matching in their shell or run
``canarchy dbc search`` first.
"""

from __future__ import annotations

from typing import Iterable

# Top-level subcommand catalogue. Keep in sync with the canonical CLI
# surface in ``canarchy.cli.build_parser``.
SUBCOMMANDS: list[tuple[str, str]] = [
    ("capture", "capture CAN traffic"),
    ("send", "send a single CAN frame"),
    ("generate", "generate cangen-style CAN frames"),
    ("gateway", "bridge frames between two CAN interfaces"),
    ("replay", "replay recorded traffic"),
    ("filter", "filter frames from a capture"),
    ("stats", "summarise a capture"),
    ("capture-info", "show capture metadata"),
    ("decode", "DBC-backed signal decode"),
    ("encode", "DBC-backed signal encode"),
    ("dbc", "DBC provider workflows"),
    ("skills", "CANarchy skill discovery and cache"),
    ("datasets", "dataset provider workflows"),
    ("export", "export structured artifacts"),
    ("session", "save and restore CANarchy session context"),
    ("j1939", "J1939 protocol workflows"),
    ("uds", "UDS diagnostic workflows"),
    ("re", "reverse-engineering helpers"),
    ("config", "inspect CANarchy configuration"),
    ("doctor", "environment health checks"),
    ("mcp", "MCP server workflows"),
    ("shell", "start the interactive shell"),
    ("tui", "start the terminal UI"),
    ("completion", "emit shell completion script"),
]

COMMON_FLAGS: list[tuple[str, str]] = [
    ("--json", "emit JSON output"),
    ("--jsonl", "emit JSONL output"),
    ("--text", "emit human-readable text"),
    ("--file", "path to capture file"),
    ("--dbc", "DBC file path or provider ref"),
    ("--max-frames", "limit analysis to N frames"),
    ("--seconds", "limit analysis to N seconds"),
    ("--offset", "skip the first N frames"),
    ("--ack-active", "confirm active transmission"),
    ("--log-level", "set the stderr log level"),
    ("--quiet", "suppress stderr logging below ERROR"),
    ("--help", "show help"),
    ("--version", "show version"),
]

LOG_LEVELS: list[str] = ["debug", "info", "warn", "error"]


SUPPORTED_SHELLS: tuple[str, ...] = ("bash", "zsh", "fish")


def _names(pairs: Iterable[tuple[str, str]]) -> list[str]:
    return [name for name, _ in pairs]


# ---------------------------------------------------------------------------
# bash
# ---------------------------------------------------------------------------


def _bash_script() -> str:
    subcmds = " ".join(_names(SUBCOMMANDS))
    flags = " ".join(_names(COMMON_FLAGS))
    levels = " ".join(LOG_LEVELS)
    return f"""# canarchy bash completion. Install one of:
#   1. Copy into /etc/bash_completion.d/canarchy (system-wide)
#   2. Copy into ~/.bash_completion.d/canarchy and source from ~/.bashrc
#   3. Or eval directly: eval "$(canarchy completion bash)"

_canarchy_completions() {{
    local cur prev subcmds opts levels
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"
    subcmds="{subcmds}"
    opts="{flags}"
    levels="{levels}"

    case "${{prev}}" in
        --file)
            COMPREPLY=( $(compgen -f -- "${{cur}}") )
            return 0
            ;;
        --log-level)
            COMPREPLY=( $(compgen -W "${{levels}}" -- "${{cur}}") )
            return 0
            ;;
        completion)
            COMPREPLY=( $(compgen -W "bash zsh fish" -- "${{cur}}") )
            return 0
            ;;
    esac

    if [[ ${{COMP_CWORD}} -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "${{subcmds}}" -- "${{cur}}") )
        return 0
    fi

    if [[ "${{cur}}" == --* ]]; then
        COMPREPLY=( $(compgen -W "${{opts}}" -- "${{cur}}") )
        return 0
    fi

    COMPREPLY=()
    return 0
}}

complete -F _canarchy_completions canarchy
"""


# ---------------------------------------------------------------------------
# zsh
# ---------------------------------------------------------------------------


def _zsh_script() -> str:
    sub_lines = "\n".join(f"        '{name}:{description}'" for name, description in SUBCOMMANDS)
    flag_lines: list[str] = []
    for name, description in COMMON_FLAGS:
        if name == "--file":
            flag_lines.append(f"        '{name}[{description}]:file:_files'")
        elif name == "--log-level":
            level_set = " ".join(LOG_LEVELS)
            flag_lines.append(f"        '{name}[{description}]:level:({level_set})'")
        else:
            flag_lines.append(f"        '{name}[{description}]'")
    flags = "\n".join(flag_lines)
    return f"""#compdef canarchy
# canarchy zsh completion. Install one of:
#   1. Place this output in a directory on $fpath (e.g.
#      ~/.zsh/completions/_canarchy) and run `compinit`.
#   2. Or eval directly from .zshrc:
#        eval "$(canarchy completion zsh)"

_canarchy() {{
    local -a _subcmds _opts
    _subcmds=(
{sub_lines}
    )
    _opts=(
{flags}
    )

    if (( CURRENT == 2 )); then
        _describe 'canarchy command' _subcmds
        return
    fi

    case "${{words[2]}}" in
        completion)
            _values 'shell' bash zsh fish
            return
            ;;
    esac

    _arguments $_opts '*::file:_files'
}}

if [ "${{funcstack[1]}}" = "_canarchy" ]; then
    _canarchy "$@"
else
    compdef _canarchy canarchy
fi
"""


# ---------------------------------------------------------------------------
# fish
# ---------------------------------------------------------------------------


def _fish_script() -> str:
    lines = [
        "# canarchy fish completion. Install one of:",
        "#   1. Copy into ~/.config/fish/completions/canarchy.fish",
        "#   2. Or eval directly: canarchy completion fish | source",
        "",
        "function __fish_canarchy_needs_subcommand",
        "    set -l cmd (commandline -opc)",
        "    if test (count $cmd) -eq 1",
        "        return 0",
        "    end",
        "    return 1",
        "end",
        "",
    ]
    for name, description in SUBCOMMANDS:
        lines.append(
            f"complete -c canarchy -f -n '__fish_canarchy_needs_subcommand' "
            f"-a '{name}' -d '{description}'"
        )
    lines.append("")
    for name, description in COMMON_FLAGS:
        long = name.removeprefix("--")
        if name == "--file":
            lines.append(f"complete -c canarchy -l {long} -d '{description}' -r")
        elif name == "--log-level":
            choices = " ".join(LOG_LEVELS)
            lines.append(f"complete -c canarchy -l {long} -d '{description}' -a '{choices}' -x")
        elif name in {"--max-frames", "--seconds", "--offset"}:
            lines.append(f"complete -c canarchy -l {long} -d '{description}' -x")
        else:
            lines.append(f"complete -c canarchy -l {long} -d '{description}'")
    lines.append("")
    lines.append(
        "complete -c canarchy -f -n '__fish_seen_subcommand_from completion' "
        "-a 'bash zsh fish' -d 'shell flavour'"
    )
    lines.append("")
    return "\n".join(lines)


_GENERATORS = {
    "bash": _bash_script,
    "zsh": _zsh_script,
    "fish": _fish_script,
}


def render_completion(shell: str) -> str:
    """Return the completion script for ``shell``.

    Raises ``ValueError`` for unsupported shells; the CLI translates this
    into a structured error.
    """

    try:
        return _GENERATORS[shell]()
    except KeyError as exc:
        supported = ", ".join(SUPPORTED_SHELLS)
        raise ValueError(f"Unsupported shell '{shell}'. Supported shells: {supported}.") from exc
