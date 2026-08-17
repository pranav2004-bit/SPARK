"use client";

import { useRouter } from "next/navigation";
import { ChevronRight, FileText, BarChart3, TrendingUp, LayoutDashboard, ClipboardList } from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";

// Same icon-tile palette convention as papers/page.tsx and
// resources/page.tsx's ModuleCard — fixed destinations here rather than a
// data-driven list, since (unlike papers/resources) these rarely change.
// Ordered to match the actual admin workflow, not alphabetically or by
// when each card was added: author → assign → review (Results/Analytics/
// Dashboard are all meaningless until an assignment exists, so Assessments
// comes right after Question Bank, not last).
const MODULES = [
  {
    key: "papers",
    title: "Question Bank",
    description: "Author question papers, sets, and questions for timed exams.",
    icon: FileText,
    bg: "#EFF6FF",
    color: "#2563EB",
    href: "/admin/assessments/papers",
  },
  {
    key: "assessments",
    title: "Assessments",
    description: "Pick a question paper and a batch, then create and manage exam assignments.",
    icon: ClipboardList,
    bg: "#F0FDFA",
    color: "#0D9488",
    href: "/admin/assessments/assign",
  },
  {
    key: "results",
    title: "Results",
    description: "Per-student scores, responses, and activity logs for a specific assignment.",
    icon: BarChart3,
    bg: "#F0FDF4",
    color: "#16A34A",
    href: "/admin/assessments/results",
  },
  {
    key: "analytics",
    title: "Analytics",
    description: "Score distribution, pass/fail rate, and per-question difficulty for a specific assignment.",
    icon: TrendingUp,
    bg: "#FDF4FF",
    color: "#9333EA",
    href: "/admin/assessments/analytics",
  },
  {
    key: "dashboard",
    title: "Dashboard",
    description: "Live KPI rollup — completion rate, average score, malpractice incidents — for a specific assignment.",
    icon: LayoutDashboard,
    bg: "#FFF4E6",
    color: "#E8820C",
    href: "/admin/assessments/dashboard",
  },
] as const;

export default function AdminAssessmentsLandingPage() {
  const router = useRouter();

  return (
    <AdminLayout>
      <PageWrapper className="max-w-5xl">
        <PageHeader
          title="Assessments"
          subtitle="Author exams, then review how students did."
        />

        {/* 2-col grid (not 3-col — a 3-column grid leaves a 4-card layout
            with an orphaned card alone on its own row, found in design
            review, 2026-08-13). At 5 cards the last row (Dashboard) is a
            single half-width card — accepted tradeoff, not a bug. */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {MODULES.map(m => {
            const Icon = m.icon;
            return (
              <button
                key={m.key}
                onClick={() => router.push(m.href)}
                className="text-left rounded-[var(--radius-xl)] overflow-hidden transition-shadow duration-150 hover:shadow-[var(--shadow-md)] cursor-pointer group px-5 pt-5 pb-5"
                style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="w-11 h-11 rounded-[var(--radius-lg)] flex items-center justify-center shrink-0" style={{ background: m.bg }}>
                    <Icon size={20} style={{ color: m.color }} />
                  </div>
                  <ChevronRight
                    size={16}
                    style={{ color: "var(--color-text-subtle)", marginTop: 2, flexShrink: 0 }}
                    className="transition-transform duration-150 group-hover:translate-x-0.5"
                  />
                </div>
                <div className="mt-3">
                  <p className="text-[15px] font-semibold leading-snug" style={{ color: "var(--color-text)" }}>{m.title}</p>
                  <p className="text-xs mt-1.5 leading-relaxed" style={{ color: "var(--color-text-subtle)" }}>{m.description}</p>
                </div>
              </button>
            );
          })}
        </div>
      </PageWrapper>
    </AdminLayout>
  );
}
