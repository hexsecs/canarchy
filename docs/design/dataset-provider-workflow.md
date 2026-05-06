# Design: Dataset Provider Workflow

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented (Phase 2) |
| Issue | #216, #220, #233, #235, #241, #242, #243, #245, #246, #259 |
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
canarchy datasets convert <file> --source-format hcrl-csv --format candump|jsonl [--output <path>]
canarchy datasets stream <file> --source-format hcrl-csv|candump --format candump|jsonl [--chunk-size N] [--max-frames N] [--provider-ref <ref>] [--output <path>]
canarchy datasets replay <dataset-ref-or-url> [--file <id-or-name>] [--list-files] [--format candump|jsonl] [--rate N] [--max-frames N] [--max-seconds N] [--dry-run]
```

All commands follow the standard `--json`, `--jsonl`, `--table`, `--raw` output modes.

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

Ref resolution: `catalog:road` or bare `road`. Bare names search registered providers in order.

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
| `syncan` | CAN | MIT | ~100 MB |
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

---

## Non-Goals (Phase 1)

- Vendoring large external datasets into the repository
- Network-dependent tests
- Active replay of dataset frames onto a live bus
- Bypassing dataset licenses, access forms, or redistribution terms
- Provider-specific download automation (operators download manually from `source_url`)

---

## Future Work

- Automated download for small, openly-licensed datasets (e.g., SynCAN)
- Additional source formats (SynCAN CSV, ROAD CSV, comma.ai msgpack)
- `datasets convert` reading from a provider ref after a future automated-download feature resolves the dataset payload
- Provider-specific streaming adapters for remote datasets such as commaCarSegments
- Explicit safe live-bus replay from dataset streams
