"""
Reference/lookup schemas package.

Re-exports schemas for entities that are mostly used as lookups or
foreign-key references from other schemas (users, roles, departments,
priorities, statuses, categories).
"""

from app.schemas.references.category import (
    CategoryBrief,
    CategoryCreate,
    CategoryListResponse,
    CategoryResponse,
    CategoryUpdate,
)
from app.schemas.references.department import (
    DepartmentBrief,
    DepartmentCreate,
    DepartmentListResponse,
    DepartmentResponse,
    DepartmentUpdate,
)
from app.schemas.references.priority import (
    PriorityBrief,
    PriorityCreate,
    PriorityListResponse,
    PriorityResponse,
    PriorityUpdate,
)
from app.schemas.references.role import (
    RoleBrief,
    RoleCreate,
    RoleListResponse,
    RoleResponse,
    RoleUpdate,
)
from app.schemas.references.status import (
    StatusBrief,
    StatusCreate,
    StatusListResponse,
    StatusResponse,
    StatusUpdate,
)
from app.schemas.references.user import (
    UserBrief,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserUpdate,
)

__all__ = [
    # category
    "CategoryBrief",
    "CategoryCreate",
    "CategoryListResponse",
    "CategoryResponse",
    "CategoryUpdate",
    # department
    "DepartmentBrief",
    "DepartmentCreate",
    "DepartmentListResponse",
    "DepartmentResponse",
    "DepartmentUpdate",
    # priority
    "PriorityBrief",
    "PriorityCreate",
    "PriorityListResponse",
    "PriorityResponse",
    "PriorityUpdate",
    # role
    "RoleBrief",
    "RoleCreate",
    "RoleListResponse",
    "RoleResponse",
    "RoleUpdate",
    # status
    "StatusBrief",
    "StatusCreate",
    "StatusListResponse",
    "StatusResponse",
    "StatusUpdate",
    # user
    "UserBrief",
    "UserCreate",
    "UserListResponse",
    "UserResponse",
    "UserUpdate",
]