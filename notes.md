# Notes

Running notes for this application.

---

## Async ClamAV Malware Scan

**Usage:** Every file an admin uploads (resource-service) is scanned by ClamAV in the
background after confirm. Status shows as "Scanning…" (`pending`) until the scan finishes,
then flips to `clean` (visible to students) or gets deleted if `infected`. Runs async via
Celery (`resource-worker`) so the upload request itself doesn't wait on it.
