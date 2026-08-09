from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def ensure_virtualenv() -> None:
    """Re-run this script with the project interpreter created by bootstrap."""
    if not VENV_PYTHON.exists():
        raise SystemExit("Virtual environment not found. Run scripts/bootstrap.py with Python 3.12 first.")
    if Path(sys.executable).resolve() != VENV_PYTHON.resolve():
        completed = subprocess.run([str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]], cwd=ROOT)
        raise SystemExit(completed.returncode)


def main() -> None:
    ensure_virtualenv()
    from dotenv import dotenv_values

    parser = argparse.ArgumentParser()
    parser.add_argument("--production", action="store_true")
    parser.add_argument(
        "--downgrade-base",
        action="store_true",
        help="Development rehearsal only: remove all application migrations.",
    )
    args = parser.parse_args()
    values = {**dotenv_values(ROOT / ".env"), **os.environ}
    url = values.get("SUPABASE_MIGRATION_DB_URL") or values.get("SUPABASE_DB_URL")
    if not url:
        raise SystemExit("SUPABASE_MIGRATION_DB_URL or SUPABASE_DB_URL is required")
    parsed = urlparse(str(url))
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname or not parsed.username:
        raise SystemExit("Migration target must be a PostgreSQL connection string, not a Supabase HTTPS project URL")
    project_ref = parsed.username.rsplit(".", 1)[-1].lower() if "." in parsed.username else ""
    production_ref = str(values.get("PRODUCTION_SUPABASE_PROJECT_REF") or "").lower()
    app_env = values.get("APP_ENV")
    if args.downgrade_base and (args.production or app_env == "production"):
        raise SystemExit("Refusing to downgrade the production database")
    if app_env == "production" and not args.production:
        raise SystemExit("Refusing production migration without --production")
    if args.production:
        if not production_ref or project_ref != production_ref:
            raise SystemExit("Production migration target does not match PRODUCTION_SUPABASE_PROJECT_REF")
    elif production_ref and project_ref == production_ref:
        raise SystemExit("Refusing to migrate the production Supabase project without --production")
    env = os.environ.copy()
    env["SUPABASE_MIGRATION_DB_URL"] = str(url)
    alembic_action = ["downgrade", "base"] if args.downgrade_base else ["upgrade", "head"]
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ROOT / "backend/alembic.ini"), *alembic_action],
        cwd=ROOT, env=env, check=True,
    )


if __name__=="__main__":main()
