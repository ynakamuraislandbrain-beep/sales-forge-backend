"""Analytics service for skill calculations, milestones, and focus recommendations."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import (
    Session,
    SessionAnalytics,
    ConversationState,
    Scenario,
    UserSkillScores,
    MilestoneDefinition,
    UserMilestone,
    Feedback,
)
from app.models.schemas import (
    SkillScores,
    Milestone,
    MilestoneCriteria,
    FocusRecommendation,
)


class AnalyticsService:
    """Service for computing analytics, skill scores, milestones, and recommendations."""

    SKILL_SCENARIO_MAP = {
        "closing_skills": ["cold_call", "demo"],
        "objection_handling": ["cold_call", "discovery"],
        "empathy_rapport": ["discovery", "coaching"],
        "discovery_efficiency": ["discovery"],
        "value_proposition": ["demo", "cold_call"],
    }

    async def calculate_skill_scores(
        self, user_id: UUID, db: AsyncSession
    ) -> SkillScores:
        """
        Calculate skill scores from session analytics and feedback data.
        
        Scoring logic:
        - closing_skills: goal_completion rate + persuasiveness_score
        - objection_handling: objection_handling_score from analytics
        - empathy_rapport: average rapport_level from conversation states
        - discovery_efficiency: question_quality_score from analytics
        - value_proposition: behavior_markers.clear_value_prop frequency
        """
        rapport_subquery = (
            select(func.avg(ConversationState.rapport_level))
            .join(Session, Session.id == ConversationState.session_id)
            .where(Session.user_id == user_id)
            .scalar_subquery()
        )

        result = await db.execute(
            select(
                func.avg(SessionAnalytics.objection_handling_score).label("avg_objection"),
                func.avg(SessionAnalytics.question_quality_score).label("avg_question"),
                func.avg(SessionAnalytics.persuasiveness_score).label("avg_persuasive"),
                func.avg(SessionAnalytics.confidence_score).label("avg_confidence"),
                func.count(SessionAnalytics.id).filter(SessionAnalytics.goal_completion == True).label("goals_met"),
                func.count(SessionAnalytics.id).label("total_sessions"),
                rapport_subquery.label("avg_rapport")
            )
            .join(Session, Session.id == SessionAnalytics.session_id)
            .where(Session.user_id == user_id, Session.status == "completed")
        )
        row = result.one_or_none()

        result = await db.execute(
            select(SessionAnalytics.behavior_markers)
            .join(Session, Session.id == SessionAnalytics.session_id)
            .where(
                Session.user_id == user_id,
                Session.status == "completed",
                SessionAnalytics.behavior_markers.isnot(None),
            )
        )
        behavior_rows = result.scalars().all()

        total_value_props = 0
        total_sessions_with_markers = 0
        for markers in behavior_rows:
            if markers and isinstance(markers, dict):
                total_value_props += markers.get("clear_value_prop", 0)
                total_sessions_with_markers += 1

        closing_skills = 0
        objection_handling = 0
        empathy_rapport = 0
        discovery_efficiency = 0
        value_proposition = 0

        avg_rapport = row.avg_rapport if row and row.avg_rapport else Decimal("0.5")

        if row and row.total_sessions > 0:
            goal_rate = (row.goals_met / row.total_sessions) * 100
            persuasive = float(row.avg_persuasive or 0)
            closing_skills = int(goal_rate * 0.6 + persuasive * 0.4)
            objection_handling = int(float(row.avg_objection or 0))
            discovery_efficiency = int(float(row.avg_question or 0))

        empathy_rapport = int(float(avg_rapport) * 100)

        if total_sessions_with_markers > 0:
            avg_value_prop = total_value_props / total_sessions_with_markers
            value_proposition = min(100, int((avg_value_prop / 3) * 100))

        skills = SkillScores(
            closing_skills=max(0, min(100, closing_skills)),
            objection_handling=max(0, min(100, objection_handling)),
            empathy_rapport=max(0, min(100, empathy_rapport)),
            discovery_efficiency=max(0, min(100, discovery_efficiency)),
            value_proposition=max(0, min(100, value_proposition)),
        )

        await self._cache_skill_scores(user_id, skills, db)

        return skills

    async def _cache_skill_scores(
        self, user_id: UUID, skills: SkillScores, db: AsyncSession
    ) -> None:
        """Cache calculated skill scores for future quick retrieval."""
        result = await db.execute(
            select(UserSkillScores).where(UserSkillScores.user_id == user_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.closing_skills = skills.closing_skills
            existing.objection_handling = skills.objection_handling
            existing.empathy_rapport = skills.empathy_rapport
            existing.discovery_efficiency = skills.discovery_efficiency
            existing.value_proposition = skills.value_proposition
            existing.last_calculated_at = datetime.utcnow()
        else:
            new_scores = UserSkillScores(
                user_id=user_id,
                closing_skills=skills.closing_skills,
                objection_handling=skills.objection_handling,
                empathy_rapport=skills.empathy_rapport,
                discovery_efficiency=skills.discovery_efficiency,
                value_proposition=skills.value_proposition,
            )
            db.add(new_scores)

        await db.commit()

    async def get_milestone_progress(
        self, user_id: UUID, db: AsyncSession
    ) -> List[Milestone]:
        """Get milestone progress for a user (Optimized)."""
        result = await db.execute(
            select(MilestoneDefinition).where(MilestoneDefinition.is_active == True)
        )
        definitions = result.scalars().all()
        if not definitions:
            return []

        result = await db.execute(
            select(UserMilestone).where(UserMilestone.user_id == user_id)
        )
        user_milestones_map = {m.milestone_id: m for m in result.scalars().all()}

        sessions_query = (
            select(
                Session.id,
                Session.overall_score,
                Session.status,
                Scenario.type.label("scenario_type"),
                Scenario.category.label("scenario_category"),
                SessionAnalytics.behavior_markers,
                (
                    select(ConversationState.rapport_level)
                    .where(ConversationState.session_id == Session.id)
                    .order_by(ConversationState.turn_number.desc())
                    .limit(1)
                    .scalar_subquery()
                ).label("final_rapport")
            )
            .join(Scenario, Scenario.id == Session.scenario_id)
            .outerjoin(SessionAnalytics, SessionAnalytics.session_id == Session.id)
            .where(Session.user_id == user_id, Session.status == "completed")
            .order_by(Session.created_at.desc())
        )
        
        result = await db.execute(sessions_query)
        session_data = result.all()

        milestones = []
        for definition in definitions:
            current_progress = self._calculate_milestone_progress_sync(
                definition, session_data
            )

            user_milestone = user_milestones_map.get(definition.id)
            if user_milestone:
                user_milestone.current_progress = current_progress
                if current_progress >= definition.criteria_target and not user_milestone.completed:
                    user_milestone.completed = True
                    user_milestone.completed_at = datetime.utcnow()
            else:
                completed = current_progress >= definition.criteria_target
                user_milestone = UserMilestone(
                    user_id=user_id,
                    milestone_id=definition.id,
                    current_progress=current_progress,
                    completed=completed,
                    completed_at=datetime.utcnow() if completed else None,
                )
                db.add(user_milestone)

            progress_pct = min(
                100, int((current_progress / definition.criteria_target) * 100) if definition.criteria_target > 0 else 100
            )

            milestones.append(
                Milestone(
                    id=str(definition.id),
                    title=definition.title,
                    description=definition.description,
                    progress=progress_pct,
                    completed=user_milestone.completed,
                    criteria=MilestoneCriteria(
                        type=definition.criteria_type,
                        target=definition.criteria_target,
                        current=current_progress,
                    ),
                )
            )

        await db.commit()
        return milestones

    def _calculate_milestone_progress_sync(
        self, definition: MilestoneDefinition, session_data: List[any]
    ) -> int:
        """Calculate progress from pre-fetched session data."""
        criteria_type = definition.criteria_type

        if criteria_type == "outbound_score_count":
            return sum(
                1 for s in session_data 
                if s.overall_score and s.overall_score >= 80 and s.scenario_category == "outbound"
            )

        elif criteria_type == "rapport_streak":
            streak = 0
            for s in session_data:
                if s.final_rapport and float(s.final_rapport) >= 0.9:
                    streak += 1
                else:
                    break
            return streak

        elif criteria_type == "discovery_count":
            return sum(1 for s in session_data if s.scenario_type == "discovery")

        elif criteria_type == "objection_handled":
            total = 0
            for s in session_data:
                if s.behavior_markers and isinstance(s.behavior_markers, dict):
                    total += s.behavior_markers.get("handled_objection", 0)
            return total

        elif criteria_type == "score_threshold":
            count = sum(1 for s in session_data if s.overall_score and s.overall_score >= definition.criteria_target)
            return 1 if count > 0 else 0

        return 0


    async def generate_focus_recommendation(
        self, user_id: UUID, skills: SkillScores, db: AsyncSession
    ) -> Optional[FocusRecommendation]:
        """Generate a personalized focus recommendation based on weakest skill."""
        skill_values = {
            "closing_skills": skills.closing_skills,
            "objection_handling": skills.objection_handling,
            "empathy_rapport": skills.empathy_rapport,
            "discovery_efficiency": skills.discovery_efficiency,
            "value_proposition": skills.value_proposition,
        }

        if all(v >= 70 for v in skill_values.values()):
            return None

        weak_skill = min(skill_values, key=skill_values.get)
        weak_value = skill_values[weak_skill]

        scenario_types = self.SKILL_SCENARIO_MAP.get(weak_skill, [])
        scenario = None
        if scenario_types:
            result = await db.execute(
                select(Scenario)
                .where(
                    Scenario.type.in_(scenario_types),
                    Scenario.is_active == True,
                    Scenario.is_locked == False,
                )
                .limit(1)
            )
            scenario = result.scalar_one_or_none()

        skill_display = weak_skill.replace("_", " ").title()

        if weak_value < 40:
            intensity = "significantly low"
            drills = 3
        elif weak_value < 60:
            intensity = "below average"
            drills = 2
        else:
            intensity = "could use improvement"
            drills = 2

        message = f"Your {skill_display} is {intensity}. "
        if scenario:
            message += f"We recommend {drills} practice sessions with the '{scenario.name}' scenario to strengthen this skill."
        else:
            message += f"We recommend {drills} focused practice sessions to improve."

        return FocusRecommendation(
            message=message,
            weak_skill=weak_skill,
            recommended_scenario_id=scenario.id if scenario else None,
            recommended_scenario_name=scenario.name if scenario else None,
            recommended_drills=drills,
        )

analytics_service = AnalyticsService()