from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_admin
from app.db.session import get_db
from app.models import SystemUser

DBSessionDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[SystemUser, Depends(get_current_user)]
AdminUserDep = Annotated[SystemUser, Depends(require_admin)]

__all__ = ["AdminUserDep", "CurrentUserDep", "DBSessionDep", "get_db"]
