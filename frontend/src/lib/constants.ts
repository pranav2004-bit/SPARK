// DEPARTMENTS used to live here as a hardcoded list. It's backend-managed
// now (2026-08-20, IT's Departments module) — use useDepartments() from
// @/lib/departmentsContext instead.

export const UPLOAD_TYPE_LABELS: Record<string, string> = {
  pdf: "PDF",
  audio: "Audio",
  video: "Video",
  image: "Image",
  video_link: "Video Link",
  external_link: "External Link",
};

export const UPLOAD_ACCEPT_MAP: Record<string, string> = {
  pdf: ".pdf",
  audio: ".mp3,.aac,.m4a,.ogg",
  video: ".mp4,.webm",
  image: ".jpg,.jpeg,.png,.gif,.webp",
};

export const FILE_UPLOAD_TYPES = ["pdf", "audio", "video", "image"] as const;
export const LINK_UPLOAD_TYPES = ["video_link", "external_link"] as const;

// ── Upload constraints ─────────────────────────────────────────────────────────
// Mirrors services/resource-service/core/upload_constraints.py — keep both in
// sync when changing. .svg is excluded (inline <script>/event-handler
// payloads make it a stored-XSS vector when opened via a raw link), .wav is
// excluded (uncompressed audio blows through any single size cap in
// minutes), and .avi/.mov/.mkv are excluded for video (none of them play in
// an HTML5 <video>/browser tab the way this app serves files — only
// .mp4/.webm do). The backend re-validates all of this independently and is
// the actual source of truth — these are just for fast client-side UX.

/** Hard file-size ceilings per type (bytes). Enforced client-side before upload. */
export const MAX_FILE_SIZES: Record<string, number> = {
  pdf:   25  * 1024 * 1024,  // 25 MB  — brochures, JDs
  audio: 100 * 1024 * 1024,  // 100 MB — interview tips, recordings
  video: 500 * 1024 * 1024,  // 500 MB — prep videos
  image: 5   * 1024 * 1024,  //  5 MB  — logos, posters
};

/** Human-readable size label for each type (used in error messages). */
export const MAX_FILE_SIZE_LABELS: Record<string, string> = {
  pdf:   "25 MB",
  audio: "100 MB",
  video: "500 MB",
  image: "5 MB",
};

/** Allowed file extensions per type (lowercase, dot-prefixed). */
export const ALLOWED_EXTENSIONS: Record<string, string[]> = {
  pdf:   [".pdf"],
  audio: [".mp3", ".aac", ".m4a", ".ogg"],
  video: [".mp4", ".webm"],
  image: [".jpg", ".jpeg", ".png", ".gif", ".webp"],
};

/** Allowed MIME types per type (secondary check — extension is primary). */
export const ALLOWED_MIME_TYPES: Record<string, string[]> = {
  pdf:   ["application/pdf"],
  audio: ["audio/mpeg", "audio/mp3", "audio/aac",
          "audio/x-m4a", "audio/mp4", "audio/ogg", "audio/vorbis"],
  video: ["video/mp4", "video/webm"],
  image: ["image/jpeg", "image/png", "image/gif", "image/webp"],
};

/** Maximum uploads allowed per section (prevents runaway storage). */
export const MAX_UPLOADS_PER_SECTION = 50;

// ── Portal login configs ──────────────────────────────────────────────────────
// Live here (not in the page.tsx files that consume them) because Next.js's
// App Router only permits a fixed set of named exports from a `page.tsx`
// (default, config, metadata, generateStaticParams, ...) — any other named
// export, like these used to be, fails `next build`'s page-shape type check
// even though the file is otherwise valid. Exported for regression testing —
// if any of these values change, tests fail immediately.

export const ADMIN_LOGIN_CONFIG = {
  apiEndpoint: "/auth/login/",
  cookieRole: "admin" as const,
  redirectTo: "/admin/batch",
  extraBody: { role: "admin" },
} as const;

export const SUPER_ADMIN_LOGIN_CONFIG = {
  apiEndpoint: "/auth/login/",
  cookieRole: "super_admin" as const,
  redirectTo: "/super-admin/overview",
  extraBody: { role: "super_admin" },
} as const;

export const IT_LOGIN_CONFIG = {
  apiEndpoint: "/auth/login/",
  cookieRole: "it" as const,
  redirectTo: "/it/welcome",
  extraBody: { role: "it" },
} as const;
