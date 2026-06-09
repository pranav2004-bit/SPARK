/**
 * SPARK Service Worker
 *
 * Responsibilities:
 *  1. Pre-cache /offline.html on install so it is always available.
 *  2. For every navigation request (page load / route change), attempt the
 *     network first. If the network is unreachable, serve the offline page.
 *  3. All other requests (API, assets, images) fall through to the network
 *     untouched — no aggressive caching that could serve stale data.
 */

const CACHE  = "spark-shell-v1";
const OFFLINE = "/offline.html";

// ── Install — cache the offline shell ────────────────────────────────────────
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.add(OFFLINE))
  );
  // Activate immediately — don't wait for existing tabs to close
  self.skipWaiting();
});

// ── Activate — remove stale caches ───────────────────────────────────────────
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
        )
      )
  );
  self.clients.claim();
});

// ── Fetch — network-first for navigation, passthrough for everything else ─────
self.addEventListener("fetch", (event) => {
  // Only intercept full page navigations (GET, same-origin or cross-origin)
  if (event.request.mode !== "navigate") return;

  event.respondWith(
    fetch(event.request).catch(() =>
      caches.match(OFFLINE).then((cached) => cached ?? new Response("Offline", { status: 503 }))
    )
  );
});
