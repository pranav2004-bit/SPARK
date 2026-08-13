import { NextRequest, NextResponse } from "next/server";

// Which login page to show for each portal prefix
const PORTAL_LOGIN: Record<string, string> = {
  "/admin": "/admin/login",
  "/students": "/students/login",
  "/super-admin": "/super-admin/login",
};

// Where to land after successful auth, keyed by role
const PORTAL_HOME: Record<string, string> = {
  admin: "/admin/batch",
  student: "/students/home",
  super_admin: "/super-admin/overview",
};

// Path prefix each role is authorised to access
const ROLE_PREFIX: Record<string, string> = {
  admin: "/admin",
  student: "/students",
  super_admin: "/super-admin",
};

// Login pages — authenticated users are bounced away from these
const LOGIN_PATHS = new Set([
  "/login",
  "/admin/login",
  "/students/login",
  "/student/login",
  "/super-admin/login",
]);

export function isValidRole(role: string): role is "student" | "admin" | "super_admin" {
  return role === "student" || role === "admin" || role === "super_admin";
}

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Which portal (if any) owns this path?
  const portalPrefix = Object.keys(PORTAL_LOGIN).find(
    (prefix) => pathname === prefix || pathname.startsWith(prefix + "/")
  );

  // ── Not a portal path → public page ───────────────────────────────────────
  if (!portalPrefix) {
    // Edge case: /student/login or /login — bounce authenticated users away
    if (LOGIN_PATHS.has(pathname)) {
      const roleCookie = request.cookies.get("aptlogic_role")?.value;
      if (roleCookie && isValidRole(roleCookie)) {
        return NextResponse.redirect(new URL(PORTAL_HOME[roleCookie], request.url));
      }
    }
    return NextResponse.next();
  }

  // ── Portal path ────────────────────────────────────────────────────────────
  const roleCookie = request.cookies.get("aptlogic_role")?.value;
  const role = roleCookie && isValidRole(roleCookie) ? roleCookie : null;

  // Portal login page
  if (LOGIN_PATHS.has(pathname)) {
    if (role) {
      // Already authenticated → send to own portal home
      return NextResponse.redirect(new URL(PORTAL_HOME[role], request.url));
    }
    // Not authenticated → show the login page
    return NextResponse.next();
  }

  // Portal non-login page — requires authentication
  if (!role) {
    return NextResponse.redirect(new URL(PORTAL_LOGIN[portalPrefix], request.url));
  }

  // Authenticated — verify this user belongs to the portal being accessed
  if (!pathname.startsWith(ROLE_PREFIX[role])) {
    return NextResponse.redirect(new URL(PORTAL_HOME[role], request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    // Exclude Next.js internals, API routes, and static assets
    "/((?!_next/static|_next/image|favicon\\.ico|api/).*)",
  ],
};

// Alias for test compatibility — tests import { middleware } from "../proxy"
export { proxy as middleware };
