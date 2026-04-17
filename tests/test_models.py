from __future__ import annotations

import unittest

from canarchy.models import (
    AlertEvent,
    CanFrame,
    DecodedMessageEvent,
    FrameEvent,
    J1939ObservationEvent,
    ReplayActionEvent,
    SignalValueEvent,
    UdsTransactionEvent,
    serialize_events,
)


class CanFrameTests(unittest.TestCase):
    def test_classic_can_frame_serializes_to_hex_payload(self) -> None:
        frame = CanFrame(arbitration_id=0x123, data=bytes.fromhex("01020304"), interface="can0")

        payload = frame.to_payload()

        self.assertEqual(payload["arbitration_id"], 0x123)
        self.assertEqual(payload["data"], "01020304")
        self.assertEqual(payload["dlc"], 4)
        self.assertEqual(payload["frame_format"], "can")
        self.assertEqual(payload["interface"], "can0")

    def test_can_fd_frame_supports_bitrate_switch(self) -> None:
        frame = CanFrame(
            arbitration_id=0x18FEEE31,
            data=b"\x00" * 12,
            is_extended_id=True,
            frame_format="can_fd",
            bitrate_switch=True,
        )

        self.assertEqual(frame.to_payload()["frame_format"], "can_fd")
        self.assertEqual(frame.dlc, 12)

    def test_invalid_classic_can_payload_length_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "classic CAN payloads"):
            CanFrame(arbitration_id=0x123, data=b"\x00" * 9)


class EventTests(unittest.TestCase):
    def test_frame_event_serializes_with_frame_payload(self) -> None:
        event = FrameEvent(frame=CanFrame(arbitration_id=0x123, data=b"\x01")).to_event()

        self.assertEqual(event.to_payload()["event_type"], "frame")
        self.assertEqual(event.to_payload()["payload"]["frame"]["data"], "01")

    def test_decoded_message_and_signal_events_serialize(self) -> None:
        frame = CanFrame(arbitration_id=0x123, data=bytes.fromhex("11223344"))
        decoded = DecodedMessageEvent(
            message_name="engine_status",
            frame=frame,
            signals={"rpm": 621.0},
        ).to_event()
        signal = SignalValueEvent(signal_name="rpm", value=621.0, units="rpm").to_event()

        payloads = serialize_events([decoded, signal])

        self.assertEqual(payloads[0]["event_type"], "decoded_message")
        self.assertEqual(payloads[0]["payload"]["signals"]["rpm"], 621.0)
        self.assertEqual(payloads[1]["event_type"], "signal")
        self.assertEqual(payloads[1]["payload"]["units"], "rpm")

    def test_j1939_event_validates_pgn_range(self) -> None:
        with self.assertRaisesRegex(ValueError, "pgn"):
            J1939ObservationEvent(
                pgn=300000,
                source_address=0x31,
                frame=CanFrame(arbitration_id=0x18FEEE31, data=b"\x00", is_extended_id=True),
            )

    def test_replay_and_alert_events_serialize(self) -> None:
        frame = CanFrame(arbitration_id=0x123, data=b"\x01")
        replay = ReplayActionEvent(action="send", frame=frame, rate=1.0).to_event()
        alert = AlertEvent(level="warning", code="TEST", message="planned").to_event()

        payloads = serialize_events([replay, alert])

        self.assertEqual(payloads[0]["event_type"], "replay_event")
        self.assertEqual(payloads[0]["payload"]["rate"], 1.0)
        self.assertEqual(payloads[1]["event_type"], "alert")
        self.assertEqual(payloads[1]["payload"]["code"], "TEST")

    def test_uds_transaction_event_serializes(self) -> None:
        event = UdsTransactionEvent(
            request_id=0x7E0,
            response_id=0x7E8,
            service=0x10,
            service_name="DiagnosticSessionControl",
            request_data=bytes.fromhex("1003"),
            response_data=bytes.fromhex("5003003201F4"),
            ecu_address=0x7E8,
            timestamp=0.0,
        ).to_event()

        payload = event.to_payload()
        self.assertEqual(payload["event_type"], "uds_transaction")
        self.assertEqual(payload["payload"]["service_name"], "DiagnosticSessionControl")
        self.assertEqual(payload["payload"]["request_data"], "1003")
