import os
import subprocess
import sys


def main() -> int:
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", ".")
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8010",
            "--reload",
        ],
        env=env,
    )


if __name__ == "__main__":
    raise SystemExit(main())
