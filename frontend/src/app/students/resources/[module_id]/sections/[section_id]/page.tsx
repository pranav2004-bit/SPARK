"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  FileText, Music, Video, Image as ImageIcon,
  Link2, ExternalLink, ChevronRight, ArrowLeft, Upload as UploadIcon, ArrowUpRight,
} from "lucide-react";
import { StudentLayout } from "@/components/layout/StudentLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { Badge } from "@/components/ui/Badge";
import { LoadingSpinner } from "@/components/ui/Skeleton";
import { GlobalLoader } from "@/components/ui/GlobalLoader";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import { UPLOAD_TYPE_LABELS, LINK_UPLOAD_TYPES } from "@/lib/constants";
import type { Upload, UploadType, ResourceModule } from "@/types";

// ── Local types ───────────────────────────────────────────────────────────────
interface ResourceSection {
  id: string;
  name: string;
  module_id: string;
}
interface SectionDetailResponse {
  module:   ResourceModule;
  section:  ResourceSection;
  uploads:  Upload[];
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

// ── Upload type icons + backgrounds ──────────────────────────────────────────
function UploadTypeIcon({ type, size = 16 }: { type: UploadType; size?: number }) {
  const icons: Record<UploadType, React.ReactNode> = {
    pdf:           <FileText     size={size} className="text-red-500" />,
    audio:         <Music        size={size} className="text-purple-500" />,
    video:         <Video        size={size} className="text-blue-500" />,
    image:         <ImageIcon    size={size} className="text-teal-500" />,
    video_link:    <Link2        size={size} className="text-[var(--color-primary)]" />,
    external_link: <ExternalLink size={size} className="text-slate-500" />,
  };
  return <>{icons[type]}</>;
}

const ICON_BG: Record<UploadType, string> = {
  pdf:           "var(--color-danger-bg)",
  audio:         "#faf5ff",
  video:         "#eff6ff",
  image:         "#f0fdfa",
  video_link:    "var(--color-primary-light)",
  external_link: "#f8fafc",
};

function formatBytes(bytes: number | null): string {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function splitFilename(name: string): { base: string; ext: string } {
  const lastDot = name.lastIndexOf(".");
  if (lastDot <= 0) return { base: name, ext: "" };
  return { base: name.slice(0, lastDot), ext: name.slice(lastDot) };
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function StudentSectionUploadsPage() {
  const { module_id, section_id } = useParams<{ module_id: string; section_id: string }>();
  const router = useRouter();
  const { error: toastError } = useToast();

  const [detail,            setDetail]            = useState<SectionDetailResponse | null>(null);
  const [loading,           setLoading]           = useState(true);
  const [breadcrumbLoading, setBreadcrumbLoading] = useState(false);

  const navTo = (path: string) => {
    setBreadcrumbLoading(true);
    router.push(path);
  };

  useEffect(() => {
    api.get(`/resources/student/modules/${module_id}/sections/${section_id}/`)
      .then(res => setDetail(res.data.data))
      .catch(err => {
        toastError(getErrorMessage(err));
        router.push(`/students/resources/${module_id}`);
      })
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [module_id, section_id]);

  const mod     = detail?.module;
  const section = detail?.section;
  const uploads = detail?.uploads ?? [];

  if (loading) return <GlobalLoader />;

  return (
    <StudentLayout>
      <PageWrapper className="py-6 sm:py-8">

        {/* ── Breadcrumb ───────────────────────────────────────────────────────── */}
        <div className="flex items-center gap-1.5 text-sm font-medium mb-5">
          <button
            onClick={() => navTo("/students/resources")}
            disabled={breadcrumbLoading}
            className="transition-all shrink-0 disabled:opacity-50 disabled:cursor-wait inline-flex items-center gap-1"
            style={{ color: T.muted }}
            onMouseEnter={e => { if (!breadcrumbLoading) e.currentTarget.style.color = T.text; }}
            onMouseLeave={e => (e.currentTarget.style.color = T.muted)}
          >
            {breadcrumbLoading ? <LoadingSpinner size={12} /> : null}
            Resources
          </button>
          <ChevronRight size={13} style={{ color: T.subtle, flexShrink: 0 }} />
          <button
            onClick={() => navTo(`/students/resources/${module_id}`)}
            disabled={breadcrumbLoading}
            className="transition-all truncate disabled:opacity-50 disabled:cursor-wait"
            style={{ color: T.muted }}
            onMouseEnter={e => { if (!breadcrumbLoading) e.currentTarget.style.color = T.text; }}
            onMouseLeave={e => (e.currentTarget.style.color = T.muted)}
          >
            {mod?.name ?? "Module"}
          </button>
          <ChevronRight size={13} style={{ color: T.subtle, flexShrink: 0 }} />
          <span className="truncate" style={{ color: T.text }}>
            {section?.name ?? "Section"}
          </span>
        </div>

        {/* ── Page header ─────────────────────────────────────────────────────── */}
        <div className="mb-7">
          <button
            onClick={() => navTo(`/students/resources/${module_id}`)}
            disabled={breadcrumbLoading}
            className="inline-flex items-center gap-1.5 text-xs font-medium mb-2 transition-all disabled:opacity-50 disabled:cursor-wait"
            style={{ color: T.subtle }}
            onMouseEnter={e => { if (!breadcrumbLoading) e.currentTarget.style.color = T.muted; }}
            onMouseLeave={e => (e.currentTarget.style.color = T.subtle)}
          >
            {breadcrumbLoading ? <LoadingSpinner size={12} /> : <ArrowLeft size={12} />}
            Back to {mod?.name ?? "module"}
          </button>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight" style={{ color: T.text }}>
            {section?.name ?? "Section"}
          </h1>
          <p className="text-sm mt-1.5" style={{ color: T.muted }}>
            {uploads.length} {uploads.length === 1 ? "file" : "files"}
          </p>
        </div>

        {/* ── Upload list ─────────────────────────────────────────────────────── */}
        {uploads.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="w-14 h-14 rounded-full flex items-center justify-center mb-4"
              style={{ background: T.surface }}>
              <UploadIcon size={24} style={{ color: T.subtle }} />
            </div>
            <p className="text-[15px] font-semibold" style={{ color: T.muted }}>
              No files yet
            </p>
            <p className="text-sm mt-1" style={{ color: T.subtle }}>
              Files will appear here once they&apos;re added.
            </p>
          </div>
        ) : (
          <div className="bg-white border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden">
            <ul className="divide-y divide-[var(--color-border)]">
              {uploads.map((upload) => {
                const url = upload.read_url || upload.file_url;
                const isLink = LINK_UPLOAD_TYPES.includes(upload.upload_type as typeof LINK_UPLOAD_TYPES[number]);
                const displayName = upload.original_filename
                  ? (isLink ? upload.original_filename : splitFilename(upload.original_filename).base || upload.original_filename)
                  : isLink
                    ? (() => { try { return new URL(upload.file_url ?? "").hostname.replace(/^www\./, ""); } catch { return upload.file_url ?? ""; } })()
                    : upload.file_url ?? "";
                return (
                  <li
                    key={upload.id}
                    className="flex items-center gap-4 px-5 py-[15px] hover:bg-[var(--color-surface-secondary)] transition-colors group"
                  >
                    {/* Icon */}
                    <div
                      className="w-10 h-10 rounded-[var(--radius-lg)] flex items-center justify-center shrink-0"
                      style={{ background: ICON_BG[upload.upload_type] }}
                    >
                      <UploadTypeIcon type={upload.upload_type} size={18} />
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <p
                        className="text-[14px] font-medium text-[var(--color-text)] leading-snug line-clamp-2 sm:line-clamp-1 break-words sm:break-normal"
                        title={upload.original_filename ?? upload.file_url ?? ""}
                      >
                        {displayName}
                        {!isLink && upload.original_filename && (
                          <span style={{ color: "var(--color-text-muted)" }}>
                            {splitFilename(upload.original_filename).ext}
                          </span>
                        )}
                      </p>
                      <div className="flex items-center flex-wrap gap-2 mt-1.5">
                        <Badge variant={upload.upload_type}>
                          {UPLOAD_TYPE_LABELS[upload.upload_type]}
                        </Badge>
                        {upload.file_size_bytes && (
                          <span className="text-xs text-[var(--color-text-muted)]">
                            {formatBytes(upload.file_size_bytes)}
                          </span>
                        )}
                        {isLink && (
                          <span className="text-xs truncate text-[var(--color-text-subtle)]"
                            title={upload.file_url ?? ""}>
                            {upload.file_url}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Open — tinted accent button (correct weight for a repeating list action).
                        Row itself is 70px+ — Apple 44pt met by the row, not the button.
                        Hover fills to solid for a premium interaction on desktop.         */}
                    {url ? (
                      <a
                        href={url}
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
              })}
            </ul>
          </div>
        )}

      </PageWrapper>
    </StudentLayout>
  );
}
