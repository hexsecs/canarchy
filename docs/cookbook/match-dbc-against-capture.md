# Match an unknown capture against opendbc

## Goal

Given a capture from an unknown vehicle, find the top DBC candidates
from the opendbc catalogue.

## Prerequisites

* CANarchy installed.
* The opendbc provider cache populated:

  ```bash
  canarchy dbc cache refresh --provider opendbc
  ```

* A capture file. The example uses `tests/fixtures/sample.candump`.

## Run

```bash
canarchy re match-dbc tests/fixtures/sample.candump \
  --provider opendbc \
  --limit 10 \
  --text
```

The output ranks DBC files by a frequency-weighted ID coverage score.
A high score means a large fraction of the capture's frames are
described by that DBC.

## Narrow by vehicle brand

If you already know the brand, use `re shortlist-dbc` to filter before
scoring:

```bash
canarchy re shortlist-dbc tests/fixtures/sample.candump \
  --make toyota \
  --provider opendbc \
  --limit 5 \
  --text
```

## Use the chosen ref directly

Once a candidate looks plausible, decode against it:

```bash
canarchy decode \
  --file tests/fixtures/sample.candump \
  --dbc opendbc:toyota_tnga_k_pt_generated \
  --json
```

## Where to go next

* [Discover and Use Provider-Backed DBC Files tutorial](../tutorials/dbc_provider_workflow.md)
* [Find counter signals](find-counter-signals.md)
