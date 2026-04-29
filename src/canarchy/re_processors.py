"""Built-in processor plugins for reverse-engineering heuristic analysis."""

from __future__ import annotations

from typing import Any

from canarchy.models import CanFrame
from canarchy.plugins import CANARCHY_API_VERSION, ProcessorResult
from canarchy.reverse_engineering import counter_candidates, entropy_candidates, signal_analysis


class CounterCandidateProcessor:
    """Processor plugin: counter field detection via monotonicity heuristics."""

    name = "counter-candidates"
    api_version = CANARCHY_API_VERSION

    def process(self, frames: list[CanFrame], **kwargs: Any) -> ProcessorResult:
        candidates = counter_candidates(frames)
        warns = []
        if not candidates:
            warns.append("No likely counters met the current heuristic threshold.")
        return ProcessorResult(
            candidates=candidates,
            metadata={
                "analysis": "counter_detection",
                "candidate_count": len(candidates),
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
        return ProcessorResult(
            candidates=analysis["candidates"],
            metadata={
                "analysis": "signal_inference",
                "candidate_count": analysis["candidate_count"],
                "analysis_by_id": analysis["analysis_by_id"],
                "low_sample_ids": analysis["low_sample_ids"],
                "implementation": "file-backed heuristic analysis",
            },
            warnings=warns,
        )
