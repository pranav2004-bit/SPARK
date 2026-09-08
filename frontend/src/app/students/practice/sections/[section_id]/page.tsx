"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ListChecks, AlignLeft, ChevronRight, ChevronLeft, Search } from "lucide-react";
import { StudentLayout } from "@/components/layout/StudentLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { LoadingSpinner } from "@/components/ui/Skeleton";
import { GlobalLoader } from "@/components/ui/GlobalLoader";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { PracticeModule, PracticeSection, PracticeQuestion, ProgressStatus } from "@/types";

// ── Design tokens ─────────────────────────────────────────────────────────────
const T = {
  text:    "var(--color-text)",
  muted:   "var(--color-text-muted)",
  subtle:  "var(--color-text-subtle)",
  border:  "var(--color-border)",
  surface: "var(--color-surface-secondary)",
  white:   "#ffffff",
};

// ── Progress colour palette ───────────────────────────────────────────────────
const PROGRESS_STYLE: Record<ProgressStatus, {
  bg: string; color: string; border: string; label: string; dot: string;
}> = {
  not_visited: { bg: "#F1F5F9", color: "#64748B", border: "#CBD5E1", label: "Not Visited", dot: "#94A3B8" },
  visited:     { bg: "#FEF3C7", color: "#D97706", border: "#FDE68A", label: "Visited",     dot: "#FBBF24" },
  attempted:   { bg: "#FFF7ED", color: "#EA580C", border: "#FED7AA", label: "Attempted",   dot: "#FB923C" },
  completed:   { bg: "#DCFCE7", color: "#16A34A", border: "#BBF7D0", label: "Completed",   dot: "#4ADE80" },
};

// ── Types ─────────────────────────────────────────────────────────────────────
interface QuestionWithProgress extends PracticeQuestion {
  progress_status: ProgressStatus;
}

interface SectionDetailData {
  section:   PracticeSection;
  module:    PracticeModule | null;
  questions: QuestionWithProgress[];
}

// ── Legend pill ───────────────────────────────────────────────────────────────
function LegendPill({ status, count }: { status: ProgressStatus; count: number }) {
  const s = PROGRESS_STYLE[status];
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold"
      style={{ background: s.bg, color: s.color, border: `1px solid ${s.border}` }}
    >
      <span className="w-2 h-2 rounded-full shrink-0" style={{ background: s.dot }} />
      {count} {s.label}
    </span>
  );
}

// ── Responsive page size ──────────────────────────────────────────────────────
// Mobile  (< 768px) : 40  — 4-column grid × 10 complete rows.
// Desktop (≥ 768px) : 100 — 10-column grid × 10 complete rows.
// Pagination controls are hidden entirely when totalQuestions ≤ pageSize,
// so short sections (current reality: ≤ 40 questions) show no pagination UI.
const PAGE_SIZE_MOBILE  = 40;
const PAGE_SIZE_DESKTOP = 100;

function usePageSize(): number {
  const [size, setSize] = useState<number>(() =>
    typeof window !== "undefined" && window.innerWidth >= 768
      ? PAGE_SIZE_DESKTOP
      : PAGE_SIZE_MOBILE,
  );
  useEffect(() => {
    function update() {
      setSize(window.innerWidth >= 768 ? PAGE_SIZE_DESKTOP : PAGE_SIZE_MOBILE);
    }
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);
  return size;
}

// ── Page-number array builder ─────────────────────────────────────────────────
// Returns at most 7 slots: page numbers and "…" ellipsis markers.
// Pattern examples (total = 10):
//   current = 1  →  [1, 2, 3, 4, 5, …, 10]
//   current = 5  →  [1, …, 4, 5, 6, …, 10]
//   current = 9  →  [1, …, 6, 7, 8, 9, 10]
function buildPageNumbers(current: number, total: number): (number | "…")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  if (current <= 4)         return [1, 2, 3, 4, 5, "…", total];
  if (current >= total - 3) return [1, "…", total - 4, total - 3, total - 2, total - 1, total];
  return [1, "…", current - 1, current, current + 1, "…", total];
}

// ── Pagination controls ───────────────────────────────────────────────────────
// Rendered below the question grid only when totalPages > 1.
// Prev / Next + numbered page buttons with ellipsis collapse.
// Fully accessible: role="navigation", aria-label, aria-current="page".
function PaginationControls({
  currentPage,
  totalPages,
  onPageChange,
}: {
  currentPage:  number;
  totalPages:   number;
  onPageChange: (page: number) => void;
}) {
  if (totalPages <= 1) return null;

  const pages = buildPageNumbers(currentPage, totalPages);

  const base: React.CSSProperties = {
    background: T.white,
    border:     `1px solid var(--color-border)`,
    color:      T.muted,
  };
  const active: React.CSSProperties = {
    background: "var(--color-accent)",
    border:     "1px solid transparent",
    color:      "#ffffff",
  };

  return (
    <nav
      role="navigation"
      aria-label="Question pagination"
      className="flex items-center justify-center gap-1 mt-4 flex-wrap"
    >
      {/* Previous */}
      <button
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage === 1}
        aria-label="Previous page"
        className="flex items-center justify-center w-9 h-9 rounded-[var(--radius-md)] text-sm font-medium transition-all duration-150 disabled:opacity-30 disabled:cursor-not-allowed"
        style={base}
        onMouseEnter={e => {
          if (currentPage !== 1) {
            e.currentTarget.style.borderColor = "var(--color-accent)";
            e.currentTarget.style.color = "var(--color-accent)";
          }
        }}
        onMouseLeave={e => {
          e.currentTarget.style.borderColor = "var(--color-border)";
          e.currentTarget.style.color = T.muted;
        }}
      >
        <ChevronLeft size={15} />
      </button>

      {/* Page numbers + ellipsis */}
      {pages.map((p, i) =>
        p === "…" ? (
          <span
            key={`ellipsis-${i}`}
            className="flex items-center justify-center w-9 h-9 text-sm select-none"
            style={{ color: T.subtle }}
          >
            …
          </span>
        ) : (
          <button
            key={p}
            onClick={() => onPageChange(p as number)}
            aria-label={`Page ${p}`}
            aria-current={p === currentPage ? "page" : undefined}
            className="flex items-center justify-center w-9 h-9 rounded-[var(--radius-md)] text-sm font-medium transition-all duration-150"
            style={p === currentPage ? active : base}
            onMouseEnter={e => {
              if (p !== currentPage) {
                e.currentTarget.style.borderColor = "var(--color-accent)";
                e.currentTarget.style.color = "var(--color-accent)";
              }
            }}
            onMouseLeave={e => {
              if (p !== currentPage) {
                e.currentTarget.style.borderColor = "var(--color-border)";
                e.currentTarget.style.color = T.muted;
              }
            }}
          >
            {p}
          </button>
        ),
      )}

      {/* Next */}
      <button
        onClick={() => onPageChange(currentPage + 1)}
        disabled={currentPage === totalPages}
        aria-label="Next page"
        className="flex items-center justify-center w-9 h-9 rounded-[var(--radius-md)] text-sm font-medium transition-all duration-150 disabled:opacity-30 disabled:cursor-not-allowed"
        style={base}
        onMouseEnter={e => {
          if (currentPage !== totalPages) {
            e.currentTarget.style.borderColor = "var(--color-accent)";
            e.currentTarget.style.color = "var(--color-accent)";
          }
        }}
        onMouseLeave={e => {
          e.currentTarget.style.borderColor = "var(--color-border)";
          e.currentTarget.style.color = T.muted;
        }}
      >
        <ChevronRight size={15} />
      </button>
    </nav>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function StudentPracticeSectionPage() {
  const { section_id } = useParams<{ section_id: string }>();
  const router         = useRouter();
  const { error: toastError } = useToast();

  // ── Core state ─────────────────────────────────────────────────────────────
  const [detail,            setDetail]            = useState<SectionDetailData | null>(null);
  const [loading,           setLoading]           = useState(true);
  const [search,            setSearch]            = useState("");
  const [typeFilter,        setTypeFilter]        = useState<"all" | "mcq" | "fib">("all");
  const [ancestors,         setAncestors]         = useState<PracticeModule[]>([]);
  const [navigatingTo,      setNavigatingTo]      = useState<string | null>(null);
  const [breadcrumbLoading, setBreadcrumbLoading] = useState(false);

  // ── Pagination state ────────────────────────────────────────────────────────
  // pageSize comes from a responsive hook — 40 on mobile, 100 on desktop.
  // currentPage starts at 1 and is reset any time the visible result set changes.
  const pageSize    = usePageSize();
  const [currentPage, setCurrentPage] = useState(1);

  // Ref for scroll-to-grid on page change — attached to the outer grid wrapper.
  const gridRef = useRef<HTMLDivElement>(null);

  // ── Navigation helpers ──────────────────────────────────────────────────────
  const goTo = (path: string, id: string) => { setNavigatingTo(id); router.push(path); };
  const navTo = (path: string)            => { setBreadcrumbLoading(true); router.push(path); };

  // Tracks last successful fetch timestamp for stale-data detection.
  const lastFetchAt = useRef<number>(0);
  const STALE_MS    = 30_000;

  // ── Ancestor chain builder ──────────────────────────────────────────────────
  // Walks parent IDs up the module tree to populate the breadcrumb.
  const buildAncestors = async (leaf: PracticeModule) => {
    const chain: PracticeModule[] = [leaf];
    let node = leaf;
    while (node.parent) {
      try {
        const res = await api.get(`/practice/student/modules/${node.parent}/`);
        const parent = res.data.data?.module as PracticeModule | undefined;
        if (!parent) break;
        chain.unshift(parent);
        node = parent;
      } catch { break; }
    }
    setAncestors(chain);
  };

  // ── Fetch ───────────────────────────────────────────────────────────────────
  const fetchSection = (silent = false) => {
    if (!silent) setLoading(true);
    api.get(`/practice/student/sections/${section_id}/`)
      .then(res => {
        const data = res.data.data as SectionDetailData;
        setDetail(data);
        lastFetchAt.current = Date.now();
        if (data.module) buildAncestors(data.module);
        else setAncestors([]);
      })
      .catch(err => {
        if (!silent) {
          toastError(getErrorMessage(err));
          router.push("/students/practice");
        }
      })
      .finally(() => { if (!silent) setLoading(false); });
  };

  // Initial load
  useEffect(() => {
    fetchSection();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [section_id]);

  // bfcache restore (browser back button)
  useEffect(() => {
    const onPageShow = (e: PageTransitionEvent) => { if (e.persisted) fetchSection(); };
    window.addEventListener("pageshow", onPageShow);
    return () => window.removeEventListener("pageshow", onPageShow);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [section_id]);

  // Silent refetch on tab re-focus when data is stale
  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === "visible" && Date.now() - lastFetchAt.current > STALE_MS) {
        fetchSection(true);
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [section_id]);

  // ── Pagination reset ────────────────────────────────────────────────────────
  // Reset to page 1 whenever the result set changes or the page size changes.
  // Prevents the user landing on a now-empty or out-of-range page.
  // Handles:  search change, type filter change, viewport resize (40↔100).
  useEffect(() => { setCurrentPage(1); }, [search, typeFilter, pageSize]);

  // ── Early return ────────────────────────────────────────────────────────────
  if (loading) return <GlobalLoader />;

  // ── Derived data ────────────────────────────────────────────────────────────
  const section      = detail?.section;
  const allQuestions = (detail?.questions ?? []) as QuestionWithProgress[];

  const filteredQuestions = allQuestions.filter(q => {
    const matchesType   = typeFilter === "all" || q.question_type === typeFilter;
    const matchesSearch = search.trim() === "" || String(q.question_number).startsWith(search.trim());
    return matchesType && matchesSearch;
  });

  const counts = {
    completed:   allQuestions.filter(q => q.progress_status === "completed").length,
    attempted:   allQuestions.filter(q => q.progress_status === "attempted").length,
    visited:     allQuestions.filter(q => q.progress_status === "visited").length,
    not_visited: allQuestions.filter(q => q.progress_status === "not_visited").length,
  };

  const mcqCount     = allQuestions.filter(q => q.question_type === "mcq").length;
  const fibCount     = allQuestions.filter(q => q.question_type !== "mcq").length;
  const completionPct = allQuestions.length > 0
    ? Math.round((counts.completed / allQuestions.length) * 100)
    : 0;

  // ── Pagination derived values ───────────────────────────────────────────────
  // totalPages is at least 1 to avoid division-by-zero in safePage calculation.
  const totalPages = Math.max(1, Math.ceil(filteredQuestions.length / pageSize));

  // safePage clamps currentPage against the live totalPages.
  // Guards the edge case where a silent background refetch removes questions,
  // shrinking totalPages below currentPage without triggering a filter change.
  const safePage = Math.max(1, Math.min(currentPage, totalPages));

  const paginatedQuestions = filteredQuestions.slice(
    (safePage - 1) * pageSize,
    safePage * pageSize,
  );

  // showPagination: only render controls when more than one page exists.
  // At ≤ 40 questions (mobile) or ≤ 100 (desktop) the UI is pagination-free.
  const showPagination = filteredQuestions.length > pageSize;

  // Page change: clamp to valid range, update state, smooth-scroll to grid.
  // The scroll offset (72px) clears the fixed header + scrolling bar.
  function handlePageChange(page: number) {
    const clamped = Math.max(1, Math.min(page, totalPages));
    setCurrentPage(clamped);
    if (gridRef.current) {
      const y = gridRef.current.getBoundingClientRect().top + window.scrollY - 72;
      window.scrollTo({ top: Math.max(0, y), behavior: "smooth" });
    }
  }

  return (
    <StudentLayout>
      <PageWrapper className="py-6 sm:py-8">

        {/* ── Breadcrumb ───────────────────────────────────────────────────────── */}
        <nav className="flex items-center gap-1.5 text-sm font-medium mb-5 min-w-0 flex-wrap" aria-label="Breadcrumb">

          <button
            onClick={() => navTo("/students/practice")}
            disabled={breadcrumbLoading || !!navigatingTo}
            className="shrink-0 transition-all disabled:opacity-50 disabled:cursor-wait inline-flex items-center gap-1"
            style={{ color: T.muted }}
            onMouseEnter={e => { if (!breadcrumbLoading && !navigatingTo) e.currentTarget.style.color = T.text; }}
            onMouseLeave={e => (e.currentTarget.style.color = T.muted)}
          >
            {breadcrumbLoading ? <LoadingSpinner size={12} /> : null}
            Practice
          </button>

          {ancestors.map(mod => (
            <span key={mod.id} className="flex items-center gap-1.5 min-w-0">
              <ChevronRight size={13} style={{ color: T.subtle, flexShrink: 0 }} />
              <button
                onClick={() => navTo(`/students/practice/${mod.id}`)}
                disabled={breadcrumbLoading || !!navigatingTo}
                className="truncate transition-all disabled:opacity-50 disabled:cursor-wait"
                style={{ color: T.muted }}
                onMouseEnter={e => { if (!breadcrumbLoading && !navigatingTo) e.currentTarget.style.color = T.text; }}
                onMouseLeave={e => (e.currentTarget.style.color = T.muted)}
              >
                {mod.name}
              </button>
            </span>
          ))}

          <ChevronRight size={13} style={{ color: T.subtle, flexShrink: 0 }} />
          <span className="truncate font-semibold" style={{ color: T.text }}>
            {section?.name ?? "Section"}
          </span>

        </nav>

        {/* ── Page header ─────────────────────────────────────────────────────── */}
        <div className="mb-5">
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight mb-2.5" style={{ color: T.text }}>
            {section?.name ?? "Section"}
          </h1>

          <div className="flex items-center justify-between gap-3 flex-wrap">

            {/* Type summary pills */}
            <div className="flex items-center gap-2 flex-wrap">
              <span
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold"
                style={{ background: T.surface, color: T.muted, border: `1px solid ${T.border}` }}
              >
                {allQuestions.length} {allQuestions.length === 1 ? "Question" : "Questions"}
              </span>
              {mcqCount > 0 && (
                <span
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold"
                  style={{ background: "#EFF6FF", color: "#2563EB", border: "1px solid #BFDBFE" }}
                >
                  <ListChecks size={11} />
                  {mcqCount} MCQ
                </span>
              )}
              {fibCount > 0 && (
                <span
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold"
                  style={{ background: "#FDF4FF", color: "#9333EA", border: "1px solid #E9D5FF" }}
                >
                  <AlignLeft size={11} />
                  {fibCount} FIB
                </span>
              )}
            </div>

            {/* Search + type filter */}
            {allQuestions.length > 0 && (
              <div className="flex items-center gap-2 shrink-0">
                <div className="relative w-[130px] sm:w-[180px]">
                  <Search size={13}
                    className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
                    style={{ color: T.subtle }}
                  />
                  <input
                    type="text"
                    placeholder="Search by number…"
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    className="w-full pl-8 pr-3 py-1.5 text-xs rounded-[var(--radius-md)] outline-none transition-colors"
                    style={{ background: T.white, border: `1px solid ${T.border}`, color: T.text }}
                    onFocus={e => (e.currentTarget.style.borderColor = "var(--color-accent)")}
                    onBlur={e  => (e.currentTarget.style.borderColor = T.border)}
                  />
                </div>
                <div className="flex items-center gap-1">
                  {(["all", "mcq", "fib"] as const).map(t => (
                    <button key={t} onClick={() => setTypeFilter(t)}
                      className="px-3 py-1.5 rounded-full text-xs font-semibold transition-all cursor-pointer"
                      style={typeFilter === t
                        ? { background: T.text, color: "#fff", border: "1px solid transparent" }
                        : { background: T.surface, color: T.subtle, border: `1px solid ${T.border}` }
                      }
                    >
                      {t === "all" ? "All" : t.toUpperCase()}
                    </button>
                  ))}
                </div>
              </div>
            )}

          </div>
        </div>

        {/* ── Progress summary ─────────────────────────────────────────────────── */}
        {allQuestions.length > 0 && (() => {
          const next = completionPct < 100
            ? (allQuestions.find(q => q.progress_status === "not_visited") ??
               allQuestions.find(q => q.progress_status === "attempted")   ??
               allQuestions.find(q => q.progress_status === "visited"))
            : null;
          const isResume = next ? next.progress_status !== "not_visited" : false;

          return (
            <div
              className="mb-5 rounded-[var(--radius-lg)] px-5 py-4"
              style={{ background: T.white, border: `1px solid ${T.border}` }}
            >
              <div className="flex items-center justify-between gap-3 mb-3">
                <p className="text-[13px] font-semibold" style={{ color: T.text }}>Your progress</p>
                <div className="flex items-center gap-3 shrink-0">
                  {next && (
                    <button
                      onClick={() => goTo(`/students/practice/questions/${next.id}`, next.id)}
                      disabled={!!navigatingTo || breadcrumbLoading}
                      className="inline-flex items-center gap-1.5 px-3 py-1 rounded-[var(--radius-md)] text-xs font-semibold transition-all disabled:opacity-50 disabled:cursor-wait"
                      style={{ background: "var(--color-accent)", color: "#fff" }}
                      onMouseEnter={e => { if (!navigatingTo && !breadcrumbLoading) e.currentTarget.style.opacity = "0.88"; }}
                      onMouseLeave={e => (e.currentTarget.style.opacity = "1")}
                    >
                      {navigatingTo === next.id
                        ? <><LoadingSpinner size={12} color="#fff" /> {isResume ? "Resuming…" : "Starting…"}</>
                        : (isResume ? `Resume Q${next.question_number}` : `Start Q${next.question_number}`)}
                    </button>
                  )}
                  <span className="text-[13px] font-bold" style={{ color: completionPct === 100 ? "#16A34A" : "var(--color-accent)" }}>
                    {completionPct}%
                  </span>
                </div>
              </div>

              <div className="w-full h-2 rounded-full overflow-hidden" style={{ background: T.surface }}>
                <div
                  className="h-full rounded-full transition-all duration-700 ease-out"
                  style={{
                    width:      `${completionPct}%`,
                    background: completionPct === 100 ? "#16A34A" : "var(--color-accent)",
                  }}
                />
              </div>

              <div className="flex items-center justify-between mt-2.5">
                <p className="text-xs" style={{ color: T.subtle }}>
                  {counts.completed} of {allQuestions.length} questions completed
                </p>
                {completionPct === 100 ? (
                  <span className="text-xs font-semibold" style={{ color: "#16A34A" }}>Section complete ✓</span>
                ) : counts.completed === 0 && counts.attempted === 0 && counts.visited === 0 ? (
                  <span className="text-xs" style={{ color: T.subtle }}>Start practising to track your progress</span>
                ) : (
                  <span className="text-xs" style={{ color: T.subtle }}>
                    {allQuestions.length - counts.completed} remaining
                  </span>
                )}
              </div>
            </div>
          );
        })()}

        {/* ── Progress legend ──────────────────────────────────────────────────── */}
        {allQuestions.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 mb-5">
            {counts.completed   > 0 && <LegendPill status="completed"   count={counts.completed}   />}
            {counts.attempted   > 0 && <LegendPill status="attempted"   count={counts.attempted}   />}
            {counts.visited     > 0 && <LegendPill status="visited"     count={counts.visited}     />}
            {counts.not_visited > 0 && <LegendPill status="not_visited" count={counts.not_visited} />}
          </div>
        )}

        {/* ── Question grid ────────────────────────────────────────────────────── */}
        {allQuestions.length === 0 ? (

          /* Empty — no questions published yet */
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="w-14 h-14 rounded-full flex items-center justify-center mb-4"
              style={{ background: T.surface }}>
              <ListChecks size={24} style={{ color: T.subtle }} />
            </div>
            <p className="text-[15px] font-semibold" style={{ color: T.muted }}>No questions yet</p>
            <p className="text-sm mt-1" style={{ color: T.subtle }}>
              Questions will appear here once they&apos;re published.
            </p>
          </div>

        ) : filteredQuestions.length === 0 ? (

          /* Empty — no questions match the current filter / search */
          <div className="flex flex-col items-center justify-center py-14 text-center rounded-[var(--radius-lg)]"
            style={{ background: T.surface, border: `1px solid ${T.border}` }}>
            <Search size={22} className="mb-3" style={{ color: T.subtle }} />
            <p className="text-sm font-semibold" style={{ color: T.muted }}>No questions match</p>
            <p className="text-xs mt-1" style={{ color: T.subtle }}>Try a different number or change the filter.</p>
          </div>

        ) : (

          /* ref enables smooth scroll-to-grid-top on every page change */
          <div ref={gridRef}>

            {/* Question palette */}
            <div
              className="rounded-[var(--radius-lg)] p-4 sm:p-5"
              style={{ background: T.white, border: `1px solid ${T.border}` }}
            >
              <div
                className="grid gap-2"
                style={{ gridTemplateColumns: "repeat(auto-fill, minmax(52px, 60px))" }}
              >
                {paginatedQuestions.map(q => {
                  const ps       = q.progress_status;
                  const sty      = PROGRESS_STYLE[ps];
                  const isMcq    = q.question_type === "mcq";
                  const isActive = navigatingTo === q.id;
                  return (
                    <button
                      key={q.id}
                      onClick={() => goTo(`/students/practice/questions/${q.id}`, q.id)}
                      disabled={!!navigatingTo || breadcrumbLoading}
                      className="flex items-center justify-center rounded-[var(--radius-md)] transition-all duration-150 disabled:cursor-wait"
                      style={{
                        background:  sty.bg,
                        border:      `1.5px solid ${isActive ? sty.color : sty.border}`,
                        aspectRatio: "1 / 1",
                        opacity:     (navigatingTo || breadcrumbLoading) && !isActive ? 0.45 : 1,
                        transform:   isActive ? "scale(1.08)" : undefined,
                      }}
                      onMouseEnter={e => { if (!navigatingTo && !breadcrumbLoading) e.currentTarget.style.transform = "scale(1.08)"; }}
                      onMouseLeave={e => { if (!isActive) e.currentTarget.style.transform = "scale(1)"; }}
                      title={`Q${q.question_number} · ${isMcq ? "MCQ" : "FIB"} · ${sty.label}`}
                    >
                      {isActive
                        ? <LoadingSpinner size={14} />
                        : <span className="text-lg font-bold tabular-nums leading-none select-none" style={{ color: sty.color }}>
                            {q.question_number}
                          </span>}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Pagination — rendered only when questions exceed the page size */}
            {showPagination && (
              <>
                {/* Range info: "Q1–Q40 of 120 questions" */}
                <p className="text-xs text-center mt-3" style={{ color: T.subtle }}>
                  Q{(safePage - 1) * pageSize + 1}–Q{Math.min(safePage * pageSize, filteredQuestions.length)}
                  {" "}of{" "}
                  {filteredQuestions.length}
                  {filteredQuestions.length !== allQuestions.length ? " matching" : ""} questions
                </p>
                <PaginationControls
                  currentPage={safePage}
                  totalPages={totalPages}
                  onPageChange={handlePageChange}
                />
              </>
            )}

          </div>
        )}

      </PageWrapper>
    </StudentLayout>
  );
}
