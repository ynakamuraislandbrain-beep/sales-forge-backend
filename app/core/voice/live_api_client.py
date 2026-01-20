"""Gemini Live API client for real-time bidirectional audio streaming.

This module provides a WebSocket-based client for the Gemini Live API,
enabling low-latency voice conversations with context injection support.
"""

import asyncio
import logging
from typing import AsyncIterator, Optional, Callable, Any
from dataclasses import dataclass, field

from google import genai
from google.genai import types

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class LiveSessionConfig:
    """Configuration for a Live API session."""
    
    model: Optional[str] = None
    response_modalities: list = field(default_factory=lambda: ["AUDIO"])
    input_audio_transcription: bool = True
    output_audio_transcription: bool = True 
    voice: Optional[str] = None 
    language: str = "en-US"


class LiveAPIClient:
    """Client for Gemini Live API with bidirectional audio streaming.
    
    This client manages:
    - WebSocket connection to Gemini Live API
    - Audio streaming (send/receive)
    - Context injection for dynamic behavior updates
    - Transcription capture for analytics
    """
    
    def __init__(self, config: Optional[LiveSessionConfig] = None):
        """Initialize the Live API client.
        
        Args:
            config: Session configuration. Uses defaults if not provided.
        """
        settings = get_settings()
        self.config = config or LiveSessionConfig(model=settings.live_api_model)
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.session: Optional[Any] = None
        self._session_ctx: Optional[Any] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._audio_queue: asyncio.Queue = asyncio.Queue()
        self._transcription_queue: asyncio.Queue = asyncio.Queue()
        self._is_connected = False
        self._on_audio_callback: Optional[Callable[[bytes], Any]] = None
        self._on_transcription_callback: Optional[Callable[[str, str], Any]] = None
        
    async def connect(
        self,
        system_instruction: str,
        on_audio: Optional[Callable[[bytes], Any]] = None,
        on_transcription: Optional[Callable[[str, str], Any]] = None,
    ) -> None:
        """Connect to Gemini Live API.
        
        Args:
            system_instruction: The full system prompt (persona, scenario, state)
            on_audio: Callback for received audio chunks
            on_transcription: Callback for transcriptions (speaker, text)
        """
        if self._is_connected:
            logger.warning("Already connected to Live API")
            return
            
        self._on_audio_callback = on_audio
        self._on_transcription_callback = on_transcription
        
        session_config = types.LiveConnectConfig(
            response_modalities=self.config.response_modalities,
            system_instruction=system_instruction,
            input_audio_transcription=types.AudioTranscriptionConfig()
            if self.config.input_audio_transcription else None,
            output_audio_transcription=types.AudioTranscriptionConfig()
            if self.config.output_audio_transcription else None,
            context_window_compression=types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow(),
            ),
        )
        
        if self.config.voice:
            session_config.speech_config = types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.config.voice
                    )
                )
            )
        
        try:
            self._session_ctx = self.client.aio.live.connect(
                model=self.config.model,
                config=session_config,
            )
            self.session = await self._session_ctx.__aenter__()
            self._is_connected = True
            logger.info(f"Connected to Gemini Live API with model {self.config.model}")
            
            self._receive_task = asyncio.create_task(self._receive_loop())
            
        except Exception as e:
            logger.error(f"Failed to connect to Live API: {e}")
            raise
    
    async def _receive_loop(self) -> None:
        """Background task to receive responses from Live API."""
        logger.info("Starting receive loop...")
        try:
            while self._is_connected and self.session:
                logger.debug("Waiting for response from Live API...")
                turn = self.session.receive()
                async for response in turn:
                    logger.debug(f"Received response type: {type(response)}")
                    await self._process_response(response)
        except asyncio.CancelledError:
            logger.info("Receive loop cancelled")
        except Exception as e:
            logger.error(f"Error in receive loop: {e}", exc_info=True)
    
    async def _process_response(self, response: Any) -> None:
        """Process a response from Live API.
        
        Handles audio data and transcriptions.
        """
        if response.server_content and response.server_content.model_turn:
            for part in response.server_content.model_turn.parts:
                if part.inline_data and isinstance(part.inline_data.data, bytes):
                    audio_data = part.inline_data.data
                    logger.debug(f"Received audio chunk: {len(audio_data)} bytes")
                    await self._audio_queue.put(audio_data)
                    if self._on_audio_callback:
                        await self._on_audio_callback(audio_data)
        
        if hasattr(response, 'server_content') and response.server_content:
            if hasattr(response.server_content, 'output_transcription'):
                transcript = response.server_content.output_transcription
                if transcript and transcript.text:
                    await self._transcription_queue.put(("ai", transcript.text))
                    if self._on_transcription_callback:
                        await self._on_transcription_callback("ai", transcript.text)
        
        if hasattr(response, 'server_content') and response.server_content:
            if hasattr(response.server_content, 'input_transcription'):
                transcript = response.server_content.input_transcription
                if transcript and transcript.text:
                    await self._transcription_queue.put(("user", transcript.text))
                    if self._on_transcription_callback:
                        await self._on_transcription_callback("user", transcript.text)
    
    async def send_audio(self, audio_chunk: bytes, mime_type: str = "audio/pcm;rate=16000") -> None:
        """Send an audio chunk to Live API.
        
        Args:
            audio_chunk: Raw 16-bit PCM audio data
            mime_type: Audio MIME type with sample rate
        """
        if not self._is_connected or not self.session:
            raise RuntimeError("Not connected to Live API")
        
        await self.session.send_realtime_input(
            audio={"data": audio_chunk, "mime_type": mime_type}
        )
    
    async def inject_context(self, context: str) -> None:
        """Inject context update into the conversation.
        
        This is used to update the AI's understanding of the current
        conversation state (mood, rapport, etc.) without rebuilding
        the entire system prompt.
        
        Args:
            context: Context injection text from PromptBuilder.build_context_injection()
        """
        if not self._is_connected or not self.session:
            raise RuntimeError("Not connected to Live API")
        
        await self.session.send_client_content(
            turns=[{"role": "user", "parts": [{"text": f"[CONTEXT UPDATE]\n{context}"}]}],
            turn_complete=False, 
        )
        logger.debug("Injected context update into Live session")
    
    async def receive_audio(self) -> AsyncIterator[bytes]:
        """Async iterator for received audio chunks.
        
        Yields:
            Audio data chunks from the AI response
        """
        while self._is_connected:
            try:
                audio = await asyncio.wait_for(
                    self._audio_queue.get(),
                    timeout=0.1
                )
                yield audio
            except asyncio.TimeoutError:
                continue
    
    async def get_transcription(self) -> Optional[tuple[str, str]]:
        """Get the next transcription from the queue.
        
        Returns:
            Tuple of (speaker, text) or None if queue is empty
        """
        try:
            return self._transcription_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None
    
    async def get_all_transcriptions(self) -> list[tuple[str, str]]:
        """Get all pending transcriptions from the queue.
        
        Returns:
            List of (speaker, text) tuples
        """
        transcriptions = []
        while True:
            try:
                transcriptions.append(self._transcription_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return transcriptions
    
    async def disconnect(self) -> None:
        """Disconnect from Live API."""
        self._is_connected = False
        
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None
        
        if self._session_ctx:
            try:
                await self._session_ctx.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error closing Live session: {e}")
            self._session_ctx = None
            self.session = None
        
        logger.info("Disconnected from Gemini Live API")
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to Live API."""
        return self._is_connected
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()


def get_live_api_client(config: Optional[LiveSessionConfig] = None) -> LiveAPIClient:
    """Factory function to create a Live API client.
    
    Args:
        config: Optional session configuration
        
    Returns:
        LiveAPIClient instance
    """
    return LiveAPIClient(config)
