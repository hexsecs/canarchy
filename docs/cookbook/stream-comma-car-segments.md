# Stream commaCarSegments CAN data

## Goal

List comma.ai commaCarSegments route segments for a vehicle platform, plan a
bounded replay, and stream CAN frames from a selected openpilot `rlog.zst`.

## Prerequisites

* Network access to the HuggingFace `commaai/commaCarSegments` dataset.
* Optional openpilot LogReader/cereal support installed for actual `comma-rlog`
  frame streaming (`uv pip install git+https://github.com/commaai/openpilot.git`;
  requires Python 3.12.x).
* A bounded plan (`--limit`, `--max-frames`, or `--max-seconds`) before
  working with large segment lists.

## List Tesla segments

Start with a platform filter and a small manifest limit:

```bash
canarchy datasets replay catalog:comma-car-segments \
  --platform TESLA_MODEL_3 \
  --list-files \
  --limit 20 \
  --json
```

The result contains stable file `id` values. Use one with `--file` in later
commands.

## Dry-run a selected segment

Dry-run resolves metadata without opening the rlog payload stream:

```bash
canarchy datasets replay catalog:comma-car-segments \
  --platform TESLA_MODEL_3 \
  --file 0 \
  --dry-run \
  --json
```

## Stream frames

Stream a bounded JSONL sample once optional parser support is available:

```bash
canarchy datasets replay catalog:comma-car-segments \
  --platform TESLA_MODEL_3 \
  --file 0 \
  --format jsonl \
  --max-frames 1000
```

Pipe directly into analysis commands when using candump output:

```bash
canarchy datasets replay catalog:comma-car-segments \
  --platform TESLA_MODEL_3 \
  --file 0 \
  --max-frames 1000 \
  | canarchy stats --file - --json
```

## Stream a local rlog

If you already downloaded an `rlog.zst`, stream it as a local dataset file:

```bash
canarchy datasets stream ./rlog.zst \
  --source-format comma-rlog \
  --format jsonl \
  --provider-ref catalog:comma-car-segments \
  --max-frames 1000
```

If optional openpilot parser support is missing, CANarchy returns
`COMMA_RLOG_SUPPORT_UNAVAILABLE`; list and dry-run workflows still work.

## Where to go next

* [Stream the CANdid dataset into stats](stream-candid-into-stats.md)
* [Match an unknown capture against opendbc](match-dbc-against-capture.md)
