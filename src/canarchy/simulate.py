"""Standalone bus simulator — deterministic synthetic CAN/J1939 traffic profiles.

Profiles are data-driven JSON resources under
``canarchy.resources.simulate.profiles`` so new vehicle archetypes can be
added without touching this module. Each profile mixes classic CAN frames,
J1939 PGN traffic, and occasional DM1 fault bursts.
"""

from __future__ import annotations

import importlib.resources
import json
import random
from functools import lru_cache
from typing import Any

from canarchy.j1939 import compose_arbitration_id
from canarchy.models import CanFrame
from canarchy.transport import TransportError

__all__ = [
    "PROFILE_NAMES",
    "load_profile",
    "simulate_frames",
]


@lru_cache(maxsize=1)
def _profiles() -> dict[str, dict[str, Any]]:
    text = (
        importlib.resources.files("canarchy.resources.simulate")
        .joinpath("profiles.json")
        .read_text(encoding="utf-8")
    )
    return json.loads(text)


def _profile_names() -> tuple[str, ...]:
    return tuple(sorted(_profiles()))


PROFILE_NAMES: tuple[str, ...] = _profile_names()


def load_profile(name: str) -> dict[str, Any]:
    """Return the data-driven profile definition for *name*.

    Raises :class:`canarchy.transport.TransportError` (``SIMULATE_UNKNOWN_PROFILE``)
    for an unrecognised profile name.
    """
    profiles = _profiles()
    profile = profiles.get(name)
    if profile is None:
        raise TransportError(
            "SIMULATE_UNKNOWN_PROFILE",
            f"Unknown simulation profile `{name}`.",
            f"Choose one of: {', '.join(sorted(profiles))}.",
        )
    return profile


def _encode_dtc(
    *, spn: int, fmi: int, occurrence_count: int = 1, conversion_method: int = 0
) -> int:
    """Pack a DM1 DTC the same way ``j1939._parse_dtcs`` unpacks it."""
    spn_low16 = spn & 0xFFFF
    spn_high3 = (spn >> 16) & 0x7
    return (
        spn_low16
        | ((fmi & 0x1F) << 16)
        | (spn_high3 << 21)
        | ((occurrence_count & 0x7F) << 24)
        | ((conversion_method & 0x1) << 31)
    )


_LAMP_BIT_OFFSETS = {
    "mil": 0,
    "red_stop": 2,
    "amber_warning": 4,
    "protect": 6,
}


def _build_dm1_payload(dm1_spec: dict[str, Any]) -> bytes:
    lamp_name = dm1_spec.get("lamp_status", "amber_warning")
    lamp_value = 0
    offset = _LAMP_BIT_OFFSETS.get(lamp_name, 4)
    lamp_value |= 0x1 << offset  # "on"
    # All other lamps report "off" (0b00), which is already the default.
    payload = bytearray(lamp_value.to_bytes(2, byteorder="little"))
    payload.extend(b"\x00\x00")  # reserved bytes the decoder skips before the DTC block
    for fault in dm1_spec.get("fault_codes", [])[:1]:
        dtc = _encode_dtc(
            spn=int(fault["spn"]),
            fmi=int(fault["fmi"]),
            occurrence_count=int(fault.get("occurrence_count", 1)),
        )
        payload.extend(dtc.to_bytes(4, byteorder="little"))
    return bytes(payload)


def _pattern_data(pattern: str, *, dlc: int, index: int, rng: random.Random) -> bytes:
    if pattern == "counter":
        return bytes((index + offset) % 256 for offset in range(dlc))
    if pattern == "slow-drift":
        base = (index // 8) % 256
        return bytes((base + offset) % 256 for offset in range(dlc))
    return bytes(rng.randint(0, 255) for _ in range(dlc))


def _select_template(templates: list[dict[str, Any]], rng: random.Random) -> dict[str, Any]:
    weights = [max(int(template.get("weight", 1)), 1) for template in templates]
    return rng.choices(templates, weights=weights, k=1)[0]


def simulate_frames(
    profile_name: str,
    *,
    interface: str | None = None,
    rate: float = 50.0,
    duration: float = 10.0,
    seed: int = 0,
) -> list[CanFrame]:
    """Generate a deterministic, profile-driven mix of synthetic CAN frames.

    The mix is sampled from the profile's ``classic_frames``, ``j1939_messages``,
    and ``dm1`` definitions, weighted by each template's ``weight``. Frame
    timestamps are evenly spaced at ``1 / rate`` seconds apart over ``duration``
    seconds. The same ``seed`` always yields the same sequence of frames.
    """
    if rate <= 0:
        raise TransportError(
            "SIMULATE_INVALID_RATE",
            f"`--rate` must be greater than zero (got {rate}).",
            "Pass a positive frame rate in Hz, e.g. `--rate 50`.",
        )
    if duration <= 0:
        raise TransportError(
            "SIMULATE_INVALID_DURATION",
            f"`--duration` must be greater than zero (got {duration}).",
            "Pass a positive duration in seconds, e.g. `--duration 10`.",
        )

    profile = load_profile(profile_name)
    rng = random.Random(seed)

    templates: list[dict[str, Any]] = []
    for entry in profile.get("classic_frames", []):
        templates.append({**entry, "_kind": "classic"})
    for entry in profile.get("j1939_messages", []):
        templates.append({**entry, "_kind": "j1939"})
    dm1_spec = profile.get("dm1")
    if dm1_spec is not None:
        templates.append({**dm1_spec, "_kind": "dm1", "weight": dm1_spec.get("weight", 1)})

    if not templates:
        raise TransportError(
            "SIMULATE_EMPTY_PROFILE",
            f"Profile `{profile_name}` defines no frame templates.",
            "Add `classic_frames`, `j1939_messages`, or `dm1` entries to the profile.",
        )

    frame_count = max(int(round(duration * rate)), 1)
    gap_seconds = 1.0 / rate
    frames: list[CanFrame] = []
    for index in range(frame_count):
        template = _select_template(templates, rng)
        timestamp = index * gap_seconds
        kind = template["_kind"]
        if kind == "classic":
            arbitration_id = int(template["arbitration_id"], 16)
            is_extended = bool(template.get("extended", False))
            dlc = int(template.get("dlc", 8))
            data = _pattern_data(
                template.get("data_pattern", "random"), dlc=dlc, index=index, rng=rng
            )
        elif kind == "j1939":
            arbitration_id = compose_arbitration_id(
                int(template["pgn"]),
                priority=int(template.get("priority", 6)),
                source_address=int(template.get("source_address", 0)),
            )
            is_extended = True
            dlc = int(template.get("dlc", 8))
            data = _pattern_data(
                template.get("data_pattern", "random"), dlc=dlc, index=index, rng=rng
            )
        else:  # dm1
            from canarchy.j1939 import DM1_PGN

            arbitration_id = compose_arbitration_id(
                DM1_PGN,
                priority=6,
                source_address=int(template.get("source_address", 0)),
            )
            is_extended = True
            data = _build_dm1_payload(template)

        frames.append(
            CanFrame(
                arbitration_id=arbitration_id,
                data=data,
                interface=interface,
                is_extended_id=is_extended,
                timestamp=timestamp,
            )
        )

    return frames
