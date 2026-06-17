"""
narrator.py
===========
Turns scene narration text into speech using the ElevenLabs Text-to-Speech API,
then measures each clip so the video timeline can lock to the real audio length
(perfect audio/visual sync).

Only the standard `requests` library is needed — we call the REST endpoint
directly so there is no heavy SDK dependency.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Callable, Optional

import requests

ELEVEN_BASE = "https://api.elevenlabs.io/v1"
DEFAULT_VOICE = "EXAVITQu4vr4xnSDxMaL"   # "Sarah" — warm, friendly, great for explainers
DEFAULT_MODEL = "eleven_turbo_v2_5"      # fast + high quality, supports many languages


class NarrationError(Exception):
    pass


def list_voices(api_key: str) -> list[dict]:
    """Return available voices for the account (id + name)."""
    r = requests.get(f"{ELEVEN_BASE}/voices",
                     headers={"xi-api-key": api_key}, timeout=20)
    if r.status_code != 200:
        raise NarrationError(f"Could not list voices ({r.status_code}): {r.text[:200]}")
    return [{"voice_id": v["voice_id"], "name": v["name"]}
            for v in r.json().get("voices", [])]


def _spoken(text: str) -> str:
    """Make narration read naturally by a TTS voice.
    Fixes things like 'int()' being pronounced 'intee', and reads operators
    as words. Only affects the audio — on-screen captions keep the original.
    """
    t = text or ""
    t = re.sub(r"\b([A-Za-z_]\w*)\(\)", r"\1", t)     # int() -> int, print() -> print
    t = t.replace(">=", " greater than or equal to ").replace("<=", " less than or equal to ")
    t = t.replace("==", " equals ").replace("!=", " not equal to ")
    t = t.replace("≥", " greater than or equal to ").replace("≤", " less than or equal to ")
    t = t.replace("—", ", ").replace("–", ", ")        # em/en dashes -> a natural pause
    t = t.replace("_", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _ffprobe_duration_ms(path: str) -> int:
    """Measure an audio file's duration in milliseconds via ffprobe."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
            capture_output=True, text=True, timeout=20)
        dur = float(json.loads(out.stdout)["format"]["duration"])
        return int(dur * 1000)
    except Exception:
        return 0


def synth_clip(api_key: str, text: str, out_path: str,
               voice_id: str = DEFAULT_VOICE, model_id: str = DEFAULT_MODEL,
               stability: float = 0.45, similarity: float = 0.75,
               style: float = 0.15) -> int:
    """Synthesize one narration clip to `out_path` (mp3). Returns duration in ms."""
    url = f"{ELEVEN_BASE}/text-to-speech/{voice_id}"
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity,
            "style": style,
            "use_speaker_boost": True,
        },
    }
    headers = {"xi-api-key": api_key, "Content-Type": "application/json",
               "Accept": "audio/mpeg"}
    r = requests.post(url, json=payload, headers=headers, timeout=120)
    if r.status_code != 200:
        msg = r.text[:300]
        raise NarrationError(f"ElevenLabs error {r.status_code}: {msg}")
    with open(out_path, "wb") as fh:
        fh.write(r.content)
    return _ffprobe_duration_ms(out_path)


def narrate_script(script: dict, api_key: str, audio_dir: str,
                   voice_id: str = DEFAULT_VOICE,
                   tail_ms: int = 650, min_scene_ms: int = 1600,
                   progress: Optional[Callable[[int, int], None]] = None) -> dict:
    """Generate audio for every scene and rewrite scene durations to match the
    real spoken length. Returns the updated script with an added
    ``audio`` list (one entry per scene: {file, url, ms} or None).

    The script object is modified in place and also returned.
    """
    os.makedirs(audio_dir, exist_ok=True)
    scenes = script["scenes"]
    audio = []
    total = len(scenes)
    for idx, sc in enumerate(scenes):
        text = (sc.get("narration") or "").strip()
        if not text:
            audio.append(None)
            if progress:
                progress(idx + 1, total)
            continue
        fname = f"scene_{idx:03d}.mp3"
        fpath = os.path.join(audio_dir, fname)
        ms = synth_clip(api_key, _spoken(text), fpath, voice_id=voice_id)
        # Lock the scene to the real audio length (+ a small breathing tail).
        sc["durationMs"] = max(min_scene_ms, ms + tail_ms)
        audio.append({"file": fname, "url": f"audio/{fname}", "ms": ms})
        if progress:
            progress(idx + 1, total)

    # Recompute total timeline.
    script["meta"]["totalMs"] = sum(s["durationMs"] for s in scenes)
    script["audio"] = audio
    return script


def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
