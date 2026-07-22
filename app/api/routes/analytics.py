"""Analytics routes."""

from typing import Annotated, List
from uuid import UUID
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.db import get_db
from app.models.database import Session, SessionAnalytics, User, Scenario
from app.models.schemas import (
    SessionAnalyticsResponse,
    UserPerformanceSummary,
    SessionResponse,
    BehaviorMarkers,
    SentimentDataPoint,
    ErrorResponse,
    UserRole,
    SkillScores,
)
from app.core.analytics_service import analytics_service
from app.api.routes.auth import get_current_user, require_manager

router = APIRouter()


@router.get(
    "/sessions/{session_id}",
    response_model=SessionAnalyticsResponse,
    responses={404: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def get_session_analytics(
    session_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionAnalyticsResponse:
    """Get detailed analytics for a session."""
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="セッションが見つかりません",
        )

    if session.user_id != current_user.id and current_user.role == UserRole.REP.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="このセッションのアナリティクスは表示できません",
        )

    result = await db.execute(
        select(SessionAnalytics).where(SessionAnalytics.session_id == session_id)
    )
    analytics = result.scalar_one_or_none()

    if not analytics:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analytics not found for this session",
        )

    behavior_markers = None
    if analytics.behavior_markers:
        try:
            behavior_markers = BehaviorMarkers(**analytics.behavior_markers)
        except Exception:
            behavior_markers = BehaviorMarkers()

    sentiment_timeline = None
    if analytics.sentiment_timeline:
        try:
            sentiment_timeline = [
                SentimentDataPoint(**point) for point in analytics.sentiment_timeline
            ]
        except Exception:
            sentiment_timeline = []

    return SessionAnalyticsResponse(
        id=analytics.id,
        session_id=analytics.session_id,
        rep_talk_time_seconds=analytics.rep_talk_time_seconds,
        ai_talk_time_seconds=analytics.ai_talk_time_seconds,
        talk_listen_ratio=analytics.talk_listen_ratio,
        total_turns=analytics.total_turns,
        rep_turns=analytics.rep_turns,
        ai_turns=analytics.ai_turns,
        avg_rep_response_time_ms=analytics.avg_rep_response_time_ms,
        interruption_count=analytics.interruption_count,
        objection_handling_score=analytics.objection_handling_score,
        question_quality_score=analytics.question_quality_score,
        confidence_score=analytics.confidence_score,
        professionalism_score=analytics.professionalism_score,
        persuasiveness_score=analytics.persuasiveness_score,
        goal_completion=analytics.goal_completion,
        behavior_markers=behavior_markers,
        sentiment_timeline=sentiment_timeline,
        created_at=analytics.created_at,
    )


@router.get(
    "/user/{user_id}/summary",
    response_model=UserPerformanceSummary,
    responses={404: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def get_user_performance_summary(
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserPerformanceSummary:
    """Get performance summary for a user."""
    if (
        user_id != current_user.id
        and current_user.role not in (UserRole.MANAGER.value, UserRole.ADMIN.value)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot view performance for this user",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    result = await db.execute(
        select(
            func.count(Session.id).label("total"),
            func.count(Session.id).filter(Session.status == "completed").label("completed"),
            func.avg(Session.overall_score).label("avg_score"),
        )
        .where(Session.user_id == user_id)
    )
    stats_row = result.one()
    total_sessions = stats_row.total or 0
    completed_sessions = stats_row.completed or 0
    average_score = Decimal(str(stats_row.avg_score)) if stats_row.avg_score else None

    result = await db.execute(
        select(
            func.avg(SessionAnalytics.talk_listen_ratio).label("avg_talk_listen"),
            func.avg(SessionAnalytics.objection_handling_score).label("avg_objection"),
            func.avg(SessionAnalytics.confidence_score).label("avg_confidence"),
            func.count(SessionAnalytics.id).filter(SessionAnalytics.goal_completion).label("goals_met"),
            func.count(SessionAnalytics.id).label("total_analytics"),
        )
        .join(Session, Session.id == SessionAnalytics.session_id)
        .where(Session.user_id == user_id)
    )
    analytics_row = result.one_or_none()

    avg_talk_listen = None
    avg_objection = None
    avg_confidence = None
    goal_completion_rate = None

    if analytics_row:
        if analytics_row.avg_talk_listen:
            avg_talk_listen = Decimal(str(analytics_row.avg_talk_listen))
        if analytics_row.avg_objection:
            avg_objection = Decimal(str(analytics_row.avg_objection))
        if analytics_row.avg_confidence:
            avg_confidence = Decimal(str(analytics_row.avg_confidence))
        if analytics_row.total_analytics > 0:
            goal_completion_rate = Decimal(str(analytics_row.goals_met / analytics_row.total_analytics))

    result = await db.execute(
        select(Session)
        .options(selectinload(Session.scenario).selectinload(Scenario.persona))
        .where(Session.user_id == user_id)
        .order_by(Session.created_at.desc())
        .limit(5)
    )
    recent_sessions = result.scalars().all()

    try:
        skills = await analytics_service.calculate_skill_scores(user_id, db)
    except Exception:
        skills = SkillScores()

    try:
        milestones = await analytics_service.get_milestone_progress(user_id, db)
    except Exception:
        milestones = []

    try:
        focus_recommendation = await analytics_service.generate_focus_recommendation(
            user_id, skills, db
        )
    except Exception:
        focus_recommendation = None

    return UserPerformanceSummary(
        user_id=user_id,
        total_sessions=total_sessions,
        completed_sessions=completed_sessions,
        average_score=average_score,
        avg_talk_listen_ratio=avg_talk_listen,
        avg_objection_handling=avg_objection,
        avg_confidence_score=avg_confidence,
        goal_completion_rate=goal_completion_rate,
        improvement_trend=None,  # TODO: Calculate trend from recent sessions
        recent_sessions=[SessionResponse.model_validate(s) for s in recent_sessions],
        skills=skills,
        milestones=milestones,
        focus_recommendation=focus_recommendation,
    )


@router.get(
    "/team",
    response_model=List[UserPerformanceSummary],
    responses={403: {"model": ErrorResponse}},
)
async def get_team_performance(
    current_user: Annotated[User, Depends(require_manager)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=20, le=50),
) -> List[UserPerformanceSummary]:
    """Get performance summary for team members (managers only)."""
    query = select(User).where(User.role == UserRole.REP.value)

    if current_user.company_id:
        query = query.where(User.company_id == current_user.company_id)

    query = query.limit(limit)

    result = await db.execute(query)
    reps = result.scalars().all()

    stats_query = (
        select(
            User.id,
            func.count(Session.id).label("total"),
            func.count(Session.id).filter(Session.status == "completed").label("completed"),
            func.avg(Session.overall_score).label("avg_score")
        )
        .outerjoin(Session, Session.user_id == User.id)
        .where(User.id.in_([rep.id for rep in reps]))
        .group_by(User.id)
    )

    result = await db.execute(stats_query)
    stats_map = {row.id: row for row in result}

    summaries = []
    for rep in reps:
        row = stats_map.get(rep.id)
        
        summaries.append(
            UserPerformanceSummary(
                user_id=rep.id,
                total_sessions=row.total if row else 0,
                completed_sessions=row.completed if row else 0,
                average_score=Decimal(str(row.avg_score)) if row and row.avg_score else None,
                avg_talk_listen_ratio=None,
                avg_objection_handling=None,
                avg_confidence_score=None,
                goal_completion_rate=None,
                improvement_trend=None,
                recent_sessions=[],
            )
        )

    return summaries