"""UDS protocol helpers."""

from __future__ import annotations

from dataclasses import dataclass

from canarchy.models import CanFrame, UdsTransactionEvent


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


def uds_services_payload() -> list[dict[str, object]]:
    return [service.to_payload() for service in UDS_SERVICE_CATALOG]


def uds_trace_transactions(frames: list[CanFrame], *, source: str) -> list[UdsTransactionEvent]:
    pending_requests: list[tuple[int, bytes]] = []
    events: list[UdsTransactionEvent] = []

    for frame in sorted(frames, key=lambda candidate: candidate.timestamp or 0.0):
        payload = _single_frame_payload(frame)
        if payload is None or not payload:
            continue

        if _is_request_id(frame.arbitration_id):
            pending_requests.append((frame.arbitration_id, payload))
            continue

        if not _is_response_id(frame.arbitration_id):
            continue

        request_index = _match_request_index(pending_requests, frame.arbitration_id)
        if request_index is None:
            continue

        request_id, request_payload = pending_requests.pop(request_index)
        service, service_name = _response_service_info(payload)
        if service is None or service_name is None:
            continue

        events.append(
            UdsTransactionEvent(
                request_id=request_id,
                response_id=frame.arbitration_id,
                service=service,
                service_name=service_name,
                request_data=request_payload,
                response_data=payload,
                ecu_address=frame.arbitration_id,
                source=source,
                timestamp=frame.timestamp,
            )
        )

    return events


def uds_scan_transactions(frames: list[CanFrame], *, source: str) -> list[UdsTransactionEvent]:
    request_id = 0x7DF
    request_payload = bytes.fromhex("1001")
    events: list[UdsTransactionEvent] = []

    for frame in sorted(frames, key=lambda candidate: candidate.timestamp or 0.0):
        if not _is_response_id(frame.arbitration_id):
            continue
        payload = _single_frame_payload(frame)
        if payload is None or not payload:
            continue

        service, service_name = _response_service_info(payload)
        if service is None or service_name is None:
            continue

        events.append(
            UdsTransactionEvent(
                request_id=request_id,
                response_id=frame.arbitration_id,
                service=service,
                service_name=service_name,
                request_data=request_payload,
                response_data=payload,
                ecu_address=frame.arbitration_id,
                source=source,
                timestamp=frame.timestamp,
            )
        )

    return events


def diagnostic_session_control_request_frame(interface: str | None = None) -> CanFrame:
    return CanFrame(
        arbitration_id=0x7DF,
        data=bytes.fromhex("0210010000000000"),
        interface=interface,
    )


def _single_frame_payload(frame: CanFrame) -> bytes | None:
    if frame.is_extended_id or frame.is_remote_frame or frame.is_error_frame or not frame.data:
        return None
    pci = frame.data[0] >> 4
    if pci != 0:
        return None
    payload_length = frame.data[0] & 0x0F
    if payload_length == 0:
        return None
    available = frame.data[1 : 1 + payload_length]
    if len(available) < payload_length:
        return None
    return bytes(available)


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
