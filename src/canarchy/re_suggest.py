"""Heuristic signal-name suggestions for ranked RE candidates (#332).

`re suggest` builds on the `re signals` candidate inference: for each ranked
candidate it proposes one or more names from, in order of confidence:

* a reference DBC's signals on the same message id (range/length ranked),
* the bundled J1939 SPN catalog (bit-range overlap, conventions aligned),
* the J1939 PGN name (coarse, when no SPN overlaps), and
* a plain-English template derived from the candidate's change behaviour.

This module is pure and offline. The optional LLM enrichment lives in
``canarchy.llm_suggest`` and is layered on top by the CLI.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from canarchy.j1939_metadata import decodable_spns, spn_lookup

# Maximum suggestions retained per candidate.
_MAX_SUGGESTIONS = 5


@lru_cache(maxsize=1)
def _spn_index() -> dict[int, list[dict[str, Any]]]:
    """Map each PGN to its decodable SPNs, converted to a 0-based bit range.

    Bundled SPN metadata stores ``start`` / ``length`` in bytes (e.g. Engine
    Speed = start 3, length 2 -> bits 24..39), matching the little-endian bit
    numbering the candidate extractor uses.
    """
    index: dict[int, list[dict[str, Any]]] = {}
    for spn in decodable_spns():
        entry = spn_lookup(spn) or {}
        name = entry.get("name")
        try:
            pgn = int(entry["pgn"])
            start = int(entry["start"])
            length = int(entry["length"])
        except (KeyError, TypeError, ValueError):
            continue
        if not name:
            continue
        index.setdefault(pgn, []).append(
            {
                "spn": spn,
                "name": name,
                "start_bit": start * 8,
                "bit_length": length * 8,
                "units": entry.get("units"),
            }
        )
    return index


def _overlap_bits(a_start: int, a_len: int, b_start: int, b_len: int) -> int:
    return max(0, min(a_start + a_len, b_start + b_len) - max(a_start, b_start))


def _template_name(candidate: dict[str, Any]) -> str:
    change_rate = float(candidate.get("change_rate", 0.0) or 0.0)
    if change_rate < 0.05:
        descriptor = "static"
    elif change_rate < 0.4:
        descriptor = "slow_value"
    elif change_rate < 0.85:
        descriptor = "active_value"
    else:
        descriptor = "fast_or_counter"
    return f"{descriptor}_{candidate['arbitration_id']:X}_b{candidate['start_bit']}"


def _spn_suggestions(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    pgn = candidate.get("pgn")
    if pgn is None:
        return []
    start_bit = int(candidate["start_bit"])
    bit_length = int(candidate["bit_length"])
    suggestions: list[dict[str, Any]] = []
    for spn in _spn_index().get(int(pgn), []):
        overlap = _overlap_bits(start_bit, bit_length, spn["start_bit"], spn["bit_length"])
        if overlap <= 0:
            continue
        fraction = overlap / min(bit_length, spn["bit_length"])
        suggestions.append(
            {
                "name": spn["name"],
                "source": "spn",
                "confidence": round(0.7 + 0.25 * fraction, 3),
                "spn": spn["spn"],
                "units": spn["units"],
            }
        )
    return suggestions


def _dbc_suggestions(
    candidate: dict[str, Any], dbc_signals_by_id: dict[int, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    signals = dbc_signals_by_id.get(int(candidate["arbitration_id"]))
    if not signals:
        return []
    bit_length = int(candidate["bit_length"])
    observed_max = int(candidate.get("observed_max", 0) or 0)
    suggestions: list[dict[str, Any]] = []
    for signal in signals:
        length = int(signal["length"])
        length_match = (
            1.0 if length == bit_length else max(0.0, 1.0 - abs(length - bit_length) / 8.0)
        )
        fits = observed_max < (1 << length)
        suggestions.append(
            {
                "name": signal["name"],
                "source": "dbc",
                "confidence": round(0.5 + 0.35 * length_match + (0.05 if fits else 0.0), 3),
                "unit": signal.get("unit"),
                "length": length,
            }
        )
    suggestions.sort(key=lambda item: -item["confidence"])
    return suggestions


def suggest_for_candidate(
    candidate: dict[str, Any],
    dbc_signals_by_id: dict[int, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Return ``candidate`` augmented with ranked name ``suggestions``."""
    suggestions: list[dict[str, Any]] = []
    suggestions.extend(_spn_suggestions(candidate))
    if dbc_signals_by_id:
        suggestions.extend(_dbc_suggestions(candidate, dbc_signals_by_id))

    pgn = candidate.get("pgn")
    if pgn is not None and not any(item["source"] == "spn" for item in suggestions):
        label = candidate.get("pgn_label") or candidate.get("pgn_name")
        if label:
            suggestions.append(
                {
                    "name": f"{label} byte{int(candidate['start_bit']) // 8}",
                    "source": "pgn",
                    "confidence": 0.4,
                }
            )

    suggestions.append(
        {"name": _template_name(candidate), "source": "heuristic", "confidence": 0.2}
    )

    suggestions.sort(key=lambda item: -item["confidence"])
    suggestions = suggestions[:_MAX_SUGGESTIONS]
    top = suggestions[0]
    return {
        **candidate,
        "suggestions": suggestions,
        "suggested_name": top["name"],
        "suggested_source": top["source"],
    }


def suggest_names(
    candidates: list[dict[str, Any]],
    dbc_signals_by_id: dict[int, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    return [suggest_for_candidate(candidate, dbc_signals_by_id) for candidate in candidates]
