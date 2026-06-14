# Design Spec: `re suggest` — Signal-Name Suggestions

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy re suggest` |
| Primary area | Analysis, CLI |
| Related specs | `docs/design/reverse-engineering-helpers.md`, `docs/design/active-transmit-safety.md` |

## Goal

After `re signals` ranks changing bit-fields as signal candidates, an analyst
still has to name them. `re suggest` proposes names for those candidates using
offline heuristics by default, with an optional, off-by-default external-LLM
enrichment. It turns "here are 30 candidate fields" into "here are 30 candidate
fields with proposed names and where each name came from".

## User-Facing Motivation

Naming is the slow, manual step of reverse engineering. Cross-referencing a
known DBC, the J1939 SPN/PGN catalog, and the candidate's value behaviour
automates the obvious cases and gives the analyst a ranked starting point for
the rest — without sending anything off the machine unless they explicitly opt in.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-SUG-01` | Ubiquitous | The system shall provide `re suggest <file>` that ranks signal candidates (reusing `re signals`) and attaches one or more name suggestions to each, fully offline. |
| `REQ-SUG-02` | Ubiquitous | Each suggestion shall carry a `source` (`dbc` / `spn` / `pgn` / `heuristic` / `llm`) and a `confidence`; the highest-confidence suggestion shall be reported as `suggested_name` / `suggested_source`. |
| `REQ-SUG-03` | Optional feature | Where `--reference-dbc <ref>` is supplied, the system shall cross-reference the candidate's message id against that database's signals and rank them by bit-length match and observed-range plausibility. |
| `REQ-SUG-04` | Ubiquitous | For J1939 candidates, the system shall name fields by bit-range overlap with the bundled decodable SPN catalog, falling back to the PGN name when no SPN overlaps. |
| `REQ-SUG-05` | Optional feature | Where `--llm <provider>` is specified, the system shall enrich names via an external LLM, but only after explicit confirmation, and shall record an `external_enrichment` note plus an `EXTERNAL_SERVICE_CALLED` warning in the envelope. |
| `REQ-SUG-06` | Unwanted behaviour | If `--llm` enrichment is not confirmed (no `--yes`, no `CANARCHY_LLM_NONINTERACTIVE=1`, and a non-`YES` reply), the system shall return `LLM_CONFIRMATION_DECLINED` and exit code 1, having sent nothing. |
| `REQ-SUG-07` | Unwanted behaviour | If the `--llm` provider is unknown or unavailable, the system shall return `LLM_PROVIDER_UNSUPPORTED` (exit 1) or `LLM_PROVIDER_UNAVAILABLE` (exit 2). |
| `REQ-SUG-08` | Ubiquitous | Only candidate metadata (arbitration ids, bit ranges, observed value ranges, change rate, and heuristic names) shall be sent to an LLM provider — never raw payload bytes. |
| `REQ-SUG-09` | Ubiquitous | `re suggest` shall be exposed as the MCP tool `re_suggest` for the heuristic path only; the external `--llm` enrichment shall be CLI-only. |

## Command Surface

```text
canarchy re suggest (<file> | --file <file>) [--reference-dbc <ref>] [--limit <n>]
    [--llm <provider> [--llm-model <model>] [--yes]] [--json|--jsonl|--text]
```

## Suggestion Sources And Ranking

| Source | Basis | Confidence |
|--------|-------|------------|
| `llm` | External provider proposal (opt-in) | 0.98 |
| `spn` | Bit-range overlap with a bundled decodable SPN | 0.70–0.95 (overlap fraction) |
| `dbc` | Signal on the candidate's message id, ranked by length/range fit | 0.50–0.90 |
| `pgn` | PGN name (coarse, when no SPN overlaps) | 0.40 |
| `heuristic` | Plain-English template from change behaviour | 0.20 |

SPN `start`/`length` are byte-based in the bundled catalog and converted to a
0-based bit range (`start*8`, `length*8`), which matches the little-endian bit
numbering the candidate extractor uses, so overlap is well defined.

## Output Contracts

`--json` returns the envelope with `candidates`, each carrying `suggestions`,
`suggested_name`, and `suggested_source`; `--jsonl` streams the same; `--text`
renders a per-candidate suggestion table. When `--llm` is used, `data` also
carries `external_enrichment` and the warnings list includes
`EXTERNAL_SERVICE_CALLED`.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `LLM_CONFIRMATION_DECLINED` | `--llm` not confirmed | 1 |
| `LLM_PROVIDER_UNSUPPORTED` | unknown `--llm` provider | 1 |
| `LLM_PROVIDER_UNAVAILABLE` | provider configured but missing credentials | 2 |
| `LLM_REQUEST_FAILED` | the external request failed | 2 |
| `DBC_LOAD_FAILED` | `--reference-dbc` could not be parsed | 3 |

## Privacy And Boundaries

In scope: an offline heuristic naming engine and a confirmed, metadata-only LLM
enrichment. Out of scope (v1): training/embedding-based matching, writing names
back into a DBC, and any LLM use without explicit per-invocation confirmation.

## Deferred Decisions

* Additional LLM providers beyond `anthropic`.
* Emitting a draft DBC from accepted suggestions.
