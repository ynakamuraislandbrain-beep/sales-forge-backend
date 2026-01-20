"""Gemini LLM client for analysis and feedback generation.

Supports multilingual analysis (English, Hindi, Hinglish, etc.)
"""

import json
import logging
import re
from typing import List, Optional

from google import genai
from google.genai import types

from app.config import get_settings

logger = logging.getLogger(__name__)


def _safe_parse_json(text: str, default: dict) -> dict:
    """Safely parse JSON with multiple fallback strategies."""
    if not text:
        return default
    
    text = text.strip()
    
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    
    brace_count = 0
    start_idx = None
    for i, char in enumerate(text):
        if char == '{':
            if start_idx is None:
                start_idx = i
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0 and start_idx is not None:
                try:
                    return json.loads(text[start_idx:i+1])
                except json.JSONDecodeError:
                    pass
                start_idx = None
    
    logger.error(f"All JSON parsing strategies failed. Raw text: {text[:500]}...")
    return default


class GeminiClient:
    """Gemini API client for analysis and feedback.
    
    Uses gemini-2.5-flash for text analysis tasks.
    Supports multilingual analysis (English, Hindi, Hinglish, etc.)
    """

    def __init__(self):
        settings = get_settings()
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model_name = settings.analysis_api_model
        
        self.config = types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=2048,
        )
        self._load_prompts()

    def _load_prompts(self):
        """Load system prompts from JSON file."""
        from pathlib import Path
        import json

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
            logger.warning(f"Using template prompts from {self.prompts_example_path}")
            try:
                with open(self.prompts_example_path, "r") as f:
                    self.prompts = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load template prompts: {e}")

    def get_prompt(self, key: str, default: str) -> str:
        """Get a prompt by key with a hardcoded fallback."""
        return self.prompts.get(key, default)

    async def analyze_turn(
        self,
        turn_text: str,
        persona_context: str,
    ) -> dict:
        """Analyze a rep's turn for sentiment and behavior markers.
        
        Supports multilingual input (English, Hindi, Hinglish, etc.)
        """
        
        default_result = {
            "sentiment_score": 0,
            "confidence_level": 0.5,
            "hesitation_detected": False,
            "filler_words": [],
            "behavior_markers": [],
            "quality_indicators": {},
            "suggested_mood_shift": "neutral",
            "rapport_delta": 0,
            "interest_delta": 0,
        }
        
        if not turn_text or len(turn_text.strip()) < 3:
            return default_result
        
        analysis_prompt_template = self.get_prompt("analysis_prompt", "Return JSON analysis of turn_text in context.")
        analysis_prompt = analysis_prompt_template.format(
            context=persona_context[:200] if persona_context else 'Sales roleplay call',
            text=turn_text[:500]
        )

        logger.info(f"[GEMINI] Analyzing: '{turn_text[:50]}...'")
        
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=analysis_prompt,
                config=self.config
            )
            
            result = _safe_parse_json(response.text, default_result)
            merged = {**default_result, **result}
            
            logger.debug(f"Analysis result: mood={merged.get('suggested_mood_shift')}, "
                        f"markers={merged.get('behavior_markers')}")
            
            return merged
            
        except Exception as e:
            logger.error(f"Turn analysis failed: {e}")
            return default_result

    async def generate_feedback(
        self,
        transcript: List[dict],
        scenario_context: str,
        success_criteria: List[str],
    ) -> dict:
        """Generate post-call feedback for the sales rep.
        
        Supports multilingual transcripts (English, Hindi, Hinglish, etc.)
        Provides feedback in English regardless of transcript language.
        """
        
        default_feedback = {
            "overall_score": 50,
            "goal_achieved": False,
            "strengths": ["Call completed"],
            "weaknesses": ["Unable to fully analyze"],
            "suggestions": ["Review the recording for detailed feedback"],
            "highlighted_moments": [],
            "summary": "Call analysis was partially completed.",
        }
        
        if not transcript or len(transcript) < 2:
            logger.warning(f"Insufficient transcript: {len(transcript) if transcript else 0} turns")
            return {
                **default_feedback,
                "overall_score": 0,
                "summary": "Call was too short for meaningful analysis.",
                "weaknesses": ["Call ended before meaningful interaction"],
            }
        
        transcript_lines = []
        for i, turn in enumerate(transcript[:25]):
            speaker = "Rep" if turn.get("speaker") == "rep" else "Prospect"
            text = turn.get("text", "")[:250]
            if text:
                transcript_lines.append(f"{speaker}: {text}")
        
        transcript_text = "\n".join(transcript_lines)
        goals = ", ".join(success_criteria[:3]) if success_criteria else "Book a meeting"

        feedback_prompt_template = self.get_prompt("feedback_prompt", "Return JSON feedback for transcript in scenario with goals.")
        feedback_prompt = feedback_prompt_template.format(
            scenario=scenario_context[:100] if scenario_context else 'Sales call',
            goals=goals,
            transcript=transcript_text
        )

        logger.info(f"[GEMINI] Generating feedback for {len(transcript)} turns")
        
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=feedback_prompt,
                config=self.config
            )
            
            logger.debug(f"Feedback raw response: {response.text[:300]}...")
            result = _safe_parse_json(response.text, default_feedback)
            
            if not isinstance(result.get("overall_score"), (int, float)):
                result["overall_score"] = 50
            else:
                result["overall_score"] = max(0, min(100, int(result["overall_score"])))
            
            result.setdefault("goal_achieved", False)
            
            if not isinstance(result.get("strengths"), list) or len(result["strengths"]) == 0:
                result["strengths"] = ["Call was completed"]
            if not isinstance(result.get("weaknesses"), list) or len(result["weaknesses"]) == 0:
                result["weaknesses"] = ["Review recording for specific areas"]
            if not isinstance(result.get("suggestions"), list) or len(result["suggestions"]) == 0:
                result["suggestions"] = ["Continue practicing"]
                
            result.setdefault("summary", "Call completed. Review detailed feedback.")
            result.setdefault("highlighted_moments", [])
            
            logger.info(f"[GEMINI] Feedback generated: score={result['overall_score']}, "
                       f"strengths={len(result['strengths'])}, weaknesses={len(result['weaknesses'])}")
            
            return result
            
        except Exception as e:
            logger.error(f"Feedback generation failed: {e}", exc_info=True)
            return default_feedback

    async def quick_sentiment(self, text: str) -> dict:
        """Quick sentiment analysis for real-time updates.
        
        Lightweight analysis that returns fast for live updates.
        Used during live call for real-time mood estimation.
        """
        if not text or len(text.strip()) < 3:
            return {"mood": "neutral", "rapport_delta": 0}
        
        text_lower = text.lower()
        
        positive_words = [
            "great", "excellent", "thank", "appreciate", "understand", 
            "definitely", "absolutely", "perfect", "wonderful", "yes",
            "accha", "bahut", "dhanyavaad", "zaroor", "bilkul", "theek",
            "sahi", "badiya", "samjha", "haan"
        ]
        
        negative_words = [
            "no", "not", "can't", "won't", "don't", "problem", "issue",
            "expensive", "busy", "later", "nahi", "nahin", "problem",
            "mushkil", "mehnga", "baad", "nahi chahiye"
        ]
        
        filler_words = [
            "um", "uh", "like", "so", "actually", "basically",
            "matlab", "yani", "woh", "aisa"
        ]
        
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        filler_count = sum(1 for word in filler_words if word in text_lower)
        
        if positive_count > negative_count + 1:
            mood = "impressed" if positive_count > 3 else "more_interested"
            rapport_delta = min(0.1, positive_count * 0.03)
        elif negative_count > positive_count + 1:
            mood = "annoyed" if negative_count > 3 else "skeptical"
            rapport_delta = max(-0.1, -negative_count * 0.03)
        elif filler_count > 2:
            mood = "skeptical"
            rapport_delta = -0.02
        else:
            mood = "neutral"
            rapport_delta = 0
        
        return {"mood": mood, "rapport_delta": rapport_delta}

    async def summarize_conversation(
        self,
        turns: List[dict],
    ) -> str:
        """Generate a brief conversation summary."""
        if not turns:
            return "No conversation to summarize."
        
        turns_text = ""
        for turn in turns[-5:]:
            speaker = "Rep" if turn.get("speaker") == "rep" else "Prospect"
            text = turn.get("text", "")[:100]
            turns_text += f"{speaker}: {text}\n"

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=self.get_prompt("summarize_prompt", "Summarize this: {text}").format(text=turns_text),
                config=self.config
            )
            return response.text.strip()[:300]
        except Exception as e:
            logger.error(f"Summary failed: {e}")
            return "Summary unavailable."


_client: Optional[GeminiClient] = None

def get_gemini_client() -> GeminiClient:
    """Get or create the Gemini client singleton."""
    global _client
    if _client is None:
        _client = GeminiClient()
    return _client
