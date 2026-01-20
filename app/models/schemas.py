"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

class UserRole(str, Enum):
    REP = "rep"
    MANAGER = "manager"
    ADMIN = "admin"


class ScenarioType(str, Enum):
    COLD_CALL = "cold_call"
    DISCOVERY = "discovery"
    DEMO = "demo"
    COACHING = "coaching"
    POST_SALES = "post_sales"


class ScenarioDifficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    EXPERT = "expert"


class ScenarioCategory(str, Enum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"
    MANAGER = "manager"


class SessionStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class AssignmentStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    OVERDUE = "overdue"


class BaseSchema(BaseModel):
    """Base schema with common configuration."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class TimestampMixin(BaseModel):
    """Mixin for created/updated timestamps."""

    created_at: datetime
    updated_at: datetime


class UserBase(BaseModel):
    """Base user schema."""

    email: EmailStr
    name: str = Field(..., min_length=1, max_length=255)
    role: UserRole = UserRole.REP


class UserUpdate(BaseModel):
    """User update schema."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    avatar_url: Optional[str] = None
    role: Optional[UserRole] = None  


class UserResponse(BaseSchema, TimestampMixin):
    """User response schema."""

    id: UUID
    email: str
    name: str
    role: UserRole
    avatar_url: Optional[str] = None
    company_id: Optional[UUID] = None

class CompanyBase(BaseModel):
    """Base company schema."""

    name: str = Field(..., min_length=1, max_length=255)


class CompanyCreate(CompanyBase):
    """Company creation schema."""

    pass


class CompanyResponse(BaseSchema, TimestampMixin):
    """Company response schema."""

    id: UUID
    name: str


class VoiceProfile(BaseModel):
    """Voice configuration for TTS."""

    provider: str = "gemini"
    voice_id: Optional[str] = None
    settings: Optional[dict[str, Any]] = None


class BehaviorConfig(BaseModel):
    """Behavior configuration for dynamic AI adjustments."""

    base_skepticism: float = Field(default=0.5, ge=0, le=1)
    base_patience: float = Field(default=0.5, ge=0, le=1)
    interrupt_frequency: float = Field(default=0.3, ge=0, le=1)
    agreeableness: float = Field(default=0.3, ge=0, le=1)
    detail_orientation: float = Field(default=0.5, ge=0, le=1)


class PersonaBase(BaseModel):
    """Base persona schema."""

    name: str = Field(..., min_length=1, max_length=255)
    title: str = Field(..., min_length=1, max_length=255)
    company: str = Field(..., min_length=1, max_length=255)
    industry: Optional[str] = Field(None, max_length=100)
    traits: List[str] = Field(..., min_length=1)
    default_mood: str = Field(..., min_length=1, max_length=50)
    system_prompt_template: str = Field(..., min_length=10)
    voice_profile: Optional[VoiceProfile] = None
    behavior_config: Optional[BehaviorConfig] = None


class PersonaCreate(PersonaBase):
    """Persona creation schema."""

    pass


class PersonaUpdate(BaseModel):
    """Persona update schema."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    traits: Optional[List[str]] = None
    default_mood: Optional[str] = None
    system_prompt_template: Optional[str] = None
    voice_profile: Optional[VoiceProfile] = None
    behavior_config: Optional[BehaviorConfig] = None


class PersonaResponse(BaseSchema, TimestampMixin):
    """Persona response schema."""

    id: UUID
    name: str
    title: str
    company: str
    industry: Optional[str] = None
    traits: List[str]
    default_mood: str
    system_prompt_template: str
    voice_profile: Optional[dict] = None
    behavior_config: Optional[dict] = None


class PersonaSummary(BaseSchema):
    """Minimal persona info for scenario cards."""

    id: UUID
    name: str
    title: str
    company: str
    traits: List[str]
    default_mood: str

class PriorContext(BaseModel):
    """Prior context for discovery calls."""

    previous_interactions: Optional[str] = None
    known_pain_points: Optional[List[str]] = None
    company_info: Optional[str] = None
    relationship_history: Optional[str] = None


class SuccessCriteria(BaseModel):
    """Success criteria for scenario evaluation."""

    primary_goals: List[str]
    secondary_goals: Optional[List[str]] = None
    failure_conditions: Optional[List[str]] = None


class ScenarioBase(BaseModel):
    """Base scenario schema."""

    name: str = Field(..., min_length=1, max_length=255)
    type: ScenarioType
    difficulty: ScenarioDifficulty
    category: ScenarioCategory
    instructions: str = Field(..., min_length=10)
    scenario_rules: str = Field(..., min_length=10)
    success_criteria: SuccessCriteria
    book_rate: Optional[Decimal] = Field(None, ge=0, le=1)
    prior_context: Optional[PriorContext] = None


class ScenarioCreate(ScenarioBase):
    """Scenario creation schema."""

    persona_id: UUID


class ScenarioUpdate(BaseModel):
    """Scenario update schema."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    instructions: Optional[str] = None
    scenario_rules: Optional[str] = None
    success_criteria: Optional[SuccessCriteria] = None
    is_active: Optional[bool] = None
    is_locked: Optional[bool] = None


class ScenarioResponse(BaseSchema, TimestampMixin):
    """Scenario response schema."""

    id: UUID
    persona_id: Optional[UUID] = None
    name: str
    type: ScenarioType
    difficulty: ScenarioDifficulty
    category: ScenarioCategory
    instructions: str
    scenario_rules: str
    success_criteria: dict
    book_rate: Optional[Decimal] = None
    is_active: bool
    is_locked: bool
    prior_context: Optional[dict] = None
    persona: Optional[PersonaSummary] = None


class ScenarioCard(BaseSchema):
    """Scenario card for listing view."""

    id: UUID
    name: str
    type: ScenarioType
    difficulty: ScenarioDifficulty
    category: ScenarioCategory
    book_rate: Optional[Decimal] = None
    is_locked: bool
    persona: Optional[PersonaSummary] = None


class TranscriptTurn(BaseModel):
    """Single turn in a conversation transcript."""

    speaker: str 
    text: str
    timestamp: datetime
    audio_duration_ms: Optional[int] = None
    sentiment_score: Optional[float] = Field(None, ge=-1, le=1)
    hesitation_detected: bool = False
    filler_words: Optional[List[str]] = None
    response_latency_ms: Optional[int] = None
    behavior_markers: Optional[List[str]] = None


class TranscriptResponse(BaseSchema):
    """Transcript response schema."""

    id: UUID
    session_id: UUID
    turns: List[TranscriptTurn]
    raw_audio_url: Optional[str] = None
    created_at: datetime

class HighlightedMoment(BaseModel):
    """Highlighted moment in transcript."""

    turn_index: int
    comment: str
    type: str  


class FeedbackResponse(BaseSchema):
    """Feedback response schema."""

    id: UUID
    session_id: UUID
    strengths: List[str]
    weaknesses: List[str]
    suggestions: List[str]
    highlighted_moments: Optional[List[HighlightedMoment]] = None
    ai_generated: bool
    manager_comments: Optional[str] = None
    created_at: datetime


class ManagerFeedbackUpdate(BaseModel):
    """Manager feedback update schema."""

    manager_comments: str = Field(..., min_length=1)


class SessionCreate(BaseModel):
    """Session creation schema."""

    scenario_id: UUID
    training_assignment_id: Optional[UUID] = None


class SessionResponse(BaseSchema, TimestampMixin):
    """Session response schema."""

    id: UUID
    user_id: UUID
    scenario_id: Optional[UUID] = None
    training_assignment_id: Optional[UUID] = None
    status: SessionStatus
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    overall_score: Optional[Decimal] = None
    rapport_score: Optional[Decimal] = None  
    scenario: Optional["ScenarioCard"] = None  

class SessionDetail(SessionResponse):
    """Detailed session response with transcript and feedback."""

    transcript: Optional[TranscriptResponse] = None
    feedback: Optional[FeedbackResponse] = None

class BehaviorMarkers(BaseModel):
    """Behavior markers detected during session - flexible dict of marker counts."""
    model_config = ConfigDict(extra="allow")

    rude_count: int = 0
    unprofessional_count: int = 0
    not_convincing_count: int = 0
    filler_word_count: int = 0
    hesitation_count: int = 0
    interruption_count: int = 0
    clear_value_prop: int = 0
    good_question: int = 0
    handled_objection: int = 0
    active_listening: int = 0


class SentimentDataPoint(BaseModel):
    """Single point in sentiment timeline."""

    timestamp: datetime
    turn_index: Optional[int] = None
    sentiment: float = Field(ge=-1, le=1, default=0)
    speaker: Optional[str] = None 
    rapport_level: Optional[float] = Field(ge=0, le=1, default=None)
    interest_level: Optional[float] = Field(ge=0, le=1, default=None)


class SessionAnalyticsResponse(BaseSchema):
    """Session analytics response schema."""

    id: UUID
    session_id: UUID

    rep_talk_time_seconds: Optional[int] = None
    ai_talk_time_seconds: Optional[int] = None
    talk_listen_ratio: Optional[Decimal] = None

    total_turns: Optional[int] = None
    rep_turns: Optional[int] = None
    ai_turns: Optional[int] = None
    avg_rep_response_time_ms: Optional[int] = None
    interruption_count: Optional[int] = None

    objection_handling_score: Optional[Decimal] = None
    question_quality_score: Optional[Decimal] = None
    confidence_score: Optional[Decimal] = None
    professionalism_score: Optional[Decimal] = None
    persuasiveness_score: Optional[Decimal] = None
    goal_completion: Optional[bool] = None

    behavior_markers: Optional[BehaviorMarkers] = None
    sentiment_timeline: Optional[List[SentimentDataPoint]] = None
    created_at: datetime

class SkillScores(BaseModel):
    """User skill scores across key dimensions."""

    closing_skills: int = Field(default=0, ge=0, le=100)
    objection_handling: int = Field(default=0, ge=0, le=100)
    empathy_rapport: int = Field(default=0, ge=0, le=100)
    discovery_efficiency: int = Field(default=0, ge=0, le=100)
    value_proposition: int = Field(default=0, ge=0, le=100)


class MilestoneCriteria(BaseModel):
    """Criteria for milestone completion."""

    type: str 
    target: int
    current: int


class Milestone(BaseModel):
    """User milestone with progress tracking."""

    id: str
    title: str
    description: str
    progress: int = Field(default=0, ge=0, le=100)  
    completed: bool = False
    criteria: MilestoneCriteria


class FocusRecommendation(BaseModel):
    """AI-generated focus recommendation based on user performance."""

    message: str
    weak_skill: str
    recommended_scenario_id: Optional[UUID] = None
    recommended_scenario_name: Optional[str] = None
    recommended_drills: int = Field(default=2, ge=1, le=5)


class UserPerformanceSummary(BaseModel):
    """User performance summary across sessions."""

    user_id: UUID
    total_sessions: int
    completed_sessions: int
    average_score: Optional[Decimal] = None
    avg_talk_listen_ratio: Optional[Decimal] = None
    avg_objection_handling: Optional[Decimal] = None
    avg_confidence_score: Optional[Decimal] = None
    goal_completion_rate: Optional[Decimal] = None
    improvement_trend: Optional[str] = None 
    recent_sessions: List[SessionResponse] = []

    skills: Optional[SkillScores] = None
    milestones: List[Milestone] = []
    focus_recommendation: Optional[FocusRecommendation] = None


class AssignmentCreate(BaseModel):
    """Assignment creation schema."""

    rep_id: UUID
    scenario_id: UUID
    due_date: Optional[datetime] = None
    notes: Optional[str] = None


class AssignmentUpdate(BaseModel):
    """Assignment update schema."""

    due_date: Optional[datetime] = None
    notes: Optional[str] = None
    status: Optional[AssignmentStatus] = None


class AssignmentResponse(BaseSchema, TimestampMixin):
    """Assignment response schema."""

    id: UUID
    manager_id: UUID
    rep_id: UUID
    scenario_id: UUID
    due_date: Optional[datetime] = None
    status: AssignmentStatus
    notes: Optional[str] = None
    scenario: Optional[ScenarioCard] = None
    rep: Optional[UserResponse] = None


class DynamicModifiers(BaseModel):
    """Dynamic modifiers for AI behavior."""

    skepticism_level: float = Field(default=0.5, ge=0, le=1)
    interrupt_frequency: float = Field(default=0.3, ge=0, le=1)
    patience_level: float = Field(default=0.5, ge=0, le=1)
    agreeableness: float = Field(default=0.3, ge=0, le=1)
    formality: float = Field(default=0.5, ge=0, le=1)
    detail_orientation: float = Field(default=0.5, ge=0, le=1)


class ConversationStateResponse(BaseSchema):
    """Conversation state response schema."""

    id: UUID
    session_id: UUID
    turn_number: int
    current_mood: Optional[str] = None
    rapport_level: Optional[Decimal] = None
    interest_level: Optional[Decimal] = None
    objections_raised: Optional[List[str]] = None
    rep_strengths_observed: Optional[List[str]] = None
    rep_weaknesses_observed: Optional[List[str]] = None
    conversation_summary: Optional[str] = None
    dynamic_modifiers: Optional[DynamicModifiers] = None
    created_at: datetime


class WSMessageType(str, Enum):
    """WebSocket message types."""

    AUDIO = "audio"
    TRANSCRIPT = "transcript"
    STATE_UPDATE = "state_update"
    CALL_STARTED = "call_started"
    CALL_ENDED = "call_ended"
    ERROR = "error"
    END_CALL = "end_call"


class WSClientMessage(BaseModel):
    """WebSocket message from client."""

    type: WSMessageType
    data: Optional[str] = None  


class WSServerMessage(BaseModel):
    """WebSocket message from server."""

    type: WSMessageType
    speaker: Optional[str] = None
    text: Optional[str] = None
    data: Optional[str] = None  
    mood: Optional[str] = None
    rapport: Optional[float] = None
    session_id: Optional[str] = None
    error: Optional[str] = None

class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str
    code: Optional[str] = None


class ValidationErrorDetail(BaseModel):
    """Validation error detail."""

    loc: List[str]
    msg: str
    type: str


class ValidationErrorResponse(BaseModel):
    """Validation error response."""

    detail: List[ValidationErrorDetail]
