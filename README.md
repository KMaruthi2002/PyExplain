# 🐍 PyExplain — Animated Python Code Explainer

Paste Python code, pick a style, and get a fun, animated, narrated video that
explains how the code works — like it's being taught to a curious high-schooler.

It actually *runs* your code (safely, in a sandbox) so the explanations use the
real values your variables take on, and the narration timing locks to the
voiceover for perfect sync.

---

## Quick start

1. Make sure **ffmpeg** is installed (used to build the MP4):
   - macOS: `brew install ffmpeg`
   - Windows: `winget install Gyan.FFmpeg`
   - Linux: `sudo apt install ffmpeg`

2. Launch it:
   ```bash
   python run.py
   ```
   - **macOS:** you can also double-click `start.command`
   - **Windows:** double-click `start.bat`

   The first run installs a few Python packages and a small headless browser
   (used to render frames), then opens the app at <http://127.0.0.1:8000>.

3. **One-time setup** (first launch only): the app shows a small Setup card. Paste
   your two API keys and click **Save**:
   - **Claude API key** (from console.anthropic.com) — writes the video script.
   - **ElevenLabs API key** — the voiceover.

   They're saved locally in `config.json` and never shown again. (Click **⚙ Setup**
   any time to update them.)

4. Then it's one button:
   - Paste your Python.
   - *(Optional)* open **Describe the video** to give a brief — audience, tone,
     length, what to emphasise — or leave it blank for a great beginner-friendly default.
   - Click **✨ Create Video**.

   You'll see a live animated **preview** within seconds while the final **MP4**
   renders in the background; a **Download** button appears when it's done. If Manim
   isn't available (or hits a snag), it automatically falls back to the quick
   renderer so you always get a video.

---

## Writing your own narration script

By default the app explains the code for you. But you can take full control under
**Video settings → Explanation script → "Write my own"**.

- Write your narration as paragraphs. **Each blank-line-separated paragraph is one
  scene.**
- Optionally start a paragraph with a **line tag** to spotlight code while you talk:
  - `[3]` — highlight line 3
  - `[3-5]` — highlight lines 3 through 5
- For tagged lines, the engine still pulls the **real variable values and printed
  output**, so your custom narration gets the same animated boxes and console.

Example:

```
[1] First we build a little machine called add_scores that adds up a list of numbers.

[2] It starts a running total at zero.

[3-4] Then it walks through every score, adding each one to the total.

[9] Finally, it prints the grand total to the screen!
```

Untick **"Add intro & outro title cards"** if you want only your own scenes.

---

## Render engines (cinematic vs quick)

Under **Pick a style → Export engine** you choose how the final MP4 is rendered:

- **🎬 Manim (recommended)** — renders with [Manim Community Edition](https://docs.manim.community)
  for smooth, cinematic motion (gliding highlights, springy variable cards, clean
  auto-fit code). Needs a one-time install:
  - macOS: `brew install py3cairo pango pkg-config` then `pip install manim`
  - Linux: `sudo apt install libcairo2-dev libpango1.0-dev` then `pip install manim`
  - Windows: `pip install manim` (see the Manim docs for system libraries)

  This is **`manim` (Community Edition)** — *not* `manimgl`. The top-right of the
  app shows a green "Manim ready" dot once it's installed.

- **⚡ Quick** — renders the exact frames of the live HTML preview (via the headless
  browser). No extra install beyond the first-run setup.

The live preview in the app is always the fast HTML engine; the engine choice only
affects the downloaded MP4.

---

## The four styles

| Style | Vibe |
|-------|------|
| **Fun Cartoon** | bright, bouncy, emoji, playful — the default |
| **Classroom** | clean whiteboard look, calm and clear |
| **Neon Arcade** | dark mode, glowing accents, bold |
| **Minimal Mono** | quiet, sharp, lots of whitespace |

You pick the style **before rendering**, and the live preview updates instantly
so you can compare them.

---

## How it works

```
Your code ──▶ analyzer.py ──▶ scene script (JSON)
                  │              (AST structure + a sandboxed run trace
                  │               so explanations use real values)
                  ▼
        ElevenLabs narration (optional)  ──▶ locks scene timing to the audio
                  ▼
   engine.js renders each scene deterministically in the browser
                  ▼
   renderer.py seeks frame-by-frame with headless Chromium ──▶ PNG frames
                  ▼
            ffmpeg ──▶ final MP4 (1920×1080, H.264 + AAC)
```

The animation engine is **deterministic** — every frame is a pure function of
time — so the exported MP4 looks pixel-identical to the live preview.

---

## Project layout

```
run.py                 one-command launcher (auto-installs deps + browser)
requirements.txt
app/
  server.py            FastAPI backend + job tracking
  analyzer.py          Python AST + sandboxed trace → scene script
  narrator.py          ElevenLabs text-to-speech + timing lock
  renderer.py          Playwright frame capture + ffmpeg encode/mux
  static/
    index.html         the web UI
    app.js             UI controller
    styles.css         UI styling
    player.html        the 1920×1080 animation stage
    engine.js          deterministic animation engine + 4 themes
jobs/                  generated audio + videos (created at runtime)
```

---

## Notes & tips

- **No API key?** Turn narration off — you still get a fully animated video with
  on-screen captions and the live preview.
- **Privacy:** everything runs locally on your machine. Your code and API key are
  only sent to ElevenLabs (for the voiceover) and never anywhere else.
- **Safety:** your code is executed in a separate, time-limited process with a
  6-second cap, so an infinite loop can't hang the app. If the code can't run,
  the walkthrough falls back to explaining the structure.
- **Longer code** makes longer videos. The length slider sets a target, but
  narration is never sped past a natural talking pace.
- **Render speed:** rendering is frame-by-frame for maximum quality. A ~60s video
  takes a couple of minutes depending on your machine.

Enjoy making code make sense! 🎬
