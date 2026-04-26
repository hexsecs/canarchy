"""Optional Scapy-backed UDS payload inspection helpers."""

from __future__ import annotations

from functools import lru_cache
from importlib import import_module
from typing import Any


@lru_cache(maxsize=1)
def _load_uds_packet_class() -> type[Any] | None:
    try:
        module = import_module("scapy.contrib.automotive.uds")
    except Exception:
        try:
            scapy_all = import_module("scapy.all")
            load_contrib = getattr(scapy_all, "load_contrib", None)
            if callable(load_contrib):
                load_contrib("automotive.uds")
            module = import_module("scapy.contrib.automotive.uds")
        except Exception:
            return None
    return getattr(module, "UDS", None)


def scapy_uds_available() -> bool:
    return _load_uds_packet_class() is not None


def inspect_uds_payload(payload: bytes) -> dict[str, Any] | None:
    uds_packet = _load_uds_packet_class()
    if uds_packet is None or not payload:
        return None

    try:
        packet = uds_packet(payload)
    except Exception:
        return None

    summary: str | None = None
    try:
        packet_summary = packet.summary()
        if packet_summary:
            summary = str(packet_summary)
    except Exception:
        summary = None

    result: dict[str, Any] = {"summary": summary}
    fields = _normalize_mapping(getattr(packet, "fields", {}))
    if fields:
        result["fields"] = fields
    return result


def _normalize_mapping(mapping: Any) -> dict[str, Any]:
    if not isinstance(mapping, dict):
        return {}
    return {str(key): _normalize_value(value) for key, value in mapping.items()}


def _normalize_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return _normalize_mapping(value)
    if isinstance(value, (list, tuple)):
        return [_normalize_value(item) for item in value]
    return str(value)
