from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.providers.base import ProviderConfigurationError

router = APIRouter(tags=["audio"])

MAX_AUDIO_BYTES = 25 * 1024 * 1024
SUPPORTED_AUDIO_MIME_TYPES = {
    "audio/mp3",
    "audio/mp4",
    "audio/mpeg",
    "audio/mpga",
    "audio/m4a",
    "audio/wav",
    "audio/webm",
    "video/webm",
}


class AudioTranscriptionResponse(BaseModel):
    text: str


@router.post("/audio/transcriptions", response_model=AudioTranscriptionResponse)
async def transcribe_audio(request: Request) -> AudioTranscriptionResponse:
    mime_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if mime_type not in SUPPORTED_AUDIO_MIME_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported audio type")

    audio = await request.body()
    if not audio:
        raise HTTPException(status_code=400, detail="Audio payload is empty")
    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio payload exceeds 25 MB")

    filename = _safe_audio_filename(
        request.headers.get("x-audio-filename"),
        fallback=_filename_for_mime_type(mime_type),
    )
    accept_language = request.headers.get("accept-language")
    transcriber = request.app.state.audio_transcriber
    try:
        text = await _transcribe_audio(
            transcriber,
            audio,
            filename,
            mime_type,
            accept_language=accept_language,
        )
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from None
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Voice transcription failed: {exc}") from exc
    return AudioTranscriptionResponse(text=text)


def _safe_audio_filename(raw: str | None, fallback: str) -> str:
    candidate = Path(raw or fallback).name.strip()
    return candidate or fallback


def _filename_for_mime_type(mime_type: str) -> str:
    if mime_type == "audio/wav":
        return "voice-input.wav"
    if mime_type in {"audio/mp3", "audio/mpeg"}:
        return "voice-input.mp3"
    if mime_type in {"audio/mp4", "video/mp4"}:
        return "voice-input.mp4"
    return "voice-input.webm"


async def _transcribe_audio(
    transcriber: Any,
    audio: bytes,
    filename: str,
    mime_type: str,
    *,
    accept_language: str | None,
) -> str:
    if _accepts_accept_language(transcriber):
        return await transcriber.transcribe_audio(
            audio,
            filename,
            mime_type,
            accept_language=accept_language,
        )
    return await transcriber.transcribe_audio(audio, filename, mime_type)


def _accepts_accept_language(transcriber: Any) -> bool:
    try:
        signature = inspect.signature(transcriber.transcribe_audio)
    except (AttributeError, TypeError, ValueError):
        return False
    return any(
        name == "accept_language" or parameter.kind is inspect.Parameter.VAR_KEYWORD
        for name, parameter in signature.parameters.items()
    )
