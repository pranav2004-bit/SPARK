"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Users, Briefcase, LogOut, ChevronDown, MessageSquare, Radio, BookOpen } from "lucide-react";
import { ScrollingUpdates } from "@/components/ui/ScrollingUpdates";
import { useAuth } from "@/hooks/useAuth";
import { useState, useRef, useEffect } from "react";

interface NavItem {
  href: string;
  label: string;
  icon: React.ReactNode;
  matchPrefix?: string;
  altMatchPrefix?: string;  // secondary path that also keeps this item active
}

const NAV_ITEMS: NavItem[] = [
  {
    href: "/admin/batch",
    label: "Batches",
    icon: <LayoutDashboard size={15} />,
    matchPrefix: "/admin/batch",
  },
  {
    href: "/admin/students",
    label: "Students",
    icon: <Users size={15} />,
    matchPrefix: "/admin/students",
  },
  {
    href: "/admin/resources",
    label: "Resources",
    icon: <Briefcase size={15} />,
    matchPrefix: "/admin/resources",
    altMatchPrefix: "/admin/companies",  // stays active when managing a company
  },
  {
    href: "/admin/inquiries",
    label: "Inquiries",
    icon: <MessageSquare size={15} />,
    matchPrefix: "/admin/inquiries",
  },
  {
    href: "/admin/practice",
    label: "Practice",
    icon: <BookOpen size={15} />,
    matchPrefix: "/admin/practice",
  },
  {
    href: "/admin/scroll",
    label: "Scrollbar",
    icon: <Radio size={15} />,
    matchPrefix: "/admin/scroll",
  },
];

export function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const userEmail = "email" in (user ?? {}) ? (user as { email: string }).email : "Admin";
  const initials = userEmail.charAt(0).toUpperCase();

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

  return (
    <div className="flex flex-col min-h-screen">

      {/* ── Top Header ─────────────────────────────────────────────────────────── */}
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
            <Image
              src="/institution-logo.svg"
              alt="Institution"
              width={0}
              height={0}
              style={{ height: 52, width: "auto" }}
              priority
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
              priority
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
            Admin Portal
          </span>
        </div>

        {/* Center — Nav links */}
        <nav className="flex items-center gap-1">
          {NAV_ITEMS.map((item) => {
            const isActive =
              pathname.startsWith(item.matchPrefix ?? item.href) ||
              (item.altMatchPrefix ? pathname.startsWith(item.altMatchPrefix) : false);
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
            style={{
              color: "rgba(255,255,255,0.75)",
              background: dropdownOpen ? "rgba(255,255,255,0.08)" : "transparent",
            }}
          >
            {/* Avatar */}
            <span
              className="flex items-center justify-center rounded-full text-xs font-bold"
              style={{
                width: 28,
                height: 28,
                background: "var(--color-accent)",
                color: "#fff",
              }}
            >
              {initials}
            </span>
            <span className="text-sm hidden sm:block max-w-[140px] truncate">
              {userEmail}
            </span>
            <ChevronDown size={14} style={{ opacity: 0.6 }} />
          </button>

          {/* Dropdown */}
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
                  {userEmail}
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

      {/* ── Main content ───────────────────────────────────────────────────────── */}
      <main className="flex-1 pb-8" style={{ marginTop: 56 }}>
        {/* Announcement strip — sticky below fixed 56px header */}
        <ScrollingUpdates context="admin" stickyTop={56} />
        {children}
      </main>

    </div>
  );
}
