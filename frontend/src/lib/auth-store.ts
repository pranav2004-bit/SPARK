"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { AuthUser } from "@/types";

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: AuthUser | null;
  setTokens: (access: string, refresh: string, user: AuthUser) => void;
  setAccessToken: (token: string) => void;
  setUser: (user: AuthUser) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,

      setTokens: (access, refresh, user) =>
        set({ accessToken: access, refreshToken: refresh, user }),

      setAccessToken: (token) => set({ accessToken: token }),

      setUser: (user) => set({ user }),

      clearAuth: () =>
        set({ accessToken: null, refreshToken: null, user: null }),
    }),
    {
      name: "aptlogic_auth",
      // sessionStorage is tab-isolated — each tab maintains its own login session.
      // Multiple tabs (admin, student1, student2) can be logged in simultaneously
      // with different accounts without interfering with each other.
      storage: createJSONStorage(() => sessionStorage),
    }
  )
);
