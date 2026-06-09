"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import { Building2, ChevronRight, Search, Loader2, Layers } from "lucide-react";
import { StudentLayout } from "@/components/layout/StudentLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { GlobalLoader } from "@/components/ui/GlobalLoader";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { Company, PaginatedResponse } from "@/types";

// ── Seed-color palette ────────────────────────────────────────────────────────
// Deterministic: same company name always gets the same colour
const SEED_PALETTE = [
  { bg: "#FFF4E6", text: "#E8820C" }, // amber  (accent-family)
  { bg: "#EFF6FF", text: "#2563EB" }, // blue
  { bg: "#F0FDF4", text: "#16A34A" }, // green
  { bg: "#FDF4FF", text: "#9333EA" }, // purple
  { bg: "#FFF1F2", text: "#E11D48" }, // rose
  { bg: "#F0FDFA", text: "#0D9488" }, // teal
  { bg: "#FFFBEB", text: "#B45309" }, // yellow
  { bg: "#F5F3FF", text: "#7C3AED" }, // violet
];

function seedColor(name: string) {
  let h = 0;
  for (let i = 0; i < name.length; i++) {
    h = name.charCodeAt(i) + ((h << 5) - h);
  }
  return SEED_PALETTE[Math.abs(h) % SEED_PALETTE.length];
}

// ── Company card ──────────────────────────────────────────────────────────────
function CompanyCard({
  company,
  onClick,
  isNavigating,
}: {
  company: Company;
  onClick: () => void;
  isNavigating?: boolean;
}) {
  const initial = company.company_name.trim()[0]?.toUpperCase() ?? "C";
  const color = seedColor(company.company_name);

  const sectionText =
    company.section_count == null
      ? null
      : company.section_count === 1
      ? "1 section"
      : `${company.section_count} sections`;

  return (
    <button
      onClick={onClick}
      disabled={isNavigating}
      className="group w-full text-left bg-white border border-[var(--color-border)] rounded-[var(--radius-xl)] p-5 hover:shadow-[var(--shadow-md)] hover:border-[var(--color-border-strong)] hover:-translate-y-0.5 transition-all duration-150 focus-visible:outline-2 focus-visible:outline-[var(--color-accent)] focus-visible:outline-offset-2 disabled:opacity-60 disabled:pointer-events-none"
    >
      <div className="flex items-center gap-4">

        {/* Seeded-color monogram */}
        <div
          className="w-12 h-12 rounded-[var(--radius-lg)] flex items-center justify-center shrink-0 transition-opacity duration-150"
          style={{ background: color.bg }}
        >
          <span className="text-lg font-bold" style={{ color: color.text }}>
            {initial}
          </span>
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <p className="text-[15px] font-semibold text-[var(--color-text)] truncate group-hover:text-[var(--color-accent)] transition-colors duration-150 leading-snug">
            {company.company_name}
          </p>
          {sectionText && (
            <div className="flex items-center gap-1 mt-1">
              <Layers size={11} className="text-[var(--color-text-subtle)] shrink-0" />
              <span className="text-xs text-[var(--color-text-muted)]">
                {sectionText}
              </span>
            </div>
          )}
        </div>

        {/* Arrow / loading */}
        {isNavigating ? (
          <Loader2
            size={16}
            className="animate-spin shrink-0"
            style={{ color: color.text }}
          />
        ) : (
          <ChevronRight
            size={16}
            className="text-[var(--color-text-subtle)] group-hover:text-[var(--color-accent)] group-hover:translate-x-0.5 transition-all duration-150 shrink-0"
          />
        )}
      </div>
    </button>
  );
}

// ── Card skeleton ─────────────────────────────────────────────────────────────
function CompanyCardSkeleton() {
  return (
    <div className="bg-white border border-[var(--color-border)] rounded-[var(--radius-xl)] p-5">
      <div className="flex items-center gap-4">
        <Skeleton className="w-12 h-12 rounded-[var(--radius-lg)] shrink-0" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-3 w-1/3" />
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function StudentCompaniesPage() {
  const router = useRouter();
  const toast = useToast();

  const [companies, setCompanies] = useState<Company[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [navigatingId, setNavigatingId] = useState<string | null>(null);
  const [backLoading, setBackLoading] = useState(false);

  function handleBack() {
    setBackLoading(true);
    router.push("/students/resources");
  }

  const fetchCompanies = useCallback(async () => {
    try {
      const res = await api.get<PaginatedResponse<Company>>("/students/companies/");
      setCompanies(res.data.results);
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { fetchCompanies(); }, [fetchCompanies]);

  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return companies;
    return companies.filter((c) => c.company_name.toLowerCase().includes(q));
  }, [companies, searchQuery]);

  const hasResults = filtered.length > 0;
  const hasCompanies = companies.length > 0;

  if (loading) return <GlobalLoader />;

  function navigateTo(id: string) {
    setNavigatingId(id);
    router.push(`/students/companies/${id}`);
  }

  return (
    <StudentLayout>
      <PageWrapper className="max-w-5xl py-8">
        <PageHeader
          title="Companies"
          subtitle="Browse placement materials by company."
          onBack={handleBack}
          backLoading={backLoading}
        />

        {/* ── Search ────────────────────────────────────────────────────────── */}
        {hasCompanies && (
          <div className="relative mb-6">
            <Search
              size={16}
              className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] pointer-events-none"
            />
            <input
              type="text"
              placeholder="Search companies…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full h-10 pl-10 pr-4 text-sm rounded-[var(--radius-md)] border border-[var(--color-border)] bg-white text-[var(--color-text)] placeholder:text-[var(--color-text-subtle)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] hover:border-[var(--color-border-strong)] transition-colors"
            />
          </div>
        )}

        {/* ── Grid ─────────────────────────────────────────────────────────── */}
        {!hasCompanies ? (
          <EmptyState
            icon={Building2}
            title="No companies yet"
            subtitle="Your administrator hasn't published any company materials. Check back soon."
          />

        ) : !hasResults ? (
          <div className="flex flex-col items-center py-16 text-center">
            <p className="text-base font-medium text-[var(--color-text)]">
              No results for &ldquo;{searchQuery}&rdquo;
            </p>
            <p className="text-sm text-[var(--color-text-muted)] mt-1">Try a different name.</p>
            <button
              onClick={() => setSearchQuery("")}
              className="mt-4 text-sm text-[var(--color-accent)] hover:underline"
            >
              Clear search
            </button>
          </div>

        ) : (
          <>
            {searchQuery && (
              <p className="text-xs text-[var(--color-text-muted)] mb-4">
                {filtered.length} result{filtered.length !== 1 ? "s" : ""} for &ldquo;{searchQuery}&rdquo;
              </p>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {filtered.map((company) => (
                <CompanyCard
                  key={company.id}
                  company={company}
                  isNavigating={navigatingId === company.id}
                  onClick={() => navigateTo(company.id)}
                />
              ))}
            </div>
          </>
        )}

      </PageWrapper>
    </StudentLayout>
  );
}
