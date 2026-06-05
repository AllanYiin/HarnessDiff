from __future__ import annotations

import io
import os
from typing import Any, Protocol

from app.providers.base import ProviderConfigurationError


DEFAULT_TRANSCRIPTION_MODEL = "gpt-4o-mini-transcribe"


class AudioTranscriber(Protocol):
    async def transcribe_audio(self, audio: bytes, filename: str, mime_type: str) -> str:
        raise NotImplementedError


class OpenAIAudioTranscriber:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str | None = None,
        client_factory: Any | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = (
            model
            or os.environ.get("OPENAI_TRANSCRIPTION_MODEL")
            or DEFAULT_TRANSCRIPTION_MODEL
        )
        self.client_factory = client_factory

    async def transcribe_audio(self, audio: bytes, filename: str, mime_type: str) -> str:
        if not self.api_key:
            raise ProviderConfigurationError(
                "OPENAI_API_KEY is required for voice transcription."
            )

        client = self._build_client()
        file_obj = io.BytesIO(audio)
        file_obj.name = filename or _filename_for_mime_type(mime_type)
        transcription = await client.audio.transcriptions.create(
            file=file_obj,
            model=self.model,
        )
        text = getattr(transcription, "text", "")
        if isinstance(text, str):
            return text.strip()
        if isinstance(transcription, dict):
            return str(transcription.get("text", "")).strip()
        return ""

    def _build_client(self) -> Any:
        if self.client_factory is not None:
            return self.client_factory(api_key=self.api_key)
        from openai import AsyncOpenAI

        return AsyncOpenAI(api_key=self.api_key)


def _filename_for_mime_type(mime_type: str) -> str:
    if mime_type == "audio/wav":
        return "voice-input.wav"
    if mime_type == "audio/mpeg":
        return "voice-input.mp3"
    if mime_type == "audio/mp4":
        return "voice-input.mp4"
    return "voice-input.webm"
