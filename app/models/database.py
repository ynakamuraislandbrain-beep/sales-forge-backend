"""SQLAlchemy database models."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class Company(Base):
    """Company model for multi-tenant support."""

    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    users: Mapped[List["User"]] = relationship("User", back_populates="company")


class User(Base):
    """User model for sales reps and managers.
    
    Note: Authentication is handled by Neon Auth (frontend).
    Users are auto-created on first JWT validation.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE")
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="rep",
    )
    avatar_url: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("role IN ('rep', 'manager', 'admin')", name="check_user_role"),
        Index("idx_users_company", "company_id"),
        Index("idx_users_role", "role"),
    )

    company: Mapped[Optional["Company"]] = relationship("Company", back_populates="users")
    sessions: Mapped[List["Session"]] = relationship("Session", back_populates="user")
    assigned_trainings: Mapped[List["TrainingAssignment"]] = relationship(
        "TrainingAssignment",
        foreign_keys="TrainingAssignment.rep_id",
        back_populates="rep",
    )
    created_trainings: Mapped[List["TrainingAssignment"]] = relationship(
        "TrainingAssignment",
        foreign_keys="TrainingAssignment.manager_id",
        back_populates="manager",
    )


class Persona(Base):
    """AI persona model for role-play characters."""

    __tablename__ = "personas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[Optional[str]] = mapped_column(String(100))
    traits: Mapped[List[str]] = mapped_column(ARRAY(Text), nullable=False)
    default_mood: Mapped[str] = mapped_column(String(50), nullable=False)
    voice_profile: Mapped[Optional[dict]] = mapped_column(JSONB)
    system_prompt_template: Mapped[str] = mapped_column(Text, nullable=False)
    behavior_config: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    scenarios: Mapped[List["Scenario"]] = relationship("Scenario", back_populates="persona")


class Scenario(Base):
    """Training scenario model."""

    __tablename__ = "scenarios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    persona_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("personas.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    scenario_rules: Mapped[str] = mapped_column(Text, nullable=False)
    success_criteria: Mapped[dict] = mapped_column(JSONB, nullable=False)
    book_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    prior_context: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "type IN ('cold_call', 'discovery', 'demo', 'coaching', 'post_sales')",
            name="check_scenario_type",
        ),
        CheckConstraint(
            "difficulty IN ('easy', 'medium', 'hard', 'expert')",
            name="check_scenario_difficulty",
        ),
        CheckConstraint(
            "category IN ('outbound', 'inbound', 'manager')",
            name="check_scenario_category",
        ),
        Index("idx_scenarios_type", "type"),
        Index("idx_scenarios_active", "is_active", "is_locked"),
    )

    persona: Mapped[Optional["Persona"]] = relationship("Persona", back_populates="scenarios")
    sessions: Mapped[List["Session"]] = relationship("Session", back_populates="scenario")


class Session(Base):
    """Call session model."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    scenario_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenarios.id", ondelete="SET NULL")
    )
    training_assignment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("training_assignments.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    overall_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    rapport_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))  
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', 'abandoned')",
            name="check_session_status",
        ),
        Index("idx_sessions_user", "user_id"),
        Index("idx_sessions_status", "status"),
        Index("idx_sessions_created", "created_at"),
        Index("idx_sessions_user_status_created", "user_id", "status", "created_at"),
        Index("idx_sessions_overall_score", "overall_score"),
    )

    user: Mapped["User"] = relationship("User", back_populates="sessions")
    scenario: Mapped[Optional["Scenario"]] = relationship("Scenario", back_populates="sessions")
    transcript: Mapped[Optional["Transcript"]] = relationship(
        "Transcript", back_populates="session", uselist=False
    )
    feedback: Mapped[Optional["Feedback"]] = relationship(
        "Feedback", back_populates="session", uselist=False
    )
    analytics: Mapped[Optional["SessionAnalytics"]] = relationship(
        "SessionAnalytics", back_populates="session", uselist=False
    )
    conversation_states: Mapped[List["ConversationState"]] = relationship(
        "ConversationState", back_populates="session"
    )
    training_assignment: Mapped[Optional["TrainingAssignment"]] = relationship(
        "TrainingAssignment", back_populates="sessions"
    )


class Transcript(Base):
    """Call transcript model with turn-by-turn data."""

    __tablename__ = "transcripts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    turns: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)
    raw_audio_url: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("idx_transcripts_session", "session_id"),)

    session: Mapped["Session"] = relationship("Session", back_populates="transcript")


class Feedback(Base):
    """Post-call feedback model."""

    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    strengths: Mapped[List[str]] = mapped_column(ARRAY(Text), nullable=False)
    weaknesses: Mapped[List[str]] = mapped_column(ARRAY(Text), nullable=False)
    suggestions: Mapped[List[str]] = mapped_column(ARRAY(Text), nullable=False)
    highlighted_moments: Mapped[Optional[dict]] = mapped_column(JSONB)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    manager_comments: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("idx_feedback_session", "session_id"),)

    session: Mapped["Session"] = relationship("Session", back_populates="feedback")


class SessionAnalytics(Base):
    """Detailed session analytics model."""

    __tablename__ = "session_analytics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    rep_talk_time_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    ai_talk_time_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    talk_listen_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))

    total_turns: Mapped[Optional[int]] = mapped_column(Integer)
    rep_turns: Mapped[Optional[int]] = mapped_column(Integer)
    ai_turns: Mapped[Optional[int]] = mapped_column(Integer)
    avg_rep_response_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    interruption_count: Mapped[Optional[int]] = mapped_column(Integer)

    objection_handling_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    question_quality_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    confidence_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    professionalism_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    persuasiveness_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    goal_completion: Mapped[Optional[bool]] = mapped_column(Boolean)

    behavior_markers: Mapped[Optional[dict]] = mapped_column(JSONB)
    sentiment_timeline: Mapped[Optional[dict]] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (Index("idx_analytics_session", "session_id"),)

    session: Mapped["Session"] = relationship("Session", back_populates="analytics")


class ConversationState(Base):
    """Real-time conversation state tracking for dynamic LLM behavior."""

    __tablename__ = "conversation_states"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)

    current_mood: Mapped[Optional[str]] = mapped_column(String(50))
    rapport_level: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))  
    interest_level: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))  
    objections_raised: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text))
    rep_strengths_observed: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text))
    rep_weaknesses_observed: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text))

    conversation_summary: Mapped[Optional[str]] = mapped_column(Text)

    dynamic_modifiers: Mapped[Optional[dict]] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("idx_state_session_turn", "session_id", "turn_number"),
    )

    session: Mapped["Session"] = relationship("Session", back_populates="conversation_states")


class TrainingAssignment(Base):
    """Manager-assigned training tasks."""

    __tablename__ = "training_assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    manager_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    rep_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False
    )
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', 'overdue')",
            name="check_assignment_status",
        ),
        Index("idx_assignments_rep", "rep_id", "status"),
        Index("idx_assignments_manager", "manager_id"),
    )

    manager: Mapped["User"] = relationship(
        "User", foreign_keys=[manager_id], back_populates="created_trainings"
    )
    rep: Mapped["User"] = relationship(
        "User", foreign_keys=[rep_id], back_populates="assigned_trainings"
    )
    scenario: Mapped["Scenario"] = relationship("Scenario")
    sessions: Mapped[List["Session"]] = relationship(
        "Session", back_populates="training_assignment"
    )


class UserSkillScores(Base):
    """Cached skill scores for a user.
    
    Scores are computed from SessionAnalytics data and cached here
    for efficient retrieval. Recalculated periodically or on-demand.
    """

    __tablename__ = "user_skill_scores"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    
    closing_skills: Mapped[int] = mapped_column(Integer, default=0)
    objection_handling: Mapped[int] = mapped_column(Integer, default=0)
    empathy_rapport: Mapped[int] = mapped_column(Integer, default=0)
    discovery_efficiency: Mapped[int] = mapped_column(Integer, default=0)
    value_proposition: Mapped[int] = mapped_column(Integer, default=0)
    
    last_calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("closing_skills >= 0 AND closing_skills <= 100", name="check_closing_skills_range"),
        CheckConstraint("objection_handling >= 0 AND objection_handling <= 100", name="check_objection_handling_range"),
        CheckConstraint("empathy_rapport >= 0 AND empathy_rapport <= 100", name="check_empathy_rapport_range"),
        CheckConstraint("discovery_efficiency >= 0 AND discovery_efficiency <= 100", name="check_discovery_efficiency_range"),
        CheckConstraint("value_proposition >= 0 AND value_proposition <= 100", name="check_value_proposition_range"),
        Index("idx_skill_scores_user", "user_id"),
    )

    user: Mapped["User"] = relationship("User")


class MilestoneDefinition(Base):
    """Milestone definitions.
    
    Defines available milestones with their criteria.
    These are typically seeded once and rarely modified.
    """

    __tablename__ = "milestone_definitions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    criteria_type: Mapped[str] = mapped_column(String(50), nullable=False)
    criteria_target: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("idx_milestone_def_active", "is_active"),
    )

    user_progress: Mapped[List["UserMilestone"]] = relationship(
        "UserMilestone", back_populates="milestone"
    )


class UserMilestone(Base):
    """User milestone progress tracking.
    
    Tracks each user's progress toward each milestone.
    """

    __tablename__ = "user_milestones"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    milestone_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("milestone_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    current_progress: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_user_milestone_user", "user_id"),
        Index("idx_user_milestone_milestone", "milestone_id"),
        Index("idx_user_milestone_completed", "user_id", "completed"),
    )

    user: Mapped["User"] = relationship("User")
    milestone: Mapped["MilestoneDefinition"] = relationship(
        "MilestoneDefinition", back_populates="user_progress"
    )
