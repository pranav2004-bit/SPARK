"use client";

import { Suspense, useEffect, useState, useCallback } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
  FileText, Music, Video, Image as ImageIcon,
  Link2, ExternalLink, ChevronRight,
  ArrowUpRight, FolderOpen, AlertCircle, Loader2,
} from "lucide-react";
import { StudentLayout } from "@/components/layout/StudentLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { GlobalLoader } from "@/components/ui/GlobalLoader";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import { UPLOAD_TYPE_LABELS } from "@/lib/constants";
import type { Company, Upload, UploadType, PaginatedResponse, ApiSuccess } from "@/types";

// ── Per-type visual style — hardcoded hex to avoid CSS-variable cascade risk ──
const TYPE_STYLE: Record<UploadType, { bg: string; color: string }> = {
  pdf:           { bg: "#FEF2F2", color: "#EF4444" },
  audio:         { bg: "#FAF5FF", color: "#A855F7" },
  video:         { bg: "#EFF6FF", color: "#3B82F6" },
  image:         { bg: "#F0FDFA", color: "#0D9488" },
  video_link:    { bg: "#FFF4E6", color: "#E8820C" },
  external_link: { bg: "#F8FAFC", color: "#64748B" },
};

// ── Upload type icon ──────────────────────────────────────────────────────────
function UploadTypeIcon({ type, size = 20 }: { type: UploadType; size?: number }) {
  const { color } = TYPE_STYLE[type];
  const icons: Record<UploadType, React.ReactNode> = {
    pdf:           <FileText    size={size} style={{ color }} />,
    audio:         <Music       size={size} style={{ color }} />,
    video:         <Video       size={size} style={{ color }} />,
    image:         <ImageIcon   size={size} style={{ color }} />,
    video_link:    <Link2       size={size} style={{ color }} />,
    external_link: <ExternalLink size={size} style={{ color }} />,
  };
  return <>{icons[type]}</>;
}

const FILE_TYPES: UploadType[] = ["pdf", "audio", "video", "image"];
function isFileType(type: UploadType): boolean {
  return FILE_TYPES.includes(type);
}

function formatBytes(bytes: number | null): string {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ── Upload row ────────────────────────────────────────────────────────────────
function UploadRow({ upload }: { upload: Upload }) {
  const openUrl = isFileType(upload.upload_type) ? upload.read_url : upload.file_url;
  const displayName = upload.original_filename ?? upload.file_url;
  const size = formatBytes(upload.file_size_bytes);
  const { bg } = TYPE_STYLE[upload.upload_type];

  return (
    <li className="flex items-center gap-4 px-5 py-[15px] hover:bg-[var(--color-surface-secondary)] transition-colors group">

      {/* Type icon — w-11 h-11 for visual weight consistent with card pages */}
      <div
        className="w-11 h-11 rounded-[var(--radius-lg)] flex items-center justify-center shrink-0"
        style={{ background: bg }}
      >
        <UploadTypeIcon type={upload.upload_type} size={20} />
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        {/* Filename: 2 lines on mobile so students can read it; 1 line on sm+ */}
        <p
          className="text-[14px] font-medium text-[var(--color-text)] leading-snug line-clamp-2 sm:line-clamp-1 break-words sm:break-normal"
          title={displayName}
        >
          {displayName}
        </p>
        <div className="flex items-center flex-wrap gap-2 mt-1.5">
          <Badge variant={upload.upload_type}>
            {UPLOAD_TYPE_LABELS[upload.upload_type]}
          </Badge>
          {size && (
            <span className="text-xs text-[var(--color-text-muted)]">{size}</span>
          )}
        </div>
      </div>

      {/* Open — tinted accent button (correct weight for a repeating list action).
          Solid fill is reserved for single dominant CTAs (Submit, Next, Start Q).
          Row itself is 70px+ — Apple 44pt tap-target is met by the row, not this button.
          Hover fills to solid for a premium interaction feel on desktop.              */}
      {openUrl ? (
        <a
          href={openUrl}
          target="_blank"
          rel="noopener noreferrer"
          className={[
            "flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-md)] text-xs font-semibold shrink-0",
            "bg-[var(--color-accent-light)] text-[var(--color-accent)] border border-[var(--color-accent)]/20",
            "hover:bg-[var(--color-accent)] hover:text-white hover:border-transparent",
            "active:scale-95 transition-all duration-150",
          ].join(" ")}
        >
          <ArrowUpRight size={14} />
          Open
        </a>
      ) : (
        <span
          className="text-[11px] font-medium px-2.5 py-1 rounded-full shrink-0"
          style={{ background: "#F3F4F6", color: "#9CA3AF" }}
        >
          Unavailable
        </span>
      )}
    </li>
  );
}

// ── Upload row skeleton ───────────────────────────────────────────────────────
function UploadRowSkeleton() {
  return (
    <li className="flex items-center gap-4 px-5 py-[15px]">
      <Skeleton className="w-11 h-11 rounded-[var(--radius-lg)] shrink-0" />
      <div className="flex-1 space-y-2">
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-5 w-16 rounded-full" />
      </div>
      <Skeleton className="h-8 w-[72px] rounded-[var(--radius-md)] shrink-0" />
    </li>
  );
}

// ── Inner component (uses useSearchParams — must be inside Suspense) ──────────
function SectionContent() {
  const router = useRouter();
  const { section_id } = useParams<{ section_id: string }>();
  const searchParams = useSearchParams();
  const toast = useToast();

  const company_id = searchParams.get("company") ?? "";
  const sname = searchParams.get("sname") ?? "Section";

  const [company, setCompany] = useState<Company | null>(null);
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [backLoading, setBackLoading] = useState(false);

  const backHref = company_id
    ? `/students/companies/${company_id}`
    : "/students/companies";

  function goBack() {
    setBackLoading(true);
    router.push(backHref);
  }

  const fetchData = useCallback(async () => {
    if (!company_id) {
      setError("Missing company parameter. Please navigate from the companies list.");
      setLoading(false);
      return;
    }
    try {
      const [companyRes, uploadsRes] = await Promise.all([
        api.get<ApiSuccess<Company>>(`/resources/student/companies/${company_id}/`),
        api.get<PaginatedResponse<Upload>>(
          `/resources/student/companies/${company_id}/sections/${section_id}/uploads/`
        ),
      ]);
      setCompany(companyRes.data.data);
      setUploads(uploadsRes.data.results);
    } catch (err) {
      const msg = getErrorMessage(err);
      if (msg.toLowerCase().includes("not found") || msg.includes("404")) {
        setError("This section is no longer available.");
      } else {
        toast.error(msg);
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  }, [company_id, section_id, toast]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // ── Loading state — full-screen SPARK star animation ─────────────────────
  if (loading) return <GlobalLoader />;

  // ── Error state ───────────────────────────────────────────────────────────
  if (error) {
    return (
      <PageWrapper className="py-8">
        <div className="flex flex-col items-center py-20 text-center">
          <div className="w-14 h-14 rounded-[var(--radius-lg)] bg-[var(--color-danger-bg)] flex items-center justify-center mb-4">
            <AlertCircle size={24} className="text-[var(--color-danger)]" />
          </div>
          <h3 className="text-base font-semibold text-[var(--color-text)] mb-1">{error}</h3>
          <button
            onClick={() => router.push("/students/companies")}
            className="mt-4 text-sm text-[var(--color-accent)] hover:underline"
          >
            ← Back to companies
          </button>
        </div>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper className="py-8">

      {/* ── Page header ─────────────────────────────────────────────────────── */}
      <PageHeader
        title={sname}
        onBack={goBack}
        backLoading={backLoading}
        subtitle={
          uploads.length > 0
            ? `${uploads.length} resource${uploads.length !== 1 ? "s" : ""}`
            : undefined
        }
        breadcrumb={
          <span className="flex items-center gap-1 flex-wrap">
            <button
              onClick={() => { setBackLoading(true); router.push("/students/companies"); }}
              className="hover:text-[var(--color-accent)] transition-colors"
            >
              Companies
            </button>
            <ChevronRight size={12} className="opacity-50 shrink-0" />
            <button
              onClick={goBack}
              className="hover:text-[var(--color-accent)] transition-colors"
            >
              {company?.company_name ?? "—"}
            </button>
            <ChevronRight size={12} className="opacity-50 shrink-0" />
            <span className="text-[var(--color-text)] font-medium">{sname}</span>
          </span>
        }
      />

      {/* ── Resource list ────────────────────────────────────────────────────── */}
      <div className="bg-white border border-[var(--color-border)] rounded-[var(--radius-xl)] overflow-hidden shadow-[var(--shadow-sm)]">
        {uploads.length === 0 ? (
          <div className="py-4">
            <EmptyState
              icon={FolderOpen}
              title="No resources yet"
              subtitle="This section has no materials uploaded yet. Check back soon."
            />
          </div>

        ) : (
          <ul className="divide-y divide-[var(--color-border)]">
            {uploads.map((upload) => (
              <UploadRow key={upload.id} upload={upload} />
            ))}
          </ul>
        )}
      </div>

      {/* ── Temporary-link notice ────────────────────────────────────────────── */}
      {!loading && uploads.some((u) => isFileType(u.upload_type)) && (
        <p className="text-xs text-[var(--color-text-subtle)] text-center mt-4">
          File links are temporary. Refresh the page if a file link expires.
        </p>
      )}

    </PageWrapper>
  );
}

// ── Page export — wraps SectionContent in Suspense ────────────────────────────
export default function StudentSectionPage() {
  return (
    <StudentLayout>
      <Suspense fallback={<GlobalLoader />}>
        <SectionContent />
      </Suspense>
    </StudentLayout>
  );
}
