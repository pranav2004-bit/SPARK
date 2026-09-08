# nginx — Production Readiness Checklist

- [ ] Pin to an exact version + digest instead of the floating `1.25-alpine` tag, so deploys are reproducible and don't silently change on rebuild
- [ ] Verify the pinned version is current and patched — confirm no known, fixed CVEs apply to it before deploying
- [ ] Configure TLS/HTTPS termination for production — the current dev config serves plain HTTP only
- [ ] Plan for nginx's own availability in production — it's the single entry point for the entire app (frontend + all 7 services), so it going down takes everything down; put it behind a redundant setup (cloud load balancer or multiple nginx replicas), don't run it as a lone instance
- [ ] Review and tune rate-limiting thresholds for real production traffic, and confirm whether endpoints beyond auth (login/logout/token) need limits too
- [ ] Confirm internal-only routes (`/api/*/internal/`) are also blocked at the network level in production, not relying solely on nginx's own location-block logic
- [ ] Set standard security headers (HSTS, X-Frame-Options, X-Content-Type-Options, etc.) — not currently configured
- [ ] Tune `proxy_connect_timeout`/`proxy_read_timeout`/`proxy_send_timeout` deliberately, so a hung backend can't pile up connections and a legitimately slow request (upload/export) isn't cut off prematurely
- [ ] Ship nginx access/error logs somewhere durable in production — they currently go to container stdout/stderr and are lost on restart
