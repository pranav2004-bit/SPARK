import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  devIndicators: { position: "bottom-left" },
  skipTrailingSlashRedirect: true,
  // No rewrites() here on purpose: nginx already routes every real /api/*
  // path directly to its backend service (see gateway/nginx.dev.conf), and
  // the app's own HTTP client (src/lib/api.ts) calls NEXT_PUBLIC_API_URL
  // straight from the browser — this Next.js server never sits in that
  // request path. A `rewrites()` block used to catch /api/:path* here and
  // re-proxy it to `API_BASE_URL` (which is never actually set anywhere),
  // defaulting to http://127.0.0.1 with no port — nothing listens there in
  // this container, so any /api/ request nginx's catch-all forwarded here
  // (i.e. a genuinely unmatched path) crashed with an unhandled 500 instead
  // of Next.js's own normal 404. Removing it lets that 404 happen correctly.
};

export default nextConfig;
