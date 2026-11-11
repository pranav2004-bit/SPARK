#!/bin/sh
set -e
python manage.py migrate --noinput
exec gunicorn core.asgi:application \
    --bind 0.0.0.0:8000 \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers ${UVICORN_WORKERS:-3} \
    --timeout 120 \
    --graceful-timeout 30 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --access-logfile - \
    --error-logfile -
