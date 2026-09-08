// Pure data, no React/Zustand — safe to import from both proxy.ts (Edge
// middleware, no browser APIs) and ordinary client components. Single
// source of truth for portal role/path mappings, added 2026-08-27 when the
// cross-tab auth fix split routing decisions across both layers (see
// proxy.ts's own comment for why).

export type PortalRole = "student" | "admin" | "super_admin" | "it";

export function isValidRole(role: string): role is PortalRole {
  return role === "student" || role === "admin" || role === "super_admin" || role === "it";
}

// Path prefix -> login page. Used by proxy.ts's coarse "protected path,
// zero session cookie at all" gate.
export const PORTAL_LOGIN_BY_PREFIX: Record<string, string> = {
  "/admin": "/admin/login",
  "/students": "/students/login",
  "/super-admin": "/super-admin/login",
  "/it": "/it/login",
};

// Role -> login page. Used client-side (usePortalGuard) where the role is
// already known from the tab's own session, not a path prefix.
export const LOGIN_PATH_BY_ROLE: Record<PortalRole, string> = {
  student: "/students/login",
  admin: "/admin/login",
  super_admin: "/super-admin/login",
  it: "/it/login",
};

// Role -> portal home. Used both after a fresh login and by each login
// page's own "already authenticated in this tab" redirect.
export const PORTAL_HOME: Record<PortalRole, string> = {
  admin: "/admin/batch",
  student: "/students/home",
  super_admin: "/super-admin/overview",
  it: "/it/welcome",
};
