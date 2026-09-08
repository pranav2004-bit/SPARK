"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "./useAuth";
import { LOGIN_PATH_BY_ROLE, type PortalRole } from "@/lib/portalRouting";

/**
 * Client-side, per-tab replacement for the role-matching check that used
 * to live in proxy.ts (added 2026-08-27, see that file's comment for the
 * cross-tab bug this fixes). Reads the tab's own Zustand-backed session —
 * genuinely tab-isolated, unlike the shared aptlogic_role cookie — and
 * redirects to `requiredRole`'s login page if this tab isn't authenticated
 * as that role.
 *
 * Called unconditionally from every portal layout (AdminLayout,
 * StudentLayout, ITLayout) except super-admin's file-based layout.tsx,
 * which also wraps its own login page and so calls this with `skip: true`
 * while on that path — see that file for why.
 *
 * Gated on hasHydrated: without it, a genuinely logged-in tab would look
 * logged-out for the one render before sessionStorage rehydration
 * completes, and this would redirect it away incorrectly.
 */
export function usePortalGuard(requiredRole: PortalRole, options?: { skip?: boolean }) {
  const router = useRouter();
  const { user, isAuthenticated, hasHydrated } = useAuth();
  const skip = options?.skip ?? false;

  useEffect(() => {
    if (skip || !hasHydrated) return;
    if (!isAuthenticated || user?.role !== requiredRole) {
      router.replace(LOGIN_PATH_BY_ROLE[requiredRole]);
    }
  }, [skip, hasHydrated, isAuthenticated, user, requiredRole, router]);

  return { ready: hasHydrated && isAuthenticated && user?.role === requiredRole };
}
