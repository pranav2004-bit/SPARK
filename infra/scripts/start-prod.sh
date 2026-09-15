#!/bin/sh
# start-prod.sh — brings up the full SPARK production stack in dependency order.
# Usage: ./infra/scripts/start-prod.sh
#
# Referenced by docker-compose.prod.yml's own header comment since that file
# was first written, but never actually created until Task 15.2 (found and
# flagged during Task 11.2's prod-nginx-routing follow-up, deliberately
# deferred — see LIVETRACKER2_V1.md for why).
#
# Does NOT reinvent ordering logic: docker-compose.prod.yml's own
# `depends_on: { condition: service_healthy }` graph already encodes
# infra (redis/clamav) -> pgbouncer -> all 7 services/workers/outbox-worker ->
# nginx. Database itself is real AWS RDS, outside this graph entirely — it's
# already up before this script ever runs, not a container it waits on.
# A single `docker compose up -d` respects that graph on its own; this
# script's job is validating the environment first and giving an operator
# clear pass/fail feedback after, not re-deriving the ordering.
#
# Exit code: 0 = stack is up and every service reports healthy.
#            1 = env validation failed, or the stack did not reach healthy
#                within the timeout — nothing here should ever be
#                "probably fine," exam-day cannot start on a guess.

set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INFRA_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$INFRA_DIR/docker-compose.prod.yml"
HEALTH_TIMEOUT_SECONDS=300
POLL_INTERVAL_SECONDS=5

echo "═══════════════════════════════════════════════════"
echo " SPARK — Production stack startup"
echo "═══════════════════════════════════════════════════"
echo ""

# ── Step 1: validate every service's own .env file ─────────────────────────
echo "[1/4] Validating per-service environment files..."
if ! "$SCRIPT_DIR/validate-env.sh"; then
    echo ""
    echo "FAILED: validate-env.sh found missing/invalid required variables."
    echo "Fix the errors above before starting the production stack."
    exit 1
fi
echo ""

# ── Step 2: bring up the stack. `up -d` (no service names) builds and starts
# every service in the file, respecting the depends_on/service_healthy
# graph already encoded in docker-compose.prod.yml — redis/clamav first,
# then pgbouncer (which connects out to real AWS RDS, not a local
# container), then every service/worker/beat/outbox-worker, then nginx
# last (nginx's own depends_on lists all 7 services with service_healthy).
# Database itself needs no local .env check here — RDS is already running
# independently of this stack; each service's own .env (already validated
# in Step 1) carries its own DB_HOST=pgbouncer/DB_NAME/DB_USER/DB_PASSWORD.
echo "[2/3] Starting the stack (docker compose up -d --build)..."
docker compose -f "$COMPOSE_FILE" up -d --build
echo ""

# ── Step 3: don't just trust `up -d` returning 0 — that only means every
# container *started*, not that it's actually healthy. Poll until every
# service with a healthcheck reports healthy, or time out with a clear
# failure and the current state for debugging, rather than silently
# declaring success while e.g. assessment-service is still crash-looping.
echo "[3/3] Waiting for all services to report healthy (timeout: ${HEALTH_TIMEOUT_SECONDS}s)..."
elapsed=0
while [ "$elapsed" -lt "$HEALTH_TIMEOUT_SECONDS" ]; do
    unhealthy=$(docker compose -f "$COMPOSE_FILE" ps --format '{{.Name}} {{.Health}}' 2>/dev/null \
        | awk '$2 != "" && $2 != "healthy" { print $1 " (" $2 ")" }')
    # Containers with no healthcheck defined (workers, beat, outbox-worker)
    # report an empty Health column — that's expected, not a failure; only
    # flag containers that HAVE a healthcheck and haven't passed it yet.
    if [ -z "$unhealthy" ]; then
        echo ""
        echo "═══════════════════════════════════════════════════"
        echo " All services healthy. Stack is up."
        echo "═══════════════════════════════════════════════════"
        docker compose -f "$COMPOSE_FILE" ps
        exit 0
    fi
    sleep "$POLL_INTERVAL_SECONDS"
    elapsed=$((elapsed + POLL_INTERVAL_SECONDS))
done

echo ""
echo "═══════════════════════════════════════════════════"
echo " FAILED: not every service reached healthy within ${HEALTH_TIMEOUT_SECONDS}s."
echo "═══════════════════════════════════════════════════"
echo "Still unhealthy:"
echo "$unhealthy"
echo ""
echo "Check logs for the container(s) above before assuming the stack is usable:"
echo "  docker compose -f $COMPOSE_FILE logs <service-name> --tail 100"
exit 1
