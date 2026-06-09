import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Decode JWT payload without verification (edge runtime can't run crypto libs).
// The actual token verification happens server-side at the Django backend on
// every API call — this is only for client-side UX routing.
function decodeJwtPayload(
  token: string
): { role?: string; is_profile_completed?: boolean } | null {
  try {
    const base64 = token.split(".")[1];
    if (!base64) return null;
    // atob is available in the edge runtime
    const json = atob(base64.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(json);
  } catch {
    return null;
  }
}

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Read stored auth from localStorage is NOT possible in proxy (edge runtime).
  // We use a cookie set on login that mirrors the role — not httpOnly so JS can
  // also read it, but used here for edge-level route protection.
  const authCookie = request.cookies.get("aptlogic_role")?.value;
  const accessCookie = request.cookies.get("aptlogic_access")?.value;

  const role = authCookie ?? null;
  const payload = accessCookie ? decodeJwtPayload(accessCookie) : null;

  // ── Admin routes ─────────────────────────────────────────────────────────────
  if (pathname.startsWith("/admin")) {
    if (pathname === "/admin/login") {
      // Already logged in as admin → redirect to dashboard
      if (role === "admin") {
        return NextResponse.redirect(new URL("/admin/batch", request.url));
      }
      return NextResponse.next();
    }

    // Protected admin route — must have admin role
    if (role !== "admin") {
      return NextResponse.redirect(new URL("/admin/login", request.url));
    }
  }

  // ── Student routes ───────────────────────────────────────────────────────────
  if (pathname.startsWith("/students")) {
    if (pathname === "/students/login") {
      if (role === "student") {
        const isComplete = payload?.is_profile_completed ?? true;
        return NextResponse.redirect(
          new URL(
            isComplete ? "/students/home" : "/students/my_profile",
            request.url
          )
        );
      }
      return NextResponse.next();
    }

    if (role !== "student") {
      return NextResponse.redirect(new URL("/students/login", request.url));
    }

    // First-login guard
    if (
      pathname !== "/students/my_profile" &&
      payload?.is_profile_completed === false
    ) {
      return NextResponse.redirect(
        new URL("/students/my_profile", request.url)
      );
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/admin/:path*", "/students/:path*"],
};
