"use client";

import { useRouter } from "next/navigation";
import {
  ChevronRight, FileText, ClipboardList, BarChart3, TrendingUp,
  LayoutDashboard, Inbox, Bot, FileOutput, AlertTriangle, Bell,
} from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";

// Same icon-tile card convention as admin/assessments/page.tsx. All 10
// modules from the build plan (LIVETRACKER3_V1.md) are shown from Phase 2
// onward so the section's real shape is visible immediately — modules go
// live phase-by-phase as their own backend ships (essays/models.py isn't
// built ahead of the phase that needs it either); as of Phase 13
// (Notifications), all 10 modules from the original plan are live. The
// `enabled: false` / "Coming soon" rendering path below is kept, not
// deleted, for whatever this admin surface grows into next.
const MODULES = [
  {
    key: "question-bank",
    title: "Question Bank",
    description: "Author essay papers, sets, and the single writing prompt + LLM rubric per set.",
    icon: FileText,
    bg: "#EFF6FF",
    color: "#2563EB",
    href: "/admin/essay-writing/papers",
    enabled: true,
  },
  {
    key: "assign",
    title: "Assessments Assigning",
    description: "Pick a paper and a batch, then create and manage essay assignments.",
    icon: ClipboardList,
    bg: "#F0FDFA",
    color: "#0D9488",
    href: "/admin/essay-writing/assign",
    enabled: true,
  },
  {
    key: "results",
    title: "Results",
    description: "Per-student scores and LLM feedback for a specific assignment.",
    icon: BarChart3,
    bg: "#F0FDF4",
    color: "#16A34A",
    href: "/admin/essay-writing/results",
    enabled: true,
  },
  {
    key: "analytics",
    title: "Analytics",
    description: "Score distribution and per-question performance for a specific assignment.",
    icon: TrendingUp,
    bg: "#FDF4FF",
    color: "#9333EA",
    href: "/admin/essay-writing/analytics",
    enabled: true,
  },
  {
    key: "dashboard",
    title: "Dashboard",
    description: "Live KPI rollup — completion rate, average score, evaluation status.",
    icon: LayoutDashboard,
    bg: "#FFF4E6",
    color: "#E8820C",
    href: "/admin/essay-writing/dashboard",
    enabled: true,
  },
  {
    key: "submissions",
    title: "Submissions",
    description: "Monitor essay submissions moving through the LLM evaluation pipeline.",
    icon: Inbox,
    bg: "#EEF2FF",
    color: "#4F46E5",
    href: "/admin/essay-writing/submissions",
    enabled: true,
  },
  {
    key: "llm-controls",
    title: "LLM Controls",
    description: "Quota usage, model settings, and evaluation pipeline configuration.",
    icon: Bot,
    bg: "#FEF2F2",
    color: "#DC2626",
    href: "/admin/essay-writing/llm-controls",
    enabled: true,
  },
  {
    key: "reports",
    title: "Reports",
    description: "Per-student report generation and delivery status.",
    icon: FileOutput,
    bg: "#F0F9FF",
    color: "#0284C7",
    href: "/admin/essay-writing/reports",
    enabled: true,
  },
  {
    key: "dlq",
    title: "DLQ",
    description: "Failed background jobs — evaluation, reports, and more — awaiting retry or manual resolution.",
    icon: AlertTriangle,
    bg: "#FFFBEB",
    color: "#D97706",
    href: "/admin/essay-writing/dlq",
    enabled: true,
  },
  {
    key: "notifications",
    title: "Notifications",
    // Corrected from the original placeholder ("Email/notification
    // delivery for scores and reports") — that's Phase 11's own Reports
    // module, not this one. This is operational pipeline-health
    // alerting for admins, matching this tracker's own explicit
    // correction ("not a renamed copy of Phase 11").
    description: "Pipeline-health alerts (P1/P2) and a daily operational summary for admins.",
    icon: Bell,
    bg: "#F5F3FF",
    color: "#7C3AED",
    href: "/admin/essay-writing/notifications",
    enabled: true,
  },
] as const;

export default function AdminEssayWritingLandingPage() {
  const router = useRouter();

  return (
    <AdminLayout>
      <PageWrapper>
        <PageHeader
          title="Essay Writing"
          subtitle="LLM-evaluated essay assessments — author, assign, and review."
        />

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {MODULES.map(m => {
            const Icon = m.icon;
            if (!m.enabled) {
              return (
                <div
                  key={m.key}
                  aria-disabled="true"
                  className="text-left rounded-[var(--radius-xl)] overflow-hidden px-5 pt-5 pb-5 opacity-50 cursor-not-allowed"
                  style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="w-11 h-11 rounded-[var(--radius-lg)] flex items-center justify-center shrink-0" style={{ background: m.bg }}>
                      <Icon size={20} style={{ color: m.color }} />
                    </div>
                    <span
                      className="text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full shrink-0"
                      style={{ background: "var(--color-surface-subtle)", color: "var(--color-text-subtle)" }}
                    >
                      Coming soon
                    </span>
                  </div>
                  <div className="mt-3">
                    <p className="text-[15px] font-semibold leading-snug" style={{ color: "var(--color-text)" }}>{m.title}</p>
                    <p className="text-xs mt-1.5 leading-relaxed" style={{ color: "var(--color-text-subtle)" }}>{m.description}</p>
                  </div>
                </div>
              );
            }
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
