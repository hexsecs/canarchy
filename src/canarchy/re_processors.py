"""Built-in processor plugins for reverse-engineering heuristic analysis."""

from __future__ import annotations

from typing import Any

from canarchy.models import CanFrame
from canarchy.plugins import CANARCHY_API_VERSION, ProcessorResult
from canarchy.reverse_engineering import (
    counter_candidates,
    entropy_candidates,
    j1939_transport_ids,
    signal_analysis,
)


class CounterCandidateProcessor:
    """Processor plugin: counter field detection via monotonicity heuristics."""

    name = "counter-candidates"
    api_version = CANARCHY_API_VERSION

    def process(self, frames: list[CanFrame], **kwargs: Any) -> ProcessorResult:
        candidates = counter_candidates(frames)
        excluded_transport = j1939_transport_ids(frames)
        warns = []
        if not candidates:
            warns.append("No likely counters met the current heuristic threshold.")
        if excluded_transport:
            warns.append(
                f"{len(excluded_transport)} J1939 transport-protocol id(s) were excluded "
                "from counter detection (TP sequence numbers are not application counters)."
            )
        return ProcessorResult(
            candidates=candidates,
            metadata={
                "analysis": "counter_detection",
                "candidate_count": len(candidates),
                "excluded_transport_ids": excluded_transport,
                "implementation": "file-backed heuristic analysis",
            },
            warnings=warns,
        )


class EntropyCandidateProcessor:
    """Processor plugin: byte-level Shannon entropy ranking."""

    name = "entropy-candidates"
    api_version = CANARCHY_API_VERSION

    def process(self, frames: list[CanFrame], **kwargs: Any) -> ProcessorResult:
        candidates = entropy_candidates(frames)
        warns = []
        if not candidates:
            warns.append("No arbitration IDs with payload bytes were found for entropy analysis.")
        return ProcessorResult(
            candidates=candidates,
            metadata={
                "analysis": "entropy_ranking",
                "candidate_count": len(candidates),
                "implementation": "file-backed heuristic analysis",
            },
            warnings=warns,
        )


class SignalAnalysisProcessor:
    """Processor plugin: bit-field signal inference via change-rate and span heuristics."""

    name = "signal-analysis"
    api_version = CANARCHY_API_VERSION

    def process(self, frames: list[CanFrame], **kwargs: Any) -> ProcessorResult:
        analysis = signal_analysis(frames)
        warns = []
        if analysis["candidate_count"] == 0:
            warns.append("No likely signal candidates met the current heuristic threshold.")
        if analysis["excluded_transport_ids"]:
            warns.append(
                f"{len(analysis['excluded_transport_ids'])} J1939 transport-protocol id(s) "
                "were excluded from signal inference (TP framing is not an application signal)."
            )
        return ProcessorResult(
            candidates=analysis["candidates"],
            metadata={
                "analysis": "signal_inference",
                "candidate_count": analysis["candidate_count"],
                "analysis_by_id": analysis["analysis_by_id"],
                "low_sample_ids": analysis["low_sample_ids"],
                "excluded_transport_ids": analysis["excluded_transport_ids"],
                "implementation": "file-backed heuristic analysis",
            },
            warnings=warns,
        )
