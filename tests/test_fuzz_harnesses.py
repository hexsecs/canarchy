"""Smoke tests for the atheris fuzz harnesses (`tests/fuzz/`).

These run each harness's ``TestOneInput`` over its seed corpus plus a
bounded, seeded random sweep — without requiring atheris (which is only
imported inside each harness's ``_main``). They validate that the harness
logic is importable and that the targeted parsers handle the seeds and a
spread of random inputs without raising an unexpected exception. The
coverage-guided atheris run lives in the `fuzz` CI workflow.
"""

from __future__ import annotations

import importlib.util
import random
from pathlib import Path

import pytest

FUZZ_DIR = Path(__file__).parent / "fuzz"
CORPORA = FUZZ_DIR / "corpora"

# (harness module file, corpus subdirectory).
_HARNESSES = [
    ("fuzz_candump_parser.py", "candump"),
    ("fuzz_dbc_parser.py", "dbc"),
    ("fuzz_isotp_reassembly.py", "isotp"),
    ("fuzz_j1939_tp.py", "j1939_tp"),
]


def _load_harness(filename: str):
    path = FUZZ_DIR / filename
    spec = importlib.util.spec_from_file_location(f"_harness_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _corpus_inputs(corpus_dir: str) -> list[bytes]:
    directory = CORPORA / corpus_dir
    return [path.read_bytes() for path in sorted(directory.iterdir()) if path.is_file()]


def _random_inputs(seed: int, count: int) -> list[bytes]:
    rng = random.Random(seed)
    inputs: list[bytes] = [b"", b"\x00", b"\xff" * 64]
    for _ in range(count):
        inputs.append(bytes(rng.randrange(256) for _ in range(rng.randint(0, 48))))
    return inputs


@pytest.mark.parametrize(("filename", "corpus_dir"), _HARNESSES)
def test_harness_imports_without_atheris_and_exposes_test_one_input(filename, corpus_dir):
    module = _load_harness(filename)
    assert callable(module.TestOneInput)


@pytest.mark.parametrize(("filename", "corpus_dir"), _HARNESSES)
def test_harness_seed_corpus_is_present(filename, corpus_dir):
    inputs = _corpus_inputs(corpus_dir)
    assert inputs, f"expected seed inputs under corpora/{corpus_dir}"


@pytest.mark.parametrize(("filename", "corpus_dir"), _HARNESSES)
def test_harness_handles_corpus_and_random_inputs(filename, corpus_dir):
    test_one_input = _load_harness(filename).TestOneInput
    for data in _corpus_inputs(corpus_dir) + _random_inputs(seed=1337, count=1500):
        # A finding would surface as an unexpected exception escaping the
        # harness; the parsers are expected to consume any input cleanly.
        assert test_one_input(data) is None
