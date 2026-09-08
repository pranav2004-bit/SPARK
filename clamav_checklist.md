# ClamAV — Production Readiness Checklist

- [ ] Pin the image to a specific version/digest instead of the floating `:stable` tag, so deploys are reproducible and don't silently change on rebuild
- [ ] Confirm production's network egress rules allow `freshclam` to reach ClamAV's signature-update servers — or set up an internal signature mirror if outbound access is locked down
- [ ] Carry the memory limit (already tuned from the dev OOM incident) into production, sized correctly for the production host
- [ ] Set up a patch/update cadence for the ClamAV version — track security advisories, don't freeze the version indefinitely
- [ ] Mirror the image in a private registry so a Docker Hub outage can't block a production deploy
- [ ] Monitor ClamAV's health/uptime with alerting — confirm uploads fail-closed (blocked) rather than silently skipping the scan if ClamAV is down
- [ ] Verify the startup/readiness grace period in production is long enough for the signature database to fully load before traffic is routed to dependent services
- [ ] Set scan limits (`MaxScanSize`, `MaxFileSize`, `MaxRecursion`) to prevent an oversized file or a zip bomb from tying up the scanner as a DoS vector
- [ ] Confirm ClamAV's port is only reachable on the internal Docker network, never published externally
