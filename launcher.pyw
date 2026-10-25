"""Windows launcher without a console, target of the shortcut made by shortcut.bat.

pythonw.exe opens no window: the game shows in a Chrome (else Edge) application window (--app), which
carries the game's icon in the taskbar. The server stops when that window closes; if it was already
running (start.bat), the launcher only opens the window and leaves it running.
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORT = 8005
URL = f"http://127.0.0.1:{PORT}/"
LOG = ROOT / "launcher.log"


def game_running() -> bool:
    try:
        with urllib.request.urlopen(f"{URL}openapi.json", timeout=2) as response:
            return json.load(response).get("info", {}).get("title") == "Civilization"
    except (OSError, ValueError):
        return False


def app_browser() -> str | None:
    """Chrome, else Edge, present on every recent Windows: the only ones to open a page as an application window."""
    bases = [base for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                               os.environ.get("LOCALAPPDATA")) if base]
    candidates = [Path(base, "Google", "Chrome", "Application", "chrome.exe") for base in bases]
    candidates += [Path(base, "Microsoft", "Edge", "Application", "msedge.exe") for base in bases]
    for path in candidates:
        if path.is_file(): return str(path)
    return shutil.which("chrome") or shutil.which("msedge")


def open_window() -> subprocess.Popen | None:
    """A profile of the game's own makes a separate browser instance, alive as long as the window is open."""
    browser = app_browser()
    if browser is None:
        import webbrowser
        webbrowser.open(URL)
        return None
    # One profile per browser: Chrome and Edge do not share one.
    profile = Path(os.environ.get("LOCALAPPDATA", ROOT), "Civ", Path(browser).stem)
    return subprocess.Popen([browser, f"--app={URL}", f"--user-data-dir={profile}", "--no-first-run",
                             "--no-default-browser-check", "--start-maximized"])


def alert(message: str) -> None:
    import ctypes
    ctypes.windll.user32.MessageBoxW(None, message, "Civ", 0x10)


def main() -> None:
    if sys.stderr is None:  # pythonw has no console: the server's log goes to launcher.log
        sys.stdout = sys.stderr = open(LOG, "w", encoding="utf-8", buffering=1)
    if game_running():
        open_window()
        return
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / "src"))
    import uvicorn
    from server.api.app import create_app
    server = uvicorn.Server(uvicorn.Config(create_app(resume=True), host="127.0.0.1", port=PORT,
                                           log_level="warning"))

    def follow_window():
        while not server.started:
            if server.should_exit: return
            time.sleep(0.2)
        window = open_window()
        if window is not None:
            window.wait()
            server.should_exit = True

    threading.Thread(target=follow_window, daemon=True).start()
    server.run()
    if not server.started:
        raise RuntimeError(f"The server could not start on port {PORT}.")


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        print(traceback.format_exc(), file=sys.stderr)
        alert(f"Civ n'a pas pu démarrer.\n\nDétails : {LOG}")
        raise SystemExit(1)
