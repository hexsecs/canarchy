"""Built-in public CAN dataset catalog provider."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from canarchy.dataset_provider import DatasetDescriptor, DatasetError, DatasetResolution


_CATALOG: list[dict[str, Any]] = [
    {
        "name": "road",
        "version": "1.0",
        "source_url": "https://zenodo.org/records/10462796",
        "license": "CC BY 4.0",
        "protocol_family": "can",
        "formats": ("csv",),
        "size_description": "~3.5 GB",
        "description": (
            "ROAD (Real ORNL Automotive Dynamometer) CAN Dataset. "
            "Attack-free and attack-injected CAN captures from a real vehicle on a dynamometer. "
            "Includes fuzzy, replay, and fabrication attack types. "
            "See also: https://0xsam.com/road/"
        ),
        "access_notes": None,
        "conversion_targets": ("candump", "jsonl"),
        "metadata": {
            "publisher": "Oak Ridge National Laboratory",
            "paper": "https://arxiv.org/abs/2012.14600",
            "vehicle_type": "passenger",
        },
    },
    {
        "name": "comma-car-segments",
        "version": None,
        "source_url": "https://huggingface.co/datasets/commaai/commaCarSegments",
        "license": "MIT",
        "protocol_family": "can",
        "formats": ("msgpack",),
        "size_description": "100+ GB",
        "description": (
            "comma.ai commaCarSegments: real-world vehicle driving segments with CAN, GPS, "
            "and sensor data recorded by comma devices. Requires opendbc for signal decoding. "
            "Data is stored in msgpack-encoded route segments."
        ),
        "access_notes": "HuggingFace account required for download via `huggingface_hub`.",
        "conversion_targets": ("jsonl",),
        "metadata": {
            "publisher": "comma.ai",
            "vehicle_type": "passenger",
            "note": "Raw CAN bytes are available but signal names require opendbc DBC files.",
        },
    },
    {
        "name": "hcrl-car-hacking",
        "version": None,
        "source_url": "https://ocslab.hksecurity.net/Datasets/car-hacking-dataset",
        "license": "Research use only",
        "protocol_family": "can",
        "formats": ("csv",),
        "size_description": "~2.2 GB",
        "description": (
            "HCRL Car-Hacking Dataset: CAN bus attack traffic recorded from a real vehicle. "
            "Contains normal traffic and four attack types: fuzzy, impersonation, flooding, "
            "and replay. CSV format with Timestamp, ID, DLC, Data, and Label columns."
        ),
        "access_notes": "Research-use agreement may be required from ocslab.hksecurity.net.",
        "conversion_targets": ("candump", "jsonl"),
        "metadata": {
            "publisher": "HCRL / Hacking and Countermeasure Research Lab",
            "vehicle_type": "passenger",
            "csv_columns": ["Timestamp", "ID", "DLC", "Data", "Label"],
        },
    },
    {
        "name": "hcrl-j1939-attack",
        "version": None,
        "source_url": "https://ocslab.hksecurity.net/Datasets/sae-j1939-dataset",
        "license": "Research use only",
        "protocol_family": "j1939",
        "formats": ("csv",),
        "size_description": "Unknown",
        "description": (
            "HCRL SAE J1939 Attack Dataset: attack traffic captured on SAE J1939 "
            "heavy-duty vehicle networks. Includes normal and attack-injected J1939 frames."
        ),
        "access_notes": "Research-use agreement may be required from ocslab.hksecurity.net.",
        "conversion_targets": ("candump", "jsonl"),
        "metadata": {
            "publisher": "HCRL",
            "vehicle_type": "heavy-duty",
        },
    },
    {
        "name": "hcrl-can-fd",
        "version": None,
        "source_url": "https://ocslab.hksecurity.net/Datasets/can-fd-intrusion-dataset",
        "license": "Research use only",
        "protocol_family": "can_fd",
        "formats": ("csv",),
        "size_description": "Unknown",
        "description": (
            "HCRL CAN-FD Intrusion Detection Dataset: CAN FD bus traffic with "
            "intrusion attack traces. Suitable for CAN FD IDS research."
        ),
        "access_notes": "Research-use agreement may be required from ocslab.hksecurity.net.",
        "conversion_targets": ("jsonl",),
        "metadata": {"publisher": "HCRL", "vehicle_type": "passenger"},
    },
    {
        "name": "hcrl-survival-ids",
        "version": None,
        "source_url": "https://ocslab.hksecurity.net/Datasets/survival-ids",
        "license": "Research use only",
        "protocol_family": "can",
        "formats": ("csv",),
        "size_description": "Unknown",
        "description": (
            "HCRL Survival Analysis Dataset for Automobile IDS: CAN bus captures "
            "supporting survival-analysis-based intrusion detection research."
        ),
        "access_notes": "Research-use agreement may be required from ocslab.hksecurity.net.",
        "conversion_targets": ("candump", "jsonl"),
        "metadata": {"publisher": "HCRL", "vehicle_type": "passenger"},
    },
    {
        "name": "hcrl-b-can",
        "version": None,
        "source_url": "https://ocslab.hksecurity.net/Datasets/b-can-intrusion-dataset",
        "license": "Research use only",
        "protocol_family": "can",
        "formats": ("csv",),
        "size_description": "Unknown",
        "description": (
            "HCRL B-CAN Intrusion Detection Dataset: body CAN bus captures "
            "for IDS evaluation on body-network traffic."
        ),
        "access_notes": "Research-use agreement may be required from ocslab.hksecurity.net.",
        "conversion_targets": ("candump", "jsonl"),
        "metadata": {"publisher": "HCRL", "vehicle_type": "passenger"},
    },
    {
        "name": "hcrl-m-can",
        "version": None,
        "source_url": "https://ocslab.hksecurity.net/Datasets/m-can-intrusion-dataset",
        "license": "Research use only",
        "protocol_family": "can",
        "formats": ("csv",),
        "size_description": "Unknown",
        "description": (
            "HCRL M-CAN Intrusion Detection Dataset: movement CAN bus captures "
            "for IDS evaluation on chassis and powertrain traffic."
        ),
        "access_notes": "Research-use agreement may be required from ocslab.hksecurity.net.",
        "conversion_targets": ("candump", "jsonl"),
        "metadata": {"publisher": "HCRL", "vehicle_type": "passenger"},
    },
    {
        "name": "hcrl-can-signal",
        "version": None,
        "source_url": "https://ocslab.hksecurity.net/Datasets/can-signal-extraction-and-translation-dataset",
        "license": "Research use only",
        "protocol_family": "can",
        "formats": ("csv",),
        "size_description": "Unknown",
        "description": (
            "HCRL CAN Signal Extraction and Translation Dataset: labeled CAN captures "
            "for signal reverse-engineering research. Includes ground-truth signal mappings."
        ),
        "access_notes": "Research-use agreement may be required from ocslab.hksecurity.net.",
        "conversion_targets": ("candump", "jsonl"),
        "metadata": {
            "publisher": "HCRL",
            "vehicle_type": "passenger",
            "note": "Useful for benchmarking `re signals` and DBC matching workflows.",
        },
    },
    {
        "name": "hcrl-x-canids",
        "version": None,
        "source_url": "https://ocslab.hksecurity.net/Datasets/x-canids-dataset-in-vehicle-signal-dataset",
        "license": "Research use only",
        "protocol_family": "can",
        "formats": ("csv",),
        "size_description": "Unknown",
        "description": (
            "HCRL X-CANIDS In-Vehicle Signal Dataset: signal-level CAN captures "
            "supporting cross-vehicle IDS generalization research."
        ),
        "access_notes": "Research-use agreement may be required from ocslab.hksecurity.net.",
        "conversion_targets": ("candump", "jsonl"),
        "metadata": {"publisher": "HCRL", "vehicle_type": "passenger"},
    },
    {
        "name": "hcrl-challenge-2020",
        "version": "2020",
        "source_url": "https://ocslab.hksecurity.net/Datasets/carchallenge2020",
        "license": "Research use only",
        "protocol_family": "can",
        "formats": ("csv",),
        "size_description": "Unknown",
        "description": (
            "HCRL Car Hacking: Attack and Defense Challenge 2020 dataset. "
            "Competition captures covering multiple attack scenarios on real vehicles."
        ),
        "access_notes": "Research-use agreement may be required from ocslab.hksecurity.net.",
        "conversion_targets": ("candump", "jsonl"),
        "metadata": {"publisher": "HCRL", "vehicle_type": "passenger"},
    },
    {
        "name": "syncan",
        "version": "1.0",
        "source_url": "https://github.com/etas/SynCAN",
        "license": "MIT",
        "protocol_family": "can",
        "formats": ("csv",),
        "size_description": "~100 MB",
        "description": (
            "SynCAN: Synthetic Controller Area Network dataset for intrusion detection benchmarks. "
            "Synthetic CAN signals generated with realistic timing distributions. "
            "CSV format with Time and per-signal columns. MIT licensed."
        ),
        "access_notes": None,
        "conversion_targets": ("candump", "jsonl"),
        "metadata": {
            "publisher": "ETAS GmbH",
            "vehicle_type": "synthetic",
            "csv_note": "SynCAN CSV has a 'Time' column and per-signal value columns, not raw byte payloads.",
        },
    },
    {
        "name": "candid",
        "version": "vehiclesec25",
        "source_url": "https://doi.org/10.25909/29068553",
        "license": "CC BY 4.0",
        "protocol_family": "can",
        "formats": ("candump",),
        "size_description": "~13.7 GB",
        "description": (
            "CANdid: A CAN bus dataset for vehicle security research from VehicleSec 2025. "
            "Raw CAN logs captured from 10 modern passenger vehicles during controlled maneuvers "
            "(braking, steering, indicator, lights, gears, engine, driving). "
            "CAN logs are in can-utils candump format and can be used directly with CANarchy. "
            "Also includes annotation logs, GPS traces, metadata JSON, and cabin/dashboard video."
        ),
        "access_notes": "Download via Figshare: https://doi.org/10.25909/29068553. Figshare account may be required.",
        "conversion_targets": ("jsonl",),
        "metadata": {
            "publisher": "VehicleSec 2025 / University of South Australia",
            "paper": "https://www.usenix.org/conference/vehiclesec25/presentation/howson",
            "vehicle_type": "passenger",
            "vehicle_count": 10,
            "maneuvers": ["brakes", "steering", "indicator", "lights", "gears", "engine", "driving"],
            "artifacts": ["CAN.log", "annot.log", "GPS.log", "meta.json", "cabin.mp4", "dashboard.mp4"],
            "note": "CAN logs (*_CAN.log) are ready for capture-info, stats, filter, re entropy, re counters.",
            "replay": {
                "default_file": "2_brakes_CAN.log",
                "download_url": "https://ndownloader.figshare.com/files/54551156",
                "source_format": "candump",
                "files": [
                    {"id": "2_brakes_CAN.log", "name": "2_brakes_CAN.log", "vehicle": 2, "maneuver": "brakes", "format": "candump", "size_bytes": 8493164, "source_url": "https://ndownloader.figshare.com/files/54551156"},
                    {"id": "2_indicator_CAN.log", "name": "2_indicator_CAN.log", "vehicle": 2, "maneuver": "indicator", "format": "candump", "size_bytes": 15396798, "source_url": "https://ndownloader.figshare.com/files/54551552"},
                    {"id": "2_steering_CAN.log", "name": "2_steering_CAN.log", "vehicle": 2, "maneuver": "steering", "format": "candump", "size_bytes": 10598262, "source_url": "https://ndownloader.figshare.com/files/54551243"},
                    {"id": "2_lights_CAN.log", "name": "2_lights_CAN.log", "vehicle": 2, "maneuver": "lights", "format": "candump", "size_bytes": 13077892, "source_url": "https://ndownloader.figshare.com/files/54551306"},
                    {"id": "2_gears_CAN.log", "name": "2_gears_CAN.log", "vehicle": 2, "maneuver": "gears", "format": "candump", "size_bytes": 15358112, "source_url": "https://ndownloader.figshare.com/files/54551585"},
                    {"id": "2_engine_CAN.log", "name": "2_engine_CAN.log", "vehicle": 2, "maneuver": "engine", "format": "candump", "size_bytes": 33032784, "source_url": "https://ndownloader.figshare.com/files/54551876"},
                    {"id": "3_driving_CAN.log", "name": "3_driving_CAN.log", "vehicle": 3, "maneuver": "driving", "format": "candump", "size_bytes": 77387857, "source_url": "https://ndownloader.figshare.com/files/54551966"},
                    {"id": "9_driving_CAN.log", "name": "9_driving_CAN.log", "vehicle": 9, "maneuver": "driving", "format": "candump", "size_bytes": 95656994, "source_url": "https://ndownloader.figshare.com/files/54551975"},
                ],
            },
        },
    },
    {
        "name": "pivot-auto-datasets",
        "version": None,
        "source_url": "https://pivot-auto.org/datasets/",
        "license": "Mixed / varies by linked dataset",
        "protocol_family": "can",
        "formats": ("catalog",),
        "size_description": "Catalog / varies by linked dataset",
        "description": (
            "PIVOT Auto Datasets: curated automotive and transportation dataset index. "
            "The open community section lists CAN and in-vehicle networking sources including "
            "CarDS, CANdid, ROAD, ORNL intermittent fault and DriverID datasets, Colorado State "
            "J1939/heavy-vehicle data, Korea University CAN/CAN-FD/J1939 intrusion datasets, SynCAN, "
            "TU Eindhoven CAN intrusion datasets, CrySyS CAN traces, ECUPrint, and related sources."
        ),
        "access_notes": (
            "Index only; follow each linked dataset page for downloads, license, registration, "
            "and format details. Contact info@pivot-auto.org for PIVOT updates."
        ),
        "conversion_targets": (),
        "metadata": {
            "publisher": "PIVOT Project",
            "vehicle_type": "mixed",
            "source_type": "curated-index",
            "categories": [
                "open community datasets",
                "Geotab datasets",
                "industry datasets",
                "government datasets",
                "transportation datasets",
                "connected and autonomous vehicle datasets",
            ],
            "notable_can_sources": [
                "CarDS",
                "CANdid",
                "ROAD",
                "ORNL Intermittent Fault Dataset",
                "ORNL DriverID Dataset",
                "Colorado State J1939 datasets",
                "HCRL CAN/CAN-FD/J1939 datasets",
                "SynCAN",
                "TU Eindhoven CAN intrusion datasets",
                "CrySyS CAN traces",
                "UPT ECUPrint",
            ],
            "note": "Use this catalog entry to discover external CAN datasets; inspect linked sources before choosing conversion or replay workflows.",
        },
    },
]


def _score(descriptor: DatasetDescriptor, query: str) -> int:
    q = query.lower()
    name = descriptor.name.lower()
    desc = descriptor.description.lower()
    proto = descriptor.protocol_family.lower()
    if name == q:
        return 100
    if name.startswith(q):
        return 80
    if q in name:
        return 60
    if q in proto:
        return 50
    if q in desc:
        return 30
    return 0


class PublicDatasetProvider:
    """Built-in catalog of well-known public CAN bus research datasets.

    All metadata is embedded; no network access is required for list/search/inspect.
    fetch() records a local provenance file; it does not download large dataset files.
    """

    name = "catalog"

    def _descriptors(self) -> list[DatasetDescriptor]:
        return [
            DatasetDescriptor(
                provider=self.name,
                name=entry["name"],
                version=entry.get("version"),
                source_url=entry["source_url"],
                license=entry["license"],
                protocol_family=entry["protocol_family"],
                formats=tuple(entry["formats"]),
                size_description=entry["size_description"],
                description=entry["description"],
                access_notes=entry.get("access_notes"),
                conversion_targets=tuple(entry["conversion_targets"]),
                metadata=entry.get("metadata", {}),
            )
            for entry in _CATALOG
        ]

    def search(self, query: str, limit: int = 20) -> list[DatasetDescriptor]:
        if not query.strip():
            return self._descriptors()[:limit]
        scored = [
            (desc, _score(desc, query))
            for desc in self._descriptors()
        ]
        ranked = [desc for desc, score in sorted(scored, key=lambda x: -x[1]) if score > 0]
        return ranked[:limit]

    def inspect(self, name: str) -> DatasetDescriptor:
        for desc in self._descriptors():
            if desc.name == name:
                return desc
        raise DatasetError(
            code="DATASET_NOT_FOUND",
            message=f"No dataset named '{name}' in the catalog.",
            hint="Use `canarchy datasets search` to browse available datasets.",
        )

    def fetch(self, name: str) -> DatasetResolution:
        """Record local provenance for a dataset without downloading the full data.

        Large public CAN datasets are not automatically downloaded. This command saves
        a provenance record (source URL, license, timestamp) so that subsequent
        workflows can reference a confirmed, attributed dataset source.
        """
        from canarchy.dataset_cache import now_utc_iso, save_provenance

        descriptor = self.inspect(name)
        provenance = {
            "provider": self.name,
            "dataset": name,
            "source_url": descriptor.source_url,
            "license": descriptor.license,
            "fetched_at": now_utc_iso(),
            "note": (
                "Provenance record only. Download the dataset from source_url manually. "
                "See `canarchy datasets inspect catalog:{name}` for access notes."
            ),
        }
        cache_path = save_provenance(self.name, name, provenance)
        return DatasetResolution(
            descriptor=descriptor,
            cache_path=cache_path,
            is_cached=True,
            provenance=provenance,
        )

    def refresh(self, name: str | None = None) -> list[DatasetDescriptor]:
        """Catalog is embedded; refresh re-reads and saves a manifest summary."""
        from canarchy.dataset_cache import now_utc_iso, save_manifest

        descriptors = self._descriptors()
        manifest = {
            "provider": self.name,
            "generated_at": now_utc_iso(),
            "dataset_count": len(descriptors),
            "datasets": [
                {
                    "name": d.name,
                    "protocol_family": d.protocol_family,
                    "license": d.license,
                    "source_url": d.source_url,
                }
                for d in descriptors
            ],
        }
        save_manifest(self.name, manifest)
        return descriptors
