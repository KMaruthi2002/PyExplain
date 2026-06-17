#!/usr/bin/env python3
"""
PyExplain launcher
==================
One command to start everything:

    python3 run.py

To stay out of the way of your system Python (and avoid the "externally managed
environment" / PEP 668 error on modern macOS), this creates a private virtual
environment in `.venv/` inside the project, installs what it needs there, then
runs the app from it. Subsequent runs start instantly.
"""

import os
import shutil
import subprocess
import sys
import time
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
VENV = os.path.join(ROOT, ".venv")
REQ = os.path.join(ROOT, "requirements.txt")
PORT = int(os.environ.get("EXPLAINER_PORT", "8000"))


# --------------------------------------------------------------------------- #
#  Virtual-environment bootstrap
# --------------------------------------------------------------------------- #
def venv_python() -> str:
    sub = "Scripts" if os.name == "nt" else "bin"
    exe = "python.exe" if os.name == "nt" else "python"
    return os.path.join(VENV, sub, exe)


def venv_bin() -> str:
    return os.path.join(VENV, "Scripts" if os.name == "nt" else "bin")


def running_in_venv() -> bool:
    try:
        return os.path.samefile(sys.prefix, VENV)
    except Exception:
        return os.path.abspath(sys.prefix) == os.path.abspath(VENV)


def pick_base_python() -> str:
    """Prefer a stable Python (3.10–3.13) for the venv; avoid EOL 3.9 and
    bleeding-edge builds that may lack prebuilt wheels."""
    for name in ("python3.12", "python3.11", "python3.13", "python3.10"):
        p = shutil.which(name)
        if p:
            return p
    # Apple's /usr/bin/python3 (3.9) has prebuilt wheels and works for the app;
    # prefer it over a bleeding-edge build (e.g. 3.14) that often lacks wheels.
    for cand in ("python3.9", "/usr/bin/python3"):
        p = shutil.which(cand) if not os.path.isabs(cand) else (cand if os.path.exists(cand) else None)
        if p:
            return p
    return sys.executable


def bootstrap_and_reexec():
    if not os.path.exists(venv_python()):
        base = pick_base_python()
        print(f"• Creating a private environment with "
              f"{os.path.basename(base)} (one-time) …")
        try:
            subprocess.check_call([base, "-m", "venv", VENV])
        except subprocess.CalledProcessError:
            print("  Could not create the virtual environment. Make sure you have a "
                  "Python 3.10–3.13 installed (e.g.  brew install python@3.12).")
            sys.exit(1)

    vp = venv_python()
    print("• Installing Python packages (first run only) …")
    subprocess.check_call([vp, "-m", "pip", "install", "--upgrade", "pip", "-q"])
    try:
        subprocess.check_call([vp, "-m", "pip", "install", "-q", "-r", REQ])
    except subprocess.CalledProcessError:
        print("\n⚠  Package install failed. Try a stable Python:  "
              "brew install python@3.12  then delete the .venv folder and re-run.\n")
        sys.exit(1)
    print("  done.")

    # hand off to the venv's python
    os.environ["PYEXPLAIN_VENV"] = "1"
    os.execv(vp, [vp, os.path.abspath(__file__), *sys.argv[1:]])


# --------------------------------------------------------------------------- #
#  Runtime dependency helpers (run inside the venv)
# --------------------------------------------------------------------------- #
def ensure_browser():
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return
    try:
        with sync_playwright() as pw:
            path = pw.chromium.executable_path
            if path and os.path.exists(path):
                return
    except Exception:
        pass
    print("• Installing the headless browser for the Quick renderer (one-time) …")
    try:
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
        print("  done.")
    except Exception as e:
        print(f"  (could not auto-install Chromium: {e})")


def check_ffmpeg():
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        print("\n⚠  ffmpeg / ffprobe were not found on your PATH.")
        print("   Required to build the MP4 and measure narration.")
        print("   macOS:  brew install ffmpeg\n")


def free_port(start: int) -> int:
    """Return the first open port at/after `start` so a stale server never blocks us."""
    import socket
    for p in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return start


def check_manim():
    if shutil.which("manim") is None:
        print("\nℹ  Manim (Community Edition) not found — the 🎬 cinematic export needs it.")
        print("   Easiest install (isolated):  brew install pipx pango py3cairo pkg-config")
        print("                                 pipx ensurepath && pipx install manim")
        print("   (This is 'manim', NOT 'manimgl'. Without it, use the ⚡ Quick engine.)\n")


# --------------------------------------------------------------------------- #
def main():
    print("\n🐍  PyExplain — animated Python code explainer\n" + "-" * 46)

    if not running_in_venv():
        bootstrap_and_reexec()   # never returns

    # --- we are now inside .venv ---
    # make sure venv + common tool locations are searchable for `manim`, `ffmpeg`
    extra = [venv_bin(), os.path.expanduser("~/.local/bin"),
             "/opt/homebrew/bin", "/usr/local/bin"]
    os.environ["PATH"] = os.pathsep.join(extra + [os.environ.get("PATH", "")])

    ensure_browser()
    check_ffmpeg()
    check_manim()

    port = free_port(PORT)
    if port != PORT:
        print(f"ℹ  Port {PORT} was busy — using {port} instead.")
    os.environ["EXPLAINER_PORT"] = str(port)
    sys.path.insert(0, os.path.join(ROOT, "app"))
    import uvicorn
    url = f"http://127.0.0.1:{port}"
    print(f"\n✓  Starting server at {url}")
    print("   (Press Ctrl+C to stop.)\n")

    import threading

    def _open():
        time.sleep(1.4)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=_open, daemon=True).start()
    from server import app
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
