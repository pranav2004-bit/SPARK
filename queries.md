# Queries

Open questions/discussions to revisit later — not yet decided, not yet actioned.

---

## Content Bank tab — enable in production or leave off?

**Context (2026-11-13):** Noticed the admin "Content" nav tab shows up on the local dev
frontend (`localhost:3000`) but not on the live production site (`spark.sanjivo.com`),
even though both are running the same code. Root cause: it's not a deploy-sync issue —
the tab is gated behind a Next.js build-time env var, `NEXT_PUBLIC_CONTENT_BANK_ENABLED`
(`frontend/src/components/layout/AdminLayout.tsx`), which is `true` in the local `.env`
but unset/`false` on Vercel (where the frontend is actually hosted — this flag has no
effect on EC2, since EC2 only runs the backend; `NEXT_PUBLIC_*` vars only matter to the
Next.js build). It's the only nav tab in the entire app gated behind a flag like this —
every other tab (Batches, Resources, Practice, Assessments, Essay Writing, Scrollbar,
etc.) always shows, no flag involved.

**Why it's off by default:** per `LIVETRACKER4.md`, the Content Bank feature's rollout
(Phase I) isn't fully complete — items I8/I9 are still blocked, and a load test (H5)
failed and hasn't been re-run. `CONTENT_BANK_ENABLED` defaults to `False` on the backend
too (`practice-service`), with a per-institution allowlist on top of the global flag.

**Open question:** do we actually want this live in production now, or is it correctly
hidden pending the rest of Phase I? If enabling it:
- Vercel: add `NEXT_PUBLIC_CONTENT_BANK_ENABLED=true` (Production scope) and redeploy
  (env var alone does nothing until the next build — it's baked in at build time).
- Backend: confirm `practice-service`'s own `CONTENT_BANK_ENABLED` and the
  per-institution allowlist are actually set for the real institution in production —
  not yet checked.

**Decision:** not yet made — discuss and decide later.
