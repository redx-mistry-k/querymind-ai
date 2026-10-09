from __future__ import annotations

import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from backend.app.core.config import get_settings


def main() -> int:
    settings = get_settings()
    root = Path(__file__).resolve().parent
    commands = [
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--host",
            settings.app_host,
            "--port",
            str(settings.api_port),
        ],
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "frontend/app.py",
            "--server.address",
            settings.app_host,
            "--server.port",
            str(settings.streamlit_port),
            "--browser.gatherUsageStats",
            "false",
        ],
    ]
    processes: list[subprocess.Popen[str]] = []
    try:
        print("Starting QueryMind AI…")
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        for command in commands:
            processes.append(
                subprocess.Popen(command, cwd=root, text=True, creationflags=creationflags)
            )
        url = f"http://{settings.app_host}:{settings.streamlit_port}"
        print(f"Dashboard: {url}")
        print(f"API docs: http://{settings.app_host}:{settings.api_port}/docs")
        print("Press Ctrl+C to stop both services.")
        time.sleep(2)
        webbrowser.open(url)
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
        return next((process.returncode for process in processes if process.returncode), 0) or 0
    except KeyboardInterrupt:
        print("\nStopping QueryMind AI…")
        return 0
    finally:
        for process in processes:
            if process.poll() is None:
                if sys.platform == "win32":
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
