"""
manim_explainer.py
==================
A Manim Community Edition scene that turns a PyExplain *scene script* (the JSON
produced by analyzer.py) into a smooth, animated, narrated code-explainer video.

It is launched by manim_render.py via the `manim` CLI, e.g.:

    PYEXPLAIN_SCRIPT=/path/script.json PYEXPLAIN_THEME=cartoon \
        manim -qh --format=mp4 --media_dir <dir> manim_explainer.py CodeExplainer

The scene reads the script + theme from environment variables so the same file
renders any video. Durations come straight from the script (already locked to the
ElevenLabs narration length), so the silent video lines up perfectly when the
audio is muxed on afterwards.

Written defensively: Manim's `Code` API has shifted between versions, so code is
built with several fallbacks and, worst case, plain monospace Text — it will
always render *something*.
"""

import json
import os
import textwrap

from manim import (
    Scene, Text, VGroup, RoundedRectangle, Rectangle, SurroundingRectangle,
    FadeIn, FadeOut, GrowFromCenter, Write, Transform, Indicate, Flash,
    UP, DOWN, LEFT, RIGHT, ORIGIN, config,
)

try:
    from manim import Code
except Exception:                       # pragma: no cover
    Code = None

SCRIPT_PATH = os.environ.get("PYEXPLAIN_SCRIPT", "")
THEME = os.environ.get("PYEXPLAIN_THEME", "cartoon")

with open(SCRIPT_PATH, encoding="utf-8") as _fh:
    DATA = json.load(_fh)

# --------------------------------------------------------------------------- #
#  Palettes (hex strings — Manim accepts these directly)
# --------------------------------------------------------------------------- #
PALETTES = {
    "cartoon":   dict(bg="#fdf3ff", ink="#2a2350", muted="#6b6796", accent="#ff5da2",
                      accent2="#5b54e6", panel="#ffffff", panel_line="#2a2350",
                      code_bg="#fffdf7", console_bg="#2a2350", console_ink="#9dffd0"),
    "classroom": dict(bg="#eef1f6", ink="#1f2937", muted="#7b8aa0", accent="#2f7d4f",
                      accent2="#7b3fb8", panel="#ffffff", panel_line="#cfd6e2",
                      code_bg="#ffffff", console_bg="#0f2419", console_ink="#b9f5cf"),
    "neon":      dict(bg="#0b0a1f", ink="#eaf6ff", muted="#8aa0c8", accent="#22e3c3",
                      accent2="#ff6ad5", panel="#12152e", panel_line="#33407a",
                      code_bg="#0c0e1e", console_bg="#06070f", console_ink="#7dffb0"),
    "minimal":   dict(bg="#fafafa", ink="#111111", muted="#999999", accent="#111111",
                      accent2="#555555", panel="#ffffff", panel_line="#e0e0e0",
                      code_bg="#ffffff", console_bg="#111111", console_ink="#eaeaea"),
}
PAL = PALETTES.get(THEME, PALETTES["cartoon"])

FRAME_W = config.frame_width      # ~14.22
FRAME_H = config.frame_height     # 8.0


def wrap(text, width=58):
    return "\n".join(textwrap.wrap(text, width=width)) or " "


class CodeExplainer(Scene):
    def construct(self):
        self.camera.background_color = PAL["bg"]
        self.meta = DATA["meta"]
        self.scenes = DATA["scenes"]
        self.src_lines = self.meta["code"].rstrip("\n").split("\n")

        self.code_group = None
        self.line_mobs = None
        self.hl = None
        self.caption = None
        self.var_cards = {}          # name -> {box, val_mob, value}
        self.var_group = None
        self.console = None
        self.console_text = ""
        self.code_shown = False

        for i, sc in enumerate(self.scenes):
            dur = max(0.8, sc.get("durationMs", 1500) / 1000.0)
            kind = sc.get("kind", "step")
            if kind == "intro":
                self.play_card(sc, dur, intro=True)
            elif kind == "outro":
                self.play_card(sc, dur, intro=False)
            else:
                self.play_step(sc, dur)

    # ------------------------------------------------------------------ #
    #  Title / outro cards
    # ------------------------------------------------------------------ #
    def play_card(self, sc, dur, intro=True):
        kicker = Text("PYTHON EXPLAINER" if intro else "WRAP UP",
                      font_size=26, color=PAL["accent"], weight="BOLD")
        emoji = Text("🐍" if intro else "🎉", font_size=92)
        title = Text(sc.get("title", ""), font_size=64, color=PAL["ink"], weight="BOLD")
        title.scale_to_fit_width(min(FRAME_W - 2, max(2, title.width)))
        sub = Text(sc.get("subtitle", ""), font_size=34, color=PAL["muted"])
        group = VGroup(kicker, emoji, title, sub).arrange(DOWN, buff=0.4)

        self.play(FadeIn(kicker), GrowFromCenter(emoji), run_time=min(0.8, dur * 0.4))
        self.play(Write(title), run_time=min(1.0, dur * 0.4))
        self.play(FadeIn(sub, shift=UP * 0.3), run_time=0.5)
        self.caption_to(sc.get("narration", ""), dur=0.01, fade=False)
        self.wait(max(0.2, dur - 1.8))
        self.play(FadeOut(group), run_time=0.5)

    # ------------------------------------------------------------------ #
    #  Code building
    # ------------------------------------------------------------------ #
    def build_code(self):
        src = "\n".join(self.src_lines)
        mob = None
        if Code is not None:
            for kwargs in (
                dict(code_string=src, language="python", add_line_numbers=True),
                dict(code=src, language="python"),
                dict(code_string=src, language="python"),
            ):
                try:
                    mob = Code(**kwargs)
                    break
                except Exception:
                    mob = None
        if mob is None:
            # bulletproof fallback: monospace Text, indentation preserved
            rows = VGroup()
            for ln in self.src_lines:
                shown = ln.replace(" ", " ") or " "
                rows.add(Text(shown, font="Monospace", font_size=24, color=PAL["ink"]))
            rows.arrange(DOWN, aligned_edge=LEFT, buff=0.14)
            mob = rows
        # line submobjects, for highlighting (defensive across Manim versions)
        line_mobs, lines_ok = None, False
        for attr in ("code", "code_lines"):
            v = getattr(mob, attr, None)
            if v is not None and len(v) >= len(self.src_lines):
                line_mobs, lines_ok = v, True
                break
        self._lines_ok = lines_ok
        return mob, line_mobs

    # ------------------------------------------------------------------ #
    #  Step scene
    # ------------------------------------------------------------------ #
    def play_step(self, sc, dur):
        intro_anims = []
        if not self.code_shown:
            self.code_group, self.line_mobs = self.build_code()
            # fit into the left ~58% of the frame
            box_w, box_h = FRAME_W * 0.56, FRAME_H * 0.72
            scale = min(box_w / max(self.code_group.width, 0.1),
                        box_h / max(self.code_group.height, 0.1), 1.0)
            self.code_group.scale(scale)
            self.code_group.to_edge(LEFT, buff=0.6)
            self.code_shown = True
            intro_anims.append(FadeIn(self.code_group, shift=RIGHT * 0.4))

        # highlight target geometry from the requested lines
        target = self.hl_target(sc.get("highlight", []))
        used = min(0.7, dur * 0.45)
        if target is not None:
            if self.hl is None:
                self.hl = RoundedRectangle(width=target.width, height=target.height,
                                           corner_radius=0.12, color=PAL["accent"],
                                           fill_color=PAL["accent"], fill_opacity=0.14,
                                           stroke_width=3)
                self.hl.move_to(target.get_center())
                intro_anims.append(FadeIn(self.hl))
            else:
                intro_anims.append(
                    self.hl.animate.move_to(target.get_center())
                        .stretch_to_fit_height(target.height)
                        .stretch_to_fit_width(target.width))

        # caption
        cap_anim = self.caption_anim(sc.get("narration", ""))
        if cap_anim:
            intro_anims.append(cap_anim)

        if intro_anims:
            self.play(*intro_anims, run_time=used)
        else:
            used = 0.0

        # variables + output happen as a small follow-up beat
        beat = []
        for v in sc.get("vars", []):
            beat += self.var_anim(v)
        if sc.get("output") is not None:
            beat += self.console_anim(sc["output"])
        spent = used
        if beat:
            t = min(0.7, max(0.2, dur * 0.3))
            self.play(*beat, run_time=t)
            spent += t

        self.wait(max(0.15, dur - spent))

    # ------------------------------------------------------------------ #
    def hl_target(self, highlight):
        if not highlight or self.code_group is None:
            return None
        idxs = [n - 1 for n in highlight if 1 <= n <= len(self.src_lines)]
        if not idxs:
            return None
        # Preferred: wrap the actual line submobjects (perfectly tight).
        if self._lines_ok and self.line_mobs is not None:
            try:
                grp = VGroup(*[self.line_mobs[i] for i in idxs if i < len(self.line_mobs)])
                if len(grp) > 0:
                    return SurroundingRectangle(grp, buff=0.08)
            except Exception:
                pass
        # Fallback: compute the rectangle from the code block's geometry.
        n = max(1, len(self.src_lines))
        top = self.code_group.get_top()[1]
        line_h = self.code_group.height / n
        first, last = min(idxs), max(idxs)
        y_hi = top - first * line_h
        y_lo = top - (last + 1) * line_h
        rect = Rectangle(width=self.code_group.width + 0.2,
                         height=max(0.2, (y_hi - y_lo)))
        rect.move_to([self.code_group.get_center()[0], (y_hi + y_lo) / 2, 0])
        return rect

    def var_anim(self, v):
        name, value, vtype = v.get("name", "?"), str(v.get("value", "")), v.get("type", "")
        disp = value if len(value) <= 26 else value[:25] + "…"
        if name in self.var_cards:                     # update existing
            card = self.var_cards[name]
            new_val = Text(disp, font="Monospace", font_size=26, color=PAL["ink"])
            new_val.move_to(card["val_mob"])
            anims = [Transform(card["val_mob"], new_val), Indicate(card["box"], color=PAL["accent"])]
            return anims
        # create new card
        nm = Text(name, font="Monospace", font_size=24, color=PAL["accent2"], weight="BOLD")
        val = Text(disp, font="Monospace", font_size=26, color=PAL["ink"])
        inner = VGroup(nm, val).arrange(DOWN, buff=0.12)
        box = RoundedRectangle(width=inner.width + 0.5, height=inner.height + 0.4,
                               corner_radius=0.12, color=PAL["panel_line"],
                               fill_color=PAL["panel"], fill_opacity=1.0, stroke_width=2)
        card = VGroup(box, inner)
        self.var_cards[name] = {"box": box, "val_mob": val, "group": card}
        self._relayout_vars()
        return [GrowFromCenter(card)]

    def _relayout_vars(self):
        cards = [c["group"] for c in self.var_cards.values()]
        if self.var_group is None:
            self.var_group = VGroup()
        grp = VGroup(*cards).arrange(DOWN, aligned_edge=LEFT, buff=0.3)
        grp.to_edge(RIGHT, buff=0.7).shift(UP * 1.2)
        self.var_group = grp

    def console_anim(self, text):
        self.console_text = (self.console_text + "\n" + text).strip() if self.console_text else text
        shown = self.console_text if len(self.console_text) < 120 else self.console_text[-120:]
        new_console = Text("› " + shown.replace("\n", "\n› "), font="Monospace",
                           font_size=24, color=PAL["console_ink"])
        new_console.scale_to_fit_width(min(FRAME_W * 0.36, max(0.5, new_console.width)))
        new_console.to_edge(RIGHT, buff=0.7).to_edge(DOWN, buff=1.7)
        if self.console is None:
            self.console = new_console
            return [Write(self.console)]
        anims = [Transform(self.console, new_console)]
        return anims

    # ------------------------------------------------------------------ #
    def caption_anim(self, text):
        new_cap = Text(wrap(text), font_size=30, color=PAL["ink"],
                       line_spacing=0.8)
        new_cap.scale_to_fit_width(min(FRAME_W - 1.4, max(0.5, new_cap.width)))
        new_cap.to_edge(DOWN, buff=0.5)
        if self.caption is None:
            self.caption = new_cap
            return FadeIn(self.caption, shift=UP * 0.2)
        return Transform(self.caption, new_cap)

    def caption_to(self, text, dur=0.4, fade=True):
        anim = self.caption_anim(text)
        if anim:
            self.play(anim, run_time=dur)
