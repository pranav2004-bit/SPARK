"use client";

import { useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/auth-store";
import { clearAuthCookies } from "@/lib/cookies";
import api from "@/lib/api";

export function useAuth() {
  const router = useRouter();
  const { user, accessToken, clearAuth } = useAuthStore();

  const isAdmin = user?.role === "admin";
  const isStudent = user?.role === "student";
  const isAuthenticated = !!accessToken && !!user;

  const logout = useCallback(async () => {
    // Capture role before clearing — used for redirect target
    const currentRole = useAuthStore.getState().user?.role;
    try {
      const refreshToken = useAuthStore.getState().refreshToken;
      if (refreshToken && currentRole === "admin") {
        await api.post("/admin/logout/", { refresh: refreshToken });
      }
    } catch {
      // Ignore errors — clear auth regardless
    } finally {
      clearAuth();
      clearAuthCookies();
      router.push(currentRole === "student" ? "/students/login" : "/admin/login");
    }
  }, [clearAuth, router]);

  return {
    user,
    isAdmin,
    isStudent,
    isAuthenticated,
    logout,
  };
}
