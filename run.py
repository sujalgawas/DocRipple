#!/usr/bin/env python3
"""DocRipple Unified Runner.

Starts both:
  1. Backend + Agent (docsync-agent FastAPI server at http://localhost:8000)
  2. Frontend (React + Vite dashboard at http://localhost:5173)

Usage:
    python run.py
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

# ANSI colors for readable multi-service logs
COLOR_RESET = "\033[0m"
COLOR_CYAN = "\033[36m"
COLOR_MAGENTA = "\033[35m"
COLOR_GREEN = "\033[32m"
COLOR_YELLOW = "\033[33m"
COLOR_RED = "\033[31m"
COLOR_BOLD = "\033[1m"

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "docsync-agent"
FRONTEND_DIR = ROOT_DIR / "frontend"


def stream_output(
    pipe, prefix: str, color: str, stop_event: threading.Event
) -> None:
    """Stream process stdout/stderr line-by-line with service prefix."""
    try:
        for line in iter(pipe.readline, ""):
            if not line and stop_event.is_set():
                break
            clean_line = line.rstrip("\r\n")
            if clean_line:
                print(f"{color}{prefix}{COLOR_RESET} {clean_line}", flush=True)
    except Exception:
        pass
    finally:
        pipe.close()


def find_backend_cmd() -> list[str]:
    """Resolve the most reliable command to start the backend."""
    # 1. Prefer 'uv run uvicorn' if uv is installed
    if shutil.which("uv"):
        return ["uv", "run", "uvicorn", "src.main:app", "--reload", "--port", "8000"]

    # 2. Check local virtual environment uvicorn
    if sys.platform == "win32":
        venv_uvicorn = BACKEND_DIR / ".venv" / "Scripts" / "uvicorn.exe"
    else:
        venv_uvicorn = BACKEND_DIR / ".venv" / "bin" / "uvicorn"

    if venv_uvicorn.is_file():
        return [str(venv_uvicorn), "src.main:app", "--reload", "--port", "8000"]

    # 3. Fallback to current Python interpreter
    return [
        sys.executable,
        "-m",
        "uvicorn",
        "src.main:app",
        "--reload",
        "--port",
        "8000",
    ]


def find_frontend_cmd() -> list[str]:
    """Resolve npm command for frontend."""
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    if not shutil.which(npm_cmd):
        print(
            f"{COLOR_RED}[ERROR] 'npm' was not found in PATH. Please install Node.js.{COLOR_RESET}",
            file=sys.stderr,
        )
        sys.exit(1)
    return [npm_cmd, "run", "dev"]


def sync_env_files() -> None:
    """Ensure docsync-agent has an active .env configuration."""
    backend_env = BACKEND_DIR / ".env"
    root_env = ROOT_DIR / ".env"

    if not backend_env.exists() and root_env.exists():
        try:
            shutil.copy2(root_env, backend_env)
            print(
                f"{COLOR_YELLOW}[SETUP] Copied .env from root to docsync-agent/.env{COLOR_RESET}"
            )
        except Exception:
            pass
    elif not backend_env.exists():
        example_env = BACKEND_DIR / ".env.example"
        if example_env.exists():
            try:
                shutil.copy2(example_env, backend_env)
                print(
                    f"{COLOR_YELLOW}[SETUP] Initialized docsync-agent/.env from .env.example{COLOR_RESET}"
                )
            except Exception:
                pass


def kill_proc(proc: subprocess.Popen) -> None:
    """Forcefully terminate a process tree cleanly on Windows and Unix."""
    if proc.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            proc.terminate()
            proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def main() -> None:
    # Ensure UTF-8 output encoding on Windows consoles
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # Enable ANSI terminal coloring on Windows
    if sys.platform == "win32":
        os.system("")

    print(
        f"\n{COLOR_BOLD}{COLOR_GREEN}"
        f"+-----------------------------------------------------------------+\n"
        f"|                     DocRipple Dev Runner                        |\n"
        f"+-----------------------------------------------------------------+\n"
        f"|  * Backend + Agent:  http://localhost:8000                      |\n"
        f"|    - Swagger Docs:   http://localhost:8000/docs                 |\n"
        f"|    - Health Check:   http://localhost:8000/health               |\n"
        f"|  * Frontend:         http://localhost:5173                      |\n"
        f"|                                                                 |\n"
        f"|  Press Ctrl+C at any time to stop all services.                 |\n"
        f"+-----------------------------------------------------------------+"
        f"{COLOR_RESET}\n"
    )

    sync_env_files()

    backend_cmd = find_backend_cmd()
    frontend_cmd = find_frontend_cmd()

    stop_event = threading.Event()
    processes: list[subprocess.Popen] = []

    try:
        # Start Backend (FastAPI + DocSync Agent worker)
        print(f"{COLOR_CYAN}[BACKEND]{COLOR_RESET} Starting FastAPI backend and agent...")
        backend_proc = subprocess.Popen(
            backend_cmd,
            cwd=str(BACKEND_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=os.environ.copy(),
        )
        processes.append(backend_proc)

        # Start Frontend (Vite React app)
        print(f"{COLOR_MAGENTA}[FRONTEND]{COLOR_RESET} Starting React/Vite development server...")
        frontend_proc = subprocess.Popen(
            frontend_cmd,
            cwd=str(FRONTEND_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=os.environ.copy(),
        )
        processes.append(frontend_proc)

        # Threaded log streaming
        t_backend = threading.Thread(
            target=stream_output,
            args=(backend_proc.stdout, "[BACKEND] ", COLOR_CYAN, stop_event),
            daemon=True,
        )
        t_frontend = threading.Thread(
            target=stream_output,
            args=(frontend_proc.stdout, "[FRONTEND]", COLOR_MAGENTA, stop_event),
            daemon=True,
        )

        t_backend.start()
        t_frontend.start()

        # Supervise child processes
        while True:
            if backend_proc.poll() is not None:
                print(
                    f"\n{COLOR_RED}[BACKEND] Process exited with code {backend_proc.returncode}.{COLOR_RESET}"
                )
                break
            if frontend_proc.poll() is not None:
                print(
                    f"\n{COLOR_RED}[FRONTEND] Process exited with code {frontend_proc.returncode}.{COLOR_RESET}"
                )
                break
            time.sleep(0.5)

    except KeyboardInterrupt:
        print(f"\n{COLOR_YELLOW}[SHUTDOWN] Stopping all services...{COLOR_RESET}")
    finally:
        stop_event.set()
        for p in processes:
            kill_proc(p)
        print(f"{COLOR_GREEN}[SHUTDOWN] All services stopped cleanly.{COLOR_RESET}\n")


if __name__ == "__main__":
    main()
