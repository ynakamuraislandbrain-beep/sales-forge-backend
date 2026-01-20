"""Conversation orchestrator for managing real-time sales role-play.

This is the central component that coordinates:
- State management and context injection
- Turn analysis and behavior updates
- Analytics tracking
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.core.llm.gemini_client import GeminiClient, get_gemini_client
from app.core.llm.prompt_builder import (
    PromptBuilder,
    PersonaContext,
    ScenarioContext,
    ConversationStateContext,
)

logger = logging.getLogger(__name__)


class ConversationOrchestrator:
    """Orchestrates real-time sales role-play conversations via Gemini Live API.
    
    Manages the flow:
    1. Track rep and AI transcriptions
    2. Analyze each turn
    3. Update conversation state
    4. Generate context injections for Live API
    5. Track analytics
    """

    def __init__(
        self,
        persona: PersonaContext,
        scenario: ScenarioContext,
        gemini_client: Optional[GeminiClient] = None,
    ):
        self.persona = persona
        self.scenario = scenario
        self.gemini = gemini_client or get_gemini_client()
        self.prompt_builder = PromptBuilder()

        self.state = ConversationStateContext(
            current_mood=persona.default_mood,
            rapport_level=0.3,
            interest_level=0.3,
            objections_raised=[],
            rep_strengths_observed=[],
            rep_weaknesses_observed=[],
            conversation_summary="",
            turn_count=0,
            dynamic_modifiers=self._init_modifiers(persona),
        )

        self.turns: List[dict] = []

        self.analytics = {
            "rep_talk_time_ms": 0,
            "ai_talk_time_ms": 0,
            "response_latencies": [],
            "behavior_markers": [],
            "sentiment_timeline": [],
        }

    def _init_modifiers(self, persona: PersonaContext) -> Dict[str, float]:
        """Initialize dynamic modifiers from persona config."""
        config = persona.behavior_config or {}
        return {
            "skepticism_level": config.get("base_skepticism", 0.5),
            "interrupt_frequency": config.get("interrupt_frequency", 0.3),
            "patience_level": config.get("base_patience", 0.5),
            "agreeableness": config.get("agreeableness", 0.3),
            "formality": 0.5,
            "detail_orientation": config.get("detail_orientation", 0.5),
        }

    async def process_turn(
        self,
        rep_text: str,
        ai_text: str,
        rep_audio_duration_ms: int = 0,
        ai_audio_duration_ms: int = 0,
    ) -> str:
        """Process a conversation turn from Gemini Live transcriptions.
        
        Handles state tracking, turn analysis, and returns a context injection
        to update Gemini Live's understanding of the conversation state.
        
        Args:
            rep_text: Transcribed text from the rep
            ai_text: Transcribed AI response
            rep_audio_duration_ms: Duration of the rep's audio
            ai_audio_duration_ms: Duration of the AI's audio response
            
        Returns:
            Context injection string to send to Gemini Live
        """
        start_time = datetime.now(timezone.utc)

        rep_turn = {
            "speaker": "rep",
            "text": rep_text,
            "timestamp": start_time.isoformat(),
            "audio_duration_ms": rep_audio_duration_ms,
        }
        self.turns.append(rep_turn)
        self.analytics["rep_talk_time_ms"] += rep_audio_duration_ms

        ai_turn = {
            "speaker": "ai",
            "text": ai_text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "audio_duration_ms": ai_audio_duration_ms,
        }
        self.turns.append(ai_turn)
        self.analytics["ai_talk_time_ms"] += ai_audio_duration_ms

        analysis = await self._analyze_turn(rep_text)
        
        await self._update_state(analysis)
        
        self.analytics["sentiment_timeline"].append({
            "timestamp": start_time.isoformat(),
            "turn_index": self.state.turn_count,
            "sentiment": analysis.get("sentiment_score", 0),
            "speaker": "rep",
            "rapport_level": round(self.state.rapport_level, 2),
            "interest_level": round(self.state.interest_level, 2),
        })

        self.state.turn_count += 1

        if self.state.turn_count % 5 == 0:
            asyncio.create_task(self._update_summary())
        return self.prompt_builder.build_context_injection(self.state)

    def get_initial_system_prompt(self) -> str:
        """Build the initial system prompt for Live API connection.
        
        Returns:
            Complete system prompt with persona, scenario, and initial state
        """
        return self.prompt_builder.build_system_prompt(
            self.persona,
            self.scenario,
            self.state,
        )

    async def _analyze_turn(self, rep_text: str) -> dict:
        """Analyze the rep's turn for sentiment and quality."""
        context = f"{self.scenario.type} call with {self.persona.name}"
        return await self.gemini.analyze_turn(rep_text, context)

    async def _update_state(self, analysis: dict):
        """Update conversation state based on turn analysis."""
        self.state.rapport_level = max(0, min(1,
            self.state.rapport_level + analysis.get("rapport_delta", 0)
        ))
        self.state.interest_level = max(0, min(1,
            self.state.interest_level + analysis.get("interest_delta", 0)
        ))

        mood_shift = analysis.get("suggested_mood_shift", "neutral")
        mood_map = {
            "more_interested": "engaged",
            "less_interested": "bored",
            "annoyed": "annoyed",
            "impressed": "interested",
            "curious": "curious",
            "skeptical": "skeptical",
            "engaged": "engaged",
            "interested": "interested",
        }
        if mood_shift in mood_map:
            self.state.current_mood = mood_map[mood_shift]
            logger.debug(f"Mood updated to: {self.state.current_mood}")

        markers = analysis.get("behavior_markers", [])
        self.analytics["behavior_markers"].extend(markers)

        positive = ["clear_value_prop", "good_question", "handled_objection", "active_listening"]
        for marker in markers:
            if marker in positive and marker not in self.state.rep_strengths_observed:
                self.state.rep_strengths_observed.append(marker)

        negative = ["rude", "unprofessional", "not_convincing", "too_pushy", "passive"]
        for marker in markers:
            if marker in negative and marker not in self.state.rep_weaknesses_observed:
                self.state.rep_weaknesses_observed.append(marker)

        self._adjust_modifiers()

    def _adjust_modifiers(self):
        """Adjust AI behavior modifiers based on current state."""
        self.state.dynamic_modifiers["skepticism_level"] = max(0.2,
            0.8 - self.state.rapport_level * 0.6
        )

        self.state.dynamic_modifiers["patience_level"] = max(0.2,
            self.state.interest_level * 0.8
        )

        objection_factor = min(1, len(self.state.objections_raised) * 0.15)
        self.state.dynamic_modifiers["agreeableness"] = max(0.1, 0.4 - objection_factor)

    async def _update_summary(self):
        """Update the rolling conversation summary."""
        try:
            self.state.conversation_summary = await self.gemini.summarize_conversation(
                self.turns
            )
        except Exception as e:
            logger.error(f"Failed to update summary: {e}")

    async def generate_feedback(self) -> dict:
        """Generate post-call feedback after conversation ends."""
        return await self.gemini.generate_feedback(
            self.turns,
            f"{self.scenario.type} call with {self.persona.name} ({self.persona.title})",
            self.scenario.success_criteria.get("primary_goals", []),
        )

    def get_analytics(self) -> dict:
        """Get conversation analytics."""
        total_time = self.analytics["rep_talk_time_ms"] + self.analytics["ai_talk_time_ms"]
        talk_ratio = (
            self.analytics["rep_talk_time_ms"] / total_time
            if total_time > 0
            else 0.5
        )

        avg_latency = (
            sum(self.analytics["response_latencies"]) / len(self.analytics["response_latencies"])
            if self.analytics["response_latencies"]
            else 0
        )

        marker_counts = {}
        for marker in self.analytics["behavior_markers"]:
            marker_counts[marker] = marker_counts.get(marker, 0) + 1

        return {
            "rep_talk_time_seconds": self.analytics["rep_talk_time_ms"] // 1000,
            "ai_talk_time_seconds": self.analytics["ai_talk_time_ms"] // 1000,
            "talk_listen_ratio": round(talk_ratio, 2),
            "total_turns": len(self.turns),
            "rep_turns": len([t for t in self.turns if t["speaker"] == "rep"]),
            "ai_turns": len([t for t in self.turns if t["speaker"] == "ai"]),
            "avg_rep_response_time_ms": int(avg_latency),
            "behavior_markers": marker_counts,
            "sentiment_timeline": self.analytics["sentiment_timeline"],
            "final_rapport": self.state.rapport_level,
            "final_interest": self.state.interest_level,
        }

    def get_transcript(self) -> List[dict]:
        """Get the full conversation transcript."""
        return self.turns.copy()

    def get_state(self) -> ConversationStateContext:
        """Get the current conversation state."""
        return self.state
