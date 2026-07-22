"""Scenario management routes."""

from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.models.database import Scenario, Persona, User
from app.models.schemas import (
    ScenarioCreate,
    ScenarioResponse,
    ScenarioCard,
    ScenarioUpdate,
    ScenarioCategory,
    ScenarioDifficulty,
    ScenarioType,
    PersonaSummary,
    ErrorResponse,
)
from app.api.routes.auth import get_current_user, require_admin

router = APIRouter()


@router.get(
    "",
    response_model=List[ScenarioCard],
)
async def list_scenarios(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    category: ScenarioCategory | None = None,
    type: ScenarioType | None = None,
    difficulty: ScenarioDifficulty | None = None,
    include_locked: bool = Query(default=False, description="Include locked scenarios"),
) -> List[ScenarioCard]:
    """List available scenarios with optional filters."""
    query = (
        select(Scenario)
        .options(selectinload(Scenario.persona))
        .where(Scenario.is_active)
    )

    if not include_locked:
        query = query.where(~Scenario.is_locked)

    if category:
        query = query.where(Scenario.category == category.value)
    if type:
        query = query.where(Scenario.type == type.value)
    if difficulty:
        query = query.where(Scenario.difficulty == difficulty.value)

    query = query.order_by(Scenario.category, Scenario.difficulty)

    result = await db.execute(query)
    scenarios = result.scalars().all()

    cards = []
    for s in scenarios:
        persona_summary = None
        if s.persona:
            persona_summary = PersonaSummary(
                id=s.persona.id,
                name=s.persona.name,
                title=s.persona.title,
                company=s.persona.company,
                traits=s.persona.traits,
                default_mood=s.persona.default_mood,
            )

        cards.append(
            ScenarioCard(
                id=s.id,
                name=s.name,
                type=s.type,
                difficulty=s.difficulty,
                category=s.category,
                book_rate=s.book_rate,
                is_locked=s.is_locked,
                persona=persona_summary,
            )
        )

    return cards


@router.get(
    "/{scenario_id}",
    response_model=ScenarioResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_scenario(
    scenario_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ScenarioResponse:
    """Get scenario details with persona information."""
    result = await db.execute(
        select(Scenario)
        .options(selectinload(Scenario.persona))
        .where(Scenario.id == scenario_id)
    )
    scenario = result.scalar_one_or_none()

    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="シナリオが見つかりません",
        )

    persona_summary = None
    if scenario.persona:
        persona_summary = PersonaSummary(
            id=scenario.persona.id,
            name=scenario.persona.name,
            title=scenario.persona.title,
            company=scenario.persona.company,
            traits=scenario.persona.traits,
            default_mood=scenario.persona.default_mood,
        )

    return ScenarioResponse(
        id=scenario.id,
        persona_id=scenario.persona_id,
        name=scenario.name,
        type=scenario.type,
        difficulty=scenario.difficulty,
        category=scenario.category,
        instructions=scenario.instructions,
        scenario_rules=scenario.scenario_rules,
        success_criteria=scenario.success_criteria,
        book_rate=scenario.book_rate,
        is_active=scenario.is_active,
        is_locked=scenario.is_locked,
        prior_context=scenario.prior_context,
        persona=persona_summary,
        created_at=scenario.created_at,
        updated_at=scenario.updated_at,
    )


@router.post(
    "",
    response_model=ScenarioResponse,
    status_code=status.HTTP_201_CREATED,
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def create_scenario(
    scenario_data: ScenarioCreate,
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ScenarioResponse:
    """Create a new scenario (admin only)."""
    result = await db.execute(select(Persona).where(Persona.id == scenario_data.persona_id))
    persona = result.scalar_one_or_none()

    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Persona not found",
        )

    scenario = Scenario(
        persona_id=scenario_data.persona_id,
        name=scenario_data.name,
        type=scenario_data.type.value,
        difficulty=scenario_data.difficulty.value,
        category=scenario_data.category.value,
        instructions=scenario_data.instructions,
        scenario_rules=scenario_data.scenario_rules,
        success_criteria=scenario_data.success_criteria.model_dump(),
        book_rate=scenario_data.book_rate,
        prior_context=scenario_data.prior_context.model_dump() if scenario_data.prior_context else None,
    )
    db.add(scenario)
    await db.flush()
    await db.refresh(scenario)

    persona_summary = PersonaSummary(
        id=persona.id,
        name=persona.name,
        title=persona.title,
        company=persona.company,
        traits=persona.traits,
        default_mood=persona.default_mood,
    )

    return ScenarioResponse(
        id=scenario.id,
        persona_id=scenario.persona_id,
        name=scenario.name,
        type=scenario.type,
        difficulty=scenario.difficulty,
        category=scenario.category,
        instructions=scenario.instructions,
        scenario_rules=scenario.scenario_rules,
        success_criteria=scenario.success_criteria,
        book_rate=scenario.book_rate,
        is_active=scenario.is_active,
        is_locked=scenario.is_locked,
        prior_context=scenario.prior_context,
        persona=persona_summary,
        created_at=scenario.created_at,
        updated_at=scenario.updated_at,
    )


@router.put(
    "/{scenario_id}",
    response_model=ScenarioResponse,
    responses={404: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def update_scenario(
    scenario_id: UUID,
    update_data: ScenarioUpdate,
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ScenarioResponse:
    """Update scenario (admin only)."""
    result = await db.execute(
        select(Scenario)
        .options(selectinload(Scenario.persona))
        .where(Scenario.id == scenario_id)
    )
    scenario = result.scalar_one_or_none()

    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="シナリオが見つかりません",
        )

    update_dict = update_data.model_dump(exclude_unset=True)

    if "success_criteria" in update_dict and update_dict["success_criteria"]:
        update_dict["success_criteria"] = update_dict["success_criteria"].model_dump() if hasattr(update_dict["success_criteria"], "model_dump") else update_dict["success_criteria"]

    for field, value in update_dict.items():
        setattr(scenario, field, value)

    await db.flush()
    await db.refresh(scenario)

    persona_summary = None
    if scenario.persona:
        persona_summary = PersonaSummary(
            id=scenario.persona.id,
            name=scenario.persona.name,
            title=scenario.persona.title,
            company=scenario.persona.company,
            traits=scenario.persona.traits,
            default_mood=scenario.persona.default_mood,
        )

    return ScenarioResponse(
        id=scenario.id,
        persona_id=scenario.persona_id,
        name=scenario.name,
        type=scenario.type,
        difficulty=scenario.difficulty,
        category=scenario.category,
        instructions=scenario.instructions,
        scenario_rules=scenario.scenario_rules,
        success_criteria=scenario.success_criteria,
        book_rate=scenario.book_rate,
        is_active=scenario.is_active,
        is_locked=scenario.is_locked,
        prior_context=scenario.prior_context,
        persona=persona_summary,
        created_at=scenario.created_at,
        updated_at=scenario.updated_at,
    )


@router.delete(
    "/{scenario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def delete_scenario(
    scenario_id: UUID,
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete scenario (admin only). Soft delete by setting is_active=False."""
    result = await db.execute(select(Scenario).where(Scenario.id == scenario_id))
    scenario = result.scalar_one_or_none()

    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="シナリオが見つかりません",
        )

    scenario.is_active = False
    await db.flush()
