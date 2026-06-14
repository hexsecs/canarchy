"""Response-feedback guided fuzzing loop (#350).

A thin loop on top of the :mod:`canarchy.fuzzing` mutators that uses the
:mod:`canarchy.fuzz_feedback` fingerprint engine as its novelty signal. Inputs
that elicit previously-unseen target behaviour are kept as corpus seeds and
their lineage is prioritised for further mutation. The loop is pure given an
injected ``responder`` callable, so it is fully testable against a mocked
responder with no live bus; the CLI wires a transport-backed responder.
"""

from __future__ import annotations

import itertools
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from canarchy.fuzz_feedback import (
    DEFAULT_WEIGHTS,
    SIGNAL_CATEGORIES,
    FeedbackTracker,
    ResponseObservation,
    fingerprint_response,
)
from canarchy.fuzzing import havoc_payload, splice_payload

Responder = Callable[[bytes], ResponseObservation]
Mutator = Callable[[bytes, random.Random, list[bytes]], bytes]

_LINEAGE_MANIFEST = "lineage.json"


@dataclass(slots=True, frozen=True)
class Seed:
    data: bytes
    seed_id: str
    parent_id: str | None
    generation: int
    score: float


@dataclass(slots=True, frozen=True)
class Finding:
    iteration: int
    seed_id: str
    parent_id: str | None
    generation: int
    gain: int
    new_markers: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "iteration": self.iteration,
            "seed_id": self.seed_id,
            "parent_id": self.parent_id,
            "generation": self.generation,
            "gain": self.gain,
            "new_markers": list(self.new_markers),
        }


@dataclass(slots=True)
class GuidedFuzzResult:
    iterations: int
    new_behaviour_count: int
    corpus_size: int
    unique_markers: int
    stop_reason: str
    findings: list[Finding]
    seeds: list[Seed]


def default_mutator(data: bytes, rng: random.Random, corpus: list[bytes]) -> bytes:
    """Mutate via the bundled havoc / splice mutators."""
    seed = rng.randrange(1 << 31)
    if len(corpus) >= 2 and rng.random() < 0.3:
        return next(splice_payload(corpus, seed=seed, count=1))
    return next(havoc_payload(data or b"\x00", seed=seed, count=1))


def _select_seed(corpus: list[Seed], rng: random.Random) -> Seed:
    # Energy proportional to score: productive lineages get mutated more, while
    # the +1 floor keeps every seed reachable. Deterministic under a seeded rng.
    weights = [seed.score + 1.0 for seed in corpus]
    return rng.choices(corpus, weights=weights, k=1)[0]


def _prune(corpus: list[Seed], max_corpus: int) -> None:
    if len(corpus) <= max_corpus:
        return
    corpus.sort(key=lambda seed: (-seed.score, seed.generation, seed.seed_id))
    del corpus[max_corpus:]


def run_guided_fuzz(
    initial_seeds: list[bytes],
    responder: Responder,
    *,
    signals: tuple[str, ...] = SIGNAL_CATEGORIES,
    weights: dict[str, int] | None = None,
    max_iterations: int = 200,
    max_seconds: float | None = None,
    max_corpus: int = 64,
    max_payload: int | None = None,
    rng_seed: int = 0,
    mutate: Mutator = default_mutator,
    clock: Callable[[], float] = time.monotonic,
    kill_switch: Callable[[], bool] | None = None,
) -> GuidedFuzzResult:
    """Run the guided campaign, returning the result and final corpus.

    The initial seeds' responses prime the tracker as the behaviour baseline, so
    only genuinely new markers count as findings. ``max_payload`` clamps seeds and
    mutations to a valid frame size (e.g. 8 for classic CAN).
    """
    rng = random.Random(rng_seed)
    tracker = FeedbackTracker(weights=dict(weights or DEFAULT_WEIGHTS))
    counter = itertools.count()
    corpus: list[Seed] = []

    def _clamp(payload: bytes) -> bytes:
        return payload[:max_payload] if max_payload is not None else payload

    seed_inputs = initial_seeds or [bytes(8)]
    for data in seed_inputs:
        seed_data = _clamp(bytes(data))
        # Prime the baseline: observe (do not score) each initial seed.
        tracker.observe(fingerprint_response(responder(seed_data), signals=signals))
        corpus.append(Seed(seed_data, f"s{next(counter)}", None, 0, 0.0))

    findings: list[Finding] = []
    start = clock()
    iteration = 0
    stop_reason = "max_iterations"

    while True:
        if iteration >= max_iterations:
            stop_reason = "max_iterations"
            break
        if max_seconds is not None and (clock() - start) >= max_seconds:
            stop_reason = "max_seconds"
            break
        if kill_switch is not None and kill_switch():
            stop_reason = "kill_switch"
            break

        parent = _select_seed(corpus, rng)
        child_data = _clamp(mutate(parent.data, rng, [seed.data for seed in corpus]))
        observation = responder(child_data)
        fingerprint = fingerprint_response(observation, signals=signals)
        gain, new_markers = tracker.score_and_observe(fingerprint)
        iteration += 1

        if gain > 0:
            child = Seed(
                data=child_data,
                seed_id=f"s{next(counter)}",
                parent_id=parent.seed_id,
                generation=parent.generation + 1,
                score=float(gain),
            )
            corpus.append(child)
            findings.append(
                Finding(
                    iteration=iteration,
                    seed_id=child.seed_id,
                    parent_id=parent.seed_id,
                    generation=child.generation,
                    gain=gain,
                    new_markers=tuple(sorted(new_markers)),
                )
            )
            _prune(corpus, max_corpus)

    return GuidedFuzzResult(
        iterations=iteration,
        new_behaviour_count=len(findings),
        corpus_size=len(corpus),
        unique_markers=len(tracker.seen),
        stop_reason=stop_reason,
        findings=findings,
        seeds=list(corpus),
    )


def save_corpus(directory: str | Path, seeds: list[Seed]) -> None:
    """Persist seeds as raw files plus a ``lineage.json`` manifest."""
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []
    for seed in seeds:
        file_name = f"{seed.seed_id}.bin"
        (path / file_name).write_bytes(seed.data)
        manifest.append(
            {
                "seed_id": seed.seed_id,
                "parent_id": seed.parent_id,
                "generation": seed.generation,
                "score": seed.score,
                "file": file_name,
            }
        )
    (path / _LINEAGE_MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def load_corpus(directory: str | Path) -> list[bytes]:
    """Load seed payloads from a persisted corpus directory (empty if absent)."""
    path = Path(directory)
    manifest_path = path / _LINEAGE_MANIFEST
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = []
        seeds: list[bytes] = []
        for entry in manifest:
            file_name = entry.get("file") if isinstance(entry, dict) else None
            if file_name and (path / file_name).is_file():
                seeds.append((path / file_name).read_bytes())
        if seeds:
            return seeds
    # Fall back to any raw .bin files present.
    return [item.read_bytes() for item in sorted(path.glob("*.bin"))] if path.is_dir() else []
