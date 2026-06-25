"""Active UDS diagnostic workflows (ISO 14229 over ISO-TP / CAN).

Passive trace/scan analysis lives in :mod:`canarchy.uds`; this module adds the
*active* request/response workflows that transmit on the bus: service and
subservice enumeration, ECU reset, TesterPresent, SecurityAccess seed
collection, DID dumping, memory reads, and a bounded zero-knowledge
reconnaissance chain (``auto``). These mirror CaringCaribou's UDS modes while
preserving CANarchy's structured-event envelope and active-transmit safety
model.

Every workflow is written against a small :class:`UdsClient` seam — "send one
UDS request, observe at most one reassembled response" — so the workflow logic
is pure and unit-testable with a fake client, and the transport-backed
:class:`TransportUdsClient` is the only piece that touches live hardware.

Single-frame ISO-TP requests cover every request this module issues (each is
<= 7 payload bytes); responses are reassembled with the existing
:func:`canarchy.uds.reassemble_uds_pdus`, which handles single-frame and
multi-frame (first-frame + consecutive-frame) responses captured inside the
transaction window. CANarchy does not transmit ISO-TP flow-control frames, so a
multi-frame response is only fully reassembled when the sender streams its
consecutive frames without waiting for flow control (the common ECU behaviour
on a quiet bus) and the backend capture window is large enough; the workflows
here keep responses small and bounded so this stays reliable. See
``docs/design/uds-active-workflows.md``.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from canarchy.models import UdsTransactionEvent
from canarchy.uds import (
    UDS_NEGATIVE_RESPONSE_CODES,
    UDS_SERVICE_CATALOG,
    ReassembledUdsPdu,
    reassemble_uds_pdus,
    uds_service_name,
)

# --- protocol constants ------------------------------------------------------

NEGATIVE_RESPONSE_SID = 0x7F
POSITIVE_RESPONSE_OFFSET = 0x40

# Negative response codes that mean "this service / subfunction does not exist".
NRC_SERVICE_NOT_SUPPORTED = 0x11
NRC_SUB_FUNCTION_NOT_SUPPORTED = 0x12
NRC_SUB_FUNCTION_NOT_SUPPORTED_IN_ACTIVE_SESSION = 0x7E
NRC_SERVICE_NOT_SUPPORTED_IN_ACTIVE_SESSION = 0x7F
# "busy, response pending" — the responder will follow up with the real answer.
NRC_RESPONSE_PENDING = 0x78

# A service / subfunction is "absent" only on the plain not-supported NRC. The
# "...InActiveSession" variants (0x7F / 0x7E) mean it exists but is gated to a
# different diagnostic session, so it still counts as supported.
_SERVICE_ABSENT_CODES = frozenset({NRC_SERVICE_NOT_SUPPORTED})
_SUBFUNCTION_ABSENT_CODES = frozenset({NRC_SUB_FUNCTION_NOT_SUPPORTED})

SID_DIAGNOSTIC_SESSION_CONTROL = 0x10
SID_ECU_RESET = 0x11
SID_READ_DATA_BY_IDENTIFIER = 0x22
SID_READ_MEMORY_BY_ADDRESS = 0x23
SID_SECURITY_ACCESS = 0x27
SID_TESTER_PRESENT = 0x3E

# Conventional 11-bit OBD-II diagnostic id pairs, used as discovery defaults.
DEFAULT_FUNCTIONAL_REQUEST_ID = 0x7DF
DEFAULT_PHYSICAL_REQUEST_BASE = 0x7E0
DEFAULT_PHYSICAL_RESPONSE_BASE = 0x7E8

# Conservative bounds so a stray invocation cannot run away on a live bus.
DEFAULT_PER_REQUEST_TIMEOUT = 0.2
DEFAULT_DID_LIMIT = 256
DEFAULT_SEED_COUNT = 1
MAX_MEMORY_DUMP_BYTES = 0x10000
DEFAULT_MEMORY_CHUNK = 4
# A single-frame ISO-TP request carries at most 7 payload bytes.
MAX_SINGLE_FRAME_PAYLOAD = 7
_CAN_SFF_MAX = 0x7FF


class UdsActiveError(Exception):
    """Raised for operator-input / bounds problems before any transmission."""

    def __init__(self, code: str, message: str, hint: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


# --- exchange model ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UdsExchange:
    """One request and the single reassembled response it elicited (if any)."""

    request_id: int
    response_id: int | None
    request: bytes
    response: bytes | None
    complete: bool = True
    elapsed: float | None = None

    @property
    def responded(self) -> bool:
        return self.response is not None and len(self.response) > 0

    @property
    def negative(self) -> bool:
        return self.responded and self.response[0] == NEGATIVE_RESPONSE_SID

    @property
    def positive(self) -> bool:
        return self.responded and not self.negative

    @property
    def negative_code(self) -> int | None:
        if self.negative and len(self.response) >= 3:
            return self.response[2]
        return None

    @property
    def negative_name(self) -> str | None:
        code = self.negative_code
        if code is None:
            return None
        return UDS_NEGATIVE_RESPONSE_CODES.get(code, f"ResponseCode0x{code:02X}")

    @property
    def status(self) -> str:
        if not self.responded:
            return "no_response"
        return "negative" if self.negative else "positive"

    def to_record(self) -> dict[str, object]:
        return {
            "request": self.request.hex(),
            "request_id": self.request_id,
            "response": self.response.hex() if self.response is not None else None,
            "response_id": self.response_id,
            "status": self.status,
            "complete": self.complete,
            "negative_response_code": self.negative_code,
            "negative_response_name": self.negative_name,
            "elapsed_ms": round(self.elapsed * 1000, 3) if self.elapsed is not None else None,
        }


# --- client seam -------------------------------------------------------------


class UdsClient:
    """Send one UDS request and observe at most one reassembled response.

    Concrete subclasses do the transmitting; workflows depend only on this
    interface, so they can be exercised with an in-memory fake.
    """

    def request(
        self,
        request_id: int,
        response_id: int | None,
        payload: bytes,
        *,
        timeout: float | None = None,
    ) -> UdsExchange:  # pragma: no cover - interface
        raise NotImplementedError


def single_frame_request_frame(request_id: int, payload: bytes):
    """Build the ISO-TP single-frame request CAN frame for ``payload``."""
    from canarchy.models import CanFrame

    if not payload:
        raise UdsActiveError(
            code="UDS_EMPTY_REQUEST",
            message="A UDS request needs at least a service id byte.",
            hint="Pass a non-empty request payload.",
        )
    if len(payload) > MAX_SINGLE_FRAME_PAYLOAD:
        raise UdsActiveError(
            code="UDS_REQUEST_TOO_LONG",
            message=(
                f"Request of {len(payload)} bytes exceeds the {MAX_SINGLE_FRAME_PAYLOAD}-byte "
                "single-frame ISO-TP limit."
            ),
            hint="The active workflows only issue single-frame requests; shorten the request.",
        )
    data = bytes([len(payload)]) + payload
    data = data.ljust(8, b"\x00")
    return CanFrame(
        arbitration_id=request_id,
        data=data,
        is_extended_id=request_id > _CAN_SFF_MAX,
    )


def _select_response(
    pdus: Sequence[ReassembledUdsPdu], request_id: int, response_id: int | None
) -> ReassembledUdsPdu | None:
    """Pick the responder PDU, skipping the request echo and 0x78 pending NRCs."""
    candidates = [
        pdu
        for pdu in pdus
        if pdu.arbitration_id != request_id
        and pdu.payload
        and (response_id is None or pdu.arbitration_id == response_id)
    ]
    if not candidates:
        return None
    # Prefer a settled response over a "response pending" (0x78) placeholder.
    for pdu in candidates:
        if not _is_response_pending(pdu.payload):
            return pdu
    return candidates[-1]


def _is_response_pending(payload: bytes) -> bool:
    return (
        len(payload) >= 3
        and payload[0] == NEGATIVE_RESPONSE_SID
        and payload[2] == NRC_RESPONSE_PENDING
    )


class SilentUdsClient(UdsClient):
    """Records requests but never observes a response.

    Used when no live CAN backend is selected (the scaffold transport): the
    workflow still runs and produces a faithfully structured "no responders"
    result instead of misreading unrelated scaffold traffic as UDS responses.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[int, int | None, bytes]] = []

    def request(
        self,
        request_id: int,
        response_id: int | None,
        payload: bytes,
        *,
        timeout: float | None = None,
    ) -> UdsExchange:
        self.calls.append((request_id, response_id, bytes(payload)))
        return UdsExchange(
            request_id=request_id, response_id=response_id, request=bytes(payload), response=None
        )


@dataclass(slots=True)
class TransportUdsClient(UdsClient):
    """A :class:`UdsClient` backed by a live CANarchy transport."""

    transport: object
    interface: str

    def request(
        self,
        request_id: int,
        response_id: int | None,
        payload: bytes,
        *,
        timeout: float | None = None,
    ) -> UdsExchange:
        frame = single_frame_request_frame(request_id, payload)
        started = time.perf_counter()
        frames = self.transport.transaction(self.interface, frame, timeout=timeout)
        elapsed = time.perf_counter() - started
        pdus = reassemble_uds_pdus(list(frames), allow_extended=True)
        chosen = _select_response(pdus, request_id, response_id)
        if chosen is None:
            return UdsExchange(
                request_id=request_id,
                response_id=response_id,
                request=payload,
                response=None,
                elapsed=elapsed,
            )
        return UdsExchange(
            request_id=request_id,
            response_id=chosen.arbitration_id,
            request=payload,
            response=chosen.payload,
            complete=chosen.complete,
            elapsed=elapsed,
        )


# --- event bridging ----------------------------------------------------------


def exchange_to_transaction(exchange: UdsExchange, *, source: str) -> UdsTransactionEvent | None:
    """Turn a responded exchange into the canonical :class:`UdsTransactionEvent`."""
    if not exchange.responded:
        return None
    service = exchange.request[0]
    return UdsTransactionEvent(
        request_id=exchange.request_id,
        response_id=exchange.response_id
        if exchange.response_id is not None
        else exchange.request_id,
        service=service,
        service_name=uds_service_name(service),
        request_data=exchange.request,
        response_data=exchange.response,
        complete=exchange.complete,
        ecu_address=exchange.response_id,
        source=source,
    )


# --- service enumeration -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class ServiceProbe:
    service: int
    name: str
    supported: bool
    exchange: UdsExchange

    def to_record(self) -> dict[str, object]:
        return {
            "service": self.service,
            "name": self.name,
            "supported": self.supported,
            **self.exchange.to_record(),
        }


def classify_service_support(exchange: UdsExchange) -> bool:
    """A service exists unless it is silent or explicitly "not supported"."""
    if not exchange.responded:
        return False
    if exchange.positive:
        return True
    return exchange.negative_code not in _SERVICE_ABSENT_CODES


def _default_service_ids() -> list[int]:
    return [service.service for service in UDS_SERVICE_CATALOG]


def enumerate_services(
    client: UdsClient,
    *,
    request_id: int,
    response_id: int | None,
    services: Iterable[int] | None = None,
    timeout: float = DEFAULT_PER_REQUEST_TIMEOUT,
    max_requests: int | None = None,
    max_duration: float | None = None,
) -> list[ServiceProbe]:
    """Probe each candidate service id once and classify support."""
    candidate_ids = list(services) if services is not None else _default_service_ids()
    probes: list[ServiceProbe] = []
    started = time.perf_counter()
    for index, sid in enumerate(candidate_ids):
        if max_requests is not None and index >= max_requests:
            break
        if max_duration is not None and time.perf_counter() - started >= max_duration:
            break
        exchange = client.request(request_id, response_id, bytes([sid]), timeout=timeout)
        probes.append(
            ServiceProbe(
                service=sid,
                name=uds_service_name(sid),
                supported=classify_service_support(exchange),
                exchange=exchange,
            )
        )
    return probes


# --- subservice enumeration --------------------------------------------------


@dataclass(frozen=True, slots=True)
class SubserviceProbe:
    service: int
    subfunction: int
    supported: bool
    exchange: UdsExchange

    def to_record(self) -> dict[str, object]:
        return {
            "service": self.service,
            "subfunction": self.subfunction,
            "supported": self.supported,
            **self.exchange.to_record(),
        }


def classify_subfunction_support(exchange: UdsExchange) -> bool:
    if not exchange.responded:
        return False
    if exchange.positive:
        return True
    return exchange.negative_code not in (_SUBFUNCTION_ABSENT_CODES | _SERVICE_ABSENT_CODES)


def enumerate_subservices(
    client: UdsClient,
    *,
    request_id: int,
    response_id: int | None,
    service: int,
    sub_start: int = 0x00,
    sub_end: int = 0xFF,
    timeout: float = DEFAULT_PER_REQUEST_TIMEOUT,
    max_duration: float | None = None,
) -> list[SubserviceProbe]:
    _require_byte(service, "service")
    _require_range(sub_start, sub_end, "subfunction")
    probes: list[SubserviceProbe] = []
    started = time.perf_counter()
    for sub in range(sub_start, sub_end + 1):
        if max_duration is not None and time.perf_counter() - started >= max_duration:
            break
        exchange = client.request(request_id, response_id, bytes([service, sub]), timeout=timeout)
        probes.append(
            SubserviceProbe(
                service=service,
                subfunction=sub,
                supported=classify_subfunction_support(exchange),
                exchange=exchange,
            )
        )
    return probes


# --- single-shot services ----------------------------------------------------


def ecu_reset(
    client: UdsClient,
    *,
    request_id: int,
    response_id: int | None,
    reset_type: int = 0x01,
    timeout: float = DEFAULT_PER_REQUEST_TIMEOUT,
) -> UdsExchange:
    _require_byte(reset_type, "reset_type")
    return client.request(
        request_id, response_id, bytes([SID_ECU_RESET, reset_type]), timeout=timeout
    )


def tester_present(
    client: UdsClient,
    *,
    request_id: int,
    response_id: int | None,
    suppress_response: bool = False,
    timeout: float = DEFAULT_PER_REQUEST_TIMEOUT,
) -> UdsExchange:
    subfunction = 0x80 if suppress_response else 0x00
    return client.request(
        request_id, response_id, bytes([SID_TESTER_PRESENT, subfunction]), timeout=timeout
    )


# --- security access seed collection -----------------------------------------


@dataclass(frozen=True, slots=True)
class SeedObservation:
    index: int
    seed: bytes | None
    exchange: UdsExchange

    def to_record(self) -> dict[str, object]:
        return {
            "index": self.index,
            "seed": self.seed.hex() if self.seed is not None else None,
            **self.exchange.to_record(),
        }


@dataclass(frozen=True, slots=True)
class SecuritySeedResult:
    level: int
    session: int | None
    session_exchange: UdsExchange | None
    seeds: list[SeedObservation]

    @property
    def distinct_seeds(self) -> int:
        return len({obs.seed for obs in self.seeds if obs.seed is not None})


def security_seed(
    client: UdsClient,
    *,
    request_id: int,
    response_id: int | None,
    level: int = 0x01,
    session: int | None = None,
    count: int = DEFAULT_SEED_COUNT,
    max_duration: float | None = None,
    timeout: float = DEFAULT_PER_REQUEST_TIMEOUT,
) -> SecuritySeedResult:
    _require_byte(level, "level")
    if level % 2 == 0:
        raise UdsActiveError(
            code="UDS_INVALID_SECURITY_LEVEL",
            message=f"SecurityAccess requestSeed level 0x{level:02X} must be odd.",
            hint="Odd subfunctions request a seed; the even successor sends the key.",
        )
    if count < 1:
        raise UdsActiveError(
            code="UDS_INVALID_SEED_COUNT",
            message=f"Seed count {count} must be at least 1.",
            hint="Pass --count with a positive bound.",
        )
    session_exchange: UdsExchange | None = None
    if session is not None:
        _require_byte(session, "session")
        session_exchange = client.request(
            request_id,
            response_id,
            bytes([SID_DIAGNOSTIC_SESSION_CONTROL, session]),
            timeout=timeout,
        )
    seeds: list[SeedObservation] = []
    started = time.perf_counter()
    for index in range(count):
        if max_duration is not None and time.perf_counter() - started >= max_duration:
            break
        exchange = client.request(
            request_id, response_id, bytes([SID_SECURITY_ACCESS, level]), timeout=timeout
        )
        seed = None
        if exchange.positive and len(exchange.response) >= 2:
            seed = exchange.response[2:]
        seeds.append(SeedObservation(index=index, seed=seed or None, exchange=exchange))
    return SecuritySeedResult(
        level=level,
        session=session,
        session_exchange=session_exchange,
        seeds=seeds,
    )


# --- DID dumping -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DidRecord:
    did: int
    value: bytes | None
    exchange: UdsExchange

    @property
    def present(self) -> bool:
        return self.value is not None

    def to_record(self) -> dict[str, object]:
        return {
            "did": self.did,
            "value": self.value.hex() if self.value is not None else None,
            "present": self.present,
            **self.exchange.to_record(),
        }


def dump_dids(
    client: UdsClient,
    *,
    request_id: int,
    response_id: int | None,
    did_start: int,
    did_end: int,
    limit: int = DEFAULT_DID_LIMIT,
    timeout: float = DEFAULT_PER_REQUEST_TIMEOUT,
    max_duration: float | None = None,
) -> list[DidRecord]:
    _require_word(did_start, "did_start")
    _require_word(did_end, "did_end")
    if did_end < did_start:
        raise UdsActiveError(
            code="UDS_INVALID_DID_RANGE",
            message=f"DID end 0x{did_end:04X} is below start 0x{did_start:04X}.",
            hint="Pass --did-start <= --did-end.",
        )
    if limit < 1:
        raise UdsActiveError(
            code="UDS_INVALID_LIMIT",
            message=f"DID limit {limit} must be at least 1.",
            hint="Pass --limit with a positive bound.",
        )
    records: list[DidRecord] = []
    started = time.perf_counter()
    for did in range(did_start, did_end + 1):
        if len(records) >= limit:
            break
        if max_duration is not None and time.perf_counter() - started >= max_duration:
            break
        payload = bytes([SID_READ_DATA_BY_IDENTIFIER, (did >> 8) & 0xFF, did & 0xFF])
        exchange = client.request(request_id, response_id, payload, timeout=timeout)
        value = None
        # Positive ReadDataByIdentifier echoes 0x62 <did_hi> <did_lo> <value...>.
        if (
            exchange.positive
            and len(exchange.response) >= 3
            and exchange.response[1:3] == payload[1:3]
        ):
            value = exchange.response[3:]
        records.append(DidRecord(did=did, value=value, exchange=exchange))
    return records


# --- memory read -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MemoryChunk:
    address: int
    size: int
    data: bytes | None
    exchange: UdsExchange

    def to_record(self) -> dict[str, object]:
        return {
            "address": self.address,
            "size": self.size,
            "data": self.data.hex() if self.data is not None else None,
            **self.exchange.to_record(),
        }


def _byte_width(value: int) -> int:
    return max(1, (value.bit_length() + 7) // 8)


def read_memory_request(address: int, size: int, *, address_bytes: int, size_bytes: int) -> bytes:
    """Build a ReadMemoryByAddress request payload."""
    alfid = ((size_bytes & 0x0F) << 4) | (address_bytes & 0x0F)
    return (
        bytes([SID_READ_MEMORY_BY_ADDRESS, alfid])
        + address.to_bytes(address_bytes, "big")
        + size.to_bytes(size_bytes, "big")
    )


def plan_memory_chunks(address: int, total_size: int, chunk_size: int) -> list[tuple[int, int]]:
    """Split ``[address, address+total_size)`` into ``(address, size)`` chunks."""
    if total_size < 1:
        raise UdsActiveError(
            code="UDS_INVALID_MEMORY_SIZE",
            message=f"Memory size {total_size} must be at least 1 byte.",
            hint="Pass --size with a positive byte count.",
        )
    if total_size > MAX_MEMORY_DUMP_BYTES:
        raise UdsActiveError(
            code="UDS_MEMORY_TOO_LARGE",
            message=(
                f"Memory size {total_size} exceeds the bounded maximum of "
                f"{MAX_MEMORY_DUMP_BYTES} bytes."
            ),
            hint=f"Read at most {MAX_MEMORY_DUMP_BYTES} bytes per invocation.",
        )
    if chunk_size < 1:
        raise UdsActiveError(
            code="UDS_INVALID_CHUNK_SIZE",
            message=f"Chunk size {chunk_size} must be at least 1 byte.",
            hint="Pass --chunk-size with a positive byte count.",
        )
    chunks: list[tuple[int, int]] = []
    offset = 0
    while offset < total_size:
        size = min(chunk_size, total_size - offset)
        chunks.append((address + offset, size))
        offset += size
    return chunks


def read_memory(
    client: UdsClient,
    *,
    request_id: int,
    response_id: int | None,
    address: int,
    size: int,
    chunk_size: int = DEFAULT_MEMORY_CHUNK,
    address_bytes: int | None = None,
    size_bytes: int | None = None,
    timeout: float = DEFAULT_PER_REQUEST_TIMEOUT,
    max_duration: float | None = None,
) -> list[MemoryChunk]:
    if address < 0:
        raise UdsActiveError(
            code="UDS_INVALID_ADDRESS",
            message=f"Memory address {address} must be non-negative.",
            hint="Pass --address as a non-negative integer.",
        )
    chunks_plan = plan_memory_chunks(address, size, chunk_size)
    addr_width = address_bytes or _byte_width(address + size)
    size_width = size_bytes or _byte_width(chunk_size)
    results: list[MemoryChunk] = []
    started = time.perf_counter()
    for chunk_address, chunk_len in chunks_plan:
        if max_duration is not None and time.perf_counter() - started >= max_duration:
            break
        payload = read_memory_request(
            chunk_address, chunk_len, address_bytes=addr_width, size_bytes=size_width
        )
        exchange = client.request(request_id, response_id, payload, timeout=timeout)
        data = None
        if exchange.positive and len(exchange.response) >= 1:
            data = exchange.response[1:]
        results.append(
            MemoryChunk(address=chunk_address, size=chunk_len, data=data, exchange=exchange)
        )
    return results


# --- auto reconnaissance -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class Responder:
    request_id: int
    response_id: int
    exchange: UdsExchange

    def to_record(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "response_id": self.response_id,
            **self.exchange.to_record(),
        }


@dataclass(frozen=True, slots=True)
class AutoReport:
    responders: list[Responder]
    services: dict[int, list[ServiceProbe]] = field(default_factory=dict)
    dids: dict[int, list[DidRecord]] = field(default_factory=dict)
    complete: bool = True


def discover_responders(
    client: UdsClient,
    *,
    request_ids: Iterable[int],
    response_id: int | None = None,
    probe: bytes = bytes([SID_DIAGNOSTIC_SESSION_CONTROL, 0x01]),
    timeout: float = DEFAULT_PER_REQUEST_TIMEOUT,
    max_duration: float | None = None,
) -> list[Responder]:
    """Probe each request id with a session-control request and note responders."""
    responders: list[Responder] = []
    started = time.perf_counter()
    for request_id in request_ids:
        if max_duration is not None and time.perf_counter() - started >= max_duration:
            break
        exchange = client.request(request_id, response_id, probe, timeout=timeout)
        if exchange.responded and exchange.response_id is not None:
            responders.append(
                Responder(
                    request_id=request_id,
                    response_id=exchange.response_id,
                    exchange=exchange,
                )
            )
    return responders


def auto_recon(
    client: UdsClient,
    *,
    request_ids: Sequence[int],
    response_id: int | None = None,
    probe_services: bool = True,
    did_range: tuple[int, int] | None = None,
    did_limit: int = 16,
    timeout: float = DEFAULT_PER_REQUEST_TIMEOUT,
    max_duration: float | None = None,
) -> AutoReport:
    """Bounded zero-knowledge chain: discover -> services -> bounded DIDs."""
    started = time.perf_counter()

    def _budget_left() -> float | None:
        if max_duration is None:
            return None
        return max(0.0, max_duration - (time.perf_counter() - started))

    responders = discover_responders(
        client,
        request_ids=request_ids,
        response_id=response_id,
        timeout=timeout,
        max_duration=_budget_left(),
    )
    services: dict[int, list[ServiceProbe]] = {}
    dids: dict[int, list[DidRecord]] = {}
    complete = True
    for responder in responders:
        remaining = _budget_left()
        if remaining is not None and remaining <= 0:
            complete = False
            break
        if probe_services:
            services[responder.request_id] = enumerate_services(
                client,
                request_id=responder.request_id,
                response_id=responder.response_id,
                timeout=timeout,
                max_duration=remaining,
            )
        if did_range is not None:
            remaining = _budget_left()
            if remaining is not None and remaining <= 0:
                complete = False
                break
            dids[responder.request_id] = dump_dids(
                client,
                request_id=responder.request_id,
                response_id=responder.response_id,
                did_start=did_range[0],
                did_end=did_range[1],
                limit=did_limit,
                timeout=timeout,
                max_duration=remaining,
            )
    return AutoReport(responders=responders, services=services, dids=dids, complete=complete)


# --- validation helpers ------------------------------------------------------


def _require_byte(value: int, name: str) -> None:
    if not 0 <= value <= 0xFF:
        raise UdsActiveError(
            code="UDS_INVALID_BYTE",
            message=f"{name} 0x{value:X} must be a single byte (0x00-0xFF).",
            hint=f"Pass {name} in the 0x00-0xFF range.",
        )


def _require_word(value: int, name: str) -> None:
    if not 0 <= value <= 0xFFFF:
        raise UdsActiveError(
            code="UDS_INVALID_WORD",
            message=f"{name} 0x{value:X} must be a 16-bit value (0x0000-0xFFFF).",
            hint=f"Pass {name} in the 0x0000-0xFFFF range.",
        )


def _require_range(start: int, end: int, name: str) -> None:
    _require_byte(start, f"{name}_start")
    _require_byte(end, f"{name}_end")
    if end < start:
        raise UdsActiveError(
            code="UDS_INVALID_RANGE",
            message=f"{name} end 0x{end:02X} is below start 0x{start:02X}.",
            hint=f"Pass {name} start <= end.",
        )
