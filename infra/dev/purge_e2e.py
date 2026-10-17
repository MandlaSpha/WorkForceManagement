"""Delete the test queues a browser-test run leaves in the DEVELOPMENT database.

Run by the e2e global teardown. It finds the Postgres container that .NET Aspire started, reads its
password from the AppHost user secrets (never printed) and runs the same `purge_e2e_data` command
the dashboard button runs, which refuses to run outside development and only touches queues whose
name starts with "E2E Queue". If there is no Aspire database (CI, or the stack is down) it says so
and exits 0, so it never fails a test run.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(
    args: list[str], cwd: Path | None = None, env: dict[str, str] | None = None
) -> str:
    done = subprocess.run(
        args, cwd=cwd, env=env, capture_output=True, text=True, timeout=180, check=False
    )
    if done.returncode != 0:
        raise RuntimeError(
            done.stderr.strip().splitlines()[-1] if done.stderr else "failed"
        )
    return done.stdout


def main() -> int:
    try:
        listing = run(["docker", "ps", "--format", "{{.Names}} {{.Ports}}"])
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        print("purge_e2e: no Docker, nothing purged")
        return 0
    port = next(
        (
            m.group(1)
            for line in listing.splitlines()
            if line.startswith("postgres-")
            and (m := re.search(r"127\.0\.0\.1:(\d+)->5432", line))
        ),
        None,
    )
    if port is None:
        print("purge_e2e: no Aspire database running, nothing purged")
        return 0
    try:
        secrets = run(
            ["dotnet", "user-secrets", "list", "--project", "infra/aspire/WfmAppHost"],
            cwd=ROOT,
        )
        password = next(
            line.split("=", 1)[1].strip()
            for line in secrets.splitlines()
            if line.startswith("Parameters:postgres-password")
        )
        env = {
            **os.environ,
            "DATABASE_URL": f"postgres://postgres:{password}@localhost:{port}/wfm",
            "DJANGO_DEBUG": "1",
            "DJANGO_SECRET_KEY": "dev-only",
            "DJANGO_SETTINGS_MODULE": "config.settings.dev",
        }
        print(
            run(
                ["uv", "run", "python", "manage.py", "purge_e2e_data"],
                ROOT / "api",
                env,
            ).strip()
        )
    except (RuntimeError, OSError, StopIteration, subprocess.TimeoutExpired) as problem:
        print(
            f"purge_e2e: could not purge ({type(problem).__name__}); use the dashboard button"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
