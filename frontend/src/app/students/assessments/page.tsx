"use client";

import { ClipboardList, CheckCircle2 } from "lucide-react";
import { StudentLayout } from "@/components/layout/StudentLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";

const FEATURES = [
  "Timed full-length mock assessments",
  "Section-wise performance analytics",
  "Company-specific test patterns",
  "Detailed post-test review & insights",
];

export default function AssessmentsPage() {
  return (
    <StudentLayout>
      <PageWrapper className="py-10 sm:py-16">
        <div className="w-full max-w-sm px-6 text-center mx-auto">

          {/* v2 badge */}
          <div
            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-semibold uppercase tracking-wider mb-8"
            style={{ background: "var(--color-accent-light)", color: "var(--color-accent)" }}
          >
            Coming in SPARK v2.0
          </div>

          {/* Icon */}
          <div
            className="w-20 h-20 rounded-[var(--radius-xl)] flex items-center justify-center mx-auto mb-6"
            style={{ background: "var(--color-accent-light)" }}
          >
            <ClipboardList size={36} style={{ color: "var(--color-accent)" }} />
          </div>

          {/* Heading */}
          <h1
            className="text-2xl font-bold mb-2 tracking-tight"
            style={{ color: "var(--color-text)" }}
          >
            Assessments
          </h1>

          {/* Description */}
          <p
            className="text-sm leading-relaxed mb-8"
            style={{ color: "var(--color-text-muted)" }}
          >
            Simulate real placement tests and know exactly where you stand before the drive.
          </p>

          {/* Feature preview */}
          <div
            className="text-left rounded-[var(--radius-xl)] border p-5 space-y-3"
            style={{ background: "#fff", borderColor: "var(--color-border)" }}
          >
            <p
              className="text-[11px] font-semibold uppercase tracking-wider mb-4"
              style={{ color: "var(--color-text-subtle)" }}
            >
              What&apos;s included
            </p>
            {FEATURES.map((feat) => (
              <div key={feat} className="flex items-start gap-2.5">
                <CheckCircle2
                  size={15}
                  className="shrink-0 mt-0.5"
                  style={{ color: "var(--color-accent)" }}
                />
                <span className="text-sm leading-snug" style={{ color: "var(--color-text)" }}>
                  {feat}
                </span>
              </div>
            ))}
          </div>

          {/* Footer note */}
          <p className="text-xs mt-6" style={{ color: "var(--color-text-subtle)" }}>
            Available in the next major release of SPARK.
          </p>

        </div>
      </PageWrapper>
    </StudentLayout>
  );
}
