#!/usr/bin/env python3
"""Start TradeLab with one command: `python start.py`.

The first run sets everything up, which takes a few minutes; later runs start in seconds:
- creates a Python virtual environment in backend/venv and installs the backend's dependencies,
  again whenever backend/requirements.txt changes;
- installs the frontend's dependencies and builds it, again whenever the frontend changes
  (this needs Node.js; it isn't needed once frontend/dist is built);
- starts TradeLab on http://localhost:8000 and opens it in your browser.

Options: --port 8001, --no-browser. Stop with Ctrl+C. Uses only the Python standard library.
"""

import argparse
import hashlib
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV = BACKEND / "venv"
REQUIREMENTS = BACKEND / "requirements.txt"
REQUIREMENTS_STAMP = VENV / ".tradelab-requirements"
DIST_INDEX = FRONTEND / "dist" / "index.html"
# What the build is made from: rebuilt when any of these is newer than the last build
FRONTEND_SOURCES = ["src", "index.html", "package.json", "package-lock.json", "vite.config.js",
                    "tailwind.config.js", "postcss.config.js", "tsconfig.json"]
MIN_PYTHON = (3, 10)


def step(message: str) -> None:
    print(f"==> {message}", flush=True)


def fail(message: str) -> None:
    print(f"\nError: {message}", file=sys.stderr)
    sys.exit(1)


def run(command: list, cwd: Path) -> None:
    try:
        subprocess.run(command, cwd=cwd, check=True)
    except subprocess.CalledProcessError as e:
        fail(f"`{' '.join(map(str, command))}` failed (exit code {e.returncode}). See the output above.")


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def ensure_backend() -> Path:
    python = venv_python()
    if not python.exists():
        step("Creating a Python virtual environment in backend/venv")
        run([sys.executable, "-m", "venv", str(VENV)], ROOT)
    wanted = hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()
    installed = REQUIREMENTS_STAMP.read_text().strip() if REQUIREMENTS_STAMP.exists() else ""
    if installed != wanted:
        step("Installing the backend's dependencies")
        run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", str(REQUIREMENTS)], BACKEND)
        REQUIREMENTS_STAMP.write_text(wanted)
    return python


def newest_change(paths: list) -> float:
    newest = 0.0
    for name in paths:
        path = FRONTEND / name
        if path.is_file():
            newest = max(newest, path.stat().st_mtime)
        elif path.is_dir():
            for file in path.rglob("*"):
                if file.is_file():
                    newest = max(newest, file.stat().st_mtime)
    return newest


def ensure_frontend() -> None:
    built = DIST_INDEX.stat().st_mtime if DIST_INDEX.exists() else 0.0
    if built and built >= newest_change(FRONTEND_SOURCES):
        return
    npm = shutil.which("npm")
    if not npm:
        if built:
            print("Warning: the frontend changed but Node.js isn't installed, so the existing build is used.")
            return
        fail("Building the app needs Node.js 18 or newer (https://nodejs.org). Install it and run this again.")
    lock = FRONTEND / "package-lock.json"
    installed = FRONTEND / "node_modules" / ".package-lock.json"
    if not installed.exists() or (lock.exists() and lock.stat().st_mtime > installed.stat().st_mtime):
        step("Installing the frontend's dependencies")
        run([npm, "ci", "--no-audit", "--no-fund"], FRONTEND)
    step("Building the app")
    run([npm, "run", "build"], FRONTEND)


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        # Like the server, ignore a just-closed port's TIME_WAIT. (On Windows this option would let the
        # bind succeed even over a listening server, so it's left off there.)
        if os.name != "nt":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return True
    return False


def wait_until_up(url: str, server: subprocess.Popen, timeout: float = 60) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=2) as response:
                if response.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(0.3)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Set up (on first run) and start TradeLab.")
    parser.add_argument("--port", type=int, default=int(os.getenv("TRADELAB_PORT", "8000")))
    parser.add_argument("--no-browser", action="store_true", help="don't open the app in a browser")
    args = parser.parse_args()

    if sys.version_info < MIN_PYTHON:
        fail(f"TradeLab needs Python {'.'.join(map(str, MIN_PYTHON))} or newer; this is {sys.version.split()[0]}.")

    # Checked first: otherwise another server on the port would answer the health check
    if port_in_use(args.port):
        fail(f"Port {args.port} is already in use (is TradeLab already running?). "
             f"Use another with `python start.py --port {args.port + 1}`.")

    python = ensure_backend()
    ensure_frontend()

    url = f"http://localhost:{args.port}"
    step(f"Starting TradeLab on {url}")
    server = subprocess.Popen([str(python), "main.py"], cwd=BACKEND, env={**os.environ, "TRADELAB_PORT": str(args.port)})
    try:
        if not wait_until_up(url, server):
            server.terminate()
            fail(f"TradeLab didn't start. If port {args.port} is in use, try `python start.py --port {args.port + 1}`.")
        print(f"\nTradeLab is running at {url}  (Ctrl+C to stop)\n", flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        server.wait()
    except KeyboardInterrupt:
        print("\nStopping TradeLab...", flush=True)
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    main()
