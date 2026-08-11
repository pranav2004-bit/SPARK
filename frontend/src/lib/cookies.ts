"use client";

// These cookies are readable by Next.js middleware (edge runtime) for route
// protection. They are NOT httpOnly so we can set them from client JS.
// The access token stored here is only used for JWT payload decoding in
// middleware — never for authentication (that happens via Authorization header).

const MAX_AGE = 7 * 24 * 60 * 60; // 7 days (matches refresh token lifetime)

export function isValidRole(role: string): role is "student" | "admin" | "super_admin" {
  return role === "student" || role === "admin" || role === "super_admin";
}

export function setAuthCookies(role: string, accessToken: string) {
  document.cookie = `aptlogic_role=${role}; path=/; max-age=${MAX_AGE}; SameSite=Strict`;
  document.cookie = `aptlogic_access=${accessToken}; path=/; max-age=${MAX_AGE}; SameSite=Strict`;
}

export function clearAuthCookies() {
  document.cookie = "aptlogic_role=; path=/; max-age=0";
  document.cookie = "aptlogic_access=; path=/; max-age=0";
}
