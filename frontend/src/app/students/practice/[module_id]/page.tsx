"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Layers, FolderOpen, ChevronRight } from "lucide-react";
import { StudentLayout } from "@/components/layout/StudentLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { LoadingSpinner } from "@/components/ui/Skeleton";
import { GlobalLoader } from "@/components/ui/GlobalLoader";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { PracticeModule, PracticeSection } from "@/types";

// ── Design tokens ─────────────────────────────────────────────────────────────
const T = {
  text:    "var(--color-text)",
  muted:   "var(--color-text-muted)",
  subtle:  "var(--color-text-subtle)",
  border:  "var(--color-border)",
  surface: "var(--color-surface-secondary)",
  white:   "#ffffff",
};

const PALETTE = [
  { bg: "#FFF4E6", color: "#E8820C" },
  { bg: "#EFF6FF", color: "#2563EB" },
  { bg: "#F0FDF4", color: "#16A34A" },
  { bg: "#FDF4FF", color: "#9333EA" },
  { bg: "#FFF1F2", color: "#E11D48" },
  { bg: "#F0FDFA", color: "#0D9488" },
  { bg: "#FFFBEB", color: "#B45309" },
  { bg: "#F5F3FF", color: "#7C3AED" },
];
const palette = (i: number) => PALETTE[i % PALETTE.length];

const HOW_TO = [
  {
    n: "1",
    title: "Start with Easy",
    body:  "Build your foundation — Easy questions reinforce core concepts before you advance.",
  },
  {
    n: "2",
    title: "Solve without hints",
    body:  "Attempt every question independently first. Real exams give no hints — train like you test.",
  },
  {
    n: "3",
    title: "Progress upward",
    body:  "After completing Easy, move to Medium then Hard. Each level sharpens a different skill tier.",
  },
];

interface ModuleDetailData {
  module:   PracticeModule;
  children: PracticeModule[];
  sections: PracticeSection[];
}

export default function StudentPracticeModulePage() {
  const { module_id } = useParams<{ module_id: string }>();
  const router        = useRouter();
  const { error: toastError } = useToast();

  const [detail,           setDetail]           = useState<ModuleDetailData | null>(null);
  const [loading,          setLoading]          = useState(true);
  const [ancestors,        setAncestors]        = useState<PracticeModule[]>([]);
  const [navigatingTo,     setNavigatingTo]     = useState<string | null>(null);
  const [breadcrumbLoading, setBreadcrumbLoading] = useState(false);

  const goTo = (path: string, id: string) => {
    setNavigatingTo(id);
    router.push(path);
  };
  const navTo = (path: string) => {
    setBreadcrumbLoading(true);
    router.push(path);
  };

  const lastFetchAt = useRef<number>(0);
  const STALE_MS    = 30_000;

  // Walk up parent IDs to build the full ancestor chain for the breadcrumb.
  // e.g. current = "Functions" → ancestors = [Quantitative Aptitude]
  const buildAncestors = async (current: PracticeModule) => {
    const chain: PracticeModule[] = [];
    let node = current;
    while (node.parent) {
      try {
        const res = await api.get(`/students/practice/modules/${node.parent}/`);
        const parentMod = res.data.data?.module as PracticeModule | undefined;
        if (!parentMod) break;
        chain.unshift(parentMod);
        node = parentMod;
      } catch {
        break;
      }
    }
    setAncestors(chain);
  };

  const fetchModule = (silent = false) => {
    if (!silent) setLoading(true);
    api.get(`/students/practice/modules/${module_id}/`)
      .then(res => {
        const data = res.data.data as ModuleDetailData;
        setDetail(data);
        lastFetchAt.current = Date.now();
        buildAncestors(data.module);
      })
      .catch(err => {
        if (!silent) {
          toastError(getErrorMessage(err));
          router.push("/students/practice");
        }
      })
      .finally(() => {
        if (!silent) setLoading(false);
      });
  };

  // ── Initial fetch ──────────────────────────────────────────────────────────
  useEffect(() => {
    fetchModule();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [module_id]);

  // ── Silent refetch on tab visibility (data freshness) ─────────────────────
  useEffect(() => {
    const onVisibilityChange = () => {
      if (
        document.visibilityState === "visible" &&
        Date.now() - lastFetchAt.current > STALE_MS
      ) {
        fetchModule(true);
      }
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => document.removeEventListener("visibilitychange", onVisibilityChange);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [module_id]);

  const mod      = detail?.module;
  const children = detail?.children ?? [];
  const sections = detail?.sections ?? [];

  const totalQuestions = sections.reduce((sum, s) => sum + s.question_count, 0);
  const hasContent     = children.length > 0 || sections.length > 0;

  if (loading) return <GlobalLoader />;

  return (
    <StudentLayout>
      <PageWrapper className="max-w-5xl py-6 sm:py-8">

        {/* ── Breadcrumb ──────────────────────────────────────────────────────── */}
        {/* Full ancestor chain built from API — no "Practice" tab label,         */}
        {/* no fragile ?from= query params. Works on direct URL access too.       */}
        <nav className="flex items-center flex-wrap gap-1.5 text-sm font-medium mb-5 min-w-0" aria-label="Breadcrumb">

          {/* Practice — root anchor, always present */}
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

          {/* Ancestor modules */}
          {ancestors.map(anc => (
            <span key={anc.id} className="flex items-center gap-1.5 min-w-0">
              <ChevronRight size={13} style={{ color: T.subtle, flexShrink: 0 }} />
              <button
                onClick={() => navTo(`/students/practice/${anc.id}`)}
                disabled={breadcrumbLoading || !!navigatingTo}
                className="truncate transition-all disabled:opacity-50 disabled:cursor-wait"
                style={{ color: T.muted }}
                onMouseEnter={e => { if (!breadcrumbLoading && !navigatingTo) e.currentTarget.style.color = T.text; }}
                onMouseLeave={e => (e.currentTarget.style.color = T.muted)}
              >
                {anc.name}
              </button>
            </span>
          ))}

          {/* Current module — non-clickable terminal segment */}
          <ChevronRight size={13} style={{ color: T.subtle, flexShrink: 0 }} />
          <span className="truncate font-semibold" style={{ color: T.text }}>
            {mod?.name ?? "Module"}
          </span>

        </nav>

        {/* ── Page header ─────────────────────────────────────────────────────── */}
        <div className="mb-7 sm:mb-8">
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight" style={{ color: T.text }}>
            {mod?.name ?? "Module"}
          </h1>
          {totalQuestions > 0 && (
            <p className="text-sm mt-1.5" style={{ color: T.muted }}>
              {totalQuestions} {totalQuestions === 1 ? "question" : "questions"} available
            </p>
          )}
        </div>

        {/* ── Content ─────────────────────────────────────────────────────────── */}
        {!hasContent ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div
              className="w-14 h-14 rounded-full flex items-center justify-center mb-4"
              style={{ background: T.surface }}
            >
              <Layers size={24} style={{ color: T.subtle }} />
            </div>
            <p className="text-[15px] font-semibold" style={{ color: T.muted }}>Nothing here yet</p>
            <p className="text-sm mt-1" style={{ color: T.subtle }}>
              Content will appear here once it&apos;s published.
            </p>
          </div>

        ) : (
          <>
            {/* ── Sub-modules ─────────────────────────────────────────────────── */}
            {children.length > 0 && (
              <div className={sections.length > 0 ? "mb-8" : ""}>
                <p
                  className="text-[11px] font-bold tracking-[0.12em] uppercase mb-3"
                  style={{ color: T.subtle }}
                >
                  Modules ({children.length})
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {children.map((child, i) => {
                    const { bg, color } = palette(i);
                    const isActive = navigatingTo === child.id;
                    return (
                      <button
                        key={child.id}
                        onClick={() => goTo(`/students/practice/${child.id}`, child.id)}
                        disabled={!!navigatingTo || breadcrumbLoading}
                        className="text-left rounded-[var(--radius-xl)] px-5 py-4 flex items-center gap-4 transition-all duration-150 group disabled:cursor-wait"
                        style={{
                          background: T.white,
                          border:     `1px solid ${T.border}`,
                          boxShadow:  isActive ? "var(--shadow-md)" : "var(--shadow-sm)",
                          opacity:    (navigatingTo || breadcrumbLoading) && !isActive ? 0.5 : 1,
                        }}
                        onMouseEnter={e => {
                          if (navigatingTo || breadcrumbLoading) return;
                          e.currentTarget.style.boxShadow   = "var(--shadow-md)";
                          e.currentTarget.style.transform   = "translateY(-1px)";
                          e.currentTarget.style.borderColor = color + "55";
                        }}
                        onMouseLeave={e => {
                          e.currentTarget.style.boxShadow   = "var(--shadow-sm)";
                          e.currentTarget.style.transform   = "none";
                          e.currentTarget.style.borderColor = T.border;
                        }}
                      >
                        <div
                          className="w-10 h-10 rounded-[var(--radius-lg)] flex items-center justify-center shrink-0"
                          style={{ background: bg }}
                        >
                          <Layers size={18} style={{ color }} />
                        </div>
                        <p
                          className="flex-1 text-[14px] font-semibold leading-snug group-hover:text-[var(--color-accent)] transition-colors duration-150"
                          style={{ color: T.text }}
                        >
                          {child.name}
                        </p>
                        {isActive
                          ? <LoadingSpinner size={15} />
                          : <ChevronRight size={15} style={{ color: T.subtle, flexShrink: 0 }} className="transition-transform duration-150 group-hover:translate-x-0.5" />}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* ── Sections ────────────────────────────────────────────────────── */}
            {sections.length > 0 && (
              <div>
                <p
                  className="text-[11px] font-bold tracking-[0.12em] uppercase mb-3"
                  style={{ color: T.subtle }}
                >
                  Sections ({sections.length})
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {sections.map((sec, i) => {
                    const { bg, color } = palette(i + children.length);
                    const isActive = navigatingTo === sec.id;
                    return (
                      <button
                        key={sec.id}
                        onClick={() => goTo(`/students/practice/sections/${sec.id}`, sec.id)}
                        disabled={!!navigatingTo || breadcrumbLoading}
                        className="text-left rounded-[var(--radius-xl)] px-5 py-4 flex items-center gap-4 transition-all duration-150 group disabled:cursor-wait"
                        style={{
                          background: T.white,
                          border:     `1px solid ${T.border}`,
                          boxShadow:  isActive ? "var(--shadow-md)" : "var(--shadow-sm)",
                          opacity:    (navigatingTo || breadcrumbLoading) && !isActive ? 0.5 : 1,
                        }}
                        onMouseEnter={e => {
                          if (navigatingTo || breadcrumbLoading) return;
                          e.currentTarget.style.boxShadow   = "var(--shadow-md)";
                          e.currentTarget.style.transform   = "translateY(-1px)";
                          e.currentTarget.style.borderColor = color + "55";
                        }}
                        onMouseLeave={e => {
                          e.currentTarget.style.boxShadow   = "var(--shadow-sm)";
                          e.currentTarget.style.transform   = "none";
                          e.currentTarget.style.borderColor = T.border;
                        }}
                      >
                        <div
                          className="w-10 h-10 rounded-[var(--radius-lg)] flex items-center justify-center shrink-0"
                          style={{ background: bg }}
                        >
                          <FolderOpen size={18} style={{ color }} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p
                            className="text-[14px] font-semibold leading-snug group-hover:text-[var(--color-accent)] transition-colors duration-150"
                            style={{ color: T.text }}
                          >
                            {sec.name}
                          </p>
                          <p className="text-xs mt-0.5" style={{ color: T.subtle }}>
                            {sec.question_count} {sec.question_count === 1 ? "question" : "questions"}
                          </p>
                        </div>
                        {isActive
                          ? <LoadingSpinner size={15} />
                          : <ChevronRight size={15} style={{ color: T.subtle, flexShrink: 0 }} className="transition-transform duration-150 group-hover:translate-x-0.5" />}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* ── How to practise ─────────────────────────────────────────────── */}
            {sections.length > 0 && (
              <div className="mt-10 pt-6 border-t" style={{ borderColor: T.border }}>
                <p
                  className="text-[11px] font-bold tracking-[0.12em] uppercase mb-5"
                  style={{ color: T.subtle }}
                >
                  How to practise
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
                  {HOW_TO.map(({ n, title, body }) => (
                    <div key={n} className="flex items-start gap-3">
                      <div
                        className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-0.5"
                        style={{ background: "var(--color-accent)" }}
                      >
                        <span className="text-[10px] font-black text-white">{n}</span>
                      </div>
                      <div>
                        <p className="text-[13px] font-semibold leading-snug" style={{ color: T.text }}>
                          {title}
                        </p>
                        <p className="text-[12px] mt-1 leading-relaxed" style={{ color: T.subtle }}>
                          {body}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

      </PageWrapper>
    </StudentLayout>
  );
}
