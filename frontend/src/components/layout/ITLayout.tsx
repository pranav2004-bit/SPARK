"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { LogOut, ChevronDown, Inbox, MessageSquare, LayoutDashboard, Users, ShieldCheck, Crown, Building2 } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { usePortalGuard } from "@/hooks/usePortalGuard";
import { useState, useRef, useEffect } from "react";
import type { ITUser } from "@/types";

interface NavItem {
  href: string;
  label: string;
  icon: React.ReactNode;
}

// Dead Letter Queue and Inquiries moved here from Super Admin / Admin
// (2026-08-18); Batches and Students moved here from Admin (2026-08-19) — IT
// owns all CRUD, Admin keeps read-only access on its own pages. Admin
// account management placed here from Super Admin (2026-08-19, phase 1 —
// added alongside Super Admin, full parity); Super Admin was then restricted
// to read-only on it the same day (phase 2), same treatment as Batches.
// Super Admin account management placed here (2026-08-20) — IT is now the
// platform's bootstrapped root and provisions Super Admin the same way it
// already provisions Admin; Super Admin has zero access to this roster.
// Departments module added here (2026-08-20) — a separate module from
// Super Admins/Admins rather than merged into either: it's reference/org
// data consumed by many unrelated entities (account creation, student
// creation, batch/assessment filters), same reasoning Batches has its own
// module distinct from Students. Drives every department dropdown app-wide
// live (see @/lib/departmentsContext) — no rebuild needed to add/rename one.
// Add further modules to this array as decided.
const NAV_ITEMS: NavItem[] = [
  { href: "/it/super-admins", label: "Super Admins",   icon: <Crown size={15} /> },
  { href: "/it/admins",    label: "Admins",            icon: <ShieldCheck size={15} /> },
  { href: "/it/departments", label: "Departments",     icon: <Building2 size={15} /> },
  { href: "/it/batch",     label: "Batches",           icon: <LayoutDashboard size={15} /> },
  { href: "/it/students",  label: "Students",          icon: <Users size={15} /> },
  { href: "/it/dlq",       label: "Dead Letter Queue", icon: <Inbox size={15} /> },
  { href: "/it/inquiries", label: "Inquiries",         icon: <MessageSquare size={15} /> },
];

export function ITLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  usePortalGuard("it");
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const itUser = user?.role === "it" ? (user as ITUser) : null;
  const displayName = itUser?.name || itUser?.email || "IT";
  const initials = displayName.charAt(0).toUpperCase();

  // ── Close dropdown on outside click ─────────────────────────────────────────
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <div className="flex flex-col min-h-screen">

      {/* ── Top Header ───────────────────────────────────────────────────────── */}
      <header
        className="fixed top-0 inset-x-0 z-30 flex items-center justify-between px-6 xl:px-10"
        style={{
          height: 56,
          background: "var(--color-primary)",
          borderBottom: "1px solid rgba(255,255,255,0.08)",
        }}
      >
        {/* Left — Logos */}
        <div className="flex items-center gap-3 shrink-0">
          <div className="flex items-center gap-2.5">
            <Image src="/institution-logo.png" alt="Institution" width={0} height={0}
              style={{ height: 52, width: "auto" }} />
            <div style={{ width: 1, height: 36, backgroundColor: "rgba(255,255,255,0.22)", flexShrink: 0 }} />
            <Image src="/spark-logo.svg" alt="SPARK" width={0} height={0}
              style={{ height: 34, width: "auto" }} />
          </div>
          <span
            className="text-[11px] font-medium hidden sm:block"
            style={{ color: "rgba(255,255,255,0.40)", borderLeft: "1px solid rgba(255,255,255,0.18)", paddingLeft: 10, letterSpacing: "0.04em" }}
          >
            IT Portal
          </span>
        </div>

        {/* Center — Nav links */}
        <nav className="flex items-center gap-1">
          {NAV_ITEMS.map((item) => {
            const isActive = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                prefetch={false}
                className="flex items-center gap-2 px-4 py-1.5 rounded-lg text-sm font-medium transition-all duration-150"
                style={{
                  color: isActive ? "#fff" : "rgba(255,255,255,0.60)",
                  background: isActive ? "rgba(255,255,255,0.10)" : "transparent",
                  borderBottom: isActive ? "2px solid var(--color-accent)" : "2px solid transparent",
                  fontWeight: isActive ? 600 : 400,
                }}
              >
                {item.icon}
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* Right — User menu */}
        <div className="relative shrink-0" ref={dropdownRef}>
          <button
            onClick={() => setDropdownOpen((v) => !v)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg transition-all duration-150"
            style={{ color: "rgba(255,255,255,0.75)", background: dropdownOpen ? "rgba(255,255,255,0.08)" : "transparent" }}
          >
            <span
              className="flex items-center justify-center rounded-full text-xs font-bold"
              style={{ width: 28, height: 28, background: "var(--color-accent)", color: "#fff" }}
            >
              {initials}
            </span>
            <span className="text-sm hidden sm:block max-w-[140px] truncate">{displayName}</span>
            <ChevronDown size={14} style={{ opacity: 0.6 }} />
          </button>

          {dropdownOpen && (
            <div
              className="absolute right-0 mt-2 w-56 rounded-xl overflow-hidden"
              style={{ background: "#fff", boxShadow: "var(--shadow-lg)", border: "1px solid var(--color-border)" }}
            >
              <div className="px-4 py-3" style={{ borderBottom: "1px solid var(--color-border)" }}>
                <p className="text-xs" style={{ color: "var(--color-text-subtle)" }}>Signed in as</p>
                <p className="text-sm font-semibold truncate" style={{ color: "var(--color-text)" }}>
                  {itUser?.email ?? displayName}
                </p>
              </div>

              <button
                onClick={() => { setDropdownOpen(false); logout(); }}
                className="flex items-center gap-2 w-full px-4 py-3 text-sm transition-all duration-150"
                style={{ color: "var(--color-danger)" }}
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

      {/* ── Main content ─────────────────────────────────────────────────────── */}
      <main className="flex-1 pb-8" style={{ marginTop: 56 }}>
        {children}
      </main>

    </div>
  );
}
