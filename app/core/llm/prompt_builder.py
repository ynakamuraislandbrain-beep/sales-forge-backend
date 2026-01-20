"""Dynamic prompt builder for persona-driven conversations.

This is the core component that makes the AI assistant realistic and helpful for training.
The prompt construction considers persona traits, scenario context, conversation state,
and dynamic modifiers to create an immersive and challenging sales training experience.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class PersonaContext:
    """Persona information for prompt building."""

    name: str
    title: str
    company: str
    industry: Optional[str]
    traits: List[str]
    default_mood: str
    system_prompt_template: str
    behavior_config: Optional[Dict[str, Any]] = None


@dataclass
class ScenarioContext:
    """Scenario information for prompt building."""

    type: str  
    category: str  
    instructions: str
    scenario_rules: str
    success_criteria: Dict[str, Any]
    prior_context: Optional[Dict[str, Any]] = None


@dataclass
class ConversationStateContext:
    """Current conversation state for prompt building."""

    current_mood: str
    rapport_level: float  
    interest_level: float  
    objections_raised: List[str]
    rep_strengths_observed: List[str]
    rep_weaknesses_observed: List[str]
    conversation_summary: str
    turn_count: int
    dynamic_modifiers: Dict[str, float]


class PromptBuilder:
    """Builds comprehensive prompts for sales role-play scenarios.
    
    The prompt structure:
    1. Core persona identity and character
    2. Scenario-specific context and rules
    3. Current conversation state
    4. Dynamic behavior adjustments
    5. Hidden instructions for realistic behavior
    """

    def __init__(self):
        self.filler_words = ["um", "uh", "like", "you know", "basically", "actually"]
        self.hedging_phrases = [
            "I think", "maybe", "perhaps", "sort of", "kind of",
            "I guess", "possibly", "it seems like"
        ]
        self._load_prompts()

    def _load_prompts(self):
        """Load system prompts from JSON file."""
        from pathlib import Path
        import json
        import logging
        
        logger = logging.getLogger(__name__)
        base_dir = Path(__file__).parent.parent.parent.parent
        self.prompts_path = base_dir / "data" / "system_prompts.json"
        self.prompts_example_path = base_dir / "data" / "system_prompts.example.json"
        
        self.prompts = {}
        if self.prompts_path.exists():
            try:
                with open(self.prompts_path, "r") as f:
                    self.prompts = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load system prompts from {self.prompts_path}: {e}")
        
        if not self.prompts and self.prompts_example_path.exists():
            try:
                with open(self.prompts_example_path, "r") as f:
                    self.prompts = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load template prompts: {e}")

    def get_prompt(self, key: str, default: str) -> str:
        """Get a prompt by key from the prompt_builder section."""
        pb = self.prompts.get("prompt_builder", {})
        return pb.get(key, default)

    def build_system_prompt(
        self,
        persona: PersonaContext,
        scenario: ScenarioContext,
        state: ConversationStateContext,
    ) -> str:
        """Build the complete system prompt for the LLM.
        
        This prompt is designed to create a realistic, challenging training experience
        that adapts dynamically to the sales rep's performance.
        """
        sections = [
            self._build_persona_section(persona),
            self._build_scenario_section(scenario, persona),
            self._build_state_section(state),
            self._build_behavior_rules(persona, scenario, state),
            self._build_hidden_instructions(state),
        ]

        return "\n\n".join(sections)

    def _build_persona_section(self, persona: PersonaContext) -> str:
        """Build the core persona identity section."""
        traits_str = ", ".join(persona.traits)
        template = self.get_prompt("persona_section", "=== YOUR IDENTITY ===\n{template}\n\nName: {name}\n...")
        return template.format(
            template=persona.system_prompt_template,
            name=persona.name,
            title=persona.title,
            company=persona.company,
            industry=persona.industry or "Technology",
            traits=traits_str,
            mood=persona.default_mood
        )

    def _build_scenario_section(
        self,
        scenario: ScenarioContext,
        persona: PersonaContext,
    ) -> str:
        """Build the scenario context section."""
        scenario_type_descriptions = self.get_prompt("scenario_type_descriptions", {})
        category_contexts = self.get_prompt("category_contexts", {})

        prior_context_str = ""
        if scenario.prior_context:
            template = self.get_prompt("prior_context_section", "=== PRIOR RELATIONSHIP CONTEXT ===\n...")
            prior_context_str = template.format(
                previous_interactions=scenario.prior_context.get('previous_interactions', 'None'),
                pain_points=', '.join(scenario.prior_context.get('known_pain_points', [])),
                company_info=scenario.prior_context.get('company_info', 'Unknown'),
                relationship_history=scenario.prior_context.get('relationship_history', 'No prior relationship')
            )

        template = self.get_prompt("scenario_section", "=== SCENARIO CONTEXT ===\n...")
        return template.format(
            type_title=scenario.type.replace('_', ' ').title(),
            type_desc=scenario_type_descriptions.get(scenario.type, ''),
            category_title=scenario.category.title(),
            category_desc=category_contexts.get(scenario.category, ''),
            prior_context=prior_context_str,
            rules=scenario.scenario_rules,
            primary_goals=', '.join(scenario.success_criteria.get('primary_goals', [])),
            secondary_goals=', '.join(scenario.success_criteria.get('secondary_goals', [])),
            failure_conditions=', '.join(scenario.success_criteria.get('failure_conditions', []))
        )

    def _build_state_section(self, state: ConversationStateContext) -> str:
        """Build the current conversation state section."""
        objections_str = ", ".join(state.objections_raised) if state.objections_raised else "None yet"
        strengths_str = ", ".join(state.rep_strengths_observed) if state.rep_strengths_observed else "None observed"
        weaknesses_str = ", ".join(state.rep_weaknesses_observed) if state.rep_weaknesses_observed else "None observed"

        template = self.get_prompt("state_section", "=== CURRENT CONVERSATION STATE ===\n...")
        return template.format(
            turn_count=state.turn_count,
            mood=state.current_mood,
            rapport_desc=self._describe_level(state.rapport_level),
            rapport_pct=f"{state.rapport_level:.0%}",
            interest_desc=self._describe_level(state.interest_level),
            interest_pct=f"{state.interest_level:.0%}",
            objections=objections_str,
            strengths=strengths_str,
            weaknesses=weaknesses_str,
            summary=state.conversation_summary or "Just starting the conversation."
        )

    def _describe_level(self, level: float) -> str:
        """Convert a 0-1 level to a descriptive word."""
        if level < 0.2:
            return "Very Low"
        elif level < 0.4:
            return "Low"
        elif level < 0.6:
            return "Moderate"
        elif level < 0.8:
            return "High"
        else:
            return "Very High"

    def _build_behavior_rules(
        self,
        persona: PersonaContext,
        scenario: ScenarioContext,
        state: ConversationStateContext,
    ) -> str:
        """Build dynamic behavior rules based on state."""
        modifiers = state.dynamic_modifiers

        skepticism = modifiers.get("skepticism_level", 0.5)
        skepticism_rule = self._get_skepticism_rule(skepticism)

        patience = modifiers.get("patience_level", 0.5)
        patience_rule = self._get_patience_rule(patience)

        interrupt_freq = modifiers.get("interrupt_frequency", 0.3)
        interrupt_rule = self._get_interrupt_rule(interrupt_freq)

        agreeableness = modifiers.get("agreeableness", 0.3)
        agreeableness_rule = self._get_agreeableness_rule(agreeableness)

        template = self.get_prompt("behavior_directives_section", "=== BEHAVIOR DIRECTIVES ===\n...")
        return template.format(
            skepticism_rule=skepticism_rule,
            patience_rule=patience_rule,
            interrupt_rule=interrupt_rule,
            agreeableness_rule=agreeableness_rule
        )

    def _get_skepticism_rule(self, level: float) -> str:
        """Get skepticism behavior rule based on level."""
        rules = self.get_prompt("skepticism_rules", {})
        if level > 0.7:
            return rules.get("high", "SKEPTICISM: HIGH")
        elif level > 0.4:
            return rules.get("moderate", "SKEPTICISM: MODERATE")
        else:
            return rules.get("low", "SKEPTICISM: LOW")

    def _get_patience_rule(self, level: float) -> str:
        """Get patience behavior rule based on level."""
        rules = self.get_prompt("patience_rules", {})
        if level < 0.3:
            return rules.get("low", "PATIENCE: LOW")
        elif level < 0.6:
            return rules.get("moderate", "PATIENCE: MODERATE")
        else:
            return rules.get("high", "PATIENCE: HIGH")

    def _get_interrupt_rule(self, level: float) -> str:
        """Get interruption behavior rule based on level."""
        rules = self.get_prompt("interrupt_rules", {})
        if level > 0.6:
            return rules.get("frequent", "INTERRUPTIONS: FREQUENT")
        elif level > 0.3:
            return rules.get("occasional", "INTERRUPTIONS: OCCASIONAL")
        else:
            return rules.get("rare", "INTERRUPTIONS: RARE")

    def _get_agreeableness_rule(self, level: float) -> str:
        """Get agreeableness behavior rule based on level."""
        rules = self.get_prompt("agreeableness_rules", {})
        if level < 0.3:
            return rules.get("low", "AGREEABLENESS: LOW")
        elif level < 0.6:
            return rules.get("moderate", "AGREEABLENESS: MODERATE")
        else:
            return rules.get("high", "AGREEABLENESS: HIGH")

    def _build_hidden_instructions(self, state: ConversationStateContext) -> str:
        """Build hidden instructions that guide realistic behavior."""
        adaptive_instructions_map = self.get_prompt("adaptive_instructions", {})
        adaptive_instructions = []

        if state.turn_count < 3:
            adaptive_instructions.append(adaptive_instructions_map.get("early", ""))
        elif state.turn_count < 8:
            adaptive_instructions.append(adaptive_instructions_map.get("mid", ""))
        else:
            adaptive_instructions.append(adaptive_instructions_map.get("late", ""))

        if state.rapport_level < 0.3:
            adaptive_instructions.append(adaptive_instructions_map.get("low_rapport", ""))
        elif state.rapport_level > 0.6:
            adaptive_instructions.append(adaptive_instructions_map.get("high_rapport", ""))

        if "hesitation" in str(state.rep_weaknesses_observed).lower():
            adaptive_instructions.append(adaptive_instructions_map.get("nervous", ""))

        if "unclear value" in str(state.rep_weaknesses_observed).lower():
            adaptive_instructions.append(adaptive_instructions_map.get("unclear_value", ""))

        adaptive_str = "\n".join(f"- {inst}" for inst in adaptive_instructions if inst)

        template = self.get_prompt("hidden_instructions_section", "=== HIDDEN ADAPTIVE INSTRUCTIONS ===\n...")
        return template.format(adaptive_str=adaptive_str)

    def build_context_injection(self, state: ConversationStateContext) -> str:
        """Build a short context injection for mid-conversation state updates."""
        template = self.get_prompt("context_injection", "[UPDATED STATE]\n...")
        return template.format(
            mood=state.current_mood,
            rapport_pct=f"{state.rapport_level:.0%}",
            interest_pct=f"{state.interest_level:.0%}",
            skepticism_pct=f"{state.dynamic_modifiers.get('skepticism_level', 0.5):.0%}",
            patience_pct=f"{state.dynamic_modifiers.get('patience_level', 0.5):.0%}"
        )

    def get_conversation_summary_prompt(self, turns: List[dict]) -> str:
        """Build a prompt for summarizing the conversation so far.
        
        Used for rolling summarization to manage context length.
        """
        turns_text = ""
        for turn in turns[-10:]: 
            speaker = "Rep" if turn["speaker"] == "rep" else "Prospect"
            turns_text += f"{speaker}: {turn['text']}\n"

        template = self.get_prompt("rolling_summary", "Summarize the following interaction:\n{transcript}\nSUMMARY:")
        return template.format(transcript=turns_text)