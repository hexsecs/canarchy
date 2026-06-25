"""Tests for active UDS workflows (canarchy.uds_active)."""

from __future__ import annotations

import unittest
from collections.abc import Callable

from canarchy.models import CanFrame
from canarchy.uds_active import (
    DEFAULT_PHYSICAL_REQUEST_BASE,
    DEFAULT_PHYSICAL_RESPONSE_BASE,
    MAX_MEMORY_DUMP_BYTES,
    TransportUdsClient,
    UdsActiveError,
    UdsClient,
    UdsExchange,
    auto_recon,
    classify_service_support,
    classify_subfunction_support,
    dump_dids,
    ecu_reset,
    enumerate_services,
    enumerate_subservices,
    plan_memory_chunks,
    read_memory,
    read_memory_request,
    security_seed,
    single_frame_request_frame,
)
from canarchy.uds_active import tester_present as run_tester_present


class FakeUdsClient(UdsClient):
    """Programmable client: a rule maps a request payload to a response (or None)."""

    def __init__(
        self,
        rule: Callable[[int, bytes], bytes | None],
        *,
        response_id_for: Callable[[int], int] | None = None,
    ) -> None:
        self.rule = rule
        self.response_id_for = response_id_for or (lambda rid: rid + 0x8)
        self.calls: list[tuple[int, int | None, bytes]] = []

    def request(
        self,
        request_id: int,
        response_id: int | None,
        payload: bytes,
        *,
        timeout: float | None = None,
    ) -> UdsExchange:
        self.calls.append((request_id, response_id, payload))
        response = self.rule(request_id, payload)
        if response is None:
            return UdsExchange(
                request_id=request_id, response_id=response_id, request=payload, response=None
            )
        observed = response_id if response_id is not None else self.response_id_for(request_id)
        return UdsExchange(
            request_id=request_id,
            response_id=observed,
            request=payload,
            response=response,
        )


def _positive(service: int, tail: bytes = b"") -> bytes:
    return bytes([service + 0x40]) + tail


def _negative(service: int, code: int) -> bytes:
    return bytes([0x7F, service, code])


class FakeTransaction:
    """A fake transport whose transaction() returns canned response frames."""

    def __init__(self, frames: list[CanFrame]) -> None:
        self.frames = frames
        self.sent: list[CanFrame] = []

    def transaction(
        self, interface: str, frame: CanFrame, *, timeout: float | None = None
    ) -> list[CanFrame]:
        self.sent.append(frame)
        return self.frames


class SingleFrameRequestTest(unittest.TestCase):
    def test_builds_padded_single_frame(self) -> None:
        frame = single_frame_request_frame(0x7E0, b"\x10\x01")
        self.assertEqual(frame.arbitration_id, 0x7E0)
        self.assertEqual(frame.data, bytes.fromhex("0210010000000000"))
        self.assertFalse(frame.is_extended_id)

    def test_extended_id_flagged(self) -> None:
        frame = single_frame_request_frame(0x18DA10F1, b"\x3e\x00")
        self.assertTrue(frame.is_extended_id)

    def test_rejects_empty_payload(self) -> None:
        with self.assertRaises(UdsActiveError) as ctx:
            single_frame_request_frame(0x7E0, b"")
        self.assertEqual(ctx.exception.code, "UDS_EMPTY_REQUEST")

    def test_rejects_oversize_payload(self) -> None:
        with self.assertRaises(UdsActiveError) as ctx:
            single_frame_request_frame(0x7E0, b"\x00" * 8)
        self.assertEqual(ctx.exception.code, "UDS_REQUEST_TOO_LONG")


class TransportClientTest(unittest.TestCase):
    def test_reassembles_single_frame_response(self) -> None:
        response = CanFrame(arbitration_id=0x7E8, data=bytes.fromhex("0350010000000000"))
        transport = FakeTransaction([response])
        client = TransportUdsClient(transport=transport, interface="can0")
        exchange = client.request(0x7E0, 0x7E8, b"\x10\x01")
        self.assertTrue(exchange.positive)
        self.assertEqual(exchange.response, bytes.fromhex("500100"))
        self.assertEqual(exchange.response_id, 0x7E8)

    def test_reassembles_extended_29bit_response(self) -> None:
        response = CanFrame(
            arbitration_id=0x18DAF110,
            data=bytes.fromhex("0350010000000000"),
            is_extended_id=True,
        )
        transport = FakeTransaction([response])
        client = TransportUdsClient(transport=transport, interface="can0")
        exchange = client.request(0x18DA10F1, 0x18DAF110, b"\x10\x01")
        self.assertTrue(exchange.positive)
        self.assertEqual(exchange.response, bytes.fromhex("500100"))
        self.assertEqual(exchange.response_id, 0x18DAF110)

    def test_passes_timeout_through(self) -> None:
        class RecordingTransport(FakeTransaction):
            seen: list[float | None] = []

            def transaction(self, interface, frame, *, timeout=None):
                RecordingTransport.seen.append(timeout)
                return self.frames

        transport = RecordingTransport([])
        client = TransportUdsClient(transport=transport, interface="can0")
        client.request(0x7E0, 0x7E8, b"\x10\x01", timeout=1.0)
        self.assertEqual(RecordingTransport.seen, [1.0])

    def test_ignores_request_echo(self) -> None:
        echo = CanFrame(arbitration_id=0x7E0, data=bytes.fromhex("0210010000000000"))
        response = CanFrame(arbitration_id=0x7E8, data=bytes.fromhex("037f1011000000"))
        transport = FakeTransaction([echo, response])
        client = TransportUdsClient(transport=transport, interface="can0")
        exchange = client.request(0x7E0, None, b"\x10\x01")
        self.assertTrue(exchange.negative)
        self.assertEqual(exchange.negative_code, 0x11)

    def test_no_response_when_only_echo(self) -> None:
        echo = CanFrame(arbitration_id=0x7E0, data=bytes.fromhex("0210010000000000"))
        transport = FakeTransaction([echo])
        client = TransportUdsClient(transport=transport, interface="can0")
        exchange = client.request(0x7E0, 0x7E8, b"\x10\x01")
        self.assertFalse(exchange.responded)
        self.assertEqual(exchange.status, "no_response")

    def test_prefers_settled_over_response_pending(self) -> None:
        pending = CanFrame(arbitration_id=0x7E8, data=bytes.fromhex("037f1078000000"))
        settled = CanFrame(arbitration_id=0x7E8, data=bytes.fromhex("0650010000000000"))
        transport = FakeTransaction([pending, settled])
        client = TransportUdsClient(transport=transport, interface="can0")
        exchange = client.request(0x7E0, 0x7E8, b"\x10\x01")
        self.assertTrue(exchange.positive)


class ServiceEnumerationTest(unittest.TestCase):
    def test_classify_support(self) -> None:
        present = UdsExchange(0x7E0, 0x7E8, b"\x22", _positive(0x22, b"\x01"))
        absent = UdsExchange(0x7E0, 0x7E8, b"\x22", _negative(0x22, 0x11))
        conditions = UdsExchange(0x7E0, 0x7E8, b"\x27", _negative(0x27, 0x33))
        # NRC 0x7F (serviceNotSupportedInActiveSession) means the service exists.
        session_gated = UdsExchange(0x7E0, 0x7E8, b"\x31", _negative(0x31, 0x7F))
        silent = UdsExchange(0x7E0, 0x7E8, b"\x22", None)
        self.assertTrue(classify_service_support(present))
        self.assertFalse(classify_service_support(absent))
        self.assertTrue(classify_service_support(conditions))
        self.assertTrue(classify_service_support(session_gated))
        self.assertFalse(classify_service_support(silent))

    def test_enumerate_services_marks_supported(self) -> None:
        supported = {0x10, 0x22, 0x27}

        def rule(_rid: int, payload: bytes) -> bytes | None:
            sid = payload[0]
            if sid in supported:
                return _positive(sid)
            return _negative(sid, 0x11)

        probes = enumerate_services(FakeUdsClient(rule), request_id=0x7E0, response_id=0x7E8)
        found = {probe.service for probe in probes if probe.supported}
        self.assertEqual(found, supported)

    def test_enumerate_services_respects_max_requests(self) -> None:
        client = FakeUdsClient(lambda _r, p: _positive(p[0]))
        probes = enumerate_services(
            client, request_id=0x7E0, response_id=0x7E8, services=range(0x00, 0x40), max_requests=5
        )
        self.assertEqual(len(probes), 5)


class SubserviceEnumerationTest(unittest.TestCase):
    def test_subfunction_support(self) -> None:
        absent = UdsExchange(0x7E0, 0x7E8, b"\x19\x05", _negative(0x19, 0x12))
        present = UdsExchange(0x7E0, 0x7E8, b"\x19\x02", _positive(0x19, b"\xff"))
        self.assertFalse(classify_subfunction_support(absent))
        self.assertTrue(classify_subfunction_support(present))

    def test_enumerate_subservices(self) -> None:
        def rule(_rid: int, payload: bytes) -> bytes | None:
            if payload[1] in (0x01, 0x02):
                return _positive(payload[0])
            return _negative(payload[0], 0x12)

        probes = enumerate_subservices(
            FakeUdsClient(rule),
            request_id=0x7E0,
            response_id=0x7E8,
            service=0x19,
            sub_start=0x00,
            sub_end=0x04,
        )
        supported = {p.subfunction for p in probes if p.supported}
        self.assertEqual(supported, {0x01, 0x02})


class SingleShotTest(unittest.TestCase):
    def test_ecu_reset(self) -> None:
        client = FakeUdsClient(lambda _r, p: _positive(p[0], bytes([p[1]])))
        exchange = ecu_reset(client, request_id=0x7E0, response_id=0x7E8, reset_type=0x01)
        self.assertTrue(exchange.positive)
        self.assertEqual(client.calls[0][2], b"\x11\x01")

    def test_tester_present_suppress(self) -> None:
        client = FakeUdsClient(lambda _r, _p: None)
        run_tester_present(client, request_id=0x7E0, response_id=0x7E8, suppress_response=True)
        self.assertEqual(client.calls[0][2], b"\x3e\x80")

    def test_ecu_reset_rejects_bad_type(self) -> None:
        client = FakeUdsClient(lambda _r, _p: None)
        with self.assertRaises(UdsActiveError):
            ecu_reset(client, request_id=0x7E0, response_id=0x7E8, reset_type=0x100)


class SecuritySeedTest(unittest.TestCase):
    def test_collects_seeds(self) -> None:
        def rule(_rid: int, payload: bytes) -> bytes | None:
            if payload[0] == 0x27:
                return bytes([0x67, payload[1], 0xDE, 0xAD])
            return _positive(payload[0])

        result = security_seed(
            FakeUdsClient(rule),
            request_id=0x7E0,
            response_id=0x7E8,
            level=0x01,
            session=0x03,
            count=3,
        )
        self.assertEqual(len(result.seeds), 3)
        self.assertEqual(result.seeds[0].seed, b"\xde\xad")
        self.assertIsNotNone(result.session_exchange)
        self.assertEqual(result.distinct_seeds, 1)

    def test_rejects_even_level(self) -> None:
        with self.assertRaises(UdsActiveError) as ctx:
            security_seed(
                FakeUdsClient(lambda _r, _p: None), request_id=0x7E0, response_id=0x7E8, level=0x02
            )
        self.assertEqual(ctx.exception.code, "UDS_INVALID_SECURITY_LEVEL")


class DumpDidsTest(unittest.TestCase):
    def test_dumps_present_dids(self) -> None:
        present = {0xF190: b"VINDATA"}

        def rule(_rid: int, payload: bytes) -> bytes | None:
            did = (payload[1] << 8) | payload[2]
            if did in present:
                return bytes([0x62, payload[1], payload[2]]) + present[did]
            return _negative(0x22, 0x31)

        records = dump_dids(
            FakeUdsClient(rule),
            request_id=0x7E0,
            response_id=0x7E8,
            did_start=0xF18F,
            did_end=0xF192,
        )
        present_records = {r.did: r.value for r in records if r.present}
        self.assertEqual(present_records, {0xF190: b"VINDATA"})

    def test_limit_caps_requests(self) -> None:
        client = FakeUdsClient(lambda _r, _p: _negative(0x22, 0x31))
        records = dump_dids(
            client, request_id=0x7E0, response_id=0x7E8, did_start=0x0000, did_end=0xFFFF, limit=10
        )
        self.assertEqual(len(records), 10)

    def test_rejects_inverted_range(self) -> None:
        with self.assertRaises(UdsActiveError):
            dump_dids(
                FakeUdsClient(lambda _r, _p: None),
                request_id=0x7E0,
                response_id=0x7E8,
                did_start=0x10,
                did_end=0x05,
            )


class ReadMemoryTest(unittest.TestCase):
    def test_request_encoding(self) -> None:
        payload = read_memory_request(0x1000, 4, address_bytes=2, size_bytes=1)
        # SID 0x23, ALFID 0x12 (size_bytes=1<<4 | addr_bytes=2), addr 0x1000, size 0x04.
        self.assertEqual(payload, bytes.fromhex("2312100004"))

    def test_request_alfid(self) -> None:
        payload = read_memory_request(0x12345678, 16, address_bytes=4, size_bytes=2)
        self.assertEqual(payload[0], 0x23)
        self.assertEqual(payload[1], 0x24)  # size_bytes=2 high nibble, addr_bytes=4 low nibble
        self.assertEqual(payload[2:6], bytes.fromhex("12345678"))
        self.assertEqual(payload[6:8], bytes.fromhex("0010"))

    def test_plan_chunks(self) -> None:
        chunks = plan_memory_chunks(0x1000, 10, 4)
        self.assertEqual(chunks, [(0x1000, 4), (0x1004, 4), (0x1008, 2)])

    def test_plan_rejects_oversize(self) -> None:
        with self.assertRaises(UdsActiveError) as ctx:
            plan_memory_chunks(0, MAX_MEMORY_DUMP_BYTES + 1, 4)
        self.assertEqual(ctx.exception.code, "UDS_MEMORY_TOO_LARGE")

    def test_read_memory_collects_data(self) -> None:
        def rule(_rid: int, payload: bytes) -> bytes | None:
            # Echo a deterministic byte pattern for the requested size.
            size = payload[-1]
            return bytes([0x63]) + bytes(range(size))

        chunks = read_memory(
            FakeUdsClient(rule),
            request_id=0x7E0,
            response_id=0x7E8,
            address=0x2000,
            size=6,
            chunk_size=4,
        )
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].data, bytes(range(4)))
        self.assertEqual(chunks[1].data, bytes(range(2)))


class AutoReconTest(unittest.TestCase):
    def test_discovers_and_probes(self) -> None:
        live_request = DEFAULT_PHYSICAL_REQUEST_BASE  # 0x7E0
        supported = {0x10, 0x22}

        def rule(rid: int, payload: bytes) -> bytes | None:
            if rid != live_request:
                return None
            sid = payload[0]
            if sid in supported:
                return _positive(sid)
            return _negative(sid, 0x11)

        report = auto_recon(
            FakeUdsClient(rule),
            request_ids=range(0x7E0, 0x7E4),
            probe_services=True,
        )
        self.assertEqual(len(report.responders), 1)
        self.assertEqual(report.responders[0].request_id, live_request)
        self.assertEqual(report.responders[0].response_id, DEFAULT_PHYSICAL_RESPONSE_BASE)
        found = {p.service for p in report.services[live_request] if p.supported}
        self.assertEqual(found, supported)

    def test_auto_with_did_range(self) -> None:
        def rule(rid: int, payload: bytes) -> bytes | None:
            if rid != 0x7E0:
                return None
            if payload[0] == 0x10:
                return _positive(0x10)
            if payload[0] == 0x22:
                return bytes([0x62, payload[1], payload[2], 0xAB])
            return _negative(payload[0], 0x11)

        report = auto_recon(
            FakeUdsClient(rule),
            request_ids=[0x7E0],
            probe_services=False,
            did_range=(0xF190, 0xF192),
            did_limit=8,
        )
        self.assertIn(0x7E0, report.dids)
        self.assertTrue(all(r.present for r in report.dids[0x7E0]))


if __name__ == "__main__":
    unittest.main()
