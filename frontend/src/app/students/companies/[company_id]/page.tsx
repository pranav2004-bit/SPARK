"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  Layers, ChevronRight, Loader2,
  Calculator, Users, Code2, BookOpen, Brain,
  MessageSquare, Globe, type LucideIcon,
} from "lucide-react";
import { StudentLayout } from "@/components/layout/StudentLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { GlobalLoader } from "@/components/ui/GlobalLoader";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { Company, Section, PaginatedResponse, ApiSuccess } from "@/types";

// ── Seed-color palette (same as companies page — shared identity) ─────────────
const SEED_PALETTE = [
  { bg: "#FFF4E6", text: "#E8820C" },
  { bg: "#EFF6FF", text: "#2563EB" },
  { bg: "#F0FDF4", text: "#16A34A" },
  { bg: "#FDF4FF", text: "#9333EA" },
  { bg: "#FFF1F2", text: "#E11D48" },
  { bg: "#F0FDFA", text: "#0D9488" },
  { bg: "#FFFBEB", text: "#B45309" },
  { bg: "#F5F3FF", text: "#7C3AED" },
];

function seedColor(name: string) {
  let h = 0;
  for (let i = 0; i < name.length; i++) {
    h = name.charCodeAt(i) + ((h << 5) - h);
  }
  return SEED_PALETTE[Math.abs(h) % SEED_PALETTE.length];
}

// ── Contextual icon resolver ──────────────────────────────────────────────────
// Maps section name keywords → meaningful Lucide icon.
// A letter tells you nothing; an icon tells you the round at a glance.
function getSectionIcon(name: string): LucideIcon {
  const n = name.toLowerCase();
  if (/aptitude|quant|math|numerical|arithmetic/.test(n)) return Calculator;
  if (/\bhr\b|human.?resource|behaviour|behavioral|managerial|interview/.test(n)) return Users;
  if (/technical|coding|\bcode\b|program|software|\bdsa\b|data.?struct/.test(n)) return Code2;
  if (/verbal|english|language|communication|vocab|reading/.test(n)) return BookOpen;
  if (/reason|logical|puzzle|critical|analytical/.test(n)) return Brain;
  if (/group.?discussion|\bgd\b|discussion/.test(n)) return MessageSquare;
  if (/general|awareness|knowledge|current.?affairs/.test(n)) return Globe;
  return Layers;
}

// ── Section card ──────────────────────────────────────────────────────────────
function SectionCard({
  section,
  onClick,
  isNavigating,
}: {
  section: Section;
  onClick: () => void;
  isNavigating?: boolean;
}) {
  const color = seedColor(section.section_name);
  const Icon = getSectionIcon(section.section_name);
  const hasResources = (section.upload_count ?? 0) > 0;

  const resourceLabel =
    section.upload_count == null
      ? null
      : section.upload_count === 1
      ? "1 resource"
      : section.upload_count === 0
      ? "No resources yet"
      : `${section.upload_count} resources`;

  return (
    <button
      onClick={onClick}
      disabled={isNavigating}
      className={[
        "group w-full text-left bg-white border border-[var(--color-border)] rounded-[var(--radius-xl)] p-5",
        "hover:shadow-[var(--shadow-md)] hover:border-[var(--color-border-strong)] hover:-translate-y-0.5",
        "transition-all duration-150",
        "focus-visible:outline-2 focus-visible:outline-[var(--color-accent)] focus-visible:outline-offset-2",
        "disabled:pointer-events-none",
        // Mute cards that have no content — signals "not ready" without hiding
        !hasResources ? "opacity-60" : "",
      ].join(" ")}
    >
      <div className="flex items-center gap-4">

        {/* Contextual icon with seeded color */}
        <div
          className="w-12 h-12 rounded-[var(--radius-lg)] flex items-center justify-center shrink-0 transition-opacity duration-150"
          style={{ background: color.bg }}
        >
          <Icon size={20} style={{ color: color.text }} strokeWidth={2} />
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <p className="text-[15px] font-semibold text-[var(--color-text)] truncate group-hover:text-[var(--color-accent)] transition-colors duration-150 leading-snug">
            {section.section_name}
          </p>

          {/* Resource count pill */}
          {resourceLabel && (
            <span
              className="inline-flex items-center mt-1.5 text-[11px] font-medium px-2 py-0.5 rounded-full"
              style={
                hasResources
                  ? { background: "#F0FDF4", color: "#16A34A" }
                  : { background: "#F3F4F6", color: "#9CA3AF" }
              }
            >
              {resourceLabel}
            </span>
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
function SectionCardSkeleton() {
  return (
    <div className="bg-white border border-[var(--color-border)] rounded-[var(--radius-xl)] p-5">
      <div className="flex items-center gap-4">
        <Skeleton className="w-12 h-12 rounded-[var(--radius-lg)] shrink-0" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-5 w-24 rounded-full" />
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function CompanySectionsPage() {
  const router = useRouter();
  const { company_id } = useParams<{ company_id: string }>();
  const toast = useToast();

  const [company, setCompany] = useState<Company | null>(null);
  const [sections, setSections] = useState<Section[]>([]);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [backLoading, setBackLoading] = useState(false);
  const [navigatingId, setNavigatingId] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!company_id) { router.replace("/students/companies"); return; }
    try {
      const [companyRes, sectionsRes] = await Promise.all([
        api.get<ApiSuccess<Company>>(`/students/companies/${company_id}/`),
        api.get<PaginatedResponse<Section>>(`/students/companies/${company_id}/sections/`),
      ]);
      setCompany(companyRes.data.data);
      setSections(sectionsRes.data.results);
    } catch (err) {
      const msg = getErrorMessage(err);
      if (msg.toLowerCase().includes("not found") || msg.includes("404")) {
        setNotFound(true);
      } else {
        toast.error(msg);
      }
    } finally {
      setLoading(false);
    }
  }, [company_id, router, toast]);

  useEffect(() => { fetchData(); }, [fetchData]);

  function goBack() {
    setBackLoading(true);
    router.push("/students/companies");
  }

  function navigateTo(sectionId: string, sectionName: string) {
    setNavigatingId(sectionId);
    router.push(
      `/students/sections/${sectionId}?company=${company_id}&sname=${encodeURIComponent(sectionName)}`
    );
  }

  if (loading) return <GlobalLoader />;

  if (notFound) {
    return (
      <StudentLayout>
        <PageWrapper className="max-w-5xl py-8">
          <PageHeader
            title="Company not found"
            onBack={goBack}
            backLoading={backLoading}
            subtitle="This company may no longer be available."
          />
        </PageWrapper>
      </StudentLayout>
    );
  }

  return (
    <StudentLayout>
      <PageWrapper className="max-w-5xl py-8">
        <PageHeader
          onBack={goBack}
          backLoading={backLoading}
          title={company?.company_name ?? ""}
          subtitle={
            sections.length > 0
              ? `${sections.length} section${sections.length !== 1 ? "s" : ""} available`
              : undefined
          }
          breadcrumb={
            <span className="flex items-center gap-1">
              <button
                onClick={goBack}
                className="hover:text-[var(--color-accent)] transition-colors"
              >
                Companies
              </button>
              <ChevronRight size={12} className="opacity-50" />
              <span className="text-[var(--color-text)]">
                {company?.company_name ?? "—"}
              </span>
            </span>
          }
        />

        {sections.length === 0 ? (
          <EmptyState
            icon={Layers}
            title="No sections yet"
            subtitle="This company has no material sections available yet."
          />

        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {sections.map((section) => (
              <SectionCard
                key={section.id}
                section={section}
                isNavigating={navigatingId === section.id}
                onClick={() => navigateTo(section.id, section.section_name)}
              />
            ))}
          </div>
        )}

      </PageWrapper>
    </StudentLayout>
  );
}
