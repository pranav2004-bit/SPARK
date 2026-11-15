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

  // bfcache restore (browser back/forward) — logout (api.ts's forceLogout)
  // does a hard `window.location.href` redirect, a real page unload, which
  // is exactly what makes the page the student was just logged out of
  // eligible for the browser's back-forward cache. A later back navigation
  // can hand back that frozen pre-logout snapshot — still showing
  // isAuthenticated: true in its own frozen state, since that was captured
  // before logout ran in the *new* document — instantly, before this
  // effect's dependencies have any reason to re-fire. No API call can
  // actually succeed without a token, so this was never a real
  // re-authentication bypass, only a stale-visual-flash risk — but a full
  // reload re-reads this tab's actual, already-cleared sessionStorage from
  // scratch and re-runs the check above for real.
  useEffect(() => {
    if (skip) return;
    function handlePageShow(e: PageTransitionEvent) {
      if (e.persisted) window.location.reload();
    }
    window.addEventListener("pageshow", handlePageShow);
    return () => window.removeEventListener("pageshow", handlePageShow);
  }, [skip]);

  return { ready: hasHydrated && isAuthenticated && user?.role === requiredRole };
}
