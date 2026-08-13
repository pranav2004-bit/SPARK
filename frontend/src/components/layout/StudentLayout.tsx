"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import {
  Home, Briefcase, BookOpen, ClipboardList, Trophy,
  LogOut, ChevronDown, UserCircle2, MessageSquare,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { ScrollingUpdates } from "@/components/ui/ScrollingUpdates";
import type { StudentUser } from "@/types";

const NAV_ITEMS = [
  {
    href: "/students/home",
    label: "Home",
    mobileLabel: "Home",
    icon: Home,
    match: "/students/home",
    comingSoon: false,
  },
  {
    href: "/students/resources",
    label: "Resources",
    mobileLabel: "Resources",
    icon: Briefcase,
    match: "/students/resources",
    altMatch: "/students/companies",   // stays active when browsing a company
    comingSoon: false,
  },
  {
    href: "/students/practice",
    label: "Practice",
    mobileLabel: "Practice",
    icon: BookOpen,
    match: "/students/practice",
    comingSoon: false,
  },
  {
    href: "/students/assessments",
    label: "Assessments",
    mobileLabel: "Assessments",
    icon: ClipboardList,
    match: "/students/assessments",
    comingSoon: false,
  },
  {
    href: "/students/contests",
    label: "Contests",
    mobileLabel: "Contests",
    icon: Trophy,
    match: "/students/contests",
    comingSoon: true,
  },
];

export function StudentLayout({
  children,
  hideNav = false,
}: {
  children: React.ReactNode;
  hideNav?: boolean;
}) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);

  const studentUser = user as StudentUser | null;

  // Close menu on route change
  useEffect(() => {
    setUserMenuOpen(false);
  }, [pathname]);

  // Close menu on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false);
      }
    }
    if (userMenuOpen) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [userMenuOpen]);

  return (
    <div className="min-h-screen bg-[var(--color-surface-secondary)]">

      {/* ── Top Navbar ───────────────────────────────────────────────────────── */}
      <header
        className="fixed top-0 inset-x-0 z-40 h-14 bg-white/[0.97] backdrop-blur-md border-b border-[var(--color-border)]"
        style={{ boxShadow: "0 1px 0 0 var(--color-border), 0 2px 20px rgba(26, 49, 80, 0.05)" }}
      >
        <div className="w-full h-full px-4 sm:px-6 lg:px-8 grid grid-cols-[auto_1fr_auto] items-center gap-3 sm:gap-5">

          {/* Logo group */}
          <Link href="/students/home" className="shrink-0 select-none flex items-center gap-2 sm:gap-2.5">
            <Image
              src="/institution-logo.svg"
              alt="Institution"
              width={0}
              height={0}
              className="h-[38px] sm:h-[44px] w-auto"
            />
            <div className="w-px h-7 sm:h-8 bg-[var(--color-border)]" />
            <Image
              src="/spark-logo.svg"
              alt="SPARK"
              width={0}
              height={0}
              className="h-[26px] sm:h-[30px] w-auto"
            />
          </Link>

          {/* Desktop center nav */}
          {!hideNav && (
            <nav className="hidden md:flex items-center justify-center gap-0.5">
              {NAV_ITEMS.map(({ href, label, match, altMatch, icon: Icon, comingSoon }) => {
                const isActive =
                  match === "/students/home"
                    ? pathname === match
                    : pathname.startsWith(match) || (altMatch ? pathname.startsWith(altMatch) : false);
                return (
                  <Link
                    key={href}
                    href={href}
                    className={[
                      "relative flex items-center gap-1.5 px-3.5 py-2 rounded-[var(--radius-md)] text-sm font-medium transition-all duration-150",
                      isActive
                        ? "text-[var(--color-accent)] bg-[var(--color-accent-light)]"
                        : "text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-hover)]",
                    ].join(" ")}
                  >
                    {label}
                    {comingSoon && (
                      <span className="text-[9px] font-bold px-1 py-0.5 rounded bg-[var(--color-primary-light)] text-[var(--color-primary)] leading-none tracking-wide">
                        v2
                      </span>
                    )}
                    {isActive && (
                      <span className="absolute bottom-0 left-1/2 -translate-x-1/2 w-4 h-0.5 rounded-full bg-[var(--color-accent)]" />
                    )}
                  </Link>
                );
              })}
              {/* Contact Us — desktop nav only (mobile: profile dropdown) */}
              {(() => {
                const isActive = pathname.startsWith("/students/contact");
                return (
                  <Link
                    href="/students/contact"
                    className={[
                      "relative flex items-center gap-1.5 px-3.5 py-2 rounded-[var(--radius-md)] text-sm font-medium transition-all duration-150",
                      isActive
                        ? "text-[var(--color-accent)] bg-[var(--color-accent-light)]"
                        : "text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-hover)]",
                    ].join(" ")}
                  >
                    Contact Us
                    {isActive && (
                      <span className="absolute bottom-0 left-1/2 -translate-x-1/2 w-4 h-0.5 rounded-full bg-[var(--color-accent)]" />
                    )}
                  </Link>
                );
              })()}
            </nav>
          )}

          {/* User menu — desktop + mobile avatar */}
          <div className="flex items-center justify-end" ref={userMenuRef}>
            <div className="relative">

              {/* Desktop: avatar + name + chevron */}
              <button
                onClick={() => setUserMenuOpen((v) => !v)}
                className="hidden md:flex items-center gap-2.5 px-3 py-2 rounded-[var(--radius-md)] hover:bg-[var(--color-surface-hover)] transition-colors"
              >
                <div className="w-7 h-7 rounded-full bg-[var(--color-accent)] flex items-center justify-center shrink-0">
                  <span className="text-white text-xs font-semibold">
                    {(studentUser?.fullname?.[0] ?? studentUser?.student_id?.[0])?.toUpperCase() ?? "S"}
                  </span>
                </div>
                <span
                  className="text-sm font-medium text-[var(--color-text)] max-w-[140px] truncate"
                  title={studentUser?.student_id}
                >
                  {studentUser?.student_id ?? "Student"}
                </span>
                <ChevronDown
                  size={14}
                  className={[
                    "text-[var(--color-text-muted)] transition-transform duration-150",
                    userMenuOpen ? "rotate-180" : "",
                  ].join(" ")}
                />
              </button>

              {/* Mobile: avatar only */}
              <button
                onClick={() => setUserMenuOpen((v) => !v)}
                aria-label="Account menu"
                className="md:hidden w-8 h-8 rounded-full bg-[var(--color-accent)] flex items-center justify-center transition-opacity active:opacity-70"
              >
                <span className="text-white text-xs font-semibold">
                  {(studentUser?.fullname?.[0] ?? studentUser?.student_id?.[0])?.toUpperCase() ?? "S"}
                </span>
              </button>

              {/* Shared dropdown */}
              {userMenuOpen && (
                <div className="absolute right-0 top-full mt-2 w-56 bg-white border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden z-50"
                  style={{ boxShadow: "0 8px 24px -4px rgba(0,0,0,0.10), 0 2px 8px -2px rgba(0,0,0,0.06)" }}
                >
                  {/* Identity header */}
                  <div className="px-4 py-3.5 border-b border-[var(--color-border)]">
                    <p className="text-[11px] font-medium text-[var(--color-text-subtle)] uppercase tracking-wider mb-1.5">
                      Signed in as
                    </p>
                    {studentUser?.fullname ? (
                      <>
                        <p className="text-sm font-semibold text-[var(--color-text)] truncate leading-snug">
                          {studentUser.fullname}
                        </p>
                        <p className="text-xs text-[var(--color-text-muted)] truncate mt-0.5">
                          {studentUser.student_id}
                        </p>
                      </>
                    ) : (
                      <p className="text-sm font-semibold text-[var(--color-text)] truncate">
                        {studentUser?.student_id ?? "Student"}
                      </p>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="py-1">
                    <Link
                      href="/students/my_profile"
                      onClick={() => setUserMenuOpen(false)}
                      className="flex items-center gap-2.5 px-4 py-2.5 text-sm text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)] transition-colors"
                    >
                      <UserCircle2 size={15} className="shrink-0" />
                      My Profile
                    </Link>
                    <Link
                      href="/students/contact"
                      onClick={() => setUserMenuOpen(false)}
                      className="flex items-center gap-2.5 px-4 py-2.5 text-sm text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)] transition-colors md:hidden"
                    >
                      <MessageSquare size={15} className="shrink-0" />
                      Contact Us
                    </Link>
                  </div>

                  {/* Divider */}
                  <div className="border-t border-[var(--color-border)]" />

                  {/* Destructive */}
                  <div className="py-1">
                    <button
                      onClick={() => { setUserMenuOpen(false); logout(); }}
                      className="flex items-center gap-2.5 px-4 py-2.5 w-full text-sm text-[var(--color-danger)] hover:bg-[var(--color-danger-bg)] transition-colors"
                    >
                      <LogOut size={15} className="shrink-0" />
                      Sign out
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

        </div>
      </header>

      {/* ── Mobile Bottom Navigation ─────────────────────────────────────────── */}
      {!hideNav && (
        <nav
          className="md:hidden fixed bottom-0 inset-x-0 z-40 bg-white border-t border-[var(--color-border)]"
          style={{
            boxShadow: "0 -1px 0 0 var(--color-border)",
            paddingBottom: "env(safe-area-inset-bottom)",
          }}
        >
          <div className="flex h-16">
            {NAV_ITEMS.map(({ href, mobileLabel, icon: Icon, match, altMatch }) => {
              const isActive =
                match === "/students/home"
                  ? pathname === match
                  : pathname.startsWith(match) || (altMatch ? pathname.startsWith(altMatch) : false);
              return (
                <Link
                  key={href}
                  href={href}
                  className={[
                    "flex flex-col items-center justify-center flex-1 gap-0.5 relative select-none",
                    "transition-colors duration-200",
                    isActive
                      ? "text-[var(--color-accent)]"
                      : "text-[var(--color-text-subtle)]",
                  ].join(" ")}
                >
                  {/* Active top pill */}
                  <span
                    className="absolute top-0 left-1/2 -translate-x-1/2 h-0.5 rounded-full bg-[var(--color-accent)] transition-all duration-300 ease-out"
                    style={{ width: isActive ? "2rem" : "0" }}
                  />

                  {/* Icon with bg capsule */}
                  <div
                    className="flex items-center justify-center w-10 h-[26px] rounded-full transition-colors duration-200"
                    style={{
                      background: isActive ? "#fde8c4" : "transparent",
                    }}
                  >
                    <Icon size={18} strokeWidth={isActive ? 2.5 : 1.75} />
                  </div>

                  {/* Label */}
                  <span className="text-[10px] font-medium leading-none tracking-wide">
                    {mobileLabel}
                  </span>
                </Link>
              );
            })}
          </div>
        </nav>
      )}

      {/* ── Main Content ─────────────────────────────────────────────────────── */}
      <main
        className={[
          "pt-14 min-h-[calc(100vh-56px)]",
          !hideNav ? "pb-24 md:pb-8" : "pb-8",
        ].join(" ")}
      >
        {/* Scrolling updates bar — sticky below fixed header, in document flow */}
        <ScrollingUpdates context="student" stickyTop={56} />
        {children}
      </main>

    </div>
  );
}
