"""
manim_render.py
===============
Render a PyExplain scene script to MP4 using Manim Community Edition, then mux
the ElevenLabs narration on top.

Pipeline:
  1. write the scene script to <job>/script.json
  2. run the `manim` CLI on manim_explainer.py (reads the script via env vars)
  3. locate the silent MP4 Manim produced
  4. build the narration soundtrack (reusing renderer.build_soundtrack) and mux
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
from typing import Callable, Optional

from renderer import RenderError, build_soundtrack   # reuse audio assembly

HERE = os.path.dirname(os.path.abspath(__file__))
SCENE_FILE = os.path.join(HERE, "manim_explainer.py")


def manim_available() -> tuple[bool, str]:
    if shutil.which("manim") is None:
        return False, ("Manim isn't installed. Install Manim Community Edition:  "
                       "pip install manim   (plus system libs: on macOS  "
                       "brew install py3cairo pango pkg-config)")
    if shutil.which("ffmpeg") is None:
        return False, "ffmpeg not found on PATH."
    return True, ""


def _run(cmd, env=None, cwd=None):
    p = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=cwd)
    if p.returncode != 0:
        raise RenderError(f"{os.path.basename(cmd[0])} failed:\n{(p.stderr or p.stdout)[-900:]}")
    return p


def render_video(job_dir: str, script: dict, theme: str = "cartoon",
                 with_audio: bool = True,
                 progress: Optional[Callable[[str, float], None]] = None) -> str:
    ok, msg = manim_available()
    if not ok:
        raise RenderError(msg)

    os.makedirs(job_dir, exist_ok=True)
    script_path = os.path.join(job_dir, "script.json")
    with open(script_path, "w", encoding="utf-8") as fh:
        json.dump(script, fh)

    media_dir = os.path.join(job_dir, "manim")
    os.makedirs(media_dir, exist_ok=True)

    env = dict(os.environ)
    env["PYEXPLAIN_SCRIPT"] = script_path
    env["PYEXPLAIN_THEME"] = theme

    if progress:
        progress("rendering", 0.05)

    # -qh => 1080p60. Caching off so re-renders always reflect the latest script.
    cmd = ["manim", "-qh", "--format=mp4", "--fps", "60",
           "--media_dir", media_dir, "--disable_caching",
           "-v", "WARNING", "--progress_bar", "none",
           SCENE_FILE, "CodeExplainer"]
    _run(cmd, env=env, cwd=job_dir)

    if progress:
        progress("rendering", 0.85)

    # locate the produced mp4
    matches = sorted(glob.glob(os.path.join(media_dir, "**", "CodeExplainer*.mp4"),
                               recursive=True), key=os.path.getmtime)
    if not matches:
        raise RenderError("Manim finished but no output video was found.")
    silent = matches[-1]
    out_path = os.path.join(job_dir, "video.mp4")

    if with_audio and script.get("audio") and any(script["audio"]):
        if progress:
            progress("mixing", 0.0)
        audio_dir = os.path.join(job_dir, "audio")
        wav = os.path.join(job_dir, "soundtrack.wav")
        build_soundtrack(script, audio_dir, wav)
        if progress:
            progress("encoding", 0.0)
        _run(["ffmpeg", "-y", "-i", silent, "-i", wav,
              "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
              "-shortest", "-movflags", "+faststart", out_path])
    else:
        shutil.copyfile(silent, out_path)

    if progress:
        progress("encoding", 1.0)
    return out_path
