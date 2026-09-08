"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Layers, FolderOpen, ChevronRight, ArrowLeft } from "lucide-react";
import { StudentLayout } from "@/components/layout/StudentLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { LoadingSpinner } from "@/components/ui/Skeleton";
import { GlobalLoader } from "@/components/ui/GlobalLoader";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { ResourceModule } from "@/types";

// ── Local types ───────────────────────────────────────────────────────────────
interface ResourceSection {
  id: string;
  module_id: string;
  name: string;
  is_published: boolean;
  order: number;
}

interface ModuleDetailResponse {
  module:   ResourceModule;
  children: ResourceModule[];
  sections: ResourceSection[];
}

// ── Design tokens ─────────────────────────────────────────────────────────────
const T = {
  text:    "#1a2b3c",
  muted:   "#5c6e82",
  subtle:  "#8fa0b0",
  border:  "#e2e8f0",
  surface: "#f8f9fa",
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

export default function StudentModulePage() {
  const { module_id } = useParams<{ module_id: string }>();
  const router = useRouter();
  const { error: toastError } = useToast();

  const [detail,            setDetail]            = useState<ModuleDetailResponse | null>(null);
  const [loading,           setLoading]           = useState(true);
  const [navigatingTo,      setNavigatingTo]      = useState<string | null>(null);
  const [breadcrumbLoading, setBreadcrumbLoading] = useState(false);

  const goTo = (path: string, id: string) => {
    setNavigatingTo(id);
    router.push(path);
  };
  const navTo = (path: string) => {
    setBreadcrumbLoading(true);
    router.push(path);
  };

  useEffect(() => {
    api.get(`/resources/student/modules/${module_id}/`)
      .then(res => setDetail(res.data.data))
      .catch(err => {
        toastError(getErrorMessage(err));
        router.push("/students/resources");
      })
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [module_id]);

  const mod = detail?.module;
  const children = detail?.children ?? [];
  const sections = detail?.sections ?? [];
  const hasContent = children.length > 0 || sections.length > 0;

  if (loading) return <GlobalLoader />;

  return (
    <StudentLayout>
      <PageWrapper className="py-6 sm:py-8">

        {/* ── Back breadcrumb ──────────────────────────────────────────────────── */}
        <button
          onClick={() => navTo("/students/resources")}
          disabled={breadcrumbLoading || !!navigatingTo}
          className="inline-flex items-center gap-1.5 text-sm font-medium mb-5 transition-all disabled:opacity-50 disabled:cursor-wait"
          style={{ color: T.muted }}
          onMouseEnter={e => { if (!breadcrumbLoading && !navigatingTo) e.currentTarget.style.color = T.text; }}
          onMouseLeave={e => (e.currentTarget.style.color = T.muted)}
        >
          {breadcrumbLoading ? <LoadingSpinner size={14} /> : <ArrowLeft size={14} />}
          Resources
        </button>

        {/* ── Page header ─────────────────────────────────────────────────────── */}
        <div className="mb-7 sm:mb-8">
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight" style={{ color: T.text }}>
            {mod?.name ?? "Module"}
          </h1>
        </div>

        {/* ── Content ─────────────────────────────────────────────────────────── */}
        {!hasContent ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="w-14 h-14 rounded-full flex items-center justify-center mb-4"
              style={{ background: T.surface }}>
              <Layers size={24} style={{ color: T.subtle }} />
            </div>
            <p className="text-[15px] font-semibold" style={{ color: T.muted }}>
              Nothing here yet
            </p>
            <p className="text-sm mt-1" style={{ color: T.subtle }}>
              Content will appear here once it&apos;s published.
            </p>
          </div>
        ) : (
          <>
            {/* Sub-modules */}
            {children.length > 0 && (
              <div className="mb-8">
                <p className="text-[11px] font-bold tracking-[0.12em] uppercase mb-3"
                  style={{ color: T.subtle }}>
                  Modules ({children.length})
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {children.map((child, i) => {
                    const { bg, color } = palette(i);
                    const isActive = navigatingTo === child.id;
                    return (
                      <button
                        key={child.id}
                        onClick={() => goTo(`/students/resources/${child.id}`, child.id)}
                        disabled={!!navigatingTo || breadcrumbLoading}
                        className="text-left rounded-[var(--radius-xl)] px-4 py-3.5 transition-all duration-150 group disabled:cursor-wait"
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
                          e.currentTarget.style.boxShadow   = isActive ? "var(--shadow-md)" : "var(--shadow-sm)";
                          e.currentTarget.style.transform   = "none";
                          e.currentTarget.style.borderColor = T.border;
                        }}
                      >
                        {/* Horizontal layout: icon — text — chevron (Apple/Google/Notion standard) */}
                        <div className="flex items-center gap-3.5">
                          <div className="w-10 h-10 rounded-[var(--radius-lg)] flex items-center justify-center shrink-0"
                            style={{ background: bg }}>
                            <Layers size={18} style={{ color }} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-[14px] font-semibold leading-snug truncate" style={{ color: T.text }}>
                              {child.name}
                            </p>
                            <p className="text-xs mt-0.5" style={{ color: T.subtle }}>Sub-module</p>
                          </div>
                          {isActive
                            ? <LoadingSpinner size={15} />
                            : <ChevronRight size={15} style={{ color: T.subtle, flexShrink: 0 }}
                                className="transition-transform duration-150 group-hover:translate-x-0.5" />}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Sections */}
            {sections.length > 0 && (
              <div>
                <p className="text-[11px] font-bold tracking-[0.12em] uppercase mb-3"
                  style={{ color: T.subtle }}>
                  Sections ({sections.length})
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {sections.map((sec, i) => {
                    const { bg, color } = palette(i + children.length);
                    const isActive = navigatingTo === sec.id;
                    return (
                      <button
                        key={sec.id}
                        onClick={() => goTo(`/students/resources/${module_id}/sections/${sec.id}`, sec.id)}
                        disabled={!!navigatingTo || breadcrumbLoading}
                        className="text-left rounded-[var(--radius-xl)] px-4 py-3.5 transition-all duration-150 group disabled:cursor-wait"
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
                          e.currentTarget.style.boxShadow   = isActive ? "var(--shadow-md)" : "var(--shadow-sm)";
                          e.currentTarget.style.transform   = "none";
                          e.currentTarget.style.borderColor = T.border;
                        }}
                      >
                        {/* Horizontal layout: icon — text — chevron */}
                        <div className="flex items-center gap-3.5">
                          <div className="w-10 h-10 rounded-[var(--radius-lg)] flex items-center justify-center shrink-0"
                            style={{ background: bg }}>
                            <FolderOpen size={18} style={{ color }} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-[14px] font-semibold leading-snug truncate" style={{ color: T.text }}>
                              {sec.name}
                            </p>
                            <p className="text-xs mt-0.5" style={{ color: T.subtle }}>Section</p>
                          </div>
                          {isActive
                            ? <LoadingSpinner size={15} />
                            : <ChevronRight size={15} style={{ color: T.subtle, flexShrink: 0 }}
                                className="transition-transform duration-150 group-hover:translate-x-0.5" />}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </>
        )}

      </PageWrapper>
    </StudentLayout>
  );
}
