# Design: Dataset Provider Workflow

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented (Phase 3) |
| Issue | #216, #220, #233, #235, #241, #242, #243, #245, #246, #259, #367, #513, #514 |
| Implementation | `src/canarchy/dataset_provider.py`, `dataset_cache.py`, `dataset_catalog.py`, `dataset_convert.py` |

---

## Motivation

Public CAN bus research datasets power demos, IDS experiments, J1939 analysis, reverse-engineering
workflows, and fixture generation. Without a provider-backed workflow, operators rely on ad hoc
download instructions with no provenance tracking, no consistent metadata, and no conversion tooling.

The dataset provider workflow mirrors the existing DBC and skills provider model so the extension
pattern is familiar and the codebase stays internally consistent.

---

## Command Surface

```
canarchy datasets provider list
canarchy datasets search [query] [--provider <name>] [--limit N]
canarchy datasets inspect <ref>
canarchy datasets fetch <ref>
canarchy datasets cache list
canarchy datasets cache refresh [--provider <name>]
canarchy datasets convert <file> --source-format hcrl-csv|candump|comma-rlog|decoded-signal-csv --format candump|jsonl [--output <path>]
canarchy datasets stream <file> --source-format hcrl-csv|candump|comma-rlog|decoded-signal-csv --format candump|jsonl [--chunk-size N] [--max-frames N] [--provider-ref <ref>] [--output <path>]
canarchy datasets replay <dataset-ref-or-url> [--file <id-or-name>] [--platform <name>] [--limit N] [--list-files] [--format candump|jsonl] [--rate N] [--max-frames N] [--max-seconds N] [--dry-run]
```

All commands follow the standard `--json`, `--jsonl`, `--text` output modes.

---

## Provider Protocol

```python
@runtime_checkable
class DatasetProvider(Protocol):
    name: str
    def search(self, query: str, limit: int = 20) -> list[DatasetDescriptor]: ...
    def inspect(self, name: str) -> DatasetDescriptor: ...
    def fetch(self, name: str) -> DatasetResolution: ...
    def refresh(self, name: str | None = None) -> list[DatasetDescriptor]: ...
```

---

## DatasetDescriptor

Captures all metadata required to evaluate, cite, and convert a dataset:

| Field | Type | Description |
|-------|------|-------------|
| `provider` | str | Provider name |
| `name` | str | Stable identifier (e.g., `road`, `syncan`) |
| `version` | str \| None | Dataset version or release |
| `source_url` | str | Canonical source / download page |
| `license` | str | License identifier |
| `protocol_family` | str | `can`, `can_fd`, `j1939`, `j1708` |
| `formats` | tuple[str] | Source file formats: `csv`, `msgpack`, `pcap` |
| `size_description` | str | Human-readable size: `3.5 GB`, `unknown` |
| `description` | str | Purpose, attack types, vehicle type |
| `access_notes` | str \| None | Registration, form, or account requirements |
| `conversion_targets` | tuple[str] | `candump`, `jsonl` |
| `metadata` | dict | Publisher, paper links, format notes |

---

## Registry

`DatasetProviderRegistry` follows the DBC/skills registry pattern: lazy singleton, `reset_registry()`
for tests, config-driven search order.

Ref resolution: `catalog:road` or bare `road`. A prefixed ref goes straight to the named provider.
A bare name is offered to each registered provider in resolution order, first match wins.

### Provider resolution order

The registry is built in the order `[datasets].search_order` specifies, so the configured order is
the resolution order (#514). The built-in default is `["catalog", "offline"]`: a bare ref prefers
the real dataset of a name over synthetic offline data, and synthetic data stays opt-in through the
`offline:` prefix.

`search_order` states a *preference*, not an allow-list. A registered provider that is enabled but
absent from the list is appended after the listed providers rather than excluded, so a partial list
such as `["offline"]` reorders resolution without making `offline`'s sibling unreachable. Excluding
a provider is a separate, explicit setting — `[datasets.providers.<name>].enabled = false` — which
always wins over listing it in `search_order`.

An unknown provider name is an error, not a no-op: a silently ignored `search_order` is the defect
this replaces. Building the registry is lazy, so the error surfaces on the first `datasets` command
as a structured `DATASET_PROVIDER_NOT_FOUND` result rather than a traceback.

```toml
[datasets]
search_order = ["offline", "catalog"]

[datasets.providers.offline]
enabled = false
```

The effective order is inspectable through `datasets provider list`: `search_order` in the payload,
an `order` index on each provider entry, and a `Search order:` line in text mode. `config show`
stays scoped to transport configuration (see `docs/design/config-show-command.md`,
`REQ-CONFIG-01`) and deliberately does not restate `[datasets]` settings.

### Provider Order Requirements

| ID | Type | Requirement |
|----|------|-------------|
| REQ-DATASET-ORDER-01 | Ubiquitous | The system shall register dataset providers in the order given by `[datasets].search_order`, so that a bare ref resolves against the first listed provider that has a dataset of that name. |
| REQ-DATASET-ORDER-02 | Ubiquitous | Where `[datasets].search_order` is absent, the system shall resolve bare refs against `catalog` before `offline`. |
| REQ-DATASET-ORDER-03 | Optional feature | Where a registered provider is enabled but absent from `[datasets].search_order`, the system shall append it after the listed providers rather than excluding it. |
| REQ-DATASET-ORDER-04 | State-driven | While a provider is configured with `enabled = false`, the system shall leave it unregistered even when `[datasets].search_order` names it. |
| REQ-DATASET-ORDER-05 | Unwanted behaviour | If `[datasets].search_order` names a provider that is not known, the system shall return a structured `DATASET_PROVIDER_NOT_FOUND` error naming the entry and the known providers, with exit code 1. |
| REQ-DATASET-ORDER-06 | Unwanted behaviour | If `[datasets].search_order` is not a list of provider names, the system shall return a structured `DATASET_SEARCH_ORDER_INVALID` error with exit code 1. |
| REQ-DATASET-ORDER-07 | Ubiquitous | The system shall report the effective provider resolution order in `datasets provider list` output as a `search_order` list and a per-provider `order` index. |

---

## Cache

```
~/.canarchy/cache/datasets/
  providers/
    catalog/
      manifest.json        ← dataset count + generated_at
      provenance/
        road.json          ← per-dataset provenance record
        syncan.json
```

`datasets fetch` saves a provenance JSON (source URL, license, timestamp) without downloading
the large dataset file. The operator downloads the data manually from `source_url`.

`datasets cache refresh` rebuilds the provider manifest.

Config section: `[datasets]` in `~/.canarchy/config.toml` (mirrors `[dbc]` and `[skills]`).

---

## Built-in Catalog Provider

`PublicDatasetProvider` (name: `catalog`) embeds metadata for public CAN research datasets and curated dataset indexes:

| Dataset | Protocol | License | Size |
|---------|----------|---------|------|
| `road` | CAN | CC BY 4.0 | ~3.5 GB |
| `comma-car-segments` | CAN | MIT | 100+ GB |
| `hcrl-car-hacking` | CAN | Research use | ~2.2 GB |
| `hcrl-j1939-attack` | J1939 | Research use | Unknown |
| `hcrl-can-fd` | CAN FD | Research use | Unknown |
| `hcrl-survival-ids` | CAN | Research use | Unknown |
| `hcrl-b-can` | CAN | Research use | Unknown |
| `hcrl-m-can` | CAN | Research use | Unknown |
| `hcrl-can-signal` | CAN | Research use | Unknown |
| `hcrl-x-canids` | CAN | Research use | Unknown |
| `hcrl-challenge-2020` | CAN | Research use | Unknown |
| `syncan` | CAN | Non-commercial research only (ETAS/Bosch); no redistribution | ~100 MB |
| `candid` | CAN | CC BY 4.0 | ~13.7 GB |
| `pivot-auto-datasets` | CAN | Mixed / varies | Catalog / varies |

No network access is required for `search`, `inspect`, or `provider list`.

### Catalog Requirements

| ID | Type | Requirement |
|----|------|-------------|
| REQ-DATASET-CATALOG-01 | Ubiquitous | The system shall expose built-in catalog entries through `datasets search` and `datasets inspect` without network access. |
| REQ-DATASET-CATALOG-02 | Ubiquitous | The system shall include source URL, license or access terms, protocol family, formats, size description, description, and metadata for each built-in catalog entry. |
| REQ-DATASET-CATALOG-03 | Optional feature | Where a catalog entry represents a curated external index instead of a directly downloadable dataset, the system shall mark the entry as an index in metadata and describe that linked sources have their own access terms and formats. |
| REQ-DATASET-CATALOG-04 | Ubiquitous | The system shall include stable machine fields for JSON dataset search and inspect results: `ref`, `is_replayable`, `is_index`, `default_replay_file`, `download_url_available`, and `source_type`. |
| REQ-DATASET-CATALOG-05 | Optional feature | Where a dataset entry is a curated index, the `datasets fetch` response shall include an `is_index` field and an `index_instructions` field with guidance to visit the index page and discover datasets, while normal datasets continue to use `download_instructions`. |

---

## Conversion

`datasets convert` is explicitly separated from fetch/cache. It converts a locally-present dataset
file into a CANarchy-native format.

### Currently supported

| Source format | Description | Output formats |
|--------------|-------------|----------------|
| `hcrl-csv` | HCRL Car-Hacking CSV: `Timestamp,ID,DLC,Data[,Label]` | `candump`, `jsonl` |
| `candump` | can-utils timestamped log lines such as `(0.000000) can0 123#AABB` | `candump`, `jsonl` |
| `comma-rlog` | openpilot/comma `rlog.zst` cereal logs parsed through optional LogReader support | `candump`, `jsonl` |
| `decoded-signal-csv` | Pre-decoded per-ID signal CSV (e.g. SynCAN `Label,Time,ID,Signal1_of_ID,...`): IDs mapped deterministically, normalized signals packed as big-endian uint16 | `candump`, `jsonl` |

### candump output

```
(0.000000) can0 316#0000000000000000
(0.001000) can0 18F#000000000060000
```

### JSONL output

Each line is a FrameEvent with `event_type`, `source`, `timestamp`, and `payload`. The `Label`
column (if present) is preserved in `payload.label`.

```json
{"event_type": "frame", "source": "hcrl-csv", "timestamp": 0.0, "payload": {"arbitration_id": 790, "data": "0000000000000000", "interface": null}}
```

---

## Streaming

`datasets stream` is the streaming-oriented companion to `datasets convert`. It parses supported
dataset files incrementally and writes each output record directly to stdout or `--output` without
building a full in-memory frame list.

### Requirements

| ID | Type | Requirement |
|----|------|-------------|
| REQ-DATASET-STREAM-01 | Ubiquitous | The system shall stream supported dataset files without loading all parsed frames into memory. |
| REQ-DATASET-STREAM-02 | Ubiquitous | The system shall support `candump` and `jsonl` stream output formats for supported dataset source formats. |
| REQ-DATASET-STREAM-03 | Optional feature | Where `--provider-ref` is specified, the system shall include the provider reference in JSONL dataset provenance metadata. |
| REQ-DATASET-STREAM-04 | Ubiquitous | The system shall include `frame_offset`, `chunk_index`, and `chunk_position` metadata on JSONL streamed frame events. |
| REQ-DATASET-STREAM-05 | Unwanted behaviour | If `--chunk-size` is less than 1, the system shall return a structured `INVALID_CHUNK_SIZE` error. |
| REQ-DATASET-STREAM-06 | Unwanted behaviour | If the source file is malformed, the system shall return a structured `MALFORMED_SOURCE` error instead of emitting partial success as a normal completion. |
| REQ-DATASET-STREAM-07 | Optional feature | Where `--max-frames` is specified, the system shall stop local dataset streaming after emitting at most the requested number of frames. |
| REQ-DATASET-STREAM-08 | Unwanted behaviour | If `--max-frames` is less than 1, the system shall return a structured `INVALID_MAX_FRAMES` error. |
| REQ-DATASET-STREAM-09 | Optional feature | Where `comma-rlog` is specified, the system shall stream CAN events from openpilot rlog sources when optional LogReader support is installed. |
| REQ-DATASET-STREAM-10 | Unwanted behaviour | If `comma-rlog` support is unavailable, the system shall return `COMMA_RLOG_SUPPORT_UNAVAILABLE`. |

### JSONL Stream Event

```json
{"event_type": "frame", "source": "hcrl-csv", "timestamp": 0.0, "payload": {"arbitration_id": 790, "data": "0000000000000000", "interface": null, "dataset": {"provider_ref": "catalog:hcrl-car-hacking", "frame_offset": 0, "chunk_index": 0, "chunk_position": 0}}}
```

### Notes

- `datasets stream` writes stream records directly unless `--json` is requested.
- `--chunk-size` controls JSONL provenance chunk metadata; it does not bound the number of emitted frames.
- `--max-frames` bounds emitted frame records for local file streaming in both candump and JSONL output modes.
- With `--json`, the command returns the standard result envelope with `frame_count`, `chunks`, `max_frames`, and stream configuration metadata.
- Active live-bus replay remains out of scope for this increment; dataset streams can be saved or piped into existing file/stdin-aware analysis commands.

### Remote Replay Requirements

| ID | Type | Requirement |
|----|------|-------------|
| REQ-DATASET-REPLAY-01 | Ubiquitous | The system shall accept a direct remote candump URL as a dataset replay source. |
| REQ-DATASET-REPLAY-02 | Optional feature | Where replay metadata is available for a dataset descriptor, the system shall accept a dataset ref such as `catalog:candid` as a replay source. |
| REQ-DATASET-REPLAY-03 | Ubiquitous | The system shall stream remote replay frames incrementally without requiring a complete local dataset file. |
| REQ-DATASET-REPLAY-04 | Ubiquitous | The system shall support candump and JSONL stdout replay formats. |
| REQ-DATASET-REPLAY-05 | Optional feature | Where `--json` is specified, the system shall emit a standard result envelope without interleaving frame records. |
| REQ-DATASET-REPLAY-06 | Unwanted behaviour | If replay stdout is closed by a downstream pipeline consumer, the system shall stop replay cleanly without printing a Python traceback. |
| REQ-DATASET-REPLAY-07 | Optional feature | Where `--dry-run` is specified, the system shall resolve replay source metadata without opening the remote stream. |
| REQ-DATASET-REPLAY-08 | Unwanted behaviour | If a curated dataset index is requested as a replay source, the system shall return a structured `DATASET_INDEX_NOT_REPLAYABLE` error. |
| REQ-DATASET-REPLAY-09 | Optional feature | Where `--max-seconds` is specified, the system shall stop replay after the requested capture-time window and report `stop_reason=max_seconds`. |
| REQ-DATASET-REPLAY-10 | Optional feature | Where JSONL replay output is specified, the system shall include dataset provenance metadata on each frame event, including provider ref or URL, source URL, replay file, default replay file, frame offset, source format, and source type. |
| REQ-DATASET-REPLAY-11 | Optional feature | Where replay file metadata is available for a dataset descriptor, the system shall list replayable files with stable id, name, size, format, and source URL fields. |
| REQ-DATASET-REPLAY-12 | Optional feature | Where `--file` is specified, the system shall replay the selected file by id or name instead of the default replay file. |
| REQ-DATASET-REPLAY-13 | Unwanted behaviour | If `--file` names a file that is not present in the replay manifest, the system shall return `DATASET_REPLAY_FILE_NOT_FOUND`. |
| REQ-DATASET-REPLAY-14 | Optional feature | Where a dataset uses a dynamic replay manifest such as `catalog:comma-car-segments`, the system shall list segment entries from provider metadata without opening rlog payload streams. |
| REQ-DATASET-REPLAY-15 | Optional feature | Where `--platform` is specified for a dynamic replay manifest, the system shall restrict replay file entries to that platform. |
| REQ-DATASET-REPLAY-16 | Optional feature | Where `--limit` is specified for a dynamic replay manifest, the system shall return at most that many replay file entries. |

---

## Non-Goals (Phase 1)

- Vendoring large external datasets into the repository
- Network-dependent tests
- Active replay of dataset frames onto a live bus
- Bypassing dataset licenses, access forms, or redistribution terms
- Provider-specific download automation (operators download manually from `source_url`)

---

## Future Work

- Automated download for small datasets that can be fetched directly from `source_url` (e.g., SynCAN, whose terms permit download but not redistribution)
- Additional source formats (SynCAN CSV, ROAD CSV)
- `datasets convert` reading from a provider ref after a future automated-download feature resolves the dataset payload
- Richer commaCarSegments vehicle/platform metadata beyond the upstream `database.json` manifest
- Explicit safe live-bus replay from dataset streams
