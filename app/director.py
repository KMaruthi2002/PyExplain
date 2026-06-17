"""
director.py
===========
Turns a *creative brief* + Python code into a detailed, scene-by-scene video
script by asking Claude to act as the video's director.

Output matches the same scene schema the renderer already consumes, so the rest
of the pipeline (narration + animation) is unchanged.
"""

from __future__ import annotations

import json
import re
import textwrap
from typing import Optional

import requests

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

# A strong default brief so even "just paste code and click" yields a rich video.
DEFAULT_BRIEF = textwrap.dedent("""
    Create a fun, visually engaging educational video that teaches absolute-beginner
    high-school students (first time ever seeing Python) how to read and understand
    this exact Python program, explained line by line with precision.
    Tone: warm, upbeat, encouraging and interactive, like a friendly young teacher,
    using simple real-world analogies. Structure it as: a relatable hook, a look at
    the whole program, then a careful line-by-line walkthrough highlighting only the
    line being discussed, a short "pause and predict the output" moment, a quick
    recap of every concept, and an encouraging closing challenge. Make sure every
    Python concept that appears in the code is explained clearly in plain language.
""").strip()

SYSTEM = textwrap.dedent("""
    You are an award-winning motion-graphics director and Python teacher. You turn a
    brief + a Python program into a precise, scene-by-scene script for an ANIMATED
    explainer video aimed at absolute beginners. Each scene also chooses a LAYOUT and
    an animated VISUAL metaphor, so the composition changes with the explanation
    (not a static template).

    Reply with ONLY a single JSON object (no prose, no markdown fences):

    {
      "title": "<short punchy video title>",
      "scenes": [
        {
          "kind": "intro" | "step" | "outro",
          "layout": "title" | "code" | "split" | "metaphor" | "statement" | "terminal",
          "narration": "<what the narrator SAYS — 2 to 4 warm, spoken sentences>",
          "title": "<big on-screen title — intro/outro only, else empty>",
          "subtitle": "<subtitle — intro/outro only, else empty>",
          "highlight": [<1-based code line numbers this scene is about; [] if none>],
          "caption": "<very short on-screen phrase, e.g. 'int() turns text into a number'>",
          "badge": "<1-2 word tag, e.g. 'INPUT', 'IF / ELSE', 'VARIABLE'>",
          "visual": { "type": "...", ...fields... } | null,
          "output": "<console text for this scene, or null>"
        }
      ]
    }

    LAYOUTS — pick the one that best frames the idea:
    - "title": a full-screen kinetic title card. Use for the FIRST (hook) and LAST scenes.
    - "code": the code is the hero, full-screen, with the relevant line(s) highlighted.
      Use for the "here's the whole program" scene and for pure line-reading moments.
    - "split": code on the left + an animated metaphor on the right. Use when a line maps
      to a concrete metaphor (a variable, a comparison, a function call …).
    - "metaphor": a full-screen animated metaphor (no code). Use to teach a concept big.
    - "statement": a full-screen big-idea sentence (no code). Use for key takeaways like
      indentation or "input() always returns text".
    - "terminal": focus on the program's printed output in a terminal window.

    VISUALS — choose a "visual.type" and fill its fields (use for split/metaphor/terminal):
    - {"type":"variable_box","name":"age","value":"16"}            // a value drops into a labeled box
    - {"type":"compare","left":"age","op":">=","right":"13","result":true}   // shows a TRUE/FALSE stamp
    - {"type":"if_else","condition":"age >= 13","taken":"yes","yes_label":"watch the movie","no_label":"come back later"}  // a road splits
    - {"type":"concat","parts":["\\"Hi \\"","name","\\"!\\""],"result":"Hi Maya!"}  // text chips merge
    - {"type":"loop","items":["82","75","91"],"label":"for each score"}     // a ring cycles items
    - {"type":"accumulator","items":["82","75","91","68","88"],"result":"404","label":"total"}  // items fly into a running total that counts up — USE for a loop that builds a sum/total
    - {"type":"input_prompt","question":"How old are you?","answer":"16"}   // a prompt bubble; the user's typed answer appears — USE for input() lines
    - {"type":"function_machine","name":"int","input":"\\"16\\"","output":"16"}  // input -> machine -> output
    - {"type":"list","name":"scores","items":["82","75","91","68","88"]}     // items pop into a list
    - {"type":"terminal","text":"Hi Maya, you can watch this PG-13 movie!"}  // typed output
    - {"type":"none"}  // when no metaphor fits (use layout "code" or "statement" instead)

    Rules:
    - 12 to 16 scenes unless the brief says otherwise. First = intro, last = outro.
    - "highlight" line numbers MUST be accurate to the numbered code.
    - One idea per step. Conversational, spoken-first narration. Cover every concept in the brief.
    - Choose visuals that genuinely match the line (a comparison -> compare; an if -> if_else;
      a + on strings -> concat; a loop -> loop; int()/str() -> function_machine; a print -> terminal).
    - Vary the layouts across the video so it feels dynamic.
    - PUNCTUATION: never use em dashes or en dashes (— or –) anywhere. Use commas,
      periods, or the word "and" instead.
    - In narration and captions, write operators as plain words ("greater than or
      equal to", not ">=" or "≥"). Inside visual fields use ASCII (">=", "<="), never
      the ≥/≤ glyphs. Never add "()" you don't need in narration.
    - Return STRICT, valid JSON. No trailing commas. No commentary.
""").strip()

_LAYOUTS = {"title", "code", "split", "metaphor", "statement", "terminal"}


class DirectorError(Exception):
    pass


def _number_code(code: str) -> str:
    lines = code.rstrip("\n").split("\n")
    return "\n".join(f"{i+1:>3} | {ln}" for i, ln in enumerate(lines))


def _extract_json(text: str) -> dict:
    text = text.strip()
    # strip ```json fences if present
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.M).strip()
    # find the outermost {...}
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise DirectorError("The director did not return JSON.")
    blob = text[start:end + 1]
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        # last-ditch: remove trailing commas
        blob2 = re.sub(r",(\s*[}\]])", r"\1", blob)
        return json.loads(blob2)


def _estimate_ms(text: str) -> int:
    words = max(1, len((text or "").split()))
    return int(words / 165 * 60_000) + 600


def _fit(scenes: list[dict], target_sec: int):
    base = [max(_estimate_ms(s.get("narration", "")), 1500) for s in scenes]
    total = sum(base) or 1
    scale = max((target_sec * 1000) / total, 0.85)
    for s, b in zip(scenes, base):
        s["durationMs"] = int(b * scale)


def author_script(code: str, brief: str, api_key: str, model: str = "claude-sonnet-4-6",
                  target_sec: int = 240, title: str = "") -> dict:
    if not api_key:
        raise DirectorError("No Claude API key set. Add it once in Setup.")
    code = code.replace("\t", "    ").rstrip() + "\n"
    brief = (brief or "").strip() or DEFAULT_BRIEF

    user = (
        f"BRIEF:\n{brief}\n\n"
        f"THE EXACT PROGRAM TO EXPLAIN (numbered for your reference; the video shows "
        f"the code WITHOUT the numbers):\n{_number_code(code)}\n\n"
        f"Target length: about {target_sec} seconds.\n"
        f"Return the JSON script now."
    )

    try:
        r = requests.post(
            ANTHROPIC_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 8000,
                "system": SYSTEM,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=180,
        )
    except requests.RequestException as e:
        raise DirectorError(f"Could not reach Claude: {e}")

    if r.status_code != 200:
        raise DirectorError(f"Claude API error {r.status_code}: {r.text[:300]}")

    try:
        parts = r.json().get("content", [])
        text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
    except Exception:
        raise DirectorError("Unexpected response from Claude.")

    data = _extract_json(text)
    scenes_in = data.get("scenes") or []
    if not scenes_in:
        raise DirectorError("The director returned no scenes — try again.")

    # normalise scenes to our schema
    scenes = []
    n_lines = len(code.rstrip("\n").split("\n"))
    for s in scenes_in:
        kind = s.get("kind", "step")
        if kind not in ("intro", "step", "outro"):
            kind = "step"
        highlight = [int(x) for x in (s.get("highlight") or [])
                     if isinstance(x, (int, float)) and 1 <= int(x) <= n_lines]
        out = s.get("output")
        layout = s.get("layout")
        if layout not in _LAYOUTS:
            layout = None      # engine will infer
        visual = s.get("visual")
        if not isinstance(visual, dict) or not visual.get("type"):
            visual = None
        scenes.append({
            "kind": kind,
            "layout": layout,
            "narration": (s.get("narration") or "").strip(),
            "title": (s.get("title") or "").strip(),
            "subtitle": (s.get("subtitle") or "").strip(),
            "highlight": highlight,
            "vars": [],
            "callout": "",
            "badge": (s.get("badge") or "").strip()[:18],
            "caption": (s.get("caption") or "").strip()[:80],
            "visual": visual,
            "output": out if isinstance(out, str) and out.strip() else None,
        })

    _fit(scenes, target_sec)
    nice_title = (data.get("title") or title or "How This Python Code Works").strip()
    return {
        "ok": True,
        "meta": {
            "title": nice_title,
            "code": code,
            "lineCount": n_lines,
            "language": "python",
            "targetSec": target_sec,
            "totalMs": sum(s["durationMs"] for s in scenes),
            "authoredBy": "claude",
        },
        "scenes": scenes,
    }
