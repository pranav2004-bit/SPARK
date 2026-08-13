"use client";

import { useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/auth-store";
import { clearAuthCookies } from "@/lib/cookies";
import api from "@/lib/api";

// Exported for regression testing — paths must stay in sync with middleware.ts
// PORTAL_LOGIN and the loginPaths record in api.ts.
export const LOGIN_PATHS: Record<string, string> = {
  student: "/students/login",
  admin: "/admin/login",
  super_admin: "/super-admin/login",
};

export function useAuth() {
  const router = useRouter();
  const { user, accessToken, clearAuth } = useAuthStore();

  const isAdmin = user?.role === "admin";
  const isStudent = user?.role === "student";
  const isSuperAdmin = user?.role === "super_admin";
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
    isAuthenticated,
    logout,
  };
}
