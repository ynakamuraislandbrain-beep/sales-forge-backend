"""Persona management routes."""

from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.database import Persona, User
from app.models.schemas import (
    PersonaCreate,
    PersonaResponse,
    PersonaSummary,
    PersonaUpdate,
    ErrorResponse,
)
from app.api.routes.auth import get_current_user, require_admin

router = APIRouter()


@router.get(
    "",
    response_model=List[PersonaSummary],
)
async def list_personas(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> List[PersonaSummary]:
    """List all personas."""
    result = await db.execute(select(Persona).order_by(Persona.name))
    personas = result.scalars().all()

    return [PersonaSummary.model_validate(p) for p in personas]


@router.get(
    "/{persona_id}",
    response_model=PersonaResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_persona(
    persona_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PersonaResponse:
    """Get persona details by ID."""
    result = await db.execute(select(Persona).where(Persona.id == persona_id))
    persona = result.scalar_one_or_none()

    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ペルソナが見つかりません",
        )

    return PersonaResponse.model_validate(persona)


@router.post(
    "",
    response_model=PersonaResponse,
    status_code=status.HTTP_201_CREATED,
    responses={403: {"model": ErrorResponse}},
)
async def create_persona(
    persona_data: PersonaCreate,
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PersonaResponse:
    """Create a new persona (admin only)."""
    persona = Persona(
        name=persona_data.name,
        title=persona_data.title,
        company=persona_data.company,
        industry=persona_data.industry,
        traits=persona_data.traits,
        default_mood=persona_data.default_mood,
        system_prompt_template=persona_data.system_prompt_template,
        voice_profile=persona_data.voice_profile.model_dump() if persona_data.voice_profile else None,
        behavior_config=persona_data.behavior_config.model_dump() if persona_data.behavior_config else None,
    )
    db.add(persona)
    await db.flush()
    await db.refresh(persona)

    return PersonaResponse.model_validate(persona)


@router.put(
    "/{persona_id}",
    response_model=PersonaResponse,
    responses={404: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def update_persona(
    persona_id: UUID,
    update_data: PersonaUpdate,
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PersonaResponse:
    """Update persona (admin only)."""
    result = await db.execute(select(Persona).where(Persona.id == persona_id))
    persona = result.scalar_one_or_none()

    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ペルソナが見つかりません",
        )

    update_dict = update_data.model_dump(exclude_unset=True)

    if "voice_profile" in update_dict and update_dict["voice_profile"]:
        update_dict["voice_profile"] = update_dict["voice_profile"].model_dump() if hasattr(update_dict["voice_profile"], "model_dump") else update_dict["voice_profile"]
    if "behavior_config" in update_dict and update_dict["behavior_config"]:
        update_dict["behavior_config"] = update_dict["behavior_config"].model_dump() if hasattr(update_dict["behavior_config"], "model_dump") else update_dict["behavior_config"]

    for field, value in update_dict.items():
        setattr(persona, field, value)

    await db.flush()
    await db.refresh(persona)

    return PersonaResponse.model_validate(persona)


@router.delete(
    "/{persona_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def delete_persona(
    persona_id: UUID,
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete persona (admin only)."""
    result = await db.execute(select(Persona).where(Persona.id == persona_id))
    persona = result.scalar_one_or_none()

    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ペルソナが見つかりません",
        )

    await db.delete(persona)
