from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"


def run(command: list[str], cwd: Path = ROOT) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def main() -> None:
    if not VENV.exists(): run([sys.executable, "-m", "venv", str(VENV)])
    python = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    run([str(python), "-m", "pip", "install", "-r", "backend/requirements-dev.txt"])
    npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
    if not npm: raise SystemExit("Node.js/npm is required")
    run([npm, "install"], ROOT / "frontend")
    target = ROOT / ".env"
    if not target.exists(): shutil.copyfile(ROOT / ".env.example", target)
    print("Bootstrap complete. Fill hosted service values in .env, then run scripts/migrate.py.")


if __name__ == "__main__": main()
