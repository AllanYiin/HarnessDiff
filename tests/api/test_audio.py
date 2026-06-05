from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


class FakeAudioTranscriber:
    def __init__(self) -> None:
        self.calls: list[tuple[bytes, str, str]] = []

    async def transcribe_audio(self, audio: bytes, filename: str, mime_type: str) -> str:
        self.calls.append((audio, filename, mime_type))
        return "測試語音"


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
        },
    )

    assert response.status_code == 200
    assert response.json() == {"text": "測試語音"}
    assert transcriber.calls == [(b"webm-bytes", "voice.webm", "audio/webm")]


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
