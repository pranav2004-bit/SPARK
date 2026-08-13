#!/usr/bin/env bash
# SPARK database backup script.
# Backs up all 7 service databases to BACKUP_DIR (default: /backups).
# Writes a JSON manifest with name, size, checksum, duration, timestamp.
# Retention: 30 daily + 12 monthly (first Sunday of month).
# Exit 0 on full success, non-zero if any database fails after 3 retries.

set -uo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
PG_HOST="${PG_HOST:-postgres}"
PG_PORT="${PG_PORT:-5432}"
MAX_RETRIES=3
TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
DATE=$(date -u +"%Y-%m-%d")
IS_FIRST_SUNDAY=false

mkdir -p "${BACKUP_DIR}/daily" "${BACKUP_DIR}/monthly"

if [ "$(date -u +%A)" = "Sunday" ] && [ "$(date -u +%d)" -le 7 ]; then
  IS_FIRST_SUNDAY=true
fi

declare -a DB_NAMES=( auth_db user_db resource_db practice_db notification_db analytics_db assessment_db )
declare -a DB_USERS=( auth_db_user user_db_user resource_db_user practice_db_user notification_db_user analytics_db_user assessment_db_user )
declare -a DB_PASS=(
  "${AUTH_DB_PASSWORD:-auth_dev_password_2024}"
  "${USER_DB_PASSWORD:-user_dev_password_2024}"
  "${RESOURCE_DB_PASSWORD:-resource_dev_password_2024}"
  "${PRACTICE_DB_PASSWORD:-practice_dev_password_2024}"
  "${NOTIFICATION_DB_PASSWORD:-notification_dev_password_2024}"
  "${ANALYTICS_DB_PASSWORD:-analytics_dev_password_2024}"
  "${ASSESSMENT_DB_PASSWORD:-assessment_dev_password_2024}"
)

MANIFEST_ENTRIES=""
OVERALL_SUCCESS=true
MANIFEST_FILE="${BACKUP_DIR}/manifest_${TIMESTAMP}.json"

# ── per-DB backup ─────────────────────────────────────────────────────────────
for i in "${!DB_NAMES[@]}"; do
  DB="${DB_NAMES[$i]}"
  DB_USER="${DB_USERS[$i]}"
  BACKUP_FILENAME="${DB}_${TIMESTAMP}.dump"
  BACKUP_PATH="${BACKUP_DIR}/daily/${BACKUP_FILENAME}"
  BACKUP_OK=false
  START_TS=$(date +%s)

  echo "[backup] Starting ${DB} ..."

  export PGPASSWORD="${DB_PASS[$i]}"

  for attempt in $(seq 1 "${MAX_RETRIES}"); do
    if pg_dump \
        -h "${PG_HOST}" \
        -p "${PG_PORT}" \
        -U "${DB_USER}" \
        -d "${DB}" \
        --format=custom \
        --compress=9 \
        -f "${BACKUP_PATH}"; then
      echo "[backup] ${DB} — attempt ${attempt} succeeded"
      BACKUP_OK=true
      break
    else
      echo "[backup] ${DB} — attempt ${attempt} failed" >&2
      if [ "${attempt}" -lt "${MAX_RETRIES}" ]; then
        sleep 5
      fi
    fi
  done

  END_TS=$(date +%s)
  DURATION_MS=$(( (END_TS - START_TS) * 1000 ))

  if [ "${BACKUP_OK}" = "true" ] && [ -f "${BACKUP_PATH}" ]; then
    FILE_SIZE=$(wc -c < "${BACKUP_PATH}" | tr -d ' ')
    CHECKSUM=$(sha256sum "${BACKUP_PATH}" 2>/dev/null | awk '{print $1}' || echo "unknown")

    if [ "${IS_FIRST_SUNDAY}" = "true" ]; then
      MONTH_PATH="${BACKUP_DIR}/monthly/${DB}_$(date -u +%Y%m).dump"
      cp "${BACKUP_PATH}" "${MONTH_PATH}"
      echo "[backup] ${DB} — monthly copy: ${MONTH_PATH}"
    fi

    MANIFEST_ENTRIES="${MANIFEST_ENTRIES}{\"name\":\"${BACKUP_FILENAME}\",\"db\":\"${DB}\",\"size\":${FILE_SIZE},\"checksum\":\"${CHECKSUM}\",\"duration_ms\":${DURATION_MS}},"
    echo "[backup] ${DB} done — ${FILE_SIZE} bytes in ${DURATION_MS}ms"
  else
    echo "[backup] ERROR: ${DB} failed after ${MAX_RETRIES} retries" >&2
    OVERALL_SUCCESS=false
    MANIFEST_ENTRIES="${MANIFEST_ENTRIES}{\"name\":\"${BACKUP_FILENAME}\",\"db\":\"${DB}\",\"size\":0,\"checksum\":\"\",\"duration_ms\":${DURATION_MS},\"error\":\"backup_failed\"},"
  fi
done

# ── retention cleanup ─────────────────────────────────────────────────────────
echo "[backup] Running retention cleanup ..."
find "${BACKUP_DIR}/daily"   -name "*.dump" -mtime +30  -delete 2>/dev/null || true
find "${BACKUP_DIR}/monthly" -name "*.dump" -mtime +365 -delete 2>/dev/null || true
echo "[backup] Retention cleanup done"

# ── manifest ──────────────────────────────────────────────────────────────────
MANIFEST_ENTRIES="${MANIFEST_ENTRIES%,}"
cat > "${MANIFEST_FILE}" <<EOF
{
  "timestamp": "${TIMESTAMP}",
  "date": "${DATE}",
  "success": ${OVERALL_SUCCESS},
  "databases": [${MANIFEST_ENTRIES}]
}
EOF
echo "[backup] Manifest written to ${MANIFEST_FILE}"

if [ "${OVERALL_SUCCESS}" = "false" ]; then
  echo "[backup] FAILED" >&2
  exit 1
fi

echo "[backup] SUCCESS"
exit 0
