# Find counter signals in a capture

## Goal

Identify likely counter fields inside a capture — small monotonically
incrementing fields that often live in the upper or lower nibble of a
byte.

## Prerequisites

* CANarchy installed.
* A capture with at least a few hundred frames per ID. The examples use
  the in-tree fixture `tests/fixtures/re_counter_nibble.candump`.

## Run

```bash
canarchy re counters tests/fixtures/re_counter_nibble.candump --text
```

The text output lists candidate counters with their ID, byte position,
bit width, and stability score. JSON / JSONL output includes the same
fields machine-readably:

```bash
canarchy re counters tests/fixtures/re_counter_nibble.candump --json
```

## What "counter" means here

* The candidate field changes on most frames of the same ID.
* The change is usually +1, modulo the field width.
* Periodic rollover (for example a 4-bit counter wrapping from `0xF` to
  `0x0`) is recognised.

## Validate with `re entropy`

Counters typically have high entropy. Cross-check with:

```bash
canarchy re entropy tests/fixtures/re_counter_nibble.candump --json
```

The combination is a good first pass before you start drafting signal
definitions.

## Where to go next

* [Match an unknown capture against opendbc](match-dbc-against-capture.md)
* [Command Spec — re](../command_spec.md)
