# Fuzz regression inputs

Crashing inputs discovered by the atheris harnesses in `tests/fuzz/` are
saved here, one file per finding, named after the harness that produced
it (for example `fuzz_candump_parser_<hash>`). Each saved input should be
paired with a dedicated regression test under `tests/` that feeds the
input to the affected parser and asserts the bug stays fixed.

This directory is currently empty — the initial harness sweep over the
seed corpora found no crashes.
