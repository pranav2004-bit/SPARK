"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { AuthUser } from "@/types";

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: AuthUser | null;
  // True once zustand's persist middleware has finished reading
  // sessionStorage on this tab's first mount (added 2026-08-27). A guard
  // that checks isAuthenticated before this flips true would see a
  // genuinely logged-in tab as logged-out during the brief window before
  // rehydration completes, and could incorrectly redirect it away — see
  // usePortalGuard.ts, the consumer this exists for.
  hasHydrated: boolean;
  setTokens: (access: string, refresh: string, user: AuthUser) => void;
  setAccessToken: (token: string) => void;
  setUser: (user: AuthUser) => void;
  clearAuth: () => void;
  setHasHydrated: (v: boolean) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      hasHydrated: false,

      setTokens: (access, refresh, user) =>
        set({ accessToken: access, refreshToken: refresh, user }),

      setAccessToken: (token) => set({ accessToken: token }),

      setUser: (user) => set({ user }),

      clearAuth: () =>
        set({ accessToken: null, refreshToken: null, user: null }),

      setHasHydrated: (v) => set({ hasHydrated: v }),
    }),
    {
      name: "aptlogic_auth",
      // sessionStorage is tab-isolated — each tab maintains its own login session.
      // Multiple tabs (admin, student1, student2) can be logged in simultaneously
      // with different accounts without interfering with each other.
      storage: createJSONStorage(() => sessionStorage),
      // hasHydrated is deliberately excluded from the persisted payload —
      // it's a fresh-per-page-load signal, not part of the saved session.
      partialize: (state) => ({
        accessToken: state.accessToken, refreshToken: state.refreshToken, user: state.user,
      }),
      onRehydrateStorage: () => (state) => {
        state?.setHasHydrated(true);
      },
    }
  )
);
