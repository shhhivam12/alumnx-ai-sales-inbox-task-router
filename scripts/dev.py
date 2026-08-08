from __future__ import annotations

import shutil,signal,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    npm=shutil.which("npm.cmd" if sys.platform=="win32" else "npm");children=[subprocess.Popen([sys.executable,"-m","uvicorn","backend.app.main:app","--reload","--port","8000"],cwd=ROOT),subprocess.Popen([npm,"run","dev"],cwd=ROOT/"frontend")]
    def stop(*_):
        for child in children: child.terminate()
    signal.signal(signal.SIGINT,stop);signal.signal(signal.SIGTERM,stop)
    try:
        exit_code=next(child.wait() for child in children);raise SystemExit(exit_code)
    finally:stop()
if __name__=="__main__":main()
