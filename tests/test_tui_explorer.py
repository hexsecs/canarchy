"""Identifier analysis and synthetic-load bounds for the TUI explorer."""

from __future__ import annotations

import time
import tracemalloc

from canarchy.models import CanFrame, FrameEvent
from canarchy.tui_explorer import IdentifierKey, TrafficExplorer
from canarchy.transport import _compile_filter


def _event(
    arbitration_id: int,
    data: bytes,
    *,
    bus: str = "can0",
    extended: bool = False,
    timestamp: float = 1.0,
) -> dict:
    frame = CanFrame(
        arbitration_id=arbitration_id,
        data=data,
        timestamp=timestamp,
        interface=bus,
        is_extended_id=extended,
    )
    return FrameEvent(frame, source="capture").to_event().to_payload()


def test_identifier_identity_change_legend_and_j1939_detail() -> None:
    explorer = TrafficExplorer()
    events = [
        _event(0x123, b"\x00\x01", timestamp=1.0),
        _event(0x123, b"\x00\x03", timestamp=2.0),
        _event(0x123, b"\x09", bus="can1", timestamp=3.0),
        _event(0x123, b"\x07", extended=True, timestamp=4.0),
        _event(0x18FEEE01, b"\x01", extended=True, timestamp=5.0),
    ]
    explorer.ingest(events, received_at=10.0)
    key = IdentifierKey("can0", 0x123, False)
    assert len(explorer.activities) == 4
    assert explorer.activities[key].count == 2
    assert explorer.activities[key].changed_offsets == (1,)
    assert explorer.activities[key].rate_hz() == 1.0
    detail = explorer.detail(key)
    assert "Raw hex: 0003" in detail
    assert "01:03^" in detail
    assert "00000000 00000011" in detail
    assert "^ changed since previous payload" in detail
    assert "PGN=65262" in explorer.detail(IdentifierKey("can0", 0x18FEEE01, True))
    assert "Raw hex: 0001" in explorer.detail(key, sequence=1)
    assert "01:01 " in explorer.detail(key, sequence=1)


def test_bounded_history_and_decode_evidence() -> None:
    explorer = TrafficExplorer(capacity=2)
    events = [
        _event(0x100, b"\x01"),
        {
            "event_type": "signal",
            "source": "capture",
            "payload": {
                "frame_index": 0,
                "message_name": "Engine",
                "signal_name": "RPM",
                "value": 1200,
                "units": "rpm",
            },
        },
        _event(0x101, b"\x02"),
    ]
    explorer.ingest(events, received_at=1.0)
    assert "Engine.RPM=1200 rpm" in explorer.detail(IdentifierKey("can0", 0x100, False))
    explorer.ingest([_event(0x102, b"\x03")], received_at=2.0)
    assert len(explorer.observations) == 2
    assert IdentifierKey("can0", 0x100, False) not in explorer.activities
    assert "History evicted" in explorer.detail(IdentifierKey("can0", 0x100, False))


def test_source_address_filter_excludes_standard_ids() -> None:
    predicate = _compile_filter("sa==0x31")
    assert predicate(CanFrame(0x18FEEE31, b"", is_extended_id=True))
    assert not predicate(CanFrame(0x031, b"", is_extended_id=False))


def test_malformed_frame_keeps_source_event_positions() -> None:
    explorer = TrafficExplorer()
    added = explorer.ingest(
        [_event(0x100, b"\x01"), {"event_type": "frame", "payload": {}}, _event(0x101, b"\x02")]
    )
    assert [observation.event_index for observation in added] == [0, 2]


def test_synthetic_load_keeps_model_bounded_and_responsive() -> None:
    explorer = TrafficExplorer(capacity=512)
    tracemalloc.start()
    started = time.perf_counter()
    try:
        for batch in range(100):
            events = [
                _event(
                    0x100 + index % 64,
                    bytes((batch % 256, index % 256)),
                    timestamp=float(batch * 100 + index),
                )
                for index in range(100)
            ]
            explorer.ingest(events, received_at=float(batch))
        elapsed = time.perf_counter() - started
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert elapsed < 8.0
    assert peak_bytes < 16_000_000
    assert len(explorer.observations) == 512
    assert len(explorer.activities) <= 64
    assert all(len(activity.history) <= 512 for activity in explorer.activities.values())
