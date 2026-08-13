#!/usr/bin/env python
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
    # Auto-load .env for development convenience (dotenv is a no-op if file absent)
    try:
        from dotenv import load_dotenv
        from pathlib import Path
        base = Path(__file__).resolve().parent
        env_file = base / ".env"
        if env_file.exists():
            load_dotenv(env_file, override=False)
        else:
            load_dotenv(base / ".env.example", override=False)
    except ImportError:
        pass
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django not found. Activate your virtual environment or install requirements."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
