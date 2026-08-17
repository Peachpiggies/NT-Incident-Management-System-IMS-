"""
Vendor Management schemas.

Pydantic models for vendors, contracts, vendor SLAs, vendor
contacts, vendor-linked incidents, and vendor performance scoring.
"""

from datetime import date, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

# ==========================================================
# Enums
# ==========================================================


class ContractStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PENDING_RENEWAL = "PENDING_RENEWAL"
    EXPIRED = "EXPIRED"
    TERMINATED = "TERMINATED"


class VendorIncidentStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


# ==========================================================
# Vendor
# ==========================================================


class VendorBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    category: str = Field(..., min_length=2, max_length=100, description="e.g. 'Hardware', 'Cloud', 'ISP'")
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(None, max_length=30)
    address: str | None = Field(None, max_length=500)
    is_active: bool = True


class VendorCreate(VendorBase):
    pass


class VendorUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=200)
    category: str | None = Field(None, min_length=2, max_length=100)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(None, max_length=30)
    address: str | None = Field(None, max_length=500)
    is_active: bool | None = None


class VendorSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    category: str
    is_active: bool


class VendorResponse(VendorBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class VendorListResponse(BaseModel):
    items: list[VendorResponse]
    total: int
    page: int
    page_size: int


# ==========================================================
# Contract
# ==========================================================


class VendorContractBase(BaseModel):
    vendor_id: UUID
    contract_no: str = Field(..., min_length=2, max_length=100)
    start_date: date
    end_date: date
    value: float | None = Field(None, ge=0)
    currency: str = Field("USD", min_length=3, max_length=3)
    terms: str | None = Field(None, max_length=4000)

    @model_validator(mode="after")
    def _check_dates(self) -> "VendorContractBase":
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


class VendorContractCreate(VendorContractBase):
    pass


class VendorContractUpdate(BaseModel):
    end_date: date | None = None
    value: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    terms: str | None = Field(None, max_length=4000)
    status: ContractStatus | None = None


class VendorContractResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vendor: VendorSummary
    contract_no: str
    start_date: date
    end_date: date
    value: float | None = None
    currency: str
    status: ContractStatus
    terms: str | None = None
    created_at: datetime
    updated_at: datetime


class VendorContractListResponse(BaseModel):
    items: list[VendorContractResponse]
    total: int
    page: int
    page_size: int


# ==========================================================
# Vendor SLA
# ==========================================================


class VendorSLABase(BaseModel):
    contract_id: UUID
    metric_name: str = Field(..., min_length=2, max_length=150, description="e.g. 'Uptime', 'Response Time'")
    target_value: float
    unit: str = Field(..., min_length=1, max_length=30, description="e.g. '%', 'hours'")
    measurement_period: str = Field("MONTHLY", max_length=30, description="e.g. 'MONTHLY', 'QUARTERLY'")


class VendorSLACreate(VendorSLABase):
    pass


class VendorSLAUpdate(BaseModel):
    metric_name: str | None = Field(None, min_length=2, max_length=150)
    target_value: float | None = None
    unit: str | None = Field(None, min_length=1, max_length=30)
    measurement_period: str | None = Field(None, max_length=30)


class VendorSLAResponse(VendorSLABase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


# ==========================================================
# Vendor Contact
# ==========================================================


class VendorContactBase(BaseModel):
    vendor_id: UUID
    name: str = Field(..., min_length=1, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=30)
    role: str | None = Field(None, max_length=100, description="e.g. 'Account Manager'")
    is_primary: bool = False


class VendorContactCreate(VendorContactBase):
    pass


class VendorContactUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=30)
    role: str | None = Field(None, max_length=100)
    is_primary: bool | None = None


class VendorContactResponse(VendorContactBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


# ==========================================================
# Vendor Incident
# ==========================================================
# Links a ticket to the vendor responsible (or partly responsible) for it,
# e.g. an ISP outage ticket linked to the ISP vendor.


class VendorIncidentBase(BaseModel):
    vendor_id: UUID
    ticket_id: UUID
    description: str = Field(..., min_length=5, max_length=2000)


class VendorIncidentCreate(VendorIncidentBase):
    pass


class VendorIncidentUpdate(BaseModel):
    status: VendorIncidentStatus | None = None
    resolved_at: datetime | None = None
    notes: str | None = Field(None, max_length=2000)


class VendorIncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vendor: VendorSummary
    ticket_id: UUID
    description: str
    status: VendorIncidentStatus
    reported_at: datetime
    resolved_at: datetime | None = None
    notes: str | None = None


class VendorIncidentListResponse(BaseModel):
    items: list[VendorIncidentResponse]
    total: int
    page: int
    page_size: int


# ==========================================================
# Vendor Performance
# ==========================================================


class VendorPerformanceBase(BaseModel):
    vendor_id: UUID
    period_start: date
    period_end: date
    sla_met_percent: float = Field(..., ge=0, le=100)
    incident_count: int = Field(0, ge=0)
    avg_resolution_hours: float | None = Field(None, ge=0)
    score: float | None = Field(None, ge=0, le=100, description="Overall vendor score for the period")
    notes: str | None = Field(None, max_length=2000)

    @model_validator(mode="after")
    def _check_period(self) -> "VendorPerformanceBase":
        if self.period_end <= self.period_start:
            raise ValueError("period_end must be after period_start")
        return self


class VendorPerformanceCreate(VendorPerformanceBase):
    pass


class VendorPerformanceResponse(VendorPerformanceBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class VendorPerformanceListResponse(BaseModel):
    items: list[VendorPerformanceResponse]
    total: int
    page: int
    page_size: int
