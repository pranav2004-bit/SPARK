#!/bin/sh
set -e
python manage.py migrate --noinput
exec uvicorn core.asgi:application \
    --host 0.0.0.0 \
    --port 8000 \
    --workers ${UVICORN_WORKERS:-3}
