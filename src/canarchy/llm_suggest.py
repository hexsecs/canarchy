"""Optional LLM enrichment for `re suggest` (#332).

This is an off-by-default, feature-flagged path: the operator must pass
``--llm <provider>`` and explicitly confirm before any candidate metadata leaves
the machine. Only non-sensitive candidate metadata (arbitration ids, bit ranges,
observed value ranges, and the offline heuristic suggestions) is sent — never raw
payload bytes.

The provider client is injectable so the heuristic-plus-merge logic is fully
testable without a network call; the bundled Anthropic client is exercised only
when a real API key is configured.
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

_DEFAULT_ANTHROPIC_MODEL = "claude-fable-5"
_ANTHROPIC_ENDPOINT = "https://api.anthropic.com/v1/messages"
# Above the strongest heuristic confidence (SPN overlap, 0.95): when an operator
# explicitly opts into LLM enrichment, its proposal headlines each candidate.
_LLM_CONFIDENCE = 0.98


class LlmError(Exception):
    """Raised when the LLM enrichment provider is unavailable or fails."""

    def __init__(self, code: str, message: str, hint: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


class LlmClient(Protocol):
    def suggest(self, items: list[dict[str, Any]]) -> dict[int, dict[str, str]]:
        """Map a candidate index to ``{"name", "rationale"}`` proposals."""
        ...


def _candidate_summary(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Non-sensitive per-candidate metadata sent to the provider (no payload bytes)."""
    summary: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        summary.append(
            {
                "index": index,
                "arbitration_id_hex": candidate.get(
                    "arbitration_id_hex", f"0x{candidate['arbitration_id']:X}"
                ),
                "start_bit": candidate.get("start_bit"),
                "bit_length": candidate.get("bit_length"),
                "observed_min": candidate.get("observed_min"),
                "observed_max": candidate.get("observed_max"),
                "change_rate": candidate.get("change_rate"),
                "pgn_name": candidate.get("pgn_name"),
                "heuristic_suggestions": [s.get("name") for s in candidate.get("suggestions", [])],
            }
        )
    return summary


class _AnthropicClient:
    def __init__(self, model: str | None) -> None:
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise LlmError(
                code="LLM_PROVIDER_UNAVAILABLE",
                message="The anthropic LLM provider requires an ANTHROPIC_API_KEY.",
                hint="Export ANTHROPIC_API_KEY, or run without --llm for offline heuristics.",
            )
        self.model = model or _DEFAULT_ANTHROPIC_MODEL

    def suggest(
        self, items: list[dict[str, Any]]
    ) -> dict[int, dict[str, str]]:  # pragma: no cover - network
        import requests

        prompt = (
            "You are naming reverse-engineered CAN signal candidates. For each item, "
            "propose a concise snake_case signal name and a one-line rationale. "
            "Reply with a JSON array of {index, name, rationale}.\n\n"
            f"{json.dumps(items)}"
        )
        try:
            response = requests.post(
                _ANTHROPIC_ENDPOINT,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30,
            )
            response.raise_for_status()
            text = response.json()["content"][0]["text"]
            proposals = json.loads(text)
            if not isinstance(proposals, list):
                raise ValueError("expected a JSON array of proposals")
            # Validate the shape here, inside the error boundary, so a malformed
            # but syntactically valid response becomes a structured LlmError
            # rather than a traceback in `re suggest --llm`.
            parsed: dict[int, dict[str, str]] = {}
            for item in proposals:
                if not isinstance(item, dict) or "index" not in item or "name" not in item:
                    continue
                parsed[int(item["index"])] = {
                    "name": str(item["name"]),
                    "rationale": str(item.get("rationale", "")),
                }
        except Exception as exc:
            raise LlmError(
                code="LLM_REQUEST_FAILED",
                message=f"The anthropic LLM request failed: {exc}.",
                hint="Check connectivity and the API key, or run without --llm.",
            ) from exc
        return parsed


def _build_client(provider: str, model: str | None) -> LlmClient:
    if provider.strip().lower() == "anthropic":
        return _AnthropicClient(model)
    raise LlmError(
        code="LLM_PROVIDER_UNSUPPORTED",
        message=f"Unsupported LLM provider {provider!r}.",
        hint="The only supported provider is 'anthropic'.",
    )


def enrich_with_llm(
    provider: str,
    candidates: list[dict[str, Any]],
    *,
    model: str | None = None,
    client: LlmClient | None = None,
) -> list[dict[str, Any]]:
    """Layer LLM-proposed names onto heuristic candidates as ``llm`` suggestions.

    Each candidate gains a ``source: "llm"`` suggestion (re-ranked to the top) when
    the provider returns a name for it. ``client`` is injectable for testing.
    """
    client = client or _build_client(provider, model)
    proposals = client.suggest(_candidate_summary(candidates))

    enriched: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        proposal = proposals.get(index)
        if not proposal:
            enriched.append(candidate)
            continue
        suggestions = list(candidate.get("suggestions", []))
        suggestions.insert(
            0,
            {
                "name": proposal["name"],
                "source": "llm",
                "confidence": _LLM_CONFIDENCE,
                "rationale": proposal.get("rationale", ""),
            },
        )
        suggestions.sort(key=lambda item: -item["confidence"])
        enriched.append(
            {
                **candidate,
                "suggestions": suggestions,
                "suggested_name": suggestions[0]["name"],
                "suggested_source": suggestions[0]["source"],
            }
        )
    return enriched
