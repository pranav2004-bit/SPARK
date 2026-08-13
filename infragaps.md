# Infrastructure Gaps — Pre-Production Checklist

This file tracks the infrastructure-level gaps that exist in the current
microservices setup.  All code-level gaps have been resolved.  The items
below require infrastructure decisions and changes before the system is
considered fully production-grade at scale.

---

## 1. No Service Discovery

**What it means in this project**

The URL of auth-service is configured as a static environment variable
(`AUTH_SERVICE_URL=http://auth-service:8000`) in user-service.  Every other
service that needs to call auth-service has its own hardcoded or env-var-based
address.  If auth-service is moved to a different host, renamed, or split into
multiple instances, every dependent service must be manually updated and
redeployed.

**What goes wrong at scale**

In a multi-host deployment — whether bare metal, VMs, or Kubernetes — containers
do not stay on fixed IPs.  A container restart or rescheduling changes the IP.
A service name that resolves in Docker Compose does not automatically resolve in
a multi-host environment unless a dedicated registry is in place.

**What the fix looks like**

In Kubernetes, service discovery is built-in: services are addressed as
`auth-service.namespace.svc.cluster.local` and Kubernetes DNS updates the record
automatically when pods are rescheduled.  Outside Kubernetes, a tool like Consul
provides a service registry where each service registers itself on startup and
other services query the registry for the current address.

---

## 2. Shared Secret Instead of Mutual TLS (mTLS)

**What it means in this project**

Internal service-to-service calls are authenticated with a single shared string
(`SERVICE_KEY`) sent in the `X-Service-Key` header.  This key is the same across
all services and is stored in environment variables.  There is no per-service
identity, no certificate rotation, and no cryptographic proof of which service
is making the call.

**What goes wrong at scale**

If the `SERVICE_KEY` is leaked — through a compromised container, a log line,
or an environment variable dump — any process on the internal network can call
internal endpoints with full trust.  There is also no way to revoke access for
a single compromised service without rotating the key everywhere simultaneously.

**What the fix looks like**

Mutual TLS gives each service its own certificate.  When user-service calls
auth-service, both sides present certificates and verify each other.  A
compromised certificate can be revoked without affecting others.  In Kubernetes
this is typically handled by a service mesh such as Istio or Linkerd, which
injects sidecar proxies that manage certificate issuance and renewal
automatically via a certificate authority.  Outside Kubernetes, tools like
Vault PKI or CFSSL can issue short-lived certificates per service.

---

## 3. No Circuit Breaker

**What it means in this project**

When user-service calls auth-service, the call is attempted up to
`AUTH_SERVICE_RETRIES` times with exponential backoff.  If auth-service is
fully down, every student-creation request will block for the full retry
duration before failing.  Under load this exhausts the Django worker pool
across all three retry attempts, making user-service appear degraded even
though auth-service is the problem.

**What goes wrong at scale**

This is the cascading failure pattern.  A downstream service outage propagates
upstream and takes down services that were otherwise healthy.  With 10 concurrent
student-creation requests and a 15-second total retry window, all 10 Django
workers are blocked simultaneously, making the entire user-service unresponsive
to all other request types (batch management, resource uploads, etc.).

**What the fix looks like**

A circuit breaker monitors the failure rate of calls to a downstream service.
Once failures exceed a threshold, the circuit "opens" and subsequent calls fail
immediately without attempting the network call.  After a cooldown period the
circuit moves to a half-open state and allows one probe call through.  If the
probe succeeds the circuit closes again.  In the Python ecosystem, the `pybreaker`
library provides this.  In Kubernetes, Istio's traffic management policies can
configure circuit breaking at the infrastructure level without any code changes.

---

## 4. Single Instance — No Health-Based Load Balancing

**What it means in this project**

Each service (auth-service, user-service, etc.) runs as exactly one container.
If that container crashes or becomes unresponsive, the service is completely
unavailable until Docker restarts it.  The restart is not immediate — Docker's
health check has a grace period before it marks the container unhealthy and
triggers a restart.  During that window all requests to the service fail.

**What goes wrong at scale**

A single instance also means zero-downtime deployments are not possible.
Rebuilding and recreating the container (as done throughout this project with
`docker-compose up --build`) causes a brief outage every time code is deployed.
Under real user load this is not acceptable.

**What the fix looks like**

Kubernetes runs multiple replicas of each service (typically 2–3 for non-critical
services, more for high-traffic ones).  A Kubernetes Service load-balances
requests across healthy pods and automatically removes unhealthy pods from the
rotation via readiness probes.  Rolling deployments update one pod at a time so
there is always at least one healthy instance serving traffic.  In a pure Docker
environment, Docker Swarm provides similar capabilities with `replicas` and
`update_config` settings in the compose file.

---

## 5. No Distributed Tracing

**What it means in this project**

When a request enters user-service and triggers an internal call to auth-service,
each service logs independently.  The two log entries have no shared identifier
linking them.  To diagnose a failure that spans both services, someone must
manually correlate timestamps across two separate log streams — which becomes
impractical as the number of services grows.

**What goes wrong at scale**

With seven services currently running (auth, user, practice, resource, analytics,
notification, and the legacy monolith), a single user-facing request can touch
three or four services.  Without trace IDs propagated across service boundaries,
identifying which hop introduced a latency spike or an error requires checking
every service's logs individually and guessing based on timing.

**What the fix looks like**

A distributed tracing system assigns a trace ID to each incoming request.
When a service makes an outbound call to another service, it forwards the trace
ID in the request headers (e.g. `X-Trace-ID` or OpenTelemetry's `traceparent`).
Each service records its span — the time and outcome of its portion of the
request — and reports it to a central collector.  The collector correlates spans
by trace ID and renders the full call chain in a UI.  Jaeger and Zipkin are the
common open-source collectors.  OpenTelemetry is the standard SDK for
instrumenting Python services and is compatible with both.

---

## 6. Single Uvicorn Worker Per Service

**What it means in this project**

Every service (auth-service, user-service, practice-service, resource-service,
analytics-service, notification-service) starts Uvicorn with `--workers 1` in
its `entrypoint.sh`.  A single worker means only one HTTP request is processed
at a time per service.  If a request is slow — for example, a student creation
that waits on auth-service — every other incoming request to that service queues
behind it and appears unresponsive until the slow request finishes.

**What goes wrong at scale**

Under real concurrent load, a single worker becomes a bottleneck immediately.
Ten simultaneous admin users each adding a student means nine of them wait in
a queue behind the first.  There is also no graceful restart with a single
worker — deploying new code kills the one running worker and drops all
in-flight requests at that instant.  Gunicorn with multiple Uvicorn workers
handles graceful restarts by keeping old workers alive until their requests
finish before replacing them one at a time.

**What the fix looks like**

Replace the standalone Uvicorn command in each service's `entrypoint.sh` with
Gunicorn managing multiple Uvicorn workers:

```
gunicorn core.asgi:application \
  -k uvicorn.workers.UvicornWorker \
  --workers 4 \
  --timeout 30 \
  --bind 0.0.0.0:8000
```

The correct worker count depends on the production host spec.  The standard
formula for I/O-bound services is `2 × CPU cores + 1`.  A 2-core host gets
5 workers; a 4-core host gets 9.  Each worker consumes roughly the same RAM
as a single Django process — measure one worker's footprint first and confirm
the host has enough headroom before setting the final number.  `gunicorn` must
be added to each service's `requirements.txt` before this change is applied.

---

## 7. Synchronous Blocking Inter-Service Calls (Code + Infrastructure)

**What it means in this project**

`create_student_auth()` is called synchronously inside the Django request
handler, inside the serializer's `create()` method.  The Django/Uvicorn worker
thread is blocked — doing nothing but waiting — for the duration of the
auth-service call, which can be up to `AUTH_SERVICE_TIMEOUT × AUTH_SERVICE_RETRIES`
seconds.  During that time the worker cannot handle any other request.

**What goes wrong at scale**

Uvicorn runs a fixed pool of worker processes.  If 10 admin users simultaneously
add students, all 10 workers may be blocked waiting on auth-service.  Any other
request — loading the student list, uploading resources, fetching analytics —
queues behind them and appears slow even though those operations have nothing to
do with auth-service.

**What the fix looks like**

The student creation flow should be split into two steps.  Step one creates the
student profile in user-service and enqueues a Celery task.  Step two — the
Celery task — calls auth-service asynchronously in a background worker.  The
response to the admin is immediate.  The auth account is created within seconds
in the background.  This requires adding a Celery worker to user-service
(the pattern already exists in analytics-service and notification-service in
this project) and handling the case where the student profile briefly exists
before the auth account is ready.

---

## 8. Best-Effort Compensating Transaction (Code + Infrastructure)

**What it means in this project**

Student creation is a two-step operation across two databases: first create the
auth account in auth-service, then create the profile in user-service.  If the
second step (profile creation) fails, the code calls `delete_student_auth()` as
a rollback.  `delete_student_auth()` is best-effort — it catches and swallows
all errors.  If the rollback call also fails, an orphan auth account is created
in auth-service with no corresponding profile in user-service.  There is no
automatic detection or recovery mechanism.

**What goes wrong at scale**

Orphan auth accounts accumulate silently.  The affected student sees login
failures with no error message because the auth account exists but the profile
does not.  Diagnosing this requires manually cross-referencing two databases.
Under high-concurrency conditions (bulk imports with transient DB errors) this
can produce multiple orphans in a single session.

**What the fix looks like**

The correct pattern for multi-service writes is the Saga pattern.  Each step
publishes an event to a message broker.  If a step fails, a compensating event
triggers the rollback in the upstream service.  Since the broker persists events,
the rollback is guaranteed to execute eventually even if auth-service is
temporarily unavailable.  In the shorter term, a scheduled reconciliation job
can periodically cross-check auth-service student accounts against user-service
profiles and flag or clean up any orphans found.  RabbitMQ or Kafka are the
standard message brokers for this pattern; Celery with a durable backend
(Redis or RabbitMQ) is a pragmatic lightweight alternative already present in
this project.
