"""
config.py
=========
One small JSON file holds the user's settings (API keys + sensible defaults) so
the keys are entered ONCE and never clutter the main UI. Secrets are never sent
back to the browser — only booleans saying whether they're set.
"""

from __future__ import annotations

import json
import os
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.json")
_LOCK = threading.Lock()

DEFAULTS = {
    "anthropic_key": "",
    "elevenlabs_key": "",
    "voice_id": "EXAVITQu4vr4xnSDxMaL",     # warm, friendly default
    "style": "cartoon",
    "engine": "auto",                       # auto -> web engine (preview == MP4)
    "target_sec": 240,
    "narrate": True,
    "model": "claude-sonnet-4-6",
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            cfg.update(json.load(fh))
    except Exception:
        pass
    return cfg


def save(updates: dict) -> dict:
    with _LOCK:
        cfg = load()
        for k, v in (updates or {}).items():
            if k in DEFAULTS and v is not None and v != "":
                cfg[k] = v
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)
    return cfg


def status() -> dict:
    """Public, secret-free view for the browser."""
    cfg = load()
    return {
        "has_anthropic": bool(cfg.get("anthropic_key")),
        "has_elevenlabs": bool(cfg.get("elevenlabs_key")),
        "voice_id": cfg.get("voice_id"),
        "style": cfg.get("style"),
        "engine": cfg.get("engine"),
        "target_sec": cfg.get("target_sec"),
        "narrate": cfg.get("narrate"),
    }
