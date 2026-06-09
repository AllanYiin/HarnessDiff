from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.audio_transcription import OpenAIAudioTranscriber


class FakeAudioTranscriber:
    def __init__(self) -> None:
        self.calls: list[tuple[bytes, str, str]] = []

    async def transcribe_audio(self, audio: bytes, filename: str, mime_type: str) -> str:
        self.calls.append((audio, filename, mime_type))
        return "測試語音"


class MetadataAudioTranscriber:
    def __init__(self) -> None:
        self.calls: list[tuple[bytes, str, str, str | None]] = []

    async def transcribe_audio(
        self,
        audio: bytes,
        filename: str,
        mime_type: str,
        *,
        accept_language: str | None = None,
    ) -> str:
        self.calls.append((audio, filename, mime_type, accept_language))
        return "測試語音"


class FakeOpenAITranscriptions:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> dict[str, str]:
        self.calls.append(kwargs)
        return {"text": "  語音內容  "}


class FakeOpenAIAudio:
    def __init__(self) -> None:
        self.transcriptions = FakeOpenAITranscriptions()


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.audio = FakeOpenAIAudio()


def test_audio_transcription_accepts_raw_webm_payload(tmp_path) -> None:
    transcriber = FakeAudioTranscriber()
    client = TestClient(
        create_app(
            data_dir=tmp_path,
            harnessdiff_home=tmp_path / ".harnessdiff",
            audio_transcriber=transcriber,
        )
    )

    response = client.post(
        "/api/audio/transcriptions",
        content=b"webm-bytes",
        headers={
            "content-type": "audio/webm;codecs=opus",
            "x-audio-filename": "../voice.webm",
            "accept-language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"text": "測試語音"}
    assert transcriber.calls == [(b"webm-bytes", "voice.webm", "audio/webm")]


def test_audio_transcription_passes_accept_language_to_metadata_transcriber(tmp_path) -> None:
    transcriber = MetadataAudioTranscriber()
    client = TestClient(
        create_app(
            data_dir=tmp_path,
            harnessdiff_home=tmp_path / ".harnessdiff",
            audio_transcriber=transcriber,
        )
    )

    response = client.post(
        "/api/audio/transcriptions",
        content=b"webm-bytes",
        headers={
            "content-type": "audio/webm",
            "accept-language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    )

    assert response.status_code == 200
    assert transcriber.calls == [
        (
            b"webm-bytes",
            "voice-input.webm",
            "audio/webm",
            "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        )
    ]


def test_audio_transcription_rejects_unsupported_mime_type(tmp_path) -> None:
    transcriber = FakeAudioTranscriber()
    client = TestClient(
        create_app(
            data_dir=tmp_path,
            harnessdiff_home=tmp_path / ".harnessdiff",
            audio_transcriber=transcriber,
        )
    )

    response = client.post(
        "/api/audio/transcriptions",
        content=b"not-audio",
        headers={"content-type": "application/octet-stream"},
    )

    assert response.status_code == 415
    assert transcriber.calls == []


def test_openai_transcriber_uses_traditional_chinese_accept_language_prompt() -> None:
    openai_client = FakeOpenAIClient()
    transcriber = OpenAIAudioTranscriber(
        api_key="test-key",
        client_factory=lambda api_key: openai_client,
    )

    text = asyncio.run(
        transcriber.transcribe_audio(
            b"webm-bytes",
            "voice.webm",
            "audio/webm",
            accept_language="zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        )
    )

    assert text == "語音內容"
    assert len(openai_client.audio.transcriptions.calls) == 1
    call = openai_client.audio.transcriptions.calls[0]
    assert call["model"] == "gpt-4o-mini-transcribe"
    assert call["language"] == "zh"
    assert "繁體中文" in str(call["prompt"])
    assert "不要轉成簡體中文" in str(call["prompt"])
    assert getattr(call["file"], "name") == "voice.webm"


def test_openai_transcriber_uses_highest_q_accept_language_for_prompt() -> None:
    openai_client = FakeOpenAIClient()
    transcriber = OpenAIAudioTranscriber(
        api_key="test-key",
        client_factory=lambda api_key: openai_client,
    )

    asyncio.run(
        transcriber.transcribe_audio(
            b"webm-bytes",
            "voice.webm",
            "audio/webm",
            accept_language="en-US;q=0.4,zh-Hant;q=0.9",
        )
    )

    call = openai_client.audio.transcriptions.calls[0]
    assert call["language"] == "zh"
    assert "繁體中文" in str(call["prompt"])
