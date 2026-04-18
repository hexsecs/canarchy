"""UDS protocol helpers."""

from __future__ import annotations

from dataclasses import dataclass


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
