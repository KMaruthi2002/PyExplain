"""
analyzer.py
===========
Turns a piece of Python code into a *scene script*: an ordered list of timed
"scenes" that the animation engine plays back, narrated like it is being
explained to a curious high-schooler.

Two layers of understanding are combined:

1. STATIC analysis (``ast``) - gives us the structure of the program: which
   lines are functions, loops, conditionals, assignments, prints, returns ...
   This always works, even if the code cannot run.

2. DYNAMIC analysis (a sandboxed trace) - actually runs the code in a separate
   process with ``sys.settrace`` so we can capture the *real* values variables
   take on, line by line. This is what makes the explanations concrete and fun
   ("...so ``total`` becomes 15!"). If the code can't run (needs input, has an
   error, loops forever) we fall back gracefully to static-only narration.

The output is a plain dict (JSON-serialisable) consumed by the front-end engine.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass, field
from typing import Any, Optional


# --------------------------------------------------------------------------- #
#  Scene data model
# --------------------------------------------------------------------------- #
@dataclass
class Scene:
    kind: str                       # "intro" | "step" | "section" | "outro"
    narration: str                  # what the narrator says (drives audio)
    title: str = ""                 # big on-screen heading (intro/section/outro)
    subtitle: str = ""
    highlight: list[int] = field(default_factory=list)   # 1-based code lines to spotlight
    vars: list[dict] = field(default_factory=list)       # variable state changes
    callout: str = ""               # short punchy caption bubble
    badge: str = ""                 # tiny tag e.g. "LOOP", "IF", "RETURN"
    output: Optional[str] = None    # text printed to the console at this step
    weight: float = 1.0             # relative time weight before duration fitting
    durationMs: int = 0             # filled in by _fit_durations

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "narration": self.narration,
            "title": self.title,
            "subtitle": self.subtitle,
            "highlight": self.highlight,
            "vars": self.vars,
            "callout": self.callout,
            "badge": self.badge,
            "output": self.output,
            "durationMs": self.durationMs,
        }


# --------------------------------------------------------------------------- #
#  Friendly helpers for value/type wording
# --------------------------------------------------------------------------- #
def _short_repr(value: Any, limit: int = 60) -> str:
    try:
        r = repr(value)
    except Exception:
        r = str(value)
    if len(r) > limit:
        r = r[: limit - 1] + "…"
    return r


def _friendly_type(value: Any) -> str:
    mapping = {
        "int": "a whole number",
        "float": "a decimal number",
        "str": "some text",
        "bool": "a true/false value",
        "list": "a list",
        "dict": "a dictionary",
        "tuple": "a group of values",
        "set": "a set",
        "NoneType": "nothing (None)",
    }
    return mapping.get(type(value).__name__, f"a {type(value).__name__}")


# --------------------------------------------------------------------------- #
#  Dynamic tracing (runs in a sandboxed subprocess)
# --------------------------------------------------------------------------- #
# This script is written to a temp file and executed in its own process so a
# runaway loop or crash can never take down the web server. We cap wall-clock
# time and the number of trace events recorded.
_TRACER_TEMPLATE = r'''
import sys, json, builtins

USER_CODE = {code!r}
MAX_EVENTS = {max_events}

events = []
printed = []

_real_print = builtins.print
def _captured_print(*args, **kwargs):
    sep = kwargs.get("sep", " ")
    end = kwargs.get("end", "\n")
    try:
        text = sep.join(str(a) for a in args) + end
    except Exception:
        text = ""
    printed.append(text)

def _safe_snapshot(local_vars):
    snap = {{}}
    for k, v in local_vars.items():
        if k.startswith("__"):
            continue
        try:
            json.dumps(v)
            snap[k] = v
        except Exception:
            try:
                snap[k] = {{"__repr__": repr(v)[:60]}}
            except Exception:
                snap[k] = {{"__repr__": "<unrepresentable>"}}
    return snap

def tracer(frame, event, arg):
    if event == "line":
        if len(events) < MAX_EVENTS and frame.f_code.co_filename == "<user>":
            events.append({{
                "line": frame.f_lineno,
                "func": frame.f_code.co_name,
                "locals": _safe_snapshot(frame.f_locals),
                "printed_so_far": len(printed),
            }})
        elif len(events) >= MAX_EVENTS:
            sys.settrace(None)
            return None
    return tracer

g = {{"__name__": "__main__", "__builtins__": builtins}}
builtins.print = _captured_print
compiled = compile(USER_CODE, "<user>", "exec")
sys.settrace(tracer)
error = None
try:
    exec(compiled, g)
except Exception as e:
    error = "{{}}: {{}}".format(type(e).__name__, e)
finally:
    sys.settrace(None)
    builtins.print = _real_print

print(json.dumps({{"events": events, "printed": printed, "error": error}}))
'''


def trace_execution(code: str, timeout: float = 6.0,
                    max_events: int = 4000) -> dict:
    """Run the user's code in a locked-down subprocess and capture a line trace.

    Returns ``{"events": [...], "printed": [...], "error": str|None,
              "ok": bool}``. Never raises.
    """
    script = _TRACER_TEMPLATE.format(code=code, max_events=max_events)
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(script)
        path = fh.name
    try:
        proc = subprocess.run(
            [sys.executable, path],
            capture_output=True, text=True, timeout=timeout,
            # Block obvious filesystem surprises by running in a temp cwd.
            cwd=tempfile.gettempdir(),
        )
        out = proc.stdout.strip().splitlines()
        if not out:
            return {"events": [], "printed": [], "error": proc.stderr[-300:] or "no output", "ok": False}
        data = json.loads(out[-1])
        data["ok"] = data.get("error") is None
        return data
    except subprocess.TimeoutExpired:
        return {"events": [], "printed": [], "error": "Code took too long to run (possible infinite loop).", "ok": False}
    except Exception as e:  # pragma: no cover - defensive
        return {"events": [], "printed": [], "error": f"{type(e).__name__}: {e}", "ok": False}
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


# --------------------------------------------------------------------------- #
#  Static structure walk -> narration steps
# --------------------------------------------------------------------------- #
class _CodeNarrator:
    """Walks the AST and produces ordered explanation steps, then enriches them
    with real values from the execution trace."""

    def __init__(self, code: str, trace: dict, audience: str = "highschool"):
        self.code = code
        self.lines = code.split("\n")
        self.trace = trace
        self.events = trace.get("events", [])
        self.printed = trace.get("printed", [])
        self.audience = audience
        self.scenes: list[Scene] = []
        # line -> list of local snapshots observed (in order)
        self._line_states: dict[int, list[dict]] = {}
        for ev in self.events:
            self._line_states.setdefault(ev["line"], []).append(ev["locals"])

    # ---- value lookup helpers ------------------------------------------- #
    def _value_after(self, lineno: int, name: str):
        """Best-effort: the value a variable holds the *last* time `lineno` ran."""
        states = self._line_states.get(lineno) or []
        # The assignment's effect is visible on the *next* executed line, so we
        # also peek at the immediate successor states.
        for ev in self.events:
            pass
        # Walk events to find the state right after this line executed.
        last = None
        for i, ev in enumerate(self.events):
            if ev["line"] == lineno and i + 1 < len(self.events):
                nxt = self.events[i + 1]["locals"]
                if name in nxt:
                    last = nxt[name]
        if last is None:
            for st in states:
                if name in st:
                    last = st[name]
        return last

    def _times_run(self, lineno: int) -> int:
        return sum(1 for ev in self.events if ev["line"] == lineno)

    def _iterations_of(self, node: ast.AST) -> int:
        """Accurate loop iteration count = how many times the loop body ran."""
        body = getattr(node, "body", None)
        if not body:
            return 0
        return self._times_run(body[0].lineno)

    def _var_dict(self, name: str, value: Any, action: str) -> dict:
        if isinstance(value, dict) and "__repr__" in value:
            disp = value["__repr__"]
            tname = "object"
        else:
            disp = _short_repr(value)
            tname = type(value).__name__
        return {"name": name, "value": disp, "type": tname, "action": action}

    # ---- node dispatch --------------------------------------------------- #
    def build(self) -> list[Scene]:
        tree = ast.parse(self.code)
        self._walk_body(tree.body, depth=0)
        return self.scenes

    def _walk_body(self, body: list[ast.stmt], depth: int):
        for node in body:
            self._explain(node, depth)

    def _src(self, node: ast.AST) -> str:
        try:
            seg = ast.get_source_segment(self.code, node)
            if seg:
                return seg.strip()
        except Exception:
            pass
        ln = getattr(node, "lineno", 1) - 1
        return self.lines[ln].strip() if 0 <= ln < len(self.lines) else ""

    def _lines_of(self, node: ast.AST) -> list[int]:
        start = getattr(node, "lineno", 1)
        end = getattr(node, "end_lineno", start)
        return list(range(start, end + 1))

    def _explain(self, node: ast.AST, depth: int):
        handler = {
            ast.FunctionDef: self._fn,
            ast.AsyncFunctionDef: self._fn,
            ast.ClassDef: self._cls,
            ast.For: self._for,
            ast.While: self._while,
            ast.If: self._if,
            ast.Assign: self._assign,
            ast.AugAssign: self._augassign,
            ast.AnnAssign: self._assign,
            ast.Return: self._return,
            ast.Expr: self._expr,
            ast.Import: self._import,
            ast.ImportFrom: self._import,
            ast.With: self._with,
            ast.Try: self._try,
        }.get(type(node))
        if handler:
            handler(node, depth)
        else:
            # Generic fallback so nothing is silently skipped.
            src = self._src(node)
            if src:
                self.scenes.append(Scene(
                    kind="step",
                    narration=f"Next, the program runs this line: {src}.",
                    highlight=self._lines_of(node),
                    callout=src,
                ))

    # ---- individual constructs ------------------------------------------ #
    def _fn(self, node: ast.FunctionDef, depth: int):
        args = [a.arg for a in node.args.args]
        if args:
            arglist = ", ".join(args)
            narration = (
                f"Here we define a function called '{node.name}'. Think of a function "
                f"like a recipe: it takes some ingredients — in this case {arglist} — "
                f"and follows the steps inside whenever we call it."
            )
        else:
            narration = (
                f"Here we define a function called '{node.name}'. A function is like a "
                f"reusable recipe — a set of steps we can run whenever we need them."
            )
        self.scenes.append(Scene(
            kind="step", narration=narration,
            highlight=[node.lineno], badge="FUNCTION",
            callout=f"def {node.name}(…)",
        ))
        self._walk_body(node.body, depth + 1)

    def _cls(self, node: ast.ClassDef, depth: int):
        self.scenes.append(Scene(
            kind="step",
            narration=(
                f"Now we create a class named '{node.name}'. A class is a blueprint — "
                f"it describes what something is and what it can do, so we can build "
                f"many copies of it later."
            ),
            highlight=[node.lineno], badge="CLASS",
            callout=f"class {node.name}",
        ))
        self._walk_body(node.body, depth + 1)

    def _assign(self, node, depth: int):
        targets = []
        if isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            targets = node.targets
        names = []
        for t in targets:
            if isinstance(t, ast.Name):
                names.append(t.id)
            else:
                names.append(self._src(t))
        src = self._src(node)
        primary = names[0] if names else "a value"
        val = self._value_after(node.lineno, names[0]) if names and isinstance(targets[0], ast.Name) else None
        vars_changed = []
        if val is not None and names and isinstance(targets[0], ast.Name):
            vars_changed = [self._var_dict(names[0], val, "create")]
            narration = (
                f"We make a box labelled '{primary}' and put {_friendly_type(self._coerce(val))} "
                f"inside it: {self._display(val)}."
            )
        else:
            narration = f"We store a value in '{primary}' using this line."
        self.scenes.append(Scene(
            kind="step", narration=narration,
            highlight=self._lines_of(node), badge="ASSIGN",
            callout=src, vars=vars_changed,
        ))

    def _augassign(self, node: ast.AugAssign, depth: int):
        name = node.target.id if isinstance(node.target, ast.Name) else self._src(node.target)
        op = {ast.Add: "adds to", ast.Sub: "subtracts from", ast.Mult: "multiplies",
              ast.Div: "divides", ast.Mod: "takes the remainder of"}.get(type(node.op), "updates")
        val = self._value_after(node.lineno, name)
        vars_changed = [self._var_dict(name, val, "update")] if val is not None else []
        extra = f" Now '{name}' holds {self._display(val)}." if val is not None else ""
        self.scenes.append(Scene(
            kind="step",
            narration=f"This line {op} '{name}'.{extra}",
            highlight=self._lines_of(node), badge="UPDATE",
            callout=self._src(node), vars=vars_changed,
        ))

    def _for(self, node: ast.For, depth: int):
        target = self._src(node.target)
        iterable = self._src(node.iter)
        runs = self._iterations_of(node)
        rinfo = f" It repeats {runs} times here." if runs else ""
        self.scenes.append(Scene(
            kind="step",
            narration=(
                f"Now we hit a loop. A loop repeats the same steps again and again. "
                f"This one walks through {iterable}, and each time around it calls the "
                f"current item '{target}'.{rinfo}"
            ),
            highlight=[node.lineno], badge="LOOP",
            callout=f"for {target} in {iterable}",
        ))
        self._walk_body(node.body, depth + 1)
        if node.orelse:
            self._walk_body(node.orelse, depth + 1)

    def _while(self, node: ast.While, depth: int):
        cond = self._src(node.test)
        runs = self._iterations_of(node)
        rinfo = f" It ends up running {runs} times." if runs else ""
        self.scenes.append(Scene(
            kind="step",
            narration=(
                f"Here's a 'while' loop. It keeps repeating as long as this is true: "
                f"{cond}. The moment that stops being true, the loop ends.{rinfo}"
            ),
            highlight=[node.lineno], badge="WHILE",
            callout=f"while {cond}",
        ))
        self._walk_body(node.body, depth + 1)

    def _if(self, node: ast.If, depth: int):
        cond = self._src(node.test)
        ran = self._times_run(node.lineno) > 0
        self.scenes.append(Scene(
            kind="step",
            narration=(
                f"Now the program makes a decision. It checks: is {cond}? "
                f"If yes, it runs the first block; if not, it skips ahead."
            ),
            highlight=[node.lineno], badge="IF",
            callout=f"if {cond}?",
        ))
        self._walk_body(node.body, depth + 1)
        if node.orelse:
            # Could be elif (single If) or else block.
            if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
                self._explain(node.orelse[0], depth)
            else:
                self.scenes.append(Scene(
                    kind="step",
                    narration="Otherwise — if that check was false — it runs this part instead.",
                    highlight=[node.orelse[0].lineno] if node.orelse else [],
                    badge="ELSE", callout="else …",
                ))
                self._walk_body(node.orelse, depth + 1)

    def _return(self, node: ast.Return, depth: int):
        val = self._src(node.value) if node.value else "nothing"
        self.scenes.append(Scene(
            kind="step",
            narration=(
                f"The function hands back its answer with 'return'. It sends out: {val}. "
                f"That's the result whoever called the function gets to use."
            ),
            highlight=self._lines_of(node), badge="RETURN",
            callout=f"return {val}",
        ))

    def _expr(self, node: ast.Expr, depth: int):
        call = node.value
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "print":
            out = self._printed_at(node.lineno)
            extra = f" It shows: {out!r}" if out else ""
            self.scenes.append(Scene(
                kind="step",
                narration=f"This line prints something to the screen.{extra}",
                highlight=self._lines_of(node), badge="PRINT",
                callout=self._src(node), output=out,
            ))
        else:
            src = self._src(node)
            self.scenes.append(Scene(
                kind="step",
                narration=f"This line runs an action: {src}.",
                highlight=self._lines_of(node), callout=src,
            ))

    def _import(self, node, depth: int):
        src = self._src(node)
        self.scenes.append(Scene(
            kind="step",
            narration=(
                f"First we grab some tools we'll need with this import line. It's like "
                f"borrowing a toolbox someone already built: {src}."
            ),
            highlight=self._lines_of(node), badge="IMPORT", callout=src,
        ))

    def _with(self, node: ast.With, depth: int):
        self.scenes.append(Scene(
            kind="step",
            narration="This 'with' block safely opens something and makes sure it's tidied up afterwards.",
            highlight=[node.lineno], badge="WITH", callout=self._src(node).split("\n")[0],
        ))
        self._walk_body(node.body, depth + 1)

    def _try(self, node: ast.Try, depth: int):
        self.scenes.append(Scene(
            kind="step",
            narration="Here the program tries something that might fail, and gets ready to handle a problem gracefully if it does.",
            highlight=[node.lineno], badge="TRY", callout="try / except",
        ))
        self._walk_body(node.body, depth + 1)
        for handler in node.handlers:
            self._walk_body(handler.body, depth + 1)

    # ---- value helpers --------------------------------------------------- #
    def _coerce(self, val):
        if isinstance(val, dict) and "__repr__" in val:
            return val  # opaque object
        return val

    def _display(self, val) -> str:
        if isinstance(val, dict) and "__repr__" in val:
            return val["__repr__"]
        return _short_repr(val)

    def _printed_at(self, lineno: int) -> Optional[str]:
        # Find how many things were printed up to and including this line.
        idxs = [ev["printed_so_far"] for ev in self.events if ev["line"] == lineno]
        if not idxs or not self.printed:
            return None
        # printed_so_far is the count *before* this line executed; the print
        # itself appends one entry, so index = printed_so_far.
        first = idxs[0]
        if first < len(self.printed):
            return self.printed[first].rstrip("\n")
        return None


# --------------------------------------------------------------------------- #
#  Duration fitting
# --------------------------------------------------------------------------- #
def _estimate_speech_ms(text: str) -> int:
    # ~ 165 words per minute conversational pace + small buffer.
    words = max(1, len(text.split()))
    return int(words / 165 * 60_000) + 600


def _fit_durations(scenes: list[Scene], target_sec: int):
    """Scale per-scene durations so the whole video lands near target_sec,
    while never going faster than natural speech for the narration."""
    target_ms = target_sec * 1000
    base = [max(_estimate_speech_ms(s.narration), 1400) for s in scenes]
    total = sum(base)
    if total == 0:
        return
    scale = target_ms / total
    # Never compress below readable speech; allow stretching to fill time.
    scale = max(scale, 0.85)
    for s, b in zip(scenes, base):
        s.durationMs = int(b * scale)


# --------------------------------------------------------------------------- #
#  Custom-script mode
# --------------------------------------------------------------------------- #
# Maps each code line to "what happens there" so a user-written beat that points
# at a line still gets the right animated variable box / console output.
class _LineFacts(ast.NodeVisitor):
    def __init__(self):
        self.assigns: dict[int, str] = {}      # lineno -> variable name
        self.prints: set[int] = set()          # print() lines

    def visit_Assign(self, n):
        for t in n.targets:
            if isinstance(t, ast.Name):
                self.assigns[n.lineno] = t.id
        self.generic_visit(n)

    def visit_AugAssign(self, n):
        if isinstance(n.target, ast.Name):
            self.assigns[n.lineno] = n.target.id
        self.generic_visit(n)

    def visit_AnnAssign(self, n):
        if isinstance(n.target, ast.Name):
            self.assigns[n.lineno] = n.target.id
        self.generic_visit(n)

    def visit_Expr(self, n):
        if (isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name)
                and n.value.func.id == "print"):
            self.prints.add(n.lineno)
        self.generic_visit(n)


# A beat may start with a line directive:  [3]  [3-5]  @3  @3-5  (line 3)
_DIRECTIVE = re.compile(
    r'^\s*[\[(@]?\s*(?:lines?\s*)?(\d+)\s*(?:[-–to]+\s*(\d+))?\s*[\])]?\s*[:.\-]?\s*',
    re.I)


def _parse_beats(script_text: str):
    """Split the user's script into beats. Returns list of (highlight, text)."""
    blocks = [b.strip() for b in re.split(r'\n\s*\n', script_text.strip()) if b.strip()]
    beats = []
    for blk in blocks:
        high, text = [], blk
        # only treat a leading [n]/@n/(n) token as a directive
        if re.match(r'^\s*[\[(@]\s*\d', blk):
            m = _DIRECTIVE.match(blk)
            if m:
                a = int(m.group(1)); b = int(m.group(2)) if m.group(2) else a
                lo, hi = min(a, b), max(a, b)
                high = list(range(lo, hi + 1))
                text = blk[m.end():].strip()
        beats.append((high, " ".join(text.split())))
    return beats


def _build_custom_scenes(code: str, trace: dict, script_text: str) -> list[Scene]:
    facts = _LineFacts()
    try:
        facts.visit(ast.parse(code))
    except SyntaxError:
        pass
    nar = _CodeNarrator(code, trace)        # reuse value/output lookups
    beats = _parse_beats(script_text)
    scenes: list[Scene] = []
    prev_high: list[int] = []
    for high, text in beats:
        if not text:
            continue
        if not high:
            high = prev_high               # carry the previous focus forward
        else:
            prev_high = high
        vars_changed, output, badge = [], None, ""
        for ln in high:
            if ln in facts.assigns:
                name = facts.assigns[ln]
                val = nar._value_after(ln, name)
                if val is not None:
                    vars_changed.append(nar._var_dict(name, val, "update"))
                    badge = badge or "VALUE"
            if ln in facts.prints:
                out = nar._printed_at(ln)
                if out is not None:
                    output = out
                badge = "OUTPUT"
        scenes.append(Scene(kind="step", narration=text, highlight=high,
                            vars=vars_changed, output=output, badge=badge))
    return scenes


# --------------------------------------------------------------------------- #
#  Public entry point
# --------------------------------------------------------------------------- #
def analyze(code: str, target_sec: int = 60, title: str = "",
            audience: str = "highschool", script_text: str = "",
            script_mode: str = "auto", framing: bool = True) -> dict:
    """Produce the full scene script for a piece of Python code."""
    code = code.replace("\t", "    ").rstrip() + "\n"
    try:
        ast.parse(code)
    except SyntaxError as e:
        return {
            "ok": False,
            "error": f"That code has a syntax error on line {e.lineno}: {e.msg}. "
                     f"Fix it and try again!",
        }

    trace = trace_execution(code)

    use_custom = script_mode == "custom" and script_text.strip()
    if use_custom:
        step_scenes = _build_custom_scenes(code, trace, script_text)
        if not step_scenes:
            return {"ok": False,
                    "error": "Your script was empty after parsing. Write at least one "
                             "paragraph of narration, optionally tagged like [3] or [3-5]."}
    else:
        narrator = _CodeNarrator(code, trace, audience)
        step_scenes = narrator.build()

    if not step_scenes:
        step_scenes = [Scene(
            kind="step",
            narration="This program is short and sweet — it runs straight through these lines.",
            highlight=list(range(1, min(len(code.splitlines()), 8) + 1)),
        )]

    # Intro + optional section + outro framing.
    nice_title = title.strip() or "How This Python Code Works"
    intro = Scene(
        kind="intro",
        title=nice_title,
        subtitle="Let's break it down, step by step",
        narration=(
            "Hey there! Let's figure out how this Python program works together. "
            "Don't worry if code looks scary — by the end of this you'll totally get it. "
            "Ready? Let's dive in!"
        ),
        weight=1.2,
    )

    # Outro summary, including the program's real output if we have it.
    printed = trace.get("printed") or []
    out_text = "".join(printed).strip()
    if trace.get("error"):
        outro_extra = ("Heads up: when we ran it, Python hit a snag — "
                       f"{trace['error']} — but the walkthrough above still shows the plan.")
    elif out_text:
        shown = out_text if len(out_text) < 120 else out_text[:117] + "…"
        outro_extra = f"And when it all runs, the program prints: {shown}"
    else:
        outro_extra = "And that's the whole thing running from top to bottom."

    outro = Scene(
        kind="outro",
        title="You Got It! 🎉",
        subtitle="That's how the code works",
        narration=(
            "And that's it — you just followed a real Python program from start to finish! "
            + outro_extra +
            " Nice work. Try changing a number or a line and imagine how the video would change!"
        ),
        weight=1.2,
    )

    if framing:
        scenes = [intro] + step_scenes + [outro]
    else:
        scenes = step_scenes
    _fit_durations(scenes, target_sec)

    total_ms = sum(s.durationMs for s in scenes)
    return {
        "ok": True,
        "meta": {
            "title": nice_title,
            "code": code,
            "lineCount": len(code.splitlines()),
            "language": "python",
            "targetSec": target_sec,
            "totalMs": total_ms,
            "ranSuccessfully": trace.get("ok", False),
            "runError": trace.get("error"),
            "programOutput": out_text,
        },
        "scenes": [s.to_dict() for s in scenes],
    }


if __name__ == "__main__":
    sample = textwrap.dedent('''
        def add_scores(scores):
            total = 0
            for s in scores:
                total += s
            return total

        nums = [10, 20, 5]
        result = add_scores(nums)
        print("The total is", result)
    ''').strip()
    out = analyze(sample, target_sec=45, title="Adding Up Scores")
    print(json.dumps(out, indent=2)[:3000])
