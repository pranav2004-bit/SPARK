#!/bin/sh
# validate-env.sh — checks all required environment variables before docker-compose up
# Usage: ./infra/scripts/validate-env.sh
# Exit code: 0 = all vars set (or only warnings), 1 = one or more required vars missing

ERRORS=0
WARNINGS=0

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Validate a single service's .env file
# $1 = service name, $2 = path to .env file, $3+ = required var names
validate_service_env() {
    svc="$1"
    env_file="$2"
    shift 2
    required_vars="$*"

    if [ ! -f "$env_file" ]; then
        echo "ERROR [$svc]: .env file not found at $env_file"
        ERRORS=$((ERRORS + 1))
        return
    fi

    # Parse the .env file (skip comments and blank lines)
    for var in $required_vars; do
        value=$(grep "^${var}=" "$env_file" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '[:space:]')
        if [ -z "$value" ]; then
            echo "ERROR [$svc]: Required variable '$var' is missing or empty in $env_file"
            ERRORS=$((ERRORS + 1))
        fi
    done

    # Check SECRET_KEY minimum length
    sk=$(grep "^SECRET_KEY=" "$env_file" 2>/dev/null | head -1 | cut -d= -f2-)
    if [ -n "$sk" ] && [ ${#sk} -lt 50 ]; then
        echo "WARNING [$svc]: SECRET_KEY is shorter than recommended minimum of 50 characters (got ${#sk})."
        WARNINGS=$((WARNINGS + 1))
    fi

    # Check for placeholder values
    jwt=$(grep "^JWT_SIGNING_KEY=" "$env_file" 2>/dev/null | head -1 | cut -d= -f2-)
    case "$jwt" in
        *dev-jwt-signing*|*replace-before-production*)
            echo "WARNING [$svc]: JWT_SIGNING_KEY looks like a development placeholder. Replace before going live."
            WARNINGS=$((WARNINGS + 1))
            ;;
    esac
}

echo "Validating environment files for all 7 SPARK services..."
echo ""

validate_service_env "auth-service" \
    "$REPO_ROOT/services/auth-service/.env" \
    "SECRET_KEY" "DB_NAME" "DB_USER" "DB_PASSWORD" "DB_HOST" "REDIS_URL" "JWT_SIGNING_KEY"

validate_service_env "user-service" \
    "$REPO_ROOT/services/user-service/.env" \
    "SECRET_KEY" "DB_NAME" "DB_USER" "DB_PASSWORD" "DB_HOST" "REDIS_URL" "JWT_SIGNING_KEY"

# AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY deliberately NOT required below
# (2026-09-15) — production runs on an EC2 instance with an IAM role
# attached (spark-backend-ec2-role) and intentionally leaves both unset;
# boto3 falls back to the instance role automatically (see each service's
# core/storage.py::_get_client()). Requiring them here would have hard-
# blocked exactly that deployment. AWS_STORAGE_BUCKET_NAME/AWS_S3_CDN_DOMAIN
# are still required — those aren't credentials, storage genuinely can't
# work without them regardless of auth method.
validate_service_env "resource-service" \
    "$REPO_ROOT/services/resource-service/.env" \
    "SECRET_KEY" "DB_NAME" "DB_USER" "DB_PASSWORD" "DB_HOST" "REDIS_URL" "JWT_SIGNING_KEY" \
    "AWS_STORAGE_BUCKET_NAME" "AWS_S3_CDN_DOMAIN"

validate_service_env "practice-service" \
    "$REPO_ROOT/services/practice-service/.env" \
    "SECRET_KEY" "DB_NAME" "DB_USER" "DB_PASSWORD" "DB_HOST" "REDIS_URL" "JWT_SIGNING_KEY" \
    "AWS_STORAGE_BUCKET_NAME" "AWS_S3_CDN_DOMAIN"

validate_service_env "notification-service" \
    "$REPO_ROOT/services/notification-service/.env" \
    "SECRET_KEY" "DB_NAME" "DB_USER" "DB_PASSWORD" "DB_HOST" "REDIS_URL" "JWT_SIGNING_KEY" "SERVICE_KEY"

validate_service_env "analytics-service" \
    "$REPO_ROOT/services/analytics-service/.env" \
    "SECRET_KEY" "DB_NAME" "DB_USER" "DB_PASSWORD" "DB_HOST" "REDIS_URL" "JWT_SIGNING_KEY" "SERVICE_KEY"

validate_service_env "assessment-service" \
    "$REPO_ROOT/services/assessment-service/.env" \
    "SECRET_KEY" "DB_NAME" "DB_USER" "DB_PASSWORD" "DB_HOST" "REDIS_URL" "JWT_SIGNING_KEY" \
    "AWS_STORAGE_BUCKET_NAME" "AWS_S3_CDN_DOMAIN"

echo ""
echo "─────────────────────────────────────────────────"
if [ "$ERRORS" -gt 0 ]; then
    echo "VALIDATION FAILED: $ERRORS error(s), $WARNINGS warning(s)."
    echo "Fix the errors above before running docker-compose up."
    exit 1
elif [ "$WARNINGS" -gt 0 ]; then
    echo "VALIDATION PASSED WITH WARNINGS: $WARNINGS warning(s)."
    echo "Review warnings before deploying to production."
    exit 0
else
    echo "VALIDATION PASSED: All required environment variables are set."
    exit 0
fi
