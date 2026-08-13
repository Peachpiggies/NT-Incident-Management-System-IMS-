"""
Reference/lookup schemas package.

Re-exports schemas for entities that are mostly used as lookups or
foreign-key references from other schemas (users, roles, departments,
priorities, statuses, categories).
"""

from app.schemas.references.category import (

    CategoryCreate,

    CategoryListResponse,

    CategoryResponse,

    CategoryUpdate,

)

from app.schemas.references.department import (

    DepartmentCreate,

    DepartmentListResponse,

    DepartmentResponse,

    DepartmentUpdate,

)

from app.schemas.references.priority import (

    PriorityCreate,

    PriorityListResponse,

    PriorityResponse,

    PriorityUpdate,

)

from app.schemas.references.role import (

    RoleBrief,

    RoleCreate,

    RoleListResponse,

    RoleRequest,

    RoleResponse,

    RoleUpdate,

)

from app.schemas.references.service import (

    ServiceBrief,

    ServiceCreate,

    ServiceListResponse,

    ServiceResponse,

    ServiceUpdate,

)

from app.schemas.references.status import (

    StatusCreate,

    StatusListResponse,

    StatusResponse,

    StatusUpdate,

)

from app.schemas.references.subcategory import (

    SubcategoryBrief,

    SubcategoryCreate,

    SubcategoryListResponse,

    SubcategoryResponse,

    SubcategoryUpdate,

)

from app.schemas.references.user import (

    UserCreate,

    UserCreateRequest,

    UserListResponse,

    UserResponse,

    UserUpdate,

    UserUpdateRequest,

)

__all__ = [
    
    # category
    "CategoryCreate",
    "CategoryListResponse",
    "CategoryResponse",
    "CategoryUpdate",
    
    # department
    "DepartmentCreate",
    "DepartmentListResponse",
    "DepartmentResponse",
    "DepartmentUpdate",
    
    # priority
    "PriorityCreate",
    "PriorityListResponse",
    "PriorityResponse",
    "PriorityUpdate",
    
    # role
    "RoleBrief",
    "RoleCreate",
    "RoleListResponse",
    "RoleRequest",
    "RoleResponse",
    "RoleUpdate",
    
    # service
    "ServiceBrief",
    "ServiceCreate",
    "ServiceListResponse",
    "ServiceResponse",
    "ServiceUpdate",
    
    # status
    "StatusCreate",
    "StatusListResponse",
    "StatusResponse",
    "StatusUpdate",
    
    # subcategory
    "SubcategoryBrief",
    "SubcategoryCreate",
    "SubcategoryListResponse",
    "SubcategoryResponse",
    "SubcategoryUpdate",
    
    # user
    "UserCreate",
    "UserCreateRequest",
    "UserListResponse",
    "UserResponse",
    "UserUpdate",
    "UserUpdateRequest",
    
]