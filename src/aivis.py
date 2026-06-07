"""HTTP client for AivisSpeech (VOICEVOX-compatible) engine.

Default endpoint: http://127.0.0.1:10101 (override via AIVIS_ENDPOINT env or
project.yaml `voice.endpoint`).

Two-step synthesis flow:
  1. POST /audio_query?text=...&speaker=<style_id>  → AudioQuery JSON
     (predicted readings + accent + prosody)
  2. POST /synthesis?speaker=<style_id>  body=AudioQuery  → wav bytes

For M2 (basic) we don't edit the AudioQuery — readings come from the engine's
default G2P. M5 adds moras editing (layer 2) and Whisper verification (layer 3).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import httpx


DEFAULT_ENDPOINT = "http://127.0.0.1:10101"


class AivisError(RuntimeError):
    pass


class AivisClient:
    def __init__(self, endpoint: str | None = None, timeout: float = 60.0):
        self.endpoint = (endpoint or os.environ.get("AIVIS_ENDPOINT") or DEFAULT_ENDPOINT).rstrip("/")
        self._client = httpx.Client(timeout=timeout)

    # ---- inventory ----

    def speakers(self) -> list[dict]:
        r = self._client.get(f"{self.endpoint}/speakers")
        r.raise_for_status()
        return r.json()

    def installed_models(self) -> dict:
        r = self._client.get(f"{self.endpoint}/aivm_models")
        r.raise_for_status()
        return r.json()

    def installed_style_ids(self) -> dict[int, tuple[str, str]]:
        """Return {style_id: (speaker_name, style_name)} for everything currently loadable."""
        out: dict[int, tuple[str, str]] = {}
        for s in self.speakers():
            for st in s["styles"]:
                out[int(st["id"])] = (s["name"], st["name"])
        return out

    def has_style(self, style_id: int) -> bool:
        return style_id in self.installed_style_ids()

    # ---- synthesis ----

    def audio_query(self, text: str, speaker: int) -> dict:
        r = self._client.post(
            f"{self.endpoint}/audio_query",
            params={"text": text, "speaker": speaker},
        )
        if r.status_code >= 400:
            raise AivisError(f"audio_query failed [{r.status_code}]: {r.text[:500]}")
        return r.json()

    def synthesis(self, audio_query: dict, speaker: int) -> bytes:
        r = self._client.post(
            f"{self.endpoint}/synthesis",
            params={"speaker": speaker, "enable_interrogative_upspeak": "true"},
            json=audio_query,
        )
        if r.status_code >= 400:
            raise AivisError(f"synthesis failed [{r.status_code}]: {r.text[:500]}")
        return r.content

    def synthesize(
        self,
        text: str,
        speaker: int,
        out_path: Path,
        *,
        speed: float = 1.0,
        pitch: float = 0.0,
        intonation: float = 1.0,
        volume: float = 1.0,
    ) -> Path:
        """Synthesize one utterance. If out_path ends in .mp3, transcode via ffmpeg.

        Returns the written path.
        """
        aq = self.audio_query(text, speaker)
        # Apply prosody overrides (Aivis honors the standard VOICEVOX fields).
        aq["speedScale"] = speed
        aq["pitchScale"] = pitch
        aq["intonationScale"] = intonation
        aq["volumeScale"] = volume
        wav = self.synthesis(aq, speaker)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.suffix.lower() == ".wav":
            out_path.write_bytes(wav)
            return out_path

        # Transcode to mp3 (or whatever the suffix says) via ffmpeg.
        wav_tmp = out_path.with_suffix(".tmp.wav")
        wav_tmp.write_bytes(wav)
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(wav_tmp), "-c:a", "libmp3lame", "-b:a", "192k", str(out_path)],
                check=True, capture_output=True,
            )
        finally:
            wav_tmp.unlink(missing_ok=True)
        return out_path

    def close(self) -> None:
        self._client.close()


_DEFAULT: AivisClient | None = None


def default_client() -> AivisClient:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = AivisClient()
    return _DEFAULT
