"use client";

import { useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/auth-store";
import { clearAuthCookies } from "@/lib/cookies";
import api from "@/lib/api";
import { LOGIN_PATH_BY_ROLE, PORTAL_HOME as PORTAL_HOME_BY_ROLE } from "@/lib/portalRouting";

// Re-exported (kept as the wider Record<string, string> shape existing
// callers/tests already rely on) from lib/portalRouting.ts, the single
// source of truth shared with proxy.ts and usePortalGuard.ts since
// 2026-08-27 — see proxy.ts's own comment for why that split exists.
export const LOGIN_PATHS: Record<string, string> = LOGIN_PATH_BY_ROLE;
export const PORTAL_HOME: Record<string, string> = PORTAL_HOME_BY_ROLE;

export function useAuth() {
  const router = useRouter();
  const { user, accessToken, clearAuth, hasHydrated } = useAuthStore();

  const isAdmin = user?.role === "admin";
  const isStudent = user?.role === "student";
  const isSuperAdmin = user?.role === "super_admin";
  const isIT = user?.role === "it";
  const isAuthenticated = !!accessToken && !!user;

  const logout = useCallback(async () => {
    const currentRole = useAuthStore.getState().user?.role;
    try {
      const refreshToken = useAuthStore.getState().refreshToken;
      if (refreshToken) {
        await api.post("/auth/logout/", { refresh_token: refreshToken });
      }
    } catch {
      // Clear auth regardless of API errors
    } finally {
      clearAuth();
      clearAuthCookies();
      router.push(LOGIN_PATHS[currentRole ?? "admin"] ?? "/login");
    }
  }, [clearAuth, router]);

  return {
    user,
    isAdmin,
    isStudent,
    isSuperAdmin,
    isIT,
    isAuthenticated,
    hasHydrated,
    logout,
  };
}
