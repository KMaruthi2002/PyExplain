"""
renderer.py
===========
Renders the animation engine to a real MP4 file.

How it works
------------
1. A headless Chromium (Playwright) loads ``player.html`` in *manual* mode so we
   control the clock. Because the engine is deterministic — every frame is a pure
   function of time — we can seek to ``t = frame / fps`` and screenshot an exact,
   reproducible frame.
2. ffmpeg encodes the PNG frames into a silent H.264 video.
3. If narration audio exists, we build one continuous soundtrack by placing each
   scene's clip at its scene start (padded with silence to the scene length) and
   mux it onto the video.

Everything degrades gracefully: if Playwright isn't installed we raise a clear,
actionable error that the UI surfaces to the user.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
from typing import Callable, Optional


class RenderError(Exception):
    pass


def playwright_ready() -> tuple[bool, str]:
    try:
        from playwright.sync_api import sync_playwright  # noqa
    except Exception:
        return False, "Playwright isn't installed. Run:  pip install playwright  &&  playwright install chromium"
    return True, ""


def _run(cmd: list[str]):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RenderError(f"command failed: {' '.join(cmd[:3])}…\n{p.stderr[-500:]}")
    return p


def _scene_starts(scenes) -> list[int]:
    starts, acc = [], 0
    for s in scenes:
        starts.append(acc)
        acc += s.get("durationMs", 1500)
    return starts


# --------------------------------------------------------------------------- #
#  Frame capture
# --------------------------------------------------------------------------- #
def capture_frames(player_url: str, script: dict, theme: str, frames_dir: str,
                   fps: int, progress: Optional[Callable[[int, int], None]] = None) -> int:
    from playwright.sync_api import sync_playwright

    os.makedirs(frames_dir, exist_ok=True)
    total_ms = sum(s.get("durationMs", 1500) for s in script["scenes"])
    total_frames = max(1, math.ceil(total_ms / 1000 * fps))

    launch_args = ["--force-color-profile=srgb", "--hide-scrollbars", "--disable-gpu-vsync"]
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(args=launch_args)
        except Exception as e1:
            # Fall back to a system-installed Chrome/Edge if the bundled
            # Chromium wasn't downloaded.
            for channel in ("chrome", "msedge", "chromium"):
                try:
                    browser = pw.chromium.launch(channel=channel, args=launch_args)
                    break
                except Exception:
                    browser = None
            if browser is None:
                raise RenderError(
                    "Couldn't launch a browser to render frames. Install the engine with:  "
                    "python -m playwright install chromium\n(original error: %s)" % e1)
        page = browser.new_page(viewport={"width": 1920, "height": 1080},
                                device_scale_factor=1)
        page.goto(player_url, wait_until="load")
        # boot the engine in manual (frame-seek) mode, no preview audio
        page.evaluate(
            """([script, theme]) => window.bootEngine(script, {manual:true, theme:theme, audio:null})""",
            [script, theme],
        )
        page.wait_for_function("window.__ready === true", timeout=15000)
        # let webfonts settle
        page.wait_for_timeout(300)

        for f in range(total_frames):
            t = f / fps * 1000.0
            page.evaluate("(t) => window.__engine.renderAt(t)", t)
            page.screenshot(path=os.path.join(frames_dir, f"frame_{f:05d}.png"),
                            clip={"x": 0, "y": 0, "width": 1920, "height": 1080})
            if progress and (f % 5 == 0 or f == total_frames - 1):
                progress(f + 1, total_frames)
        browser.close()
    return total_frames


# --------------------------------------------------------------------------- #
#  Audio track assembly
# --------------------------------------------------------------------------- #
def build_soundtrack(script: dict, audio_dir: str, out_wav: str):
    """Place each scene's narration clip at its scene start, padded with silence
    to fill the scene, then concatenate into one track matching the video."""
    scenes = script["scenes"]
    audio = script.get("audio") or [None] * len(scenes)
    seg_dir = os.path.join(audio_dir, "_segments")
    os.makedirs(seg_dir, exist_ok=True)
    seg_paths = []

    for i, sc in enumerate(scenes):
        dur_s = sc.get("durationMs", 1500) / 1000.0
        seg = os.path.join(seg_dir, f"seg_{i:03d}.wav")
        a = audio[i] if i < len(audio) else None
        if a and a.get("file"):
            clip = os.path.join(audio_dir, a["file"])
            # decode clip, pad with silence up to the exact scene length
            _run(["ffmpeg", "-y", "-i", clip,
                   "-af", f"apad", "-t", f"{dur_s:.3f}",
                   "-ar", "44100", "-ac", "2", seg])
        else:
            _run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                   "anullsrc=channel_layout=stereo:sample_rate=44100",
                   "-t", f"{dur_s:.3f}", seg])
        seg_paths.append(seg)

    concat_list = os.path.join(seg_dir, "list.txt")
    with open(concat_list, "w") as fh:
        for p in seg_paths:
            fh.write(f"file '{os.path.abspath(p)}'\n")
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
          "-ar", "44100", "-ac", "2", out_wav])


# --------------------------------------------------------------------------- #
#  Encode
# --------------------------------------------------------------------------- #
def encode_video(frames_dir: str, fps: int, out_path: str,
                 audio_wav: Optional[str] = None):
    frame_glob = os.path.join(frames_dir, "frame_%05d.png")
    if audio_wav and os.path.exists(audio_wav):
        _run(["ffmpeg", "-y", "-framerate", str(fps), "-i", frame_glob,
              "-i", audio_wav,
              "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
              "-preset", "medium",
              "-c:a", "aac", "-b:a", "192k", "-shortest",
              "-movflags", "+faststart", out_path])
    else:
        _run(["ffmpeg", "-y", "-framerate", str(fps), "-i", frame_glob,
              "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
              "-preset", "medium", "-movflags", "+faststart", out_path])


# --------------------------------------------------------------------------- #
#  Orchestration
# --------------------------------------------------------------------------- #
def render_video(job_dir: str, player_url: str, script: dict, theme: str,
                 fps: int = 30, with_audio: bool = True,
                 progress: Optional[Callable[[str, float], None]] = None) -> str:
    """Full pipeline → returns path to final mp4. `progress(stage, frac)`."""
    ok, msg = playwright_ready()
    if not ok:
        raise RenderError(msg)
    if shutil.which("ffmpeg") is None:
        raise RenderError("ffmpeg not found on PATH. Install ffmpeg and try again.")

    frames_dir = os.path.join(job_dir, "frames")
    audio_dir = os.path.join(job_dir, "audio")
    out_path = os.path.join(job_dir, "video.mp4")

    def fp(stage):
        def cb(done, total):
            if progress:
                progress(stage, done / max(1, total))
        return cb

    capture_frames(player_url, script, theme, frames_dir, fps, progress=fp("rendering"))

    audio_wav = None
    if with_audio and script.get("audio") and any(script["audio"]):
        if progress:
            progress("mixing", 0.0)
        audio_wav = os.path.join(job_dir, "soundtrack.wav")
        build_soundtrack(script, audio_dir, audio_wav)
        if progress:
            progress("mixing", 1.0)

    if progress:
        progress("encoding", 0.0)
    encode_video(frames_dir, fps, out_path, audio_wav)
    if progress:
        progress("encoding", 1.0)

    # tidy up frames to save disk
    try:
        shutil.rmtree(frames_dir, ignore_errors=True)
    except Exception:
        pass
    return out_path
