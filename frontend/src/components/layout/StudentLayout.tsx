"use client";

import { useState, useEffect, useRef, useContext, createContext } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import {
  Home, Briefcase, BookOpen, ClipboardList, Trophy,
  LogOut, ChevronDown, UserCircle2, MessageSquare, DoorOpen, Menu, X,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { usePortalGuard } from "@/hooks/usePortalGuard";
import { ScrollingUpdates } from "@/components/ui/ScrollingUpdates";
import type { StudentUser } from "@/types";

// Mobile/tablet exam hamburger (added 2026-08-31) — StudentLayout owns the
// open/closed state and the hamburger button itself, but the *content* of
// what it opens belongs to the exam page (Sections nav, Question-numbers
// grid, etc.), rendered inline just above the active question rather than
// as a floating overlay from the header. This context is how the two sides
// coordinate without StudentLayout needing to know what that content is.
const ExamMobileMenuContext = createContext<{ open: boolean; setOpen: (open: boolean) => void } | null>(null);
export function useExamMobileMenu() {
  const ctx = useContext(ExamMobileMenuContext);
  if (!ctx) throw new Error("useExamMobileMenu must be called from within a StudentLayout with examMode on");
  return ctx;
}

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
  examMode = false,
  examCenterContent,
  examRightContent,
  onExitExam,
}: {
  children: React.ReactNode;
  hideNav?: boolean;
  /** Distraction-free header for a live/pending exam (added 2026-08-28):
   * no promo ticker, no nav links (desktop or mobile), the logo lockup
   * swaps for a non-clickable text wordmark (a clickable logo would let a
   * student bypass the Exit Test confirm entirely), and the header's
   * center/right cells swap from nav+account-menu to caller-supplied
   * content (e.g. the exam countdown) and an explicit "Exit Test" button.
   * Implies hideNav. */
  examMode?: boolean;
  /** Rendered in the header's center cell while examMode is on — e.g. the
   * live countdown on the active exam screen. Left empty on screens with
   * nothing to time yet (briefing, resume, error, finished). Desktop
   * (lg:) grid only — the mobile header is just a hamburger; the page
   * renders its own copy of this content inline, above the question, via
   * useExamMobileMenu(). */
  examCenterContent?: React.ReactNode;
  /** Rendered in the header's right cell while examMode is on, immediately
   * before the "Exit Test" button (added 2026-08-31) — e.g. "Submit Exam".
   * Grouped with Exit Test since both are session-ending actions, kept
   * apart from examCenterContent's purely informational countdown.
   * Desktop (lg:) grid only — see examCenterContent's note on mobile. */
  examRightContent?: React.ReactNode;
  /** Required in practice whenever examMode is on — falls back to
   * navigating to the assessments list if the caller omits it, so a
   * missed prop never leaves the button dead. */
  onExitExam?: () => void;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();
  usePortalGuard("student");
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);
  const [examMobileMenuOpen, setExamMobileMenuOpen] = useState(false);

  const studentUser = user as StudentUser | null;
  const compactNav = hideNav || examMode;
  const handleExitExam = onExitExam ?? (() => router.push("/students/assessments"));

  // Close menu on route change
  useEffect(() => {
    setUserMenuOpen(false);
    setExamMobileMenuOpen(false);
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
    <ExamMobileMenuContext.Provider value={{ open: examMobileMenuOpen, setOpen: setExamMobileMenuOpen }}>
    <div className="min-h-screen bg-[var(--color-surface-secondary)]">

      {/* ── Top Navbar ───────────────────────────────────────────────────────── */}
      <header
        className="fixed top-0 inset-x-0 z-40 h-14 bg-white backdrop-blur-md border-b border-[var(--color-border)]"
        style={{ boxShadow: "0 1px 0 0 var(--color-border), 0 2px 20px rgba(26, 49, 80, 0.05)" }}
      >
        <div
          className={[
            "w-full h-full px-4 sm:px-6 lg:px-8 grid-cols-[auto_1fr_auto] items-center gap-3 sm:gap-5",
            // Non-exam pages keep the original single-row grid at every
            // width (untouched, not part of this fix). Exam mode swaps to
            // the new two-row mobile layout below lg, then back to this
            // exact same grid at lg — desktop is byte-for-byte the same
            // markup either way.
            examMode ? "hidden lg:grid" : "grid",
          ].join(" ")}
        >

          {/* Logo group — a text wordmark in exam mode, not the clickable
              logo lockup: a Link out of this screen would let a student
              leave (and re-enter, restarting the briefing) without ever
              going through the Exit Test confirm. */}
          {examMode ? (
            <div className="shrink-0 select-none leading-tight">
              <p className="text-sm font-bold" style={{ color: "var(--color-text)" }}>
                SPARK Proctored <span style={{ color: "var(--color-text-subtle)", fontWeight: 600 }}>v1.0.0</span>
              </p>
              <p className="text-[10px] font-semibold uppercase tracking-wider flex items-center gap-1.5" style={{ color: "var(--color-text-subtle)" }}>
                <span className="relative group inline-flex items-center justify-center shrink-0 w-3 h-3">
                  <span
                    className="absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-40 animate-ping"
                    style={{ animationDuration: "2.5s" }}
                    aria-hidden="true"
                  />
                  <span className="relative w-1.5 h-1.5 rounded-full bg-red-500" aria-hidden="true" />
                  <span
                    role="tooltip"
                    className="pointer-events-none absolute left-0 top-full mt-2 w-max max-w-[200px] px-2.5 py-1.5 rounded-[var(--radius-md)] text-[11px] font-medium normal-case tracking-normal leading-snug opacity-0 group-hover:opacity-100 transition-opacity duration-150 z-50"
                    style={{ background: "#111827", color: "#fff" }}
                  >
                    Your activity is being monitored for exam integrity
                  </span>
                </span>
                Examination Mode
              </p>
            </div>
          ) : (
            <Link href="/students/home" className="shrink-0 select-none flex items-center gap-2 sm:gap-2.5">
              <Image
                src="/institution-logo.png"
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
          )}

          {/* Exam mode — caller-supplied center content (the live
              countdown, when there is one), no nav */}
          {examMode && (
            <div className="flex items-center justify-center">
              {examCenterContent}
            </div>
          )}

          {/* Desktop center nav */}
          {!compactNav && (
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

          {/* Exam mode — exit button (+ caller-supplied actions like
              Submit Exam), no account menu */}
          {examMode ? (
            <div className="flex items-center justify-end gap-2">
              {examRightContent}
              <button
                onClick={handleExitExam}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-md)] text-sm font-medium border transition-colors cursor-pointer"
                style={{ color: "var(--color-danger)", borderColor: "var(--color-danger)" }}
                onMouseEnter={e => { e.currentTarget.style.background = "var(--color-danger-bg)"; }}
                onMouseLeave={e => { e.currentTarget.style.background = "transparent"; }}
              >
                <DoorOpen size={15} />
                <span className="hidden sm:inline">Exit Test</span>
              </button>
            </div>
          ) : (
          /* User menu — desktop + mobile avatar */
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
          )}

        </div>

        {/* Exam mode, mobile/tablet only — the single h-14 grid row above
            can't fit wordmark + timer + Submit Exam + Exit Test without
            wrapping/overlapping below lg. The timer stays visible here
            (always-relevant, unlike the rest); Submit Exam, Exit Test,
            Sections nav, and the Question-numbers grid go behind a
            hamburger instead — opened/closed here, but rendered by the
            exam page itself inline, just above the active question rather
            than as a floating overlay from the header (2026-08-31,
            explicit request — see useExamMobileMenu()). Swaps back to the
            unchanged grid above at lg. */}
        {examMode && (
          <div className="lg:hidden w-full h-full px-4 flex items-center justify-between gap-2">
            <div className="shrink-0 select-none leading-tight min-w-0">
              <p className="text-sm font-bold truncate" style={{ color: "var(--color-text)" }}>
                SPARK Proctored <span style={{ color: "var(--color-text-subtle)", fontWeight: 600 }}>v1.0.0</span>
              </p>
              <p className="text-[10px] font-semibold uppercase tracking-wider flex items-center gap-1.5" style={{ color: "var(--color-text-subtle)" }}>
                <span className="relative inline-flex items-center justify-center shrink-0 w-3 h-3">
                  <span
                    className="absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-40 animate-ping"
                    style={{ animationDuration: "2.5s" }}
                    aria-hidden="true"
                  />
                  <span className="relative w-1.5 h-1.5 rounded-full bg-red-500" aria-hidden="true" />
                </span>
                Examination Mode
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {examCenterContent}
              <button
                onClick={() => setExamMobileMenuOpen(v => !v)}
                aria-label={examMobileMenuOpen ? "Close exam menu" : "Open exam menu"}
                aria-expanded={examMobileMenuOpen}
                className="shrink-0 w-9 h-9 rounded-[var(--radius-md)] flex items-center justify-center border cursor-pointer"
                style={{ borderColor: "var(--color-border)", background: examMobileMenuOpen ? "var(--color-surface-hover)" : "#fff" }}
              >
                {examMobileMenuOpen ? <X size={18} /> : <Menu size={18} />}
              </button>
            </div>
          </div>
        )}
      </header>

      {/* ── Mobile Bottom Navigation ─────────────────────────────────────────── */}
      {!compactNav && (
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
          !compactNav ? "pb-24 md:pb-8" : "pb-8",
        ].join(" ")}
      >
        {/* Scrolling updates bar — sticky below fixed header, in document flow.
            Skipped in exam mode: external promo links have no place in a
            monitored, distraction-free exam screen. */}
        {!examMode && <ScrollingUpdates context="student" stickyTop={56} />}
        {children}
      </main>

    </div>
    </ExamMobileMenuContext.Provider>
  );
}
