from __future__ import annotations

import shutil
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def main() -> None:
    if not VENV_PYTHON.exists():
        raise SystemExit("Virtual environment not found. Run scripts/bootstrap.py with Python 3.12 first.")
    npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
    if not npm:
        raise SystemExit("Node.js/npm is required. Install it, then run bootstrap again.")
    children = [
        subprocess.Popen(
            [str(VENV_PYTHON), "-m", "uvicorn", "backend.app.main:app", "--reload", "--port", "8000"],
            cwd=ROOT,
        ),
        subprocess.Popen([npm, "run", "dev"], cwd=ROOT / "frontend"),
    ]

    def stop(*_: object) -> None:
        for child in children:
            if child.poll() is None:
                child.terminate()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        exit_code = next(child.wait() for child in children)
        raise SystemExit(exit_code)
    finally:
        stop()


if __name__ == "__main__":
    main()
