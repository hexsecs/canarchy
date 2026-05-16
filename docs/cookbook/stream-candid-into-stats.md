# Stream the CANdid dataset into stats

## Goal

Pipe a remote CANdid replay stream directly into the local analysis
commands, with no temporary file on disk.

## Prerequisites

* CANarchy installed and network access to the CANdid dataset.
* The CANdid catalogue is built in; no provider cache refresh is
  required.

## Quick preflight

Resolve the replay metadata without opening the stream:

```bash
canarchy datasets replay catalog:candid --dry-run --json
```

List the replayable files in the dataset:

```bash
canarchy datasets replay catalog:candid --list-files --json
```

## Bounded replay piped into stats

```bash
canarchy datasets replay catalog:candid --rate 1000 --max-frames 1000 \
  | canarchy stats --file - --json
```

`stats --file -` reads candump text from stdin. Combine with
`--max-frames` to bound the work upfront.

## Bounded replay piped into capture-info

```bash
canarchy datasets replay catalog:candid --rate 1000 --max-frames 1000 \
  | canarchy capture-info --file - --json
```

## Select a specific file in the dataset

```bash
canarchy datasets replay catalog:candid \
  --file 2_steering_CAN.log \
  --rate 100 \
  --max-frames 200 \
  --format jsonl
```

## Where to go next

* [Stream CAN Data from CANdid tutorial](../tutorials/stream_candid_dataset.md)
* [Command Spec — datasets](../command_spec.md)
