import argparse
import getpass
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote


def main() -> None:
    parser = argparse.ArgumentParser(description="Run React, FastAPI and Telegram with PostgreSQL")
    parser.add_argument("--local-postgres", action="store_true", help="Start the project's PostgreSQL Compose service")
    parser.add_argument("--telegram", action="store_true", help="Read a bot token privately for this process")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    os.chdir(root)
    sys.path.insert(0, str(root))
    from travel_agent.config import environment

    env = environment()
    if args.local_postgres:
        existing = subprocess.run(["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=flinters", "--filter", "label=com.docker.compose.service=postgres"], capture_output=True, text=True, check=True).stdout.strip()
        password = env.get("TRAVEL_POSTGRES_PASSWORD")
        if existing and not password:
            configuration = json.loads(subprocess.run(["docker", "inspect", existing.splitlines()[0]], capture_output=True, text=True, check=True).stdout)[0]
            password = next((v.split("=", 1)[1] for v in configuration["Config"]["Env"] if v.startswith("POSTGRES_PASSWORD=")), None)
        if not password:
            volumes = subprocess.run(["docker", "volume", "ls", "-q", "--filter", "name=flinters_travel_postgres"], capture_output=True, text=True, check=True).stdout.strip()
            if volumes:
                parser.error("Existing database volume: provide its TRAVEL_POSTGRES_PASSWORD; no password was changed")
            password = secrets.token_urlsafe(32)
        subprocess.run(["docker", "compose", "-p", "flinters", "up", "-d", "postgres"], env={**os.environ, "TRAVEL_POSTGRES_PASSWORD": password}, check=True)
        env["TRAVEL_DATABASE_URL"] = f"postgresql://travel:{quote(password, safe='')}@127.0.0.1:55432/travel"
        for _ in range(30):
            status = subprocess.run(["docker", "compose", "-p", "flinters", "exec", "-T", "postgres", "pg_isready", "-U", "travel"], env={**os.environ, "TRAVEL_POSTGRES_PASSWORD": password}, capture_output=True)
            if status.returncode == 0:
                break
            time.sleep(1)
        else:
            parser.error("PostgreSQL did not become ready")
    if not env.get("TRAVEL_DATABASE_URL"):
        parser.error("Set TRAVEL_DATABASE_URL or use --local-postgres")
    if args.telegram:
        env["TELEGRAM_BOT_TOKEN"] = getpass.getpass("Telegram token (hidden, session only): ")
        if not env["TELEGRAM_BOT_TOKEN"].strip():
            parser.error("Telegram token is required with --telegram")
    os.environ.update(env)
    import uvicorn
    from travel_agent.web import create_web_app

    uvicorn.run(create_web_app(), host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
