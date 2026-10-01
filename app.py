"""Launch the desktop window with python app.py."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parent


def local_python():
    """Explorer's Python association need not be the project's interpreter."""
    environment = ROOT / ".venv"
    candidate = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if candidate.is_file() and Path(sys.prefix).resolve() != environment.resolve():
        return candidate
    return None


def report_startup_error():
    details = traceback.format_exc()
    log = ROOT / "startup-error.log"
    try:
        log.write_text(details, encoding="utf-8")
        location = f"Details: {log}"
    except OSError:
        location = details[-2000:]
    message = ("TurboTodos could not start.\n\n" + str(sys.exc_info()[1]) +
               "\n\n" + location +
               "\n\nIf dependencies are missing, run in the project folder:\n"
               "python -m venv .venv\n"
               ".venv\\Scripts\\python.exe -m pip install -r requirements.txt")
    if sys.stderr:
        print(details, file=sys.stderr)
    if os.name == "nt":
        import ctypes
        box = ctypes.windll.user32.MessageBoxW
        box.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
        box.restype = ctypes.c_int
        box(None, message, "TurboTodos startup error", 0x10)


def main():
    interpreter = local_python()
    if interpreter:
        result = subprocess.run(
            [str(interpreter), str(ROOT / "app.py"), *sys.argv[1:]],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
            env={**os.environ, "TURBOTODOS_CHILD": "1", "PYTHONIOENCODING": "utf-8"},
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or f"Project Python exited with code {result.returncode}")
        if result.stdout and sys.stdout:
            print(result.stdout, end="")
        return
    from desktop import DesktopAPI, build_html
    from closing import CloseGuard
    from storage import DEFAULT_DB
    parser = argparse.ArgumentParser(description="TurboTodos desktop")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args()
    try:
        import webview
    except ImportError as exc:
        raise RuntimeError("Desktop dependencies are missing from this Python environment.") from exc
    api = DesktopAPI(args.db)
    window = webview.create_window("TurboTodos", html=build_html(), js_api=api,
                                  width=1400, height=900, min_size=(900, 650), maximized=True,
                                  text_select=True, background_color="#f7f8f5")
    api._window = window

    close_guard = CloseGuard(window)
    window.events.closing += close_guard.on_closing
    webview.start(gui="edgechromium" if sys.platform == "win32" else None, http_server=False)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        if os.environ.get("TURBOTODOS_CHILD") == "1":
            traceback.print_exc()
        else:
            report_startup_error()
        raise SystemExit(1)
