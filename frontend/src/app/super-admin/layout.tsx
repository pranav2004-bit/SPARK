"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  Layers,
  BarChart2,
  LogOut,
  ChevronDown,
  Radio,
  UserCircle,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { usePortalGuard } from "@/hooks/usePortalGuard";
import { useState, useRef, useEffect } from "react";
import { ScrollingUpdates } from "@/components/ui/ScrollingUpdates";
import type { SuperAdminUser } from "@/types";

// ── Nav items ──────────────────────────────────────────────────────────────────
// Students module removed (2026-08-19) — Batches alone is now Super Admin's
// student-facing module too, same as Admin; a batch's own roster is still
// viewable via its card's "View students" link (super-admin/batches/[batch_id]).
// Standalone student search/list is IT-exclusive (/it/students).
// "IT Accounts" removed (2026-08-20) — IT is now the platform's bootstrapped
// root (a single account seeded from .env), and Super Admin accounts are now
// created/managed by IT instead of the other way around — see /it/super-admins.
// Scrollbar added (2026-08-20) — same module Admin has; both roles manage
// their own institution's announcement bar independently.

const NAV_ITEMS = [
  { href: "/super-admin/overview",  label: "Overview",          icon: LayoutDashboard },
  { href: "/super-admin/admins",    label: "Admins",            icon: Users           },
  { href: "/super-admin/batches",   label: "Batches",           icon: Layers          },
  { href: "/super-admin/scroll",    label: "Scrollbar",         icon: Radio           },
  { href: "/super-admin/analytics", label: "Analytics",         icon: BarChart2       },
];

// ── Layout ─────────────────────────────────────────────────────────────────────

export default function SuperAdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const isLoginPage = pathname === "/super-admin/login";
  // This file-based layout wraps the login page too (unlike Admin/Student/
  // IT's Pattern A, where the login page is bare and never sees the
  // layout's guard at all) — skip the "redirect to login" direction while
  // actually on it, since PortalLoginForm already owns the opposite
  // "already logged in, redirect away" direction for that path.
  usePortalGuard("super_admin", { skip: isLoginPage });
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const superAdmin = user?.role === "super_admin" ? (user as SuperAdminUser) : null;
  const displayName = superAdmin?.name ?? superAdmin?.email ?? "Super Admin";
  const initials = displayName.charAt(0).toUpperCase();

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  // Login page renders its own full-screen layout — skip header chrome
  if (isLoginPage) {
    return <>{children}</>;
  }

  return (
    <div className="flex flex-col min-h-screen">

      {/* ── Top header ─────────────────────────────────────────────────────────── */}
      <header
        className="fixed top-0 inset-x-0 z-30 flex items-center justify-between px-6 xl:px-10"
        style={{
          height: 56,
          background: "var(--color-primary)",
          borderBottom: "1px solid rgba(255,255,255,0.08)",
        }}
      >
        {/* Left — logos + portal label */}
        <div className="flex items-center gap-3 shrink-0">
          <div className="flex items-center gap-2.5">
            <Image
              src="/institution-logo.png"
              alt="Institution"
              width={0}
              height={0}
              style={{ height: 52, width: "auto" }}
            />
            <div
              style={{
                width: 1,
                height: 36,
                backgroundColor: "rgba(255,255,255,0.22)",
                flexShrink: 0,
              }}
            />
            <Image
              src="/spark-logo.svg"
              alt="SPARK"
              width={0}
              height={0}
              style={{ height: 34, width: "auto" }}
            />
          </div>
          <span
            className="text-[11px] font-medium hidden sm:block"
            style={{
              color: "rgba(255,255,255,0.40)",
              borderLeft: "1px solid rgba(255,255,255,0.18)",
              paddingLeft: 10,
              letterSpacing: "0.04em",
            }}
          >
            Super Admin
          </span>
        </div>

        {/* Center — nav links */}
        <nav className="flex items-center gap-1">
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
            const isActive = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                prefetch={false}
                className="flex items-center gap-2 px-4 py-1.5 rounded-lg text-sm font-medium transition-all duration-150"
                style={{
                  color: isActive ? "#fff" : "rgba(255,255,255,0.60)",
                  background: isActive ? "rgba(255,255,255,0.10)" : "transparent",
                  borderBottom: isActive ? "2px solid var(--color-accent)" : "2px solid transparent",
                  fontWeight: isActive ? 600 : 400,
                }}
              >
                <Icon size={15} />
                {label}
              </Link>
            );
          })}
        </nav>

        {/* Right — user dropdown */}
        <div className="relative shrink-0" ref={dropdownRef}>
          <button
            onClick={() => setDropdownOpen((v) => !v)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg transition-all duration-150"
            style={{
              color: "rgba(255,255,255,0.75)",
              background: dropdownOpen ? "rgba(255,255,255,0.08)" : "transparent",
            }}
          >
            <span
              className="flex items-center justify-center rounded-full text-xs font-bold"
              style={{ width: 28, height: 28, background: "var(--color-accent)", color: "#fff" }}
            >
              {initials}
            </span>
            <span className="text-sm hidden sm:block max-w-[140px] truncate">
              {displayName}
            </span>
            <ChevronDown size={14} style={{ opacity: 0.6 }} />
          </button>

          {dropdownOpen && (
            <div
              className="absolute right-0 mt-2 w-52 rounded-xl overflow-hidden"
              style={{
                background: "#fff",
                boxShadow: "var(--shadow-lg)",
                border: "1px solid var(--color-border)",
              }}
            >
              <div className="px-4 py-3" style={{ borderBottom: "1px solid var(--color-border)" }}>
                <p className="text-xs" style={{ color: "var(--color-text-subtle)" }}>Signed in as</p>
                <p className="text-sm font-semibold truncate" style={{ color: "var(--color-text)" }}>
                  {superAdmin?.email ?? displayName}
                </p>
              </div>

              <Link
                href="/super-admin/profile"
                onClick={() => setDropdownOpen(false)}
                className="flex items-center gap-2 w-full px-4 py-3 text-sm transition-all duration-150"
                style={{ color: "var(--color-text)" }}
                onMouseEnter={e => ((e.currentTarget as HTMLElement).style.background = "var(--color-surface-hover)")}
                onMouseLeave={e => ((e.currentTarget as HTMLElement).style.background = "transparent")}
              >
                <UserCircle size={15} style={{ color: "var(--color-text-muted)" }} />
                My Profile
              </Link>

              <button
                onClick={() => { setDropdownOpen(false); logout(); }}
                className="flex items-center gap-2 w-full px-4 py-3 text-sm transition-all duration-150"
                style={{ color: "var(--color-danger)", borderTop: "1px solid var(--color-border)" }}
                onMouseEnter={e => (e.currentTarget.style.background = "var(--color-danger-bg)")}
                onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
              >
                <LogOut size={15} />
                Sign out
              </button>
            </div>
          )}
        </div>
      </header>

      {/* ── Main content ───────────────────────────────────────────────────────── */}
      <main className="flex-1 pb-8" style={{ marginTop: 56 }}>
        <ScrollingUpdates context="admin" stickyTop={56} />
        {children}
      </main>

    </div>
  );
}
