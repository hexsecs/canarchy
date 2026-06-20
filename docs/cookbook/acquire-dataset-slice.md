# Acquire a bounded dataset slice for offline analysis

## Goal

Pull a small, fast slice of a public dataset to disk (or straight into
analysis) without waiting for a real-time replay of the whole capture.

## Why this recipe exists

Two footguns trip up first-time users and agents:

* **`datasets fetch` does not download frames** — it records a provenance
  JSON only. `datasets replay` is what actually retrieves the data.
* **`datasets replay` is real-time by default** (`--rate 1.0`), so streaming
  N frames takes the original capture's wall-clock duration unless you raise
  the rate.

## Steps

1. **Discover** a dataset and **inspect** its manifest (no data transfer):

   ```bash
   canarchy datasets search candid --json
   canarchy datasets inspect catalog:candid --json
   ```

2. **List the replayable files** in the dataset:

   ```bash
   canarchy datasets replay catalog:candid --list-files --json
   ```

3. **Acquire a bounded, fast slice.** Crank `--rate` and cap with
   `--max-frames` (or `--seconds`) so the run finishes promptly:

   ```bash
   # To a file
   canarchy datasets replay catalog:candid --file 2_driving_CAN.log \
     --rate 1000 --max-frames 10000 > slice.candump

   # Or piped straight into analysis (no temp file)
   canarchy datasets replay catalog:candid --rate 1000 --max-frames 10000 \
     | canarchy stats --file - --json
   ```

## Then bound the analysis too

Per-frame decoders process the whole file before printing, so check the size
first and pass the suggested bounds rather than decoding blind:

```bash
canarchy capture-info --file slice.candump --json
# → frame_count, duration_seconds, suggested_max_frames, suggested_seconds

canarchy j1939 faults --file slice.candump --max-frames 10000 --json
```

See [Working with large captures](../troubleshooting.md#working-with-large-captures)
for the full rationale and the automatic large-file cap.

## Related

* [Stream the CANdid dataset into stats](stream-candid-into-stats.md)
* [Troubleshooting: Acquiring dataset data](../troubleshooting.md#acquiring-dataset-data)
