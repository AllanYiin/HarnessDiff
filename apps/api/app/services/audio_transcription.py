from __future__ import annotations

import io
import os
from typing import Any, Protocol

from app.providers.base import ProviderConfigurationError


DEFAULT_TRANSCRIPTION_MODEL = "gpt-4o-mini-transcribe"
DIARIZE_TRANSCRIPTION_MODEL = "gpt-4o-transcribe-diarize"
TRADITIONAL_CHINESE_TRANSCRIPTION_PROMPT = (
    "以下是繁體中文語音輸入。請以繁體中文輸出，保留原意、自然標點與台灣常用詞；"
    "不要轉成簡體中文。"
)
SIMPLIFIED_CHINESE_TRANSCRIPTION_PROMPT = (
    "以下是简体中文语音输入。请以简体中文输出，保留原意、自然标点与常用词。"
)


class AudioTranscriber(Protocol):
    async def transcribe_audio(
        self,
        audio: bytes,
        filename: str,
        mime_type: str,
        *,
        accept_language: str | None = None,
    ) -> str:
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

    async def transcribe_audio(
        self,
        audio: bytes,
        filename: str,
        mime_type: str,
        *,
        accept_language: str | None = None,
    ) -> str:
        if not self.api_key:
            raise ProviderConfigurationError(
                "OPENAI_API_KEY is required for voice transcription."
            )

        client = self._build_client()
        file_obj = io.BytesIO(audio)
        file_obj.name = filename or _filename_for_mime_type(mime_type)
        create_kwargs: dict[str, Any] = {
            "file": file_obj,
            "model": self.model,
        }
        preferred_language = _preferred_accept_language(accept_language)
        language = _transcription_language(preferred_language)
        prompt = _transcription_prompt(preferred_language)
        if language:
            create_kwargs["language"] = language
        if prompt and self.model != DIARIZE_TRANSCRIPTION_MODEL:
            create_kwargs["prompt"] = prompt

        transcription = await client.audio.transcriptions.create(**create_kwargs)
        if isinstance(transcription, dict):
            return str(transcription.get("text", "")).strip()
        text = getattr(transcription, "text", "")
        if isinstance(text, str):
            return text.strip()
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


def _preferred_accept_language(accept_language: str | None) -> str:
    preferences: list[tuple[float, int, str]] = []
    for index, raw_part in enumerate((accept_language or "").split(",")):
        tag, q_value = _accept_language_part(raw_part)
        if not tag or tag == "*" or q_value <= 0:
            continue
        preferences.append((-q_value, index, tag))
    if not preferences:
        return ""
    preferences.sort()
    return preferences[0][2]


def _accept_language_part(raw_part: str) -> tuple[str, float]:
    parts = [part.strip() for part in raw_part.split(";") if part.strip()]
    if not parts:
        return "", 0
    tag = parts[0].replace("_", "-")
    if not _is_language_tag(tag):
        return "", 0
    q_value = 1.0
    for parameter in parts[1:]:
        key, separator, value = parameter.partition("=")
        if separator and key.strip().lower() == "q":
            try:
                q_value = float(value.strip())
            except ValueError:
                return "", 0
    return tag, max(0, min(q_value, 1))


def _is_language_tag(tag: str) -> bool:
    return all(
        character.isascii() and (character.isalnum() or character == "-")
        for character in tag
    )


def _transcription_language(preferred_language: str) -> str:
    base_language = preferred_language.split("-", 1)[0].lower()
    if 2 <= len(base_language) <= 3 and base_language.isalpha():
        return base_language
    return ""


def _transcription_prompt(preferred_language: str) -> str:
    tag_parts = {part.lower() for part in preferred_language.split("-") if part}
    if "zh" not in tag_parts:
        return ""
    if tag_parts & {"hant", "tw", "hk", "mo"}:
        return TRADITIONAL_CHINESE_TRANSCRIPTION_PROMPT
    if tag_parts & {"hans", "cn", "sg"}:
        return SIMPLIFIED_CHINESE_TRANSCRIPTION_PROMPT
    return ""
