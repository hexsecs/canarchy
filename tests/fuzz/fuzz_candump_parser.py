#!/usr/bin/env python3
"""Atheris fuzz harness for the candump line parser.

Targets ``canarchy.transport.parse_candump_line``. Arbitrary bytes are
decoded as latin-1 text (a total mapping, so decoding never fails) and
fed to the parser. The parser's documented ``TransportError`` is the only
expected failure; any other exception is a finding.

Run after ``pip install .[fuzz]``::

    python tests/fuzz/fuzz_candump_parser.py -max_total_time=30 \\
        tests/fuzz/corpora/candump
"""

from __future__ import annotations

import sys
from pathlib import Path

from canarchy.transport import TransportError, parse_candump_line


def TestOneInput(data: bytes) -> None:
    line = data.decode("latin-1").strip()
    if not line:
        return
    try:
        parse_candump_line(line, path=Path("-"), line_number=1)
    except TransportError:
        return


def _main() -> None:
    import atheris

    atheris.instrument_all()
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    _main()
