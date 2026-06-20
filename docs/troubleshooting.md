# Troubleshooting

CANarchy emits structured errors with a stable `code`, a human-readable
`message`, and an actionable `hint`. This page catalogues the codes you
are most likely to see, along with the typical cause and a copy-pasteable
recovery path.

Every code below also appears in the canonical envelope under
`errors[]`. The exact format is described in the
[Event Schema](event-schema.md).

If you hit a code that is not listed here, please open a
[bug report](https://github.com/hexsecs/canarchy/issues/new/choose).

---

## Common pitfalls

A few situations cause the majority of structured errors. Check these
first.

* **No live CAN interface available.** Switch to the deterministic
  scaffold backend for offline work:

  ```bash
  export CANARCHY_TRANSPORT_BACKEND=scaffold
  canarchy capture can0 --json
  ```

* **Capture file is empty or malformed.** Confirm the file with
  `capture-info`:

  ```bash
  canarchy capture-info --file path/to/capture.candump --json
  ```

* **Large captures need bounds.** File-backed J1939 analysis caps at
  500,000 frames on captures larger than 50 MB and emits a warning.
  Override with `--max-frames` or `--seconds` for full-file analysis.
  See [Working with large captures](#working-with-large-captures) below.

* **`datasets replay` is real-time by default.** It paces output at
  `--rate 1.0` (wall-clock = capture time), so streaming N frames takes
  the original capture's duration. To acquire data quickly, raise the
  rate and bound the run: `--rate 1000 --max-frames 10000`.

* **`datasets fetch` does not download data.** It records a provenance
  JSON only. Use `datasets replay` to actually retrieve frames. See
  [Acquiring dataset data](#acquiring-dataset-data) below.

* **Stdin and `--file` cannot both be specified.** Use one or the other:

  ```bash
  canarchy stats --file - < capture.candump
  ```

---

## Working with large captures

Per-frame decoders (`j1939 faults`, `j1939 dm1`, `decode`) process the whole
file before printing, so a large capture can look like it has hung. Bound the
work explicitly instead of waiting.

1. **Inspect first — never decode blind.** `capture-info` reads only the file's
   head and tail, so it returns instantly even on multi-GB captures and tells
   you how big the job is. It also suggests bounds:

   ```bash
   canarchy capture-info --file big.candump --json
   # → frame_count, duration_seconds, suggested_max_frames, suggested_seconds
   ```

2. **Run bounded.** Pass `--max-frames` (first N frames) or `--seconds` (first
   T seconds from the capture start). Start from the `suggested_*` values:

   ```bash
   canarchy j1939 faults --file big.candump --max-frames 10000 --json
   canarchy j1939 dm1    --file big.candump --seconds 30 --json
   ```

3. **Auto-cap safety net (some commands).** `j1939 dm1`, `j1939 faults`,
   `j1939 summary`, `j1939 inventory`, `j1939 compare`, and `j1939 map`
   automatically cap at 500,000 frames on captures larger than 50 MB and add a
   `truncated` warning. Other file-backed commands — `j1939 decode`,
   `j1939 pgn`, `j1939 spn`, `j1939 tp sessions`, `stats`, `filter` — are **not**
   auto-capped, so on a large file bound them yourself with `--max-frames` /
   `--seconds`. Either way, passing your own `--max-frames`/`--seconds` overrides
   the cap.

`--offset N` skips the first N frames, which—combined with `--max-frames`—lets
you window through a large capture in chunks.

## Acquiring dataset data

The dataset verbs do different things; pick by intent:

| Verb | What it does |
|------|--------------|
| `datasets search` / `datasets inspect` | Discover datasets and inspect a manifest — no data transfer. |
| `datasets fetch <ref>` | Record a **provenance JSON only** (source URL, cache path). It does **not** download frames. |
| `datasets replay <ref>` | **Retrieve the data** — stream frames from the resolved manifest to stdout (or send to an interface). |

`datasets replay` defaults to `--rate 1.0` (real-time pacing), so acquiring a
fixed number of frames quickly means cranking the rate and bounding the run:

```bash
# Discover → inspect → list files → acquire a bounded, fast slice
canarchy datasets search candid --json
canarchy datasets inspect catalog:candid --json
canarchy datasets replay catalog:candid --list-files --json
canarchy datasets replay catalog:candid --file 2_driving_CAN.log \
  --rate 1000 --max-frames 10000 > slice.candump

# Or pipe straight into analysis without a temp file
canarchy datasets replay catalog:candid --rate 1000 --max-frames 10000 \
  | canarchy stats --file - --json
```

> `j1939 pgn`/`j1939 spn` no longer require a capture: with no `--file` they
> return the built-in reference definition (name, units, bit layout). Pass
> `--file` only when you want capture-derived values.

---

## DBC workflow errors

### `DBC_LOAD_FAILED`

Symptom — a DBC file was provided but the parser rejected it.

Causes — malformed DBC syntax, mixed line endings, or a non-DBC file
passed via `--dbc`.

Recovery —

```bash
canarchy dbc inspect path/to/file.dbc --json
```

Use the inspect output to spot the failing line. Re-export the DBC from
the source tool if the structure is corrupted.

### `DBC_NOT_FOUND`

Symptom — `--dbc <ref>` does not resolve to a local file or a cached
provider entry.

Recovery — confirm the path or refresh the provider cache:

```bash
canarchy dbc cache refresh --provider opendbc
```

### `DBC_DECODE_FAILED`

Symptom — a frame matched a DBC message but signal decode failed.

Causes — DLC mismatch, signal definitions outside the frame, or a wrong
byte order for the source.

Recovery — verify the message with `dbc inspect --message <name>` and
check the signal start bits and lengths against the captured DLC.

### `DBC_CACHE_MISS`

Symptom — a provider ref (for example `opendbc:toyota_tnga_k_pt_generated`)
was used but no cached entry exists.

Recovery — the hint is copy-pasteable:

```bash
canarchy dbc cache refresh --provider opendbc
```

Enable `auto_refresh = true` under `[dbc.providers.opendbc]` in
`~/.canarchy/config.toml` if you want this to happen on first use.

### `DBC_CACHE_STALE`

Symptom — the cached provider catalogue is older than the configured
freshness window.

Recovery — re-run `dbc cache refresh --provider <name>`.

### `DBC_MESSAGE_NOT_FOUND`

Symptom — `dbc inspect --message <name>` or `encode <name> …` referenced
a message that does not exist in the active DBC.

Recovery — list messages with `dbc inspect path/to/file.dbc --json` and
match the name exactly (case-sensitive).

### `DBC_PROVIDER_NOT_FOUND`

Symptom — `--provider <name>` referred to a provider that is not
registered.

Recovery — list providers:

```bash
canarchy dbc provider list --json
```

### `DBC_SIGNAL_INVALID`

Symptom — `encode --dbc <ref> <message> sig=val …` was given a value
outside the signal range or for a signal that does not exist.

Recovery — inspect the signal definition for the message:

```bash
canarchy dbc inspect path/to/file.dbc --message <name> --signals-only --json
```

Check the `min`, `max`, and choice set before retrying.

---

### `DBC_CONVERT_FAILED` / `DBC_CONVERT_UNSUPPORTED_FORMAT` / `DBC_CONVERT_WRITE_FAILED`

Symptom — `dbc convert` could not serialize the database.

Causes — the source database uses a feature the target format cannot
express (`DBC_CONVERT_FAILED`), `--to` named a format other than
`dbc` / `kcd` / `sym` (`DBC_CONVERT_UNSUPPORTED_FORMAT`), or the `--out`
path is not writable (`DBC_CONVERT_WRITE_FAILED`).

Recovery — pick a supported target format, choose a writable `--out`
directory, or omit `--out` to receive the serialized content in the
envelope.

### `DBC_GENERATE_C_DIR_MISSING` / `DBC_GENERATE_C_FAILED` / `DBC_GENERATE_C_WRITE_FAILED`

Symptom — `dbc generate-c` could not emit C source.

Causes — the `--out-dir` does not exist (`DBC_GENERATE_C_DIR_MISSING`),
cantools could not generate code for the database
(`DBC_GENERATE_C_FAILED`), or a generated file could not be written
(`DBC_GENERATE_C_WRITE_FAILED`).

Recovery — create the output directory first, confirm the database loads
with `dbc inspect`, and ensure the directory is writable.

## Dataset workflow errors

### `DATASET_NOT_FOUND`

Symptom — `datasets fetch`, `datasets inspect`, or `datasets replay` was
called with a ref that is not in the active provider catalogue.

Recovery —

```bash
canarchy datasets search --json
```

### `DATASET_PROVIDER_NOT_FOUND`

Symptom — `--provider <name>` does not match a registered dataset
provider.

Recovery — `canarchy datasets provider list --json`.

### `DATASET_REPLAY_UNAVAILABLE`

Symptom — the dataset entry is not replayable (for example it is a
curated index rather than a CAN log).

Recovery — switch to a replayable entry. Use `datasets search` to find
entries with `is_replayable: true` and `default_replay_file` set.

### `DATASET_INDEX_NOT_REPLAYABLE`

Symptom — the ref is an index entry (`is_index: true`). Index entries
point at external sources and have no inline replay stream.

Recovery — follow the linked source pages from the inspect output:

```bash
canarchy datasets inspect <ref> --json
```

### `DATASET_REPLAY_FETCH_FAILED`

Symptom — the remote replay stream could not be opened.

Causes — network outage, transient HTTP failure, or the upstream URL
moved.

Recovery — retry the command, or run with `--dry-run` first to confirm
the resolved URL before opening the stream.

### `DATASET_REPLAY_FILE_NOT_FOUND`

Symptom — `--file <id-or-name>` did not match an entry in the dataset
replay manifest.

Recovery —

```bash
canarchy datasets replay <ref> --list-files --json
```

---

### `SOURCE_NOT_FOUND` / `MALFORMED_SOURCE`

Symptom — a dataset or replay source could not be read.

Causes — the referenced source file does not exist (`SOURCE_NOT_FOUND`),
or a `comma-rlog` source string could not be parsed
(`MALFORMED_SOURCE`).

Recovery — confirm the path or ref, and check the source syntax against
`datasets replay --help`.

### `COMMA_RLOG_SUPPORT_UNAVAILABLE`

Symptom — a `comma-rlog` dataset was requested but optional support is
not installed.

Recovery — install openpilot's LogReader support
(`uv pip install git+https://github.com/commaai/openpilot.git` on
Python 3.12.x); see the dataset cookbook recipes.

### `COMMA_SEGMENTS_MANIFEST_UNAVAILABLE` / `COMMA_SEGMENTS_MANIFEST_EMPTY` / `COMMA_SEGMENTS_MANIFEST_MALFORMED` / `COMMA_SEGMENTS_PLATFORM_NOT_FOUND` / `COMMA_SEGMENTS_URL_UNAVAILABLE` / `COMMA_SEGMENTS_LFS_POINTER_MALFORMED`

Symptom — the commaCarSegments dynamic manifest could not be resolved.

Causes — the HuggingFace manifest could not be fetched, was empty or
malformed, the requested `--platform` was not in the manifest, a segment
URL was unavailable, or a Git-LFS pointer could not be parsed.

Recovery — retry (network), pass a valid `--platform` from
`datasets replay <ref> --list-files`, and bound listings with `--limit`.

## Frame and argument validation errors

### `INVALID_ARGUMENTS`

Symptom — the parser accepted the command but the values failed a deeper
validation step.

Recovery — re-read the message and hint; they name the failing argument
and constraint.

### `INVALID_MAX_FRAMES`

Symptom — `--max-frames` value was zero, negative, or non-numeric.

Recovery — pass a positive integer such as `--max-frames 1000`.

### `INVALID_ANALYSIS_SECONDS`

Symptom — `--seconds` value was zero, negative, or non-numeric.

Recovery — pass a positive float such as `--seconds 60.0`.

### `INVALID_MAX_SECONDS`

Symptom — `--max-seconds` value was zero, negative, or non-numeric.
Used by `datasets replay`.

Recovery — pass a positive float such as `--max-seconds 10.0`.

### `ANALYSIS_WINDOW_REQUIRES_FILE`

Symptom — `--max-frames` or `--seconds` was used together with `--stdin`.
These bounds only apply when reading from a file.

Recovery — either drop the bound, or write the stream to a temporary
file first:

```bash
your-producer | canarchy filter --file - 'id==0x123'
```

### `INVALID_FRAME_ID`

Symptom — a frame identifier passed to `send`, `generate`, or `filter`
was not a valid hex value or fell outside the 11-bit or 29-bit range.

Recovery — use hex form, prefixed or unprefixed (`0x123` or `123`),
within the valid range for the frame type.

### `INVALID_FRAME_DATA`

Symptom — the payload could not be parsed as hex bytes, or its length
exceeded the allowed DLC.

Recovery — pass an even number of hex characters with no separators,
for example `11223344`.

### `INVALID_DLC` / `INVALID_COUNT` / `INVALID_GAP` / `INVALID_RATE`

Symptom — one of the `generate` flags was given a non-numeric value or
fell outside the allowed range.

Recovery — pass a positive integer (`--count`, `--dlc`, `--gap`) or
positive float (`--rate`).

### `INVALID_PGN` / `INVALID_SPN` / `INVALID_SOURCE_ADDRESS`

Symptom — a J1939 selector was outside the valid range.

Recovery — PGNs are 18-bit integers, SPNs are positive integers, and
J1939 source addresses are 0–253 (0xFE and 0xFF are reserved).

### `INVALID_CHUNK_SIZE`

Symptom — `datasets stream --chunk-size` was zero, negative, or
non-numeric.

Recovery — pass a positive integer such as `--chunk-size 1000`.

### `INVALID_SIGNAL_ASSIGNMENT`

Symptom — `encode --dbc <ref> <message> sig=val …` could not parse a
`key=value` argument.

Recovery — confirm there are no shell-splitting issues and that the
value matches the signal's declared type.

---

### `MISSING_MESSAGE`

Symptom — `send --dbc` was invoked without `--message`.

Recovery — pass the DBC message name, e.g. `--message EngineStatus1`.

### `INTERFACE_REQUIRED`

Symptom — a command needs a CAN interface but none was given and no
default is configured.

Recovery — pass the interface argument, or set
`[transport].default_interface` / `CANARCHY_DEFAULT_INTERFACE`.

### `INVALID_FRAME`

Symptom — a frame could not be constructed from the supplied id/data.

Recovery — check the hex id width and payload length against the frame
format; see `send --help`.

### `CONFLICTING_FILE_ARGUMENTS`

Symptom — a capture path was supplied both positionally and via `--file`
with different values (`re *` commands and `j1939 compare`).

Recovery — pass the capture path once, in either form.

### `INVALID_LIMIT` / `INVALID_ANALYSIS_OFFSET`

Symptom — a `--limit` was non-positive, or an analysis `--offset` was
negative.

Recovery — pass a positive `--limit` and a non-negative `--offset`.

### `J1939_COMPARE_REQUIRES_MULTIPLE_FILES`

Symptom — `j1939 compare` was given fewer than two captures.

Recovery — pass two or more capture files (positionally or via repeated
`--file`).

### `J1939_SPN_UNSUPPORTED`

Symptom — `j1939 spn` was asked for an SPN with no built-in decoder and
no matching DBC signal.

Recovery — supply a `--dbc` that defines the SPN, or add it via the SPN
override file (`$CANARCHY_J1939_SPN_OVERRIDES`).

### `INVALID_FUZZ_RANGE` / `INVALID_FUZZ_SIGNAL` / `INVALID_FUZZ_SPN`

Symptom — a fuzz command received a malformed arbitration-id range,
DBC signal selection, or SPN selection.

Recovery — check the range/signal/SPN arguments against the relevant
`fuzz ... --help`.

### `ACTIVE_TRANSMIT_INVALID_RUN_ID`

Symptom — an explicit `--run-id` was not a valid UUID.

Recovery — omit `--run-id` (a UUID is generated) or pass a valid UUID.

## Capture, stdin, and input errors

### `CAPTURE_EMPTY`

Symptom — the capture file parsed cleanly but contained no valid
frames.

Recovery — confirm the source produced output, and re-check the file
suffix and format. Stdin sources may need `--file -` rather than
`--stdin` for candump text.

### `CAPTURE_FILE_REQUIRED`

Symptom — a file-only command was called without `--file`.

Recovery — pass a path or `-` for stdin candump input.

### `MISSING_INPUT`

Symptom — a command that requires either a file or stdin received
neither.

Recovery — pass `--file <path>` or pipe candump text into the command
with `--file -`.

### `STDIN_AND_FILE_SPECIFIED`

Symptom — both `--file` and `--stdin` were given.

Recovery — choose one input source.

### `NO_STREAM_EVENTS` / `INVALID_STREAM_EVENT`

Symptom — `filter --stdin`, `decode --stdin`, or `j1939 decode --stdin`
received zero events, or an event that did not match the FrameEvent
schema.

Recovery — verify the upstream stream emits one JSON object per line
that conforms to the [Event Schema](event-schema.md).

---

## Reverse-engineering errors

### `RE_REFERENCE_REQUIRED`

Symptom — `re correlate` was called without `--reference`.

Recovery — supply a JSON or JSONL file containing a numeric series.

### `INVALID_REFERENCE_FILE`

Symptom — `--reference <path>` exists but failed to parse.

Recovery — the file must be a JSON array, a JSON object with `name`
plus `samples`, or JSONL with one numeric sample per line. NaN entries
must be omitted, not encoded as the string `"NaN"`.

### `INSUFFICIENT_OVERLAP`

Symptom — the capture and the reference series do not share enough
timestamp overlap to compute correlation.

Recovery — re-capture or re-export the reference so both cover the same
time window.

---

### `CORPUS_NO_FILES`

Symptom — `re corpus` was invoked without any capture files.

Recovery — pass capture paths positionally, via repeated `--file`, or
expand them with `--corpus-glob '<pattern>'`.

## Session and skill errors

### `SESSION_NOT_FOUND`

Symptom — `session load <name>` referred to a session that does not
exist.

Recovery — `canarchy session show --json` to list known sessions.

### `INVALID_SESSION_NAME`

Symptom — the session name contained reserved characters or was empty.

Recovery — use letters, digits, dashes, and underscores.

### `SKILL_CACHE_MISS`

Symptom — a skill ref was requested but the cache is cold.

Recovery —

```bash
canarchy skills cache refresh
```

### `SKILL_FETCH_FAILED`

Symptom — the skill manifest could not be downloaded.

Recovery — retry, or inspect the provider list with
`canarchy skills provider list --json`.

### `SKILL_MANIFEST_INVALID`

Symptom — the downloaded manifest did not pass schema validation.

Recovery — file an issue against the upstream skills repository, then
retry once the manifest is fixed.

### `SKILL_NOT_FOUND` / `SKILL_PROVIDER_NOT_FOUND`

Symptom — the ref or provider name does not match a known entry.

Recovery — use `canarchy skills search` or
`canarchy skills provider list --json` to discover valid names.

---

## Export and format errors

### `EXPORT_SOURCE_UNSUPPORTED`

Symptom — `export <source> <destination>` was called with a source the
exporter does not handle.

Recovery — see `docs/command_spec.md` for the supported source list.

### `EXPORT_FORMAT_UNSUPPORTED` / `UNSUPPORTED_OUTPUT_FORMAT`

Symptom — the requested output format is not implemented for the chosen
command.

Recovery — choose one of `--json`, `--jsonl`, `--text`, or a
command-specific frame-line mode such as `--candump` where supported.

### `EXPORT_WRITE_FAILED`

Symptom — the destination path could not be opened for writing.

Recovery — confirm the parent directory exists and that the process can
write to it.

### `EXPORT_EVENTS_UNAVAILABLE`

Symptom — the export source produced no events.

Recovery — verify the upstream command produced output; an empty stdin
or zero-frame capture is the most common cause.

### `UNSUPPORTED_SOURCE_FORMAT`

Symptom — `datasets stream --source-format <name>` was given a format
that is not implemented.

Recovery — current options are documented under
`canarchy datasets stream --help`.

---

## Active-bus operations

### `ACTIVE_ACK_REQUIRED`

Symptom — an active command (`send`, `generate`, `gateway`, `uds scan`)
was started without `--ack-active` in a non-interactive context.

Recovery — re-run with `--ack-active`, after confirming the target.

### `ACTIVE_CONFIRMATION_DECLINED`

Symptom — the operator declined the interactive confirmation prompt.

Recovery — re-run when you are ready to confirm, or pass `--ack-active`
to skip the prompt explicitly.

### `ACTIVE_TRANSMIT`

Symptom — a transmission failed at the transport layer.

Recovery — confirm the interface is up (`ip link show can0` on Linux)
and that the configured backend supports transmission. The hint should
include the underlying transport error.

### `COMMAND_PLANNED`

Symptom — informational structured response from `--dry-run` on
`datasets replay` and similar planning modes.

Recovery — no action needed. The payload describes what the command
would have done.

---

### `ACTIVE_TRANSMIT_REQUIRES_ACK`

Symptom — an active-transmit MCP tool was called without
`ack_active=true`.

Recovery — re-call with `ack_active=true` (and `dry_run=true` unless an
operator has authorised live transmission). This is the MCP gate,
separate from the CLI `--ack-active` flag.

### `SEQUENCE_LOAD_ERROR` / `SEQUENCE_ENCODE_ERROR`

Symptom — `sequence replay` could not load or encode the sequence file.

Causes — the YAML/JSON sequence is missing/malformed
(`SEQUENCE_LOAD_ERROR`), or a step's signals failed DBC encoding
(`SEQUENCE_ENCODE_ERROR`).

Recovery — validate the sequence file structure and confirm each step's
message/signals against the referenced DBC.

## Plugin errors

### `PLUGIN_NOT_FOUND`

Symptom — a plugin name referenced in `~/.canarchy/config.toml` is not
registered.

Recovery — run `canarchy plugins list --json` to inspect discovered plugin names.

### `PLUGIN_DUPLICATE`

Symptom — two plugins registered under the same entry-point name.

Recovery — remove the duplicate distribution from the environment.

### `PLUGIN_INVALID` / `PLUGIN_INCOMPATIBLE`

Symptom — the plugin failed to load or did not implement the required
protocol.

Recovery — file an issue against the plugin distribution. CANarchy will
continue to load without the failing plugin.

---

### `PLUGIN_CONFIG_INVALID` / `PLUGIN_CONFIG_WRITE_FAILED`

Symptom — `plugins enable` / `plugins disable` could not read or persist
the plugin toggle.

Causes — the `[plugins]` section in `~/.canarchy/config.toml` is
malformed (`PLUGIN_CONFIG_INVALID`), or the config file is not writable
(`PLUGIN_CONFIG_WRITE_FAILED`).

Recovery — fix or remove the malformed `[plugins]` table, and ensure the
config file is writable.

## TUI errors

### `TUI_COMMAND_UNSUPPORTED`

Symptom — a command typed into the TUI input area is not exposed to the
TUI front end.

Recovery — drop back to the shell or run the command directly from the
CLI.

---

## Plot errors

### `PLOT_DEPENDENCY_MISSING`

Symptom — `plot` needs a plotting backend that is not installed.

Recovery — install the optional extra: `pip install canarchy[plot]`
(matplotlib for PNG/SVG, plotly for HTML).

### `PLOT_ERROR`

Symptom — plotting failed after dependencies were satisfied.

Recovery — confirm the `--signal` names exist in the `--dbc` (use
`dbc signals`), and that the output path is writable.

---

## Web dashboard errors

### `WEB_BIND_INVALID`

Symptom — `web serve --bind` is not in `<host>:<port>` form, or the port
is out of range.

Recovery — pass `--bind 127.0.0.1:8474` (port 0 selects an ephemeral
port).

### `WEB_BIND_FAILED`

Symptom — the dashboard could not bind the requested address/port.

Recovery — choose a free port with `--bind`, or stop the process holding
it.

### `WEB_READ_ONLY`

Symptom — a non-GET HTTP request was sent to the dashboard (returned as
HTTP 405, not a CLI exit).

Recovery — the dashboard is read-only by design; active-transmit
workflows are CLI-only and gated by the active-transmit safety model.

---

## MCP server errors

### `TOOL_EXECUTION_ERROR`

Symptom — an MCP tool call raised an unexpected error.

Recovery — the server isolates the failure and stays usable; check the
tool arguments or run the equivalent CLI command for full diagnostics.

### `NO_RESULT`

Symptom — an MCP tool returned no result object.

Recovery — usually transient; retry the call, or run the equivalent CLI
command to surface the underlying error.

---

## Reporting unknown codes

If you encounter a code that is not on this page, please open a
[bug report](https://github.com/hexsecs/canarchy/issues/new/choose).
Include the full structured envelope and the command you ran.
