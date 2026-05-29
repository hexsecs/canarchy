# Design Spec: AFL-style mutators — `havoc` / `splice` / `interesting`

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy fuzz payload --strategy {havoc,splice,interesting}` |
| Primary area | fuzzing engine, CLI, MCP |
| Related specs | `docs/design/active-transmit-safety.md`, `docs/design/fuzz-signal.md` |

## Goal

Borrow AFL's well-tested mutator inventory and expose it through the existing
`canarchy.fuzzing` engine, significantly expanding the byte-level mutation space
beyond the original `bitflip` / `random` / `boundary` strategies (#310). No
external dependency — the deterministic operators AFL has refined since 2014 are
reimplemented as pure functions.

## User-Facing Motivation

`bitflip` walks single bits and `boundary` emits canonical patterns, but neither
reproduces the rich, stacked mutation that makes AFL effective: arithmetic
nudges, interesting-value injection, and structural block edits. `havoc` brings
that stacked mutation; `splice` recombines real captured frames; `interesting`
systematically seeds the boundary integers that trip off-by-one and signedness
bugs.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-AFL-01` | Ubiquitous | The system shall provide `havoc_payload`, `splice_payload`, and `interesting_values_payload` pure-function generators in `canarchy.fuzzing`. |
| `REQ-AFL-02` | State-driven | While generating, each generator shall be deterministic for a fixed seed (and inputs). |
| `REQ-AFL-03` | Event-driven | When `havoc_payload` is invoked, the system shall stack a random sequence of AFL havoc operators (bit/byte flips, 8/16/32-bit arithmetic `± [1, 35]`, interesting-value injection, random byte replacement, block deletion / insertion / overwrite) on a copy of the input. |
| `REQ-AFL-04` | Event-driven | When `splice_payload` is invoked, the system shall join a random prefix of one corpus seed with a random suffix of another. |
| `REQ-AFL-05` | Unwanted behaviour | If `splice_payload` is given an empty corpus, the system shall raise `ValueError`. |
| `REQ-AFL-06` | Event-driven | When `interesting_values_payload` is invoked, the system shall enumerate the AFL interesting 8/16/32-bit values at each byte / word / dword offset over a zero baseline, suppressing duplicates. |
| `REQ-AFL-07` | Ubiquitous | The generators shall clamp emitted payloads to 64 bytes (CAN FD maximum). |
| `REQ-AFL-08` | Optional feature | Where `canarchy fuzz payload --strategy {havoc,splice,interesting}` is invoked, the system shall apply the matching generator under the active-transmit safety controls. |
| `REQ-AFL-09` | Unwanted behaviour | If `--strategy splice` is used without `--corpus`, the system shall return `MISSING_INPUT`. |

## Command Surface

```text
canarchy fuzz payload <interface> --id <hex> \
    --strategy {bitflip,random,boundary,havoc,splice,interesting} \
    [--data <hex>] [--dlc <n>] [--corpus <capture>] \
    [--max <n>] [--seed <n>] [--rate <hz>] [--dry-run] [--ack-active]
```

* `havoc` uses `--data` (default 8 zero bytes) as the seed and `--max` as the
  variant count.
* `splice` reads `--corpus` (a candump capture); its frame payloads form the
  splice corpus. `--max` is the variant count.
* `interesting` enumerates over a `--dlc`-byte baseline; `--max` caps the count.

## Data Model

| Generator | Signature |
|-----------|-----------|
| `havoc_payload` | `(data: bytes, *, seed: int, count: int) -> Iterator[bytes]` |
| `splice_payload` | `(corpus: Sequence[bytes], *, seed: int, count: int) -> Iterator[bytes]` |
| `interesting_values_payload` | `(*, dlc: int) -> Iterator[bytes]` |

Interesting-value tables mirror AFL's `INTERESTING_8` / `_16` / `_32`
(the 16-bit set extends the 8-bit set; the 32-bit set extends the 16-bit set).
Arithmetic magnitude ceiling is `ARITH_MAX = 35`.

## Output Contracts

Identical to the other `fuzz payload` strategies: an `alert` plus one `frame`
event per emitted payload, each stamped with `run_id` and `dry_run`.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `MISSING_INPUT` | `--strategy splice` without `--corpus` | 1 |
| `INVALID_ARGUMENTS` | empty splice corpus, negative `--max`, or invalid `--dlc` | 1 |

## Deferred Decisions

* Big-endian interesting-value / arithmetic writes (currently little-endian only).
* Dictionary/token mutators and AFL's deterministic "two/four-walking-bits" stages.
* Splice corpus sources beyond a candump capture (e.g. a replay manifest).
