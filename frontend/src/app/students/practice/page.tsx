"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Layers, FolderOpen, ChevronRight, AlertTriangle } from "lucide-react";
import { StudentLayout } from "@/components/layout/StudentLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { LoadingSpinner } from "@/components/ui/Skeleton";
import { GlobalLoader } from "@/components/ui/GlobalLoader";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { PracticeModule, PracticeSection } from "@/types";

// ── Design tokens — mapped to global CSS variables ────────────────────────────
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

interface PracticeRootData {
  modules:  PracticeModule[];
  sections: PracticeSection[];
}

export default function StudentPracticeHubPage() {
  const router = useRouter();
  const { error: toastError } = useToast();

  const [data,         setData]         = useState<PracticeRootData>({ modules: [], sections: [] });
  const [loading,      setLoading]      = useState(true);
  const [loadError,    setLoadError]    = useState(false);
  const [navigatingTo, setNavigatingTo] = useState<string | null>(null);

  const goTo = (path: string, id: string) => {
    setNavigatingTo(id);
    router.push(path);
  };

  // On failure this must not just toast and fall through to "No practice
  // content yet" below — that reads as "there's genuinely nothing here,"
  // not "this failed to load."
  function load() {
    setLoading(true);
    setLoadError(false);
    api.get("/practice/student/")
      .then(res => setData(res.data.data ?? { modules: [], sections: [] }))
      .catch(err => { toastError(getErrorMessage(err)); setLoadError(true); })
      .finally(() => setLoading(false));
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, []);

  const { modules, sections } = data;
  const hasContent = modules.length > 0 || sections.length > 0;

  if (loading) return <GlobalLoader />;

  return (
    <StudentLayout>
      <PageWrapper className="py-6 sm:py-8">

        {/* ── Page header ─────────────────────────────────────────────────────── */}
        <div className="mb-6 sm:mb-8">
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight" style={{ color: T.text }}>
            Practice
          </h1>
          <p className="text-sm mt-1.5 leading-relaxed" style={{ color: T.muted }}>
            Topic-wise practice questions to sharpen your aptitude and reasoning.
          </p>
        </div>

        {/* ── Content ─────────────────────────────────────────────────────────── */}
        {loadError ? (
          <EmptyState
            icon={AlertTriangle}
            title="Couldn't load practice content"
            subtitle="Something went wrong fetching this data — it may be temporary. Try again in a moment."
            action={{ label: "Retry", onClick: load }}
          />

        ) : !hasContent ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div
              className="w-14 h-14 rounded-full flex items-center justify-center mb-4"
              style={{ background: T.surface }}
            >
              <Layers size={24} style={{ color: T.subtle }} />
            </div>
            <p className="text-[15px] font-semibold" style={{ color: T.muted }}>
              No practice content yet
            </p>
            <p className="text-sm mt-1" style={{ color: T.subtle }}>
              Check back later — your admin will publish questions soon.
            </p>
          </div>

        ) : (
          <>
            {/* ── Modules ─────────────────────────────────────────────────────── */}
            {modules.length > 0 && (
              <div className={sections.length > 0 ? "mb-8" : ""}>
                {modules.length > 0 && sections.length > 0 && (
                  <p
                    className="text-[11px] font-bold tracking-[0.12em] uppercase mb-3"
                    style={{ color: T.subtle }}
                  >
                    Modules ({modules.length})
                  </p>
                )}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {modules.map((mod, i) => {
                    const { bg, color } = palette(i);
                    const isActive = navigatingTo === mod.id;
                    return (
                      <button
                        key={mod.id}
                        onClick={() => goTo(`/students/practice/${mod.id}`, mod.id)}
                        disabled={!!navigatingTo}
                        className="text-left rounded-[var(--radius-xl)] px-5 py-4 flex items-center gap-4 transition-all duration-150 group disabled:opacity-50 disabled:cursor-wait"
                        style={{
                          background: T.white,
                          border:     `1px solid ${T.border}`,
                          boxShadow:  isActive ? "var(--shadow-md)" : "var(--shadow-sm)",
                          opacity:    navigatingTo && !isActive ? 0.5 : 1,
                        }}
                        onMouseEnter={e => {
                          if (navigatingTo) return;
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
                          className="w-11 h-11 rounded-[var(--radius-lg)] flex items-center justify-center shrink-0"
                          style={{ background: bg }}
                        >
                          <Layers size={20} style={{ color }} />
                        </div>
                        <p
                          className="flex-1 text-[15px] font-semibold leading-snug group-hover:text-[var(--color-accent)] transition-colors duration-150"
                          style={{ color: T.text }}
                        >
                          {mod.name}
                        </p>
                        {isActive
                          ? <LoadingSpinner size={16} />
                          : <ChevronRight size={16} style={{ color: T.subtle, flexShrink: 0 }} className="transition-transform duration-150 group-hover:translate-x-0.5" />}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* ── Root-level sections ──────────────────────────────────────────── */}
            {sections.length > 0 && (
              <div>
                {modules.length > 0 && sections.length > 0 && (
                  <p
                    className="text-[11px] font-bold tracking-[0.12em] uppercase mb-3"
                    style={{ color: T.subtle }}
                  >
                    Sections ({sections.length})
                  </p>
                )}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {sections.map((sec, i) => {
                    const { bg, color } = palette(i + modules.length);
                    const isActive = navigatingTo === sec.id;
                    return (
                      <button
                        key={sec.id}
                        onClick={() => goTo(`/students/practice/sections/${sec.id}`, sec.id)}
                        disabled={!!navigatingTo}
                        className="text-left rounded-[var(--radius-xl)] px-5 py-4 flex items-center gap-4 transition-all duration-150 group disabled:opacity-50 disabled:cursor-wait"
                        style={{
                          background: T.white,
                          border:     `1px solid ${T.border}`,
                          boxShadow:  isActive ? "var(--shadow-md)" : "var(--shadow-sm)",
                          opacity:    navigatingTo && !isActive ? 0.5 : 1,
                        }}
                        onMouseEnter={e => {
                          if (navigatingTo) return;
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
                          className="w-11 h-11 rounded-[var(--radius-lg)] flex items-center justify-center shrink-0"
                          style={{ background: bg }}
                        >
                          <FolderOpen size={20} style={{ color }} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p
                            className="text-[15px] font-semibold leading-snug group-hover:text-[var(--color-accent)] transition-colors duration-150"
                            style={{ color: T.text }}
                          >
                            {sec.name}
                          </p>
                          <p className="text-xs mt-0.5" style={{ color: T.subtle }}>
                            {sec.question_count} {sec.question_count === 1 ? "question" : "questions"}
                          </p>
                        </div>
                        {isActive
                          ? <LoadingSpinner size={16} />
                          : <ChevronRight size={16} style={{ color: T.subtle, flexShrink: 0 }} className="transition-transform duration-150 group-hover:translate-x-0.5" />}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* ── How to practise ─────────────────────────────────────────────── */}
            <div className="mt-10 pt-6 border-t" style={{ borderColor: T.border }}>
              <p
                className="text-[11px] font-bold tracking-[0.12em] uppercase mb-5"
                style={{ color: T.subtle }}
              >
                How to practise
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
                {[
                  { n: "1", title: "Pick a module",     body: "Choose the topic area you want to strengthen today." },
                  { n: "2", title: "Solve questions",   body: "Work through difficulty-graded questions at your own pace." },
                  { n: "3", title: "Build consistency", body: "Daily practice is the single biggest placement differentiator." },
                ].map(({ n, title, body }) => (
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

          </>
        )}

      </PageWrapper>
    </StudentLayout>
  );
}
