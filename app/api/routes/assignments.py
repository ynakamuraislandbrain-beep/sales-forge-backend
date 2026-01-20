"""Training assignment routes."""

from datetime import datetime, timezone
from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.models.database import TrainingAssignment, Scenario, User
from app.models.schemas import (
    AssignmentCreate,
    AssignmentResponse,
    AssignmentUpdate,
    AssignmentStatus,
    ScenarioCard,
    PersonaSummary,
    UserResponse,
    ErrorResponse,
    UserRole,
)
from app.api.routes.auth import get_current_user, require_manager

router = APIRouter()


@router.get(
    "",
    response_model=List[AssignmentResponse],
)
async def list_assignments(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: AssignmentStatus | None = Query(default=None, alias="status"),
    as_manager: bool = Query(default=False, description="List assignments created by current user"),
) -> List[AssignmentResponse]:
    """List training assignments for current user."""
    query = (
        select(TrainingAssignment)
        .options(
            selectinload(TrainingAssignment.scenario).selectinload(Scenario.persona),
            selectinload(TrainingAssignment.rep),
        )
        .order_by(TrainingAssignment.due_date.asc().nullslast())
    )

    if as_manager and current_user.role in (UserRole.MANAGER.value, UserRole.ADMIN.value):
        query = query.where(TrainingAssignment.manager_id == current_user.id)
    else:
        query = query.where(TrainingAssignment.rep_id == current_user.id)

    if status_filter:
        query = query.where(TrainingAssignment.status == status_filter.value)

    result = await db.execute(query)
    assignments = result.scalars().all()

    response = []
    for a in assignments:
        scenario_card = None
        if a.scenario:
            persona_summary = None
            if a.scenario.persona:
                persona_summary = PersonaSummary(
                    id=a.scenario.persona.id,
                    name=a.scenario.persona.name,
                    title=a.scenario.persona.title,
                    company=a.scenario.persona.company,
                    traits=a.scenario.persona.traits,
                    default_mood=a.scenario.persona.default_mood,
                )
            scenario_card = ScenarioCard(
                id=a.scenario.id,
                name=a.scenario.name,
                type=a.scenario.type,
                difficulty=a.scenario.difficulty,
                category=a.scenario.category,
                book_rate=a.scenario.book_rate,
                is_locked=a.scenario.is_locked,
                persona=persona_summary,
            )

        rep_response = None
        if a.rep:
            rep_response = UserResponse(
                id=a.rep.id,
                email=a.rep.email,
                name=a.rep.name,
                role=a.rep.role,
                avatar_url=a.rep.avatar_url,
                company_id=a.rep.company_id,
                created_at=a.rep.created_at,
                updated_at=a.rep.updated_at,
            )

        response.append(
            AssignmentResponse(
                id=a.id,
                manager_id=a.manager_id,
                rep_id=a.rep_id,
                scenario_id=a.scenario_id,
                due_date=a.due_date,
                status=a.status,
                notes=a.notes,
                scenario=scenario_card,
                rep=rep_response,
                created_at=a.created_at,
                updated_at=a.updated_at,
            )
        )

    return response


@router.get(
    "/{assignment_id}",
    response_model=AssignmentResponse,
    responses={404: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def get_assignment(
    assignment_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AssignmentResponse:
    """Get assignment details."""
    result = await db.execute(
        select(TrainingAssignment)
        .options(
            selectinload(TrainingAssignment.scenario).selectinload(Scenario.persona),
            selectinload(TrainingAssignment.rep),
        )
        .where(TrainingAssignment.id == assignment_id)
    )
    assignment = result.scalar_one_or_none()

    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found",
        )

    if (
        assignment.rep_id != current_user.id
        and assignment.manager_id != current_user.id
        and current_user.role != UserRole.ADMIN.value
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot view this assignment",
        )

    scenario_card = None
    if assignment.scenario:
        persona_summary = None
        if assignment.scenario.persona:
            persona_summary = PersonaSummary(
                id=assignment.scenario.persona.id,
                name=assignment.scenario.persona.name,
                title=assignment.scenario.persona.title,
                company=assignment.scenario.persona.company,
                traits=assignment.scenario.persona.traits,
                default_mood=assignment.scenario.persona.default_mood,
            )
        scenario_card = ScenarioCard(
            id=assignment.scenario.id,
            name=assignment.scenario.name,
            type=assignment.scenario.type,
            difficulty=assignment.scenario.difficulty,
            category=assignment.scenario.category,
            book_rate=assignment.scenario.book_rate,
            is_locked=assignment.scenario.is_locked,
            persona=persona_summary,
        )

    rep_response = None
    if assignment.rep:
        rep_response = UserResponse(
            id=assignment.rep.id,
            email=assignment.rep.email,
            name=assignment.rep.name,
            role=assignment.rep.role,
            avatar_url=assignment.rep.avatar_url,
            company_id=assignment.rep.company_id,
            created_at=assignment.rep.created_at,
            updated_at=assignment.rep.updated_at,
        )

    return AssignmentResponse(
        id=assignment.id,
        manager_id=assignment.manager_id,
        rep_id=assignment.rep_id,
        scenario_id=assignment.scenario_id,
        due_date=assignment.due_date,
        status=assignment.status,
        notes=assignment.notes,
        scenario=scenario_card,
        rep=rep_response,
        created_at=assignment.created_at,
        updated_at=assignment.updated_at,
    )


@router.post(
    "",
    response_model=AssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def create_assignment(
    assignment_data: AssignmentCreate,
    current_user: Annotated[User, Depends(require_manager)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AssignmentResponse:
    """Create a new training assignment (manager only)."""
    result = await db.execute(select(User).where(User.id == assignment_data.rep_id))
    rep = result.scalar_one_or_none()

    if not rep:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rep not found",
        )

    result = await db.execute(
        select(Scenario)
        .options(selectinload(Scenario.persona))
        .where(Scenario.id == assignment_data.scenario_id)
    )
    scenario = result.scalar_one_or_none()

    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scenario not found",
        )

    assignment = TrainingAssignment(
        manager_id=current_user.id,
        rep_id=assignment_data.rep_id,
        scenario_id=assignment_data.scenario_id,
        due_date=assignment_data.due_date,
        notes=assignment_data.notes,
        status="pending",
    )
    db.add(assignment)
    await db.flush()
    await db.refresh(assignment)

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

    scenario_card = ScenarioCard(
        id=scenario.id,
        name=scenario.name,
        type=scenario.type,
        difficulty=scenario.difficulty,
        category=scenario.category,
        book_rate=scenario.book_rate,
        is_locked=scenario.is_locked,
        persona=persona_summary,
    )

    rep_response = UserResponse(
        id=rep.id,
        email=rep.email,
        name=rep.name,
        role=rep.role,
        avatar_url=rep.avatar_url,
        company_id=rep.company_id,
        created_at=rep.created_at,
        updated_at=rep.updated_at,
    )

    return AssignmentResponse(
        id=assignment.id,
        manager_id=assignment.manager_id,
        rep_id=assignment.rep_id,
        scenario_id=assignment.scenario_id,
        due_date=assignment.due_date,
        status=assignment.status,
        notes=assignment.notes,
        scenario=scenario_card,
        rep=rep_response,
        created_at=assignment.created_at,
        updated_at=assignment.updated_at,
    )


@router.put(
    "/{assignment_id}",
    response_model=AssignmentResponse,
    responses={404: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def update_assignment(
    assignment_id: UUID,
    update_data: AssignmentUpdate,
    current_user: Annotated[User, Depends(require_manager)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AssignmentResponse:
    """Update assignment (manager only)."""
    result = await db.execute(
        select(TrainingAssignment)
        .options(
            selectinload(TrainingAssignment.scenario).selectinload(Scenario.persona),
            selectinload(TrainingAssignment.rep),
        )
        .where(TrainingAssignment.id == assignment_id)
    )
    assignment = result.scalar_one_or_none()

    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found",
        )

    if (
        assignment.manager_id != current_user.id
        and current_user.role != UserRole.ADMIN.value
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot update this assignment",
        )

    update_dict = update_data.model_dump(exclude_unset=True)
    if "status" in update_dict:
        update_dict["status"] = update_dict["status"].value

    for field, value in update_dict.items():
        setattr(assignment, field, value)

    await db.flush()
    await db.refresh(assignment)

    scenario_card = None
    if assignment.scenario:
        persona_summary = None
        if assignment.scenario.persona:
            persona_summary = PersonaSummary(
                id=assignment.scenario.persona.id,
                name=assignment.scenario.persona.name,
                title=assignment.scenario.persona.title,
                company=assignment.scenario.persona.company,
                traits=assignment.scenario.persona.traits,
                default_mood=assignment.scenario.persona.default_mood,
            )
        scenario_card = ScenarioCard(
            id=assignment.scenario.id,
            name=assignment.scenario.name,
            type=assignment.scenario.type,
            difficulty=assignment.scenario.difficulty,
            category=assignment.scenario.category,
            book_rate=assignment.scenario.book_rate,
            is_locked=assignment.scenario.is_locked,
            persona=persona_summary,
        )

    rep_response = None
    if assignment.rep:
        rep_response = UserResponse(
            id=assignment.rep.id,
            email=assignment.rep.email,
            name=assignment.rep.name,
            role=assignment.rep.role,
            avatar_url=assignment.rep.avatar_url,
            company_id=assignment.rep.company_id,
            created_at=assignment.rep.created_at,
            updated_at=assignment.rep.updated_at,
        )

    return AssignmentResponse(
        id=assignment.id,
        manager_id=assignment.manager_id,
        rep_id=assignment.rep_id,
        scenario_id=assignment.scenario_id,
        due_date=assignment.due_date,
        status=assignment.status,
        notes=assignment.notes,
        scenario=scenario_card,
        rep=rep_response,
        created_at=assignment.created_at,
        updated_at=assignment.updated_at,
    )


@router.delete(
    "/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def delete_assignment(
    assignment_id: UUID,
    current_user: Annotated[User, Depends(require_manager)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete assignment (manager only)."""
    result = await db.execute(
        select(TrainingAssignment).where(TrainingAssignment.id == assignment_id)
    )
    assignment = result.scalar_one_or_none()

    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found",
        )

    if (
        assignment.manager_id != current_user.id
        and current_user.role != UserRole.ADMIN.value
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete this assignment",
        )

    await db.delete(assignment)