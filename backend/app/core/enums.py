from enum import Enum


class TicketSource(str, Enum):
    WEB = "WEB"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    API = "API"
    MONITORING = "MONITORING"
    SYSTEM = "SYSTEM"