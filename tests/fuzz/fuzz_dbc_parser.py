#!/usr/bin/env python3
"""Atheris fuzz harness for the cantools-backed DBC parser.

Targets the parse path used by ``canarchy.dbc_runtime`` —
``cantools.database.load_string(..., database_format="dbc")``. The
adapter (`load_runtime_database`) wraps any parse failure as a
``DbcError``; cantools' own ``UnsupportedDatabaseFormatError`` is the
expected rejection for malformed input. Any other exception is a finding.

Run after ``pip install .[fuzz]``::

    python tests/fuzz/fuzz_dbc_parser.py -max_total_time=30 \\
        tests/fuzz/corpora/dbc
"""

from __future__ import annotations

import sys

import cantools
from cantools.database import UnsupportedDatabaseFormatError


def TestOneInput(data: bytes) -> None:
    text = data.decode("latin-1")
    try:
        cantools.database.load_string(text, database_format="dbc")
    except UnsupportedDatabaseFormatError:
        return


def _main() -> None:
    import atheris

    atheris.instrument_all()
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    _main()
