"""User management routes."""

from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.database import User
from app.models.schemas import UserResponse, UserUpdate, ErrorResponse, UserRole
from app.api.routes.auth import get_current_user, require_manager

router = APIRouter()


@router.get(
    "",
    response_model=List[UserResponse],
    responses={403: {"model": ErrorResponse}},
)
async def list_users(
    current_user: Annotated[User, Depends(require_manager)],
    db: Annotated[AsyncSession, Depends(get_db)],
    role: UserRole | None = None,
) -> List[UserResponse]:
    """List users (managers only). Optionally filter by role."""
    query = select(User)

    if current_user.company_id:
        query = query.where(User.company_id == current_user.company_id)

    if role:
        query = query.where(User.role == role.value)

    query = query.order_by(User.name)

    result = await db.execute(query)
    users = result.scalars().all()

    return [UserResponse.model_validate(u) for u in users]


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_user(
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Get user details by ID."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ユーザーが見つかりません",
        )

    if current_user.role == UserRole.REP.value and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="他のユーザーの情報は表示できません",
        )

    return UserResponse.model_validate(user)


@router.put(
    "/{user_id}",
    response_model=UserResponse,
    responses={404: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def update_user(
    user_id: UUID,
    update_data: UserUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Update user details. Users can update themselves, managers can update their reps."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ユーザーが見つかりません",
        )

    can_update = (
        current_user.id == user_id  
        or current_user.role == UserRole.ADMIN.value  
        or (
            current_user.role == UserRole.MANAGER.value
            and user.company_id == current_user.company_id
        ) 
    )

    if not can_update:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="このユーザーは更新できません",
        )

    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(user, field, value)

    await db.flush()
    await db.refresh(user)

    return UserResponse.model_validate(user)