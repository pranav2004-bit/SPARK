"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, Layers, ChevronRight, AlertTriangle } from "lucide-react";
import { StudentLayout } from "@/components/layout/StudentLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { LoadingSpinner } from "@/components/ui/Skeleton";
import { GlobalLoader } from "@/components/ui/GlobalLoader";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { ResourceModule } from "@/types";

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
    n:     "1",
    title: "Browse by topic",
    body:  "Choose the subject area or company type relevant to your placement target.",
  },
  {
    n:     "2",
    title: "Study the material",
    body:  "Access curated notes, PDFs and past papers organised by section.",
  },
  {
    n:     "3",
    title: "Reinforce with practice",
    body:  "Head to the Practice tab to test what you've just studied — learning sticks faster.",
  },
];

export default function StudentResourcesHubPage() {
  const router = useRouter();
  const { error: toastError } = useToast();

  const [modules,      setModules]      = useState<ResourceModule[]>([]);
  const [loading,      setLoading]      = useState(true);
  const [loadError,    setLoadError]    = useState(false);
  const [navigatingTo, setNavigatingTo] = useState<string | null>(null);

  const lastFetchAt = useRef<number>(0);
  const STALE_MS    = 30_000;

  // Silent background polls (visibility-change refetch) stay quiet on
  // failure — but a *non-silent* failure (initial load) must not just toast
  // and fall through to "No resources yet" below, which reads as "there's
  // genuinely nothing here" rather than "this failed to load."
  const fetchModules = (silent = false) => {
    if (!silent) setLoading(true);
    api.get("/resources/student/modules/")
      .then(res => {
        setModules(res.data.data ?? []);
        lastFetchAt.current = Date.now();
        setLoadError(false);
      })
      .catch(err => { if (!silent) { toastError(getErrorMessage(err)); setLoadError(true); } })
      .finally(() => { if (!silent) setLoading(false); });
  };

  useEffect(() => {
    fetchModules();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Silent refetch when tab becomes visible after 30s+
  useEffect(() => {
    const onVisibilityChange = () => {
      if (
        document.visibilityState === "visible" &&
        Date.now() - lastFetchAt.current > STALE_MS
      ) {
        fetchModules(true);
      }
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => document.removeEventListener("visibilitychange", onVisibilityChange);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleNavigate(mod: ResourceModule) {
    setNavigatingTo(mod.id);
    if (mod.is_system) {
      router.push("/students/companies");
    } else {
      router.push(`/students/resources/${mod.id}`);
    }
  }

  const hasContent = modules.length > 0;

  if (loading) return <GlobalLoader />;

  return (
    <StudentLayout>
      <PageWrapper className="py-6 sm:py-8">

        {/* ── Page header ─────────────────────────────────────────────────────── */}
        <div className="mb-6 sm:mb-8">
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight" style={{ color: T.text }}>
            Resources
          </h1>
          <p className="text-sm mt-1.5 leading-relaxed" style={{ color: T.muted }}>
            All your placement preparation material — organised by module.
          </p>
        </div>

        {/* ── Grid ────────────────────────────────────────────────────────────── */}
        {loadError ? (
          <EmptyState
            icon={AlertTriangle}
            title="Couldn't load resources"
            subtitle="Something went wrong fetching this data — it may be temporary. Try again in a moment."
            action={{ label: "Retry", onClick: () => fetchModules() }}
          />

        ) : modules.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="w-14 h-14 rounded-full flex items-center justify-center mb-4"
              style={{ background: T.surface }}>
              <Layers size={24} style={{ color: T.subtle }} />
            </div>
            <p className="text-[15px] font-semibold" style={{ color: T.muted }}>
              No resources yet
            </p>
            <p className="text-sm mt-1" style={{ color: T.subtle }}>
              Check back later — your admin will publish materials soon.
            </p>
          </div>

        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {modules.map((mod, i) => {
              const { bg, color } = palette(i);
              const Icon     = mod.is_system ? Building2 : Layers;
              const isActive = navigatingTo === mod.id;
              return (
                <button
                  key={mod.id}
                  onClick={() => handleNavigate(mod)}
                  disabled={!!navigatingTo}
                  className="text-left rounded-[var(--radius-xl)] px-5 py-4 flex items-center gap-4 transition-all duration-150 group disabled:cursor-wait"
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
                    e.currentTarget.style.boxShadow   = isActive ? "var(--shadow-md)" : "var(--shadow-sm)";
                    e.currentTarget.style.transform   = "none";
                    e.currentTarget.style.borderColor = T.border;
                  }}
                >
                  {/* Icon */}
                  <div
                    className="w-11 h-11 rounded-[var(--radius-lg)] flex items-center justify-center shrink-0"
                    style={{ background: bg }}
                  >
                    <Icon size={20} style={{ color }} />
                  </div>

                  {/* Text */}
                  <p
                    className="flex-1 text-[15px] font-semibold leading-snug group-hover:text-[var(--color-accent)] transition-colors duration-150"
                    style={{ color: T.text }}
                  >
                    {mod.name}
                  </p>

                  {/* Chevron / Spinner */}
                  {isActive
                    ? <LoadingSpinner size={16} />
                    : <ChevronRight size={16} style={{ color: T.subtle, flexShrink: 0 }}
                        className="transition-transform duration-150 group-hover:translate-x-0.5" />}
                </button>
              );
            })}
          </div>
        )}

        {/* ── How to use resources ─────────────────────────────────────────────── */}
        {hasContent && (
          <div className="mt-10 pt-6 border-t" style={{ borderColor: T.border }}>
            <p
              className="text-[11px] font-bold tracking-[0.12em] uppercase mb-5"
              style={{ color: T.subtle }}
            >
              How to use resources
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

      </PageWrapper>
    </StudentLayout>
  );
}
