"""Response-fingerprint feedback engine for guided fuzzing (#350).

When the fuzz target is an ECU across a bus there is no instrumentation
coverage, so novelty is inferred from the target's *observed responses*. A
:class:`ResponseObservation` (the response frames, elapsed time, and whether the
target went silent) is reduced to a :class:`Fingerprint` — a set of
category-prefixed behaviour markers — and a :class:`FeedbackTracker` scores each
fingerprint by how many previously-unseen markers it contributes.

Marker categories:

* ``nrc:<svc>:<code>`` — a UDS negative response (``0x7F``)
* ``pos:<svc>``        — a UDS positive response service id
* ``dm1:<spn>:<fmi>``  — an active DTC in a DM1 broadcast
* ``timing:<bucket>``  — response latency on a fixed millisecond ladder
* ``silence``          — no response within the observation window

This module is pure: it derives fingerprints and scores from observations and
opens no transport.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from canarchy.j1939 import dm1_messages
from canarchy.models import CanFrame
from canarchy.uds import reassemble_uds_pdus

# Selectable marker categories (the `--signals` surface).
SIGNAL_CATEGORIES: tuple[str, ...] = ("nrc", "pos", "dm1", "timing", "silence")

# Default scoring weights: semantic findings outrank timing noise.
DEFAULT_WEIGHTS: dict[str, int] = {"nrc": 5, "dm1": 5, "silence": 3, "pos": 2, "timing": 1}

# Response-latency bucket ladder in milliseconds (upper bounds).
_TIMING_LADDER_MS: tuple[float, ...] = (1.0, 5.0, 20.0, 50.0, 100.0, 250.0, 1000.0)


@dataclass(slots=True, frozen=True)
class ResponseObservation:
    """What the target did in response to one fuzzed input."""

    frames: tuple[CanFrame, ...] = ()
    elapsed: float = 0.0
    silent: bool = False


@dataclass(slots=True, frozen=True)
class Fingerprint:
    markers: frozenset[str]

    def is_empty(self) -> bool:
        return not self.markers


def _timing_bucket(elapsed_seconds: float) -> int:
    elapsed_ms = max(0.0, elapsed_seconds) * 1000.0
    for index, upper in enumerate(_TIMING_LADDER_MS):
        if elapsed_ms <= upper:
            return index
    return len(_TIMING_LADDER_MS)


def _category(marker: str) -> str:
    return marker.split(":", 1)[0]


def fingerprint_response(
    observation: ResponseObservation,
    *,
    signals: tuple[str, ...] = SIGNAL_CATEGORIES,
) -> Fingerprint:
    """Reduce an observation to its behaviour markers, limited to ``signals``."""
    enabled = set(signals)
    markers: set[str] = set()

    if observation.silent:
        if "silence" in enabled:
            markers.add("silence")
        if "timing" in enabled:
            # A silent window is its own timing class, distinct from a fast reply.
            markers.add(f"timing:{len(_TIMING_LADDER_MS) + 1}")
        return Fingerprint(frozenset(markers))

    if "timing" in enabled:
        markers.add(f"timing:{_timing_bucket(observation.elapsed)}")

    frames = list(observation.frames)
    if enabled & {"nrc", "pos"}:
        for pdu in reassemble_uds_pdus(frames):
            payload = pdu.payload
            if not payload:
                continue
            if payload[:1] == b"\x7f" and len(payload) >= 3:
                if "nrc" in enabled:
                    markers.add(f"nrc:{payload[1]:02x}:{payload[2]:02x}")
            elif payload[0] >= 0x40:
                if "pos" in enabled:
                    markers.add(f"pos:{payload[0]:02x}")

    if "dm1" in enabled:
        for message in dm1_messages(frames):
            for dtc in message.get("dtcs", []):  # type: ignore[union-attr]
                spn = int(dtc.get("spn", 0))
                fmi = int(dtc.get("fmi", 0))
                if spn > 0 and fmi not in (0, 31):
                    markers.add(f"dm1:{spn}:{fmi}")

    return Fingerprint(frozenset(markers))


@dataclass(slots=True)
class FeedbackTracker:
    """Tracks the behaviour markers seen so far and scores new fingerprints."""

    weights: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    seen: set[str] = field(default_factory=set)

    def gain(self, fingerprint: Fingerprint) -> tuple[int, frozenset[str]]:
        """Return the weighted novelty score and the set of new markers."""
        new = frozenset(marker for marker in fingerprint.markers if marker not in self.seen)
        score = sum(self.weights.get(_category(marker), 1) for marker in new)
        return score, new

    def observe(self, fingerprint: Fingerprint) -> None:
        self.seen |= fingerprint.markers

    def score_and_observe(self, fingerprint: Fingerprint) -> tuple[int, frozenset[str]]:
        score, new = self.gain(fingerprint)
        self.observe(fingerprint)
        return score, new
