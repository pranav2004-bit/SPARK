# SPARK — Production Secrets Management

## Overview

SPARK has 7 microservices, each requiring its own set of secrets. This document covers how to manage secrets securely in production.

**Never store secrets in:**
- Source code
- Docker images
- Git repositories (even private ones)
- Unencrypted logs

---

## Required Secrets Per Service

| Variable | Services | Description |
|----------|----------|-------------|
| `SECRET_KEY` | All 7 | Django secret key — minimum 50 characters, unique per service |
| `DB_PASSWORD` | All 7 | PostgreSQL password for the service's own dedicated, least-privilege user (`auth_db_user`, etc.) — scoped to only that one database, never the RDS instance as a whole. |
| RDS master password | None (not used by any service) | A separate, more powerful credential — full admin access to the RDS instance `spark-primary-db` and all 7 databases. No application service ever uses this; it exists only for one-off admin tasks (creating databases/users, running the parameter-group/backup setup). Store it in a password manager, not in any service's `.env`. Rotate via RDS Console → Modify → set new master password (a dynamic change, no reboot needed). |
| `JWT_SIGNING_KEY` | All 7 | Shared JWT signing/verification key — SAME value in all services |
| `SERVICE_KEY` | notification, analytics | Shared secret for internal service-to-service calls. assessment-service does **not** need this — its `core/user_service_client.py` forwards the requesting admin's own JWT (`Authorization` header) to user-service rather than using a shared service secret, so this row is deliberately not "All 7." |
| `AWS_ACCESS_KEY_ID` | resource, practice, assessment | AWS IAM user `spark-app-s3-user`'s access key for the media bucket (assessment-service added Phase 1 of `LIVETRACKER2_V1.md` — question images). Retire once services run on AWS compute — attach an IAM role to the instance instead and drop these two vars entirely. |
| `AWS_SECRET_ACCESS_KEY` | resource, practice, assessment | Matching AWS secret key |
| `SENTRY_DSN` | All 7 | Sentry project DSN for error tracking |

---

## Generating Secure Values

```bash
# SECRET_KEY (per service, unique)
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# JWT_SIGNING_KEY (shared across all services)
python -c "import secrets; print(secrets.token_hex(32))"

# SERVICE_KEY (shared across services that call internal endpoints)
python -c "import secrets; print(secrets.token_hex(32))"

# Database password (per service)
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## Option A: Docker Secrets (Docker Swarm)

Docker Swarm provides encrypted secrets stored in the Swarm's Raft log.

### Setup

```bash
# Create each secret
echo "your-secret-key-value" | docker secret create spark_auth_secret_key -
echo "your-db-password" | docker secret create spark_auth_db_password -
echo "your-jwt-key" | docker secret create spark_jwt_signing_key -

# List secrets (values are never shown after creation)
docker secret ls
```

### docker-compose.prod.yml with Docker Secrets

```yaml
services:
  auth-service:
    environment:
      SECRET_KEY_FILE: /run/secrets/spark_auth_secret_key
      DB_PASSWORD_FILE: /run/secrets/spark_auth_db_password
    secrets:
      - spark_auth_secret_key
      - spark_auth_db_password

secrets:
  spark_auth_secret_key:
    external: true
  spark_auth_db_password:
    external: true
```

### Reading _FILE Variables in Django

Add to each service's `entrypoint.sh`:
```sh
# Read Docker secrets from files into environment variables
for secret_file in /run/secrets/*; do
    secret_name=$(basename "$secret_file" | tr '[:lower:]' '[:upper:]')
    export "$secret_name"="$(cat "$secret_file")"
done
```

---

## Option B: Cloud Secrets Manager

### AWS Secrets Manager

```bash
# Store a secret
aws secretsmanager create-secret \
    --name spark/production/auth-service \
    --secret-string '{"SECRET_KEY":"...","DB_PASSWORD":"...","JWT_SIGNING_KEY":"..."}'

# Retrieve in entrypoint.sh
export_aws_secret() {
    aws secretsmanager get-secret-value \
        --secret-id "spark/production/$1" \
        --query SecretString \
        --output text | python3 -c "
import json, sys
secrets = json.load(sys.stdin)
for k, v in secrets.items():
    print(f'export {k}={v}')
" | source /dev/stdin
}

export_aws_secret auth-service
```

### GCP Secret Manager

```bash
# Store a secret
echo -n "your-secret-value" | gcloud secrets create spark-auth-secret-key \
    --data-file=-

# Access in entrypoint.sh
SECRET_KEY=$(gcloud secrets versions access latest --secret="spark-auth-secret-key")
export SECRET_KEY
```

---

## Rotation Procedure

When rotating secrets, follow this order to avoid downtime:

1. **JWT_SIGNING_KEY rotation** (most critical — causes all active sessions to invalidate):
   - Add new key to all services alongside old key (dual-key validation)
   - Wait for all active tokens to expire (max 15 minutes for access, 7 days for refresh)
   - Remove old key after refresh window expires
   - In V1, simpler approach: schedule maintenance window, update all 7 services simultaneously

2. **Database passwords**:
   - Change password in PostgreSQL: `ALTER USER auth_db_user WITH PASSWORD 'new-password';`
   - Update secret in secrets manager
   - Restart affected service (or use rolling restart in CI/CD)

3. **SERVICE_KEY**:
   - Update in secrets manager for both sending and receiving services
   - Restart both services simultaneously (rolling restart is safe if both are updated before restart)

4. **AWS S3 access keys**:
   - Generate new key in AWS Console → IAM → `spark-app-s3-user` → Security credentials
   - Update secret, restart resource-service, practice-service, and assessment-service
   - Deactivate and delete the old key once the new one is confirmed working

---

## Pre-Launch Secret Checklist

- [ ] All `SECRET_KEY` values are unique per service (not shared between services)
- [ ] All `SECRET_KEY` values are ≥50 characters
- [ ] `JWT_SIGNING_KEY` is the SAME value in all 7 services
- [ ] `SERVICE_KEY` is the same in notification-service and analytics-service
- [ ] No secret contains the word "dev", "test", "example", or "replace"
- [ ] Run `trufflehog git file://.` — zero findings
- [ ] All production secrets are stored in secrets manager (not in `.env` files on server disk)
- [ ] `.env` files are NOT committed to git (verify with `git log --all -- "*.env"`)
