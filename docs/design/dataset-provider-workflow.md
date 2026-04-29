# Design: Dataset Provider Workflow

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented (Phase 1) |
| Issue | #216 |
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

`PublicDatasetProvider` (name: `catalog`) embeds metadata for 12 public CAN research datasets:

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

No network access is required for `search`, `inspect`, or `provider list`.

---

## Conversion

`datasets convert` is explicitly separated from fetch/cache. It converts a locally-present dataset
file into a CANarchy-native format.

### Currently supported

| Source format | Description | Output formats |
|--------------|-------------|----------------|
| `hcrl-csv` | HCRL Car-Hacking CSV: `Timestamp,ID,DLC,Data[,Label]` | `candump`, `jsonl` |

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
- `datasets convert` reading from a provider ref (after fetch downloads the data)
- Streaming conversion for large files (feeds into issue #220)
