"""UDS protocol helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace

from canarchy.models import CanFrame, UdsTransactionEvent
from canarchy.scapy_uds import inspect_uds_payload, scapy_uds_available


@dataclass(slots=True, frozen=True)
class UdsService:
    service: int
    name: str
    category: str
    requires_subfunction: bool

    @property
    def positive_response_service(self) -> int:
        return self.service + 0x40

    def to_payload(self) -> dict[str, object]:
        return {
            "category": self.category,
            "name": self.name,
            "positive_response_service": self.positive_response_service,
            "requires_subfunction": self.requires_subfunction,
            "service": self.service,
        }


UDS_SERVICE_CATALOG: tuple[UdsService, ...] = (
    UdsService(0x10, "DiagnosticSessionControl", "session", True),
    UdsService(0x11, "ECUReset", "session", True),
    UdsService(0x14, "ClearDiagnosticInformation", "diagnostics", False),
    UdsService(0x19, "ReadDTCInformation", "diagnostics", True),
    UdsService(0x22, "ReadDataByIdentifier", "data", False),
    UdsService(0x23, "ReadMemoryByAddress", "data", False),
    UdsService(0x27, "SecurityAccess", "security", True),
    UdsService(0x28, "CommunicationControl", "communication", True),
    UdsService(0x2E, "WriteDataByIdentifier", "data", False),
    UdsService(0x2F, "InputOutputControlByIdentifier", "control", False),
    UdsService(0x31, "RoutineControl", "control", True),
    UdsService(0x34, "RequestDownload", "transfer", False),
    UdsService(0x35, "RequestUpload", "transfer", False),
    UdsService(0x36, "TransferData", "transfer", False),
    UdsService(0x37, "RequestTransferExit", "transfer", False),
    UdsService(0x3E, "TesterPresent", "session", True),
    UdsService(0x85, "ControlDTCSetting", "diagnostics", True),
)

UDS_NEGATIVE_RESPONSE_CODES: dict[int, str] = {
    0x10: "GeneralReject",
    0x11: "ServiceNotSupported",
    0x12: "SubFunctionNotSupported",
    0x13: "IncorrectMessageLengthOrInvalidFormat",
    0x14: "ResponseTooLong",
    0x21: "BusyRepeatRequest",
    0x22: "ConditionsNotCorrect",
    0x24: "RequestSequenceError",
    0x25: "NoResponseFromSubnetComponent",
    0x26: "FailurePreventsExecutionOfRequestedAction",
    0x31: "RequestOutOfRange",
    0x33: "SecurityAccessDenied",
    0x35: "InvalidKey",
    0x36: "ExceededNumberOfAttempts",
    0x37: "RequiredTimeDelayNotExpired",
    0x70: "UploadDownloadNotAccepted",
    0x71: "TransferDataSuspended",
    0x72: "GeneralProgrammingFailure",
    0x73: "WrongBlockSequenceCounter",
    0x78: "RequestCorrectlyReceivedResponsePending",
    0x7E: "SubFunctionNotSupportedInActiveSession",
    0x7F: "ServiceNotSupportedInActiveSession",
}


def uds_services_payload() -> list[dict[str, object]]:
    return [service.to_payload() for service in UDS_SERVICE_CATALOG]


def uds_decoder_backend() -> str:
    return "scapy" if scapy_uds_available() else "built-in"


@dataclass(slots=True, frozen=True)
class ReassembledUdsPdu:
    arbitration_id: int
    payload: bytes
    timestamp: float | None
    complete: bool = True


@dataclass(slots=True)
class _IsoTpReassemblyState:
    arbitration_id: int
    total_length: int
    payload: bytearray
    next_sequence_number: int
    timestamp: float | None


def uds_trace_transactions(frames: list[CanFrame], *, source: str) -> list[UdsTransactionEvent]:
    pending_requests: list[tuple[int, bytes]] = []
    events: list[UdsTransactionEvent] = []

    for pdu in reassemble_uds_pdus(frames):
        payload = pdu.payload
        if not payload:
            continue

        if _is_request_id(pdu.arbitration_id):
            pending_requests.append((pdu.arbitration_id, payload))
            continue

        if not _is_response_id(pdu.arbitration_id):
            continue

        request_index = _match_request_index(pending_requests, pdu.arbitration_id)
        if request_index is None:
            continue

        request_id, request_payload = pending_requests.pop(request_index)
        service, service_name = _response_service_info(payload)
        if service is None or service_name is None:
            continue

        events.append(
            UdsTransactionEvent(
                request_id=request_id,
                response_id=pdu.arbitration_id,
                service=service,
                service_name=service_name,
                request_data=request_payload,
                response_data=payload,
                complete=pdu.complete,
                ecu_address=pdu.arbitration_id,
                source=source,
                timestamp=pdu.timestamp,
            )
        )

    return enrich_uds_transactions(events)


def uds_scan_transactions(frames: list[CanFrame], *, source: str) -> list[UdsTransactionEvent]:
    request_id = 0x7DF
    request_payload = bytes.fromhex("1001")
    events: list[UdsTransactionEvent] = []

    for pdu in reassemble_uds_pdus(frames):
        if not _is_response_id(pdu.arbitration_id):
            continue
        payload = pdu.payload
        if not payload:
            continue

        service, service_name = _response_service_info(payload)
        if service is None or service_name is None:
            continue

        events.append(
            UdsTransactionEvent(
                request_id=request_id,
                response_id=pdu.arbitration_id,
                service=service,
                service_name=service_name,
                request_data=request_payload,
                response_data=payload,
                complete=pdu.complete,
                ecu_address=pdu.arbitration_id,
                source=source,
                timestamp=pdu.timestamp,
            )
        )

    return enrich_uds_transactions(events)


def enrich_uds_transactions(events: list[UdsTransactionEvent]) -> list[UdsTransactionEvent]:
    decoder = uds_decoder_backend()
    return [_enrich_uds_transaction(event, decoder=decoder) for event in events]


def _enrich_uds_transaction(event: UdsTransactionEvent, *, decoder: str) -> UdsTransactionEvent:
    request_summary: str | None = None
    response_summary: str | None = None

    if decoder == "scapy":
        request_decode = inspect_uds_payload(event.request_data) or {}
        response_decode = inspect_uds_payload(event.response_data) or {}
        request_summary = request_decode.get("summary")
        response_summary = response_decode.get("summary")

    negative_response_code: int | None = None
    negative_response_name: str | None = None
    if event.response_data[:1] == b"\x7f" and len(event.response_data) >= 3:
        negative_response_code = event.response_data[2]
        negative_response_name = UDS_NEGATIVE_RESPONSE_CODES.get(
            negative_response_code,
            f"ResponseCode0x{negative_response_code:02X}",
        )

    return replace(
        event,
        decoder=decoder,
        request_summary=request_summary,
        response_summary=response_summary,
        negative_response_code=negative_response_code,
        negative_response_name=negative_response_name,
    )


def diagnostic_session_control_request_frame(interface: str | None = None) -> CanFrame:
    return CanFrame(
        arbitration_id=0x7DF,
        data=bytes.fromhex("0210010000000000"),
        interface=interface,
    )


def reassemble_uds_pdus(frames: list[CanFrame]) -> list[ReassembledUdsPdu]:
    sessions: dict[int, _IsoTpReassemblyState] = {}
    pdus: list[ReassembledUdsPdu] = []

    for frame in sorted(frames, key=lambda candidate: candidate.timestamp or 0.0):
        payload = _transport_payload(frame)
        if payload is None:
            continue

        pci = payload[0] >> 4
        arbitration_id = frame.arbitration_id

        if pci == 0x0:
            _flush_incomplete_session(sessions, pdus, arbitration_id)
            single_frame_payload = _single_frame_payload(payload)
            if single_frame_payload:
                pdus.append(
                    ReassembledUdsPdu(
                        arbitration_id=arbitration_id,
                        payload=single_frame_payload,
                        timestamp=frame.timestamp,
                        complete=True,
                    )
                )
            continue

        if pci == 0x1:
            _flush_incomplete_session(sessions, pdus, arbitration_id)
            first_frame = _first_frame_state(arbitration_id, payload, timestamp=frame.timestamp)
            if first_frame is None:
                continue
            if len(first_frame.payload) >= first_frame.total_length:
                pdus.append(
                    ReassembledUdsPdu(
                        arbitration_id=arbitration_id,
                        payload=bytes(first_frame.payload[: first_frame.total_length]),
                        timestamp=frame.timestamp,
                        complete=True,
                    )
                )
                continue
            sessions[arbitration_id] = first_frame
            continue

        if pci == 0x2:
            session = sessions.get(arbitration_id)
            if session is None:
                continue
            sequence_number = payload[0] & 0x0F
            if sequence_number != session.next_sequence_number:
                _flush_incomplete_session(sessions, pdus, arbitration_id)
                continue
            session.payload.extend(payload[1:])
            session.timestamp = frame.timestamp
            if len(session.payload) >= session.total_length:
                pdus.append(
                    ReassembledUdsPdu(
                        arbitration_id=arbitration_id,
                        payload=bytes(session.payload[: session.total_length]),
                        timestamp=frame.timestamp,
                        complete=True,
                    )
                )
                del sessions[arbitration_id]
                continue
            session.next_sequence_number = (session.next_sequence_number + 1) & 0x0F
            continue

        if pci == 0x3:
            continue

    for arbitration_id in sorted(sessions):
        _flush_incomplete_session(sessions, pdus, arbitration_id)

    return pdus


def _transport_payload(frame: CanFrame) -> bytes | None:
    if frame.is_extended_id or frame.is_remote_frame or frame.is_error_frame or not frame.data:
        return None
    return frame.data


def _single_frame_payload(data: bytes) -> bytes | None:
    payload_length = data[0] & 0x0F
    if payload_length == 0:
        return None
    available = data[1 : 1 + payload_length]
    if len(available) < payload_length:
        return None
    return bytes(available)


def _first_frame_state(
    arbitration_id: int,
    data: bytes,
    *,
    timestamp: float | None,
) -> _IsoTpReassemblyState | None:
    if len(data) < 2:
        return None
    total_length = ((data[0] & 0x0F) << 8) | data[1]
    if total_length == 0:
        return None
    return _IsoTpReassemblyState(
        arbitration_id=arbitration_id,
        total_length=total_length,
        payload=bytearray(data[2:]),
        next_sequence_number=1,
        timestamp=timestamp,
    )


def _flush_incomplete_session(
    sessions: dict[int, _IsoTpReassemblyState],
    pdus: list[ReassembledUdsPdu],
    arbitration_id: int,
) -> None:
    session = sessions.pop(arbitration_id, None)
    if session is None or not session.payload:
        return
    pdus.append(
        ReassembledUdsPdu(
            arbitration_id=arbitration_id,
            payload=bytes(session.payload[: session.total_length]),
            timestamp=session.timestamp,
            complete=False,
        )
    )


def _is_request_id(arbitration_id: int) -> bool:
    return arbitration_id == 0x7DF or 0x7E0 <= arbitration_id <= 0x7E7


def _is_response_id(arbitration_id: int) -> bool:
    return 0x7E8 <= arbitration_id <= 0x7EF


def _match_request_index(pending_requests: list[tuple[int, bytes]], response_id: int) -> int | None:
    expected_request_id = response_id - 0x8
    for index in range(len(pending_requests) - 1, -1, -1):
        request_id, _ = pending_requests[index]
        if request_id == expected_request_id or request_id == 0x7DF:
            return index
    return None


def _response_service_info(payload: bytes) -> tuple[int | None, str | None]:
    response_sid = payload[0]
    if response_sid == 0x7F and len(payload) >= 2:
        service = payload[1]
    elif response_sid >= 0x40:
        service = response_sid - 0x40
    else:
        return None, None

    for uds_service in UDS_SERVICE_CATALOG:
        if uds_service.service == service:
            return service, uds_service.name
    return service, f"Service0x{service:02X}"
