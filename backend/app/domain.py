"""backend/app/domain.py

Provide StrEnum compatibility for Python 3.10 and 3.11+.
"""

# Python >= 3.11 provides StrEnum; fall back on 3.10
try:
    from enum import StrEnum
except ImportError:
    from enum import Enum

    class StrEnum(str, Enum):
        pass


class Role(StrEnum):
    CUSTOMER = "customer"
    TIER1 = "tier1"
    TIER2 = "tier2"
    MANAGER = "manager"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
