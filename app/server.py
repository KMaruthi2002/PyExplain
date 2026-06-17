"""
server.py
=========
FastAPI backend for the Python Code Explainer.

Pipeline the UI drives:
  1. POST /api/analyze   -> scene script (instant, offline)        [preview now]
  2. POST /api/narrate   -> ElevenLabs audio per scene (a job)     [optional]
  3. POST /api/render    -> MP4 via Playwright + ffmpeg (a job)     [download]

Jobs run on background threads; the UI polls GET /api/job/{id}.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
JOBS_ROOT = os.path.join(os.path.dirname(HERE), "jobs")
os.makedirs(JOBS_ROOT, exist_ok=True)

sys.path.insert(0, HERE)
import analyzer            # noqa: E402
import narrator            # noqa: E402
import renderer            # noqa: E402
import manim_render        # noqa: E402
import config as appconfig # noqa: E402
import director            # noqa: E402

PORT = int(os.environ.get("EXPLAINER_PORT", "8000"))
PLAYER_URL = f"http://127.0.0.1:{PORT}/static/player.html"

app = FastAPI(title="Python Code Explainer")

# in-memory job registry
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def _set_job(jid: str, **kw):
    with JOBS_LOCK:
        JOBS.setdefault(jid, {}).update(kw)


def _get_job(jid: str) -> Optional[dict]:
    with JOBS_LOCK:
        j = JOBS.get(jid)
        return dict(j) if j else None


# --------------------------------------------------------------------------- #
#  Models
# --------------------------------------------------------------------------- #
class AnalyzeReq(BaseModel):
    code: str
    target_sec: int = 60
    title: str = ""
    script_text: str = ""
    script_mode: str = "auto"        # "auto" | "custom"
    framing: bool = True             # add intro & outro cards


class AuthorReq(BaseModel):
    code: str
    brief: str = ""
    title: str = ""
    target_sec: Optional[int] = None


class ConfigSaveReq(BaseModel):
    anthropic_key: Optional[str] = None
    elevenlabs_key: Optional[str] = None
    voice_id: Optional[str] = None
    style: Optional[str] = None
    engine: Optional[str] = None
    target_sec: Optional[int] = None
    narrate: Optional[bool] = None


class VoicesReq(BaseModel):
    api_key: Optional[str] = None


class NarrateReq(BaseModel):
    script: dict
    api_key: Optional[str] = None        # falls back to saved config
    voice_id: Optional[str] = None


class RenderReq(BaseModel):
    script: dict
    theme: Optional[str] = None
    fps: int = 30
    job_id: Optional[str] = None     # reuse a narrate job (so audio files are present)
    with_audio: bool = True
    engine: Optional[str] = None     # "manim" | "html" | "auto" (falls back to config)


# --------------------------------------------------------------------------- #
#  Static / pages
# --------------------------------------------------------------------------- #
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(STATIC, "index.html"), encoding="utf-8") as fh:
        return fh.read()


@app.get("/api/jobs/{jid}/audio/{name}")
def job_audio(jid: str, name: str):
    if not name.endswith(".mp3") or "/" in name or ".." in name:
        raise HTTPException(400, "bad name")
    path = os.path.join(JOBS_ROOT, jid, "audio", name)
    if not os.path.exists(path):
        raise HTTPException(404, "not found")
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/api/jobs/{jid}/video")
def job_video(jid: str):
    path = os.path.join(JOBS_ROOT, jid, "video.mp4")
    if not os.path.exists(path):
        raise HTTPException(404, "not found")
    return FileResponse(path, media_type="video/mp4",
                        filename="code_explainer.mp4")


# --------------------------------------------------------------------------- #
#  Analyze (synchronous, fast)
# --------------------------------------------------------------------------- #
@app.post("/api/analyze")
def analyze_ep(req: AnalyzeReq):
    if not req.code.strip():
        raise HTTPException(400, "No code provided.")
    target = max(15, min(600, req.target_sec))
    result = analyzer.analyze(req.code, target_sec=target, title=req.title,
                              script_text=req.script_text, script_mode=req.script_mode,
                              framing=req.framing)
    if not result.get("ok"):
        return JSONResponse(result, status_code=200)  # carries .error for UI
    result["meta"]["style"] = "cartoon"
    return result


@app.post("/api/voices")
def voices_ep(req: VoicesReq):
    cfg = appconfig.load()
    key = req.api_key or cfg.get("elevenlabs_key")
    if not key:
        return {"ok": False, "error": "No ElevenLabs key set yet."}
    try:
        return {"ok": True, "voices": narrator.list_voices(key),
                "current": cfg.get("voice_id")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---- configuration (keys saved once, never returned to the browser) -------- #
@app.get("/api/config")
def config_get():
    return appconfig.status()


@app.post("/api/config")
def config_save(req: ConfigSaveReq):
    appconfig.save(req.model_dump(exclude_none=True))
    return appconfig.status()


# ---- AI director: brief + code -> full scene script ------------------------ #
@app.post("/api/author")
def author_ep(req: AuthorReq):
    cfg = appconfig.load()
    key = cfg.get("anthropic_key")
    if not key:
        return JSONResponse({"ok": False, "error": "Add your Claude API key once in Setup to author videos."},
                            status_code=200)
    if not req.code.strip():
        return JSONResponse({"ok": False, "error": "Paste some Python code first."}, status_code=200)
    target = max(30, min(600, req.target_sec or cfg.get("target_sec", 240)))
    try:
        result = director.author_script(req.code, req.brief, key,
                                        model=cfg.get("model", "claude-sonnet-4-6"),
                                        target_sec=target, title=req.title)
        result["meta"]["style"] = cfg.get("style", "cartoon")
        return result
    except director.DirectorError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=200)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"Couldn't author the script: {e}"}, status_code=200)


# --------------------------------------------------------------------------- #
#  Narrate (background job)
# --------------------------------------------------------------------------- #
def _narrate_worker(jid: str, script: dict, api_key: str, voice_id: str):
    try:
        job_dir = os.path.join(JOBS_ROOT, jid)
        audio_dir = os.path.join(job_dir, "audio")
        os.makedirs(audio_dir, exist_ok=True)

        def prog(done, total):
            _set_job(jid, status="narrating", stage="narrating",
                     frac=done / max(1, total))

        narrator.narrate_script(script, api_key, audio_dir,
                                voice_id=voice_id, progress=prog)
        # rewrite urls to absolute API paths for the preview player
        for a in script.get("audio", []):
            if a:
                a["url"] = f"/api/jobs/{jid}/audio/{a['file']}"
        _set_job(jid, status="narrated", stage="done", frac=1.0, script=script)
    except Exception as e:
        _set_job(jid, status="error", error=str(e))


@app.post("/api/narrate")
def narrate_ep(req: NarrateReq):
    if not narrator.have_ffmpeg():
        raise HTTPException(400, "ffmpeg/ffprobe not found — needed to measure audio length.")
    cfg = appconfig.load()
    key = req.api_key or cfg.get("elevenlabs_key")
    voice = req.voice_id or cfg.get("voice_id") or narrator.DEFAULT_VOICE
    if not key:
        raise HTTPException(400, "No ElevenLabs key set. Add it once in Setup, or turn narration off.")
    jid = uuid.uuid4().hex[:12]
    os.makedirs(os.path.join(JOBS_ROOT, jid), exist_ok=True)
    _set_job(jid, status="narrating", stage="starting", frac=0.0, kind="narrate")
    t = threading.Thread(target=_narrate_worker,
                         args=(jid, req.script, key, voice), daemon=True)
    t.start()
    return {"job_id": jid}


# --------------------------------------------------------------------------- #
#  Render (background job)
# --------------------------------------------------------------------------- #
def _render_worker(jid: str, script: dict, theme: str, fps: int,
                   with_audio: bool, engine: str):
    job_dir = os.path.join(JOBS_ROOT, jid)
    os.makedirs(job_dir, exist_ok=True)

    def prog(stage, frac):
        _set_job(jid, status="rendering", stage=stage, frac=frac)

    # The web engine is the single source of truth: the live preview the user
    # sees IS the exported MP4 (frames captured from the same engine). Manim is
    # only used if the user explicitly forces it.
    if engine in (None, "auto"):
        engine = "html"

    def _html():
        renderer.render_video(job_dir, PLAYER_URL, script, theme,
                              fps=fps, with_audio=with_audio, progress=prog)

    try:
        if engine == "manim":
            try:
                manim_render.render_video(job_dir, script, theme,
                                          with_audio=with_audio, progress=prog)
            except Exception as me:
                # never leave the user empty-handed — fall back to the quick engine
                _set_job(jid, status="rendering", stage="manim failed — using quick engine",
                         frac=0.0, note=str(me)[:200])
                _html()
        else:
            _html()
        _set_job(jid, status="done", stage="done", frac=1.0,
                 video_url=f"/api/jobs/{jid}/video")
    except Exception as e:
        _set_job(jid, status="error", error=str(e))


@app.post("/api/render")
def render_ep(req: RenderReq):
    cfg = appconfig.load()
    theme = req.theme or cfg.get("style", "cartoon")
    engine = req.engine or cfg.get("engine", "auto")
    jid = req.job_id or uuid.uuid4().hex[:12]
    os.makedirs(os.path.join(JOBS_ROOT, jid), exist_ok=True)
    _set_job(jid, status="rendering", stage="starting", frac=0.0, kind="render")
    fps = max(12, min(60, req.fps))
    t = threading.Thread(target=_render_worker,
                         args=(jid, req.script, theme, fps, req.with_audio, engine),
                         daemon=True)
    t.start()
    return {"job_id": jid}


@app.get("/api/job/{jid}")
def job_status(jid: str):
    j = _get_job(jid)
    if not j:
        raise HTTPException(404, "unknown job")
    return j


@app.get("/api/health")
def health():
    pw_ok, pw_msg = renderer.playwright_ready()
    mn_ok, mn_msg = manim_render.manim_available()
    return {
        "ok": True,
        "ffmpeg": narrator.have_ffmpeg(),
        "playwright": pw_ok,
        "playwright_msg": pw_msg,
        "manim": mn_ok,
        "manim_msg": mn_msg,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT)
