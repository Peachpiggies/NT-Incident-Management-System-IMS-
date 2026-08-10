"""Integration seam for asynchronous attachment malware scanning.

Uploads are quarantined as ``PENDING`` until a scanner reports ``CLEAN``.
Deployments can replace ``submit_attachment_for_scan`` with a ClamAV, S3 event,
or queue implementation without changing the attachment API.
"""

from dataclasses import dataclass
from typing import Literal, Protocol

from app.db.models import TicketAttachment

ScanStatus = Literal["PENDING", "CLEAN", "INFECTED", "FAILED"]


@dataclass(frozen=True)
class ScanSubmission:
    status: ScanStatus
    detail: str | None = None


class VirusScanner(Protocol):
    async def submit(self, attachment: TicketAttachment) -> ScanSubmission: ...


class DeferredVirusScanner:
    """Safe default: store quarantine state until an async scanner consumes it."""

    async def submit(self, attachment: TicketAttachment) -> ScanSubmission:
        return ScanSubmission(status="PENDING", detail="Awaiting virus scan")


scanner: VirusScanner = DeferredVirusScanner()


async def submit_attachment_for_scan(attachment: TicketAttachment) -> ScanSubmission:
    return await scanner.submit(attachment)
