"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useSearchParams } from "next/navigation";
import axios from "axios";
import {
  Upload as UploadIcon,
  Trash2,
  FileText,
  Music,
  Video,
  Image as ImageIcon,
  Link2,
  ExternalLink,
  ChevronDown,
  AlertTriangle,
} from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { Badge } from "@/components/ui/Badge";
import { LoadingSpinner } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import {
  UPLOAD_TYPE_LABELS,
  UPLOAD_ACCEPT_MAP,
  FILE_UPLOAD_TYPES,
  LINK_UPLOAD_TYPES,
} from "@/lib/constants";
import type { Company, Section, Upload, UploadType, ApiSuccess, PaginatedResponse } from "@/types";

// ── Upload icons ──────────────────────────────────────────────────────────────
function UploadTypeIcon({ type, size = 16 }: { type: UploadType; size?: number }) {
  const icons: Record<UploadType, React.ReactNode> = {
    pdf: <FileText size={size} className="text-red-500" />,
    audio: <Music size={size} className="text-purple-500" />,
    video: <Video size={size} className="text-blue-500" />,
    image: <ImageIcon size={size} className="text-teal-500" />,
    video_link: <Link2 size={size} className="text-[var(--color-primary)]" />,
    external_link: <ExternalLink size={size} className="text-slate-500" />,
  };
  return <>{icons[type]}</>;
}

function formatBytes(bytes: number | null): string {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function UploadsPage() {
  const { section_id } = useParams<{ section_id: string }>();
  // company_id passed as query param: /admin/sections/[section_id]?company=<id>
  const searchParams = useSearchParams();
  const company_id = searchParams.get("company") ?? "";
  const toast = useToast();

  const [company, setCompany] = useState<Company | null>(null);
  const [section, setSection] = useState<Section | null>(null);
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Active upload flow state
  const [uploadType, setUploadType] = useState<UploadType | null>(null);
  // File upload
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  // Link upload
  const [linkUrl, setLinkUrl] = useState("");
  const [linkError, setLinkError] = useState("");
  const [linkLoading, setLinkLoading] = useState(false);

  // Delete
  const [deleteUpload, setDeleteUpload] = useState<Upload | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const fetchData = useCallback(async () => {
    if (!company_id) return;
    setLoading(true);
    setLoadError(false);
    try {
      const [companyRes, sectionRes, uploadsRes] = await Promise.all([
        api.get<ApiSuccess<Company>>(`/resources/companies/${company_id}/`),
        api.get<ApiSuccess<Section>>(`/resources/companies/${company_id}/sections/${section_id}/`),
        api.get<PaginatedResponse<Upload>>(
          `/resources/companies/${company_id}/sections/${section_id}/uploads/`
        ),
      ]);
      setCompany(companyRes.data.data);
      setSection(sectionRes.data.data);
      setUploads(uploadsRes.data.results);
    } catch (err) {
      toast.error(getErrorMessage(err));
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [company_id, section_id, toast]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Close dropdown on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node)
      ) {
        setShowDropdown(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  function selectUploadType(type: UploadType) {
    setUploadType(type);
    setShowDropdown(false);
    setSelectedFile(null);
    setUploadProgress(0);
    setLinkUrl("");
    setLinkError("");

    if (FILE_UPLOAD_TYPES.includes(type as typeof FILE_UPLOAD_TYPES[number])) {
      setTimeout(() => fileInputRef.current?.click(), 0);
    }
  }

  function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) setSelectedFile(file);
    e.target.value = "";
  }

  async function handleFileUpload() {
    if (!selectedFile || !uploadType) return;
    setUploading(true);
    setUploadProgress(0);
    try {
      // Step 1: get presigned upload URL
      const { data: presignedResponse } = await api.post<ApiSuccess<{
        upload_url: string;
        file_key: string;
      }>>(
        `/resources/companies/${company_id}/sections/${section_id}/uploads/presign/`,
        {
          upload_type: uploadType,
          filename: selectedFile.name,
          content_type: selectedFile.type || "application/octet-stream",
        }
      );

      const presignedData = presignedResponse.data;

      // Step 2: PUT file directly to R2/MinIO (raw axios, no auth header)
      await axios.put(presignedData.upload_url, selectedFile, {
        headers: { "Content-Type": selectedFile.type || "application/octet-stream" },
        onUploadProgress: (e) => {
          if (e.total) {
            setUploadProgress(Math.round((e.loaded / e.total) * 100));
          }
        },
      });

      // Step 3: confirm (create DB record)
      const { data: confirmResponse } = await api.post<ApiSuccess<Upload>>(
        `/resources/companies/${company_id}/sections/${section_id}/uploads/confirm/`,
        {
          file_key: presignedData.file_key,
          upload_type: uploadType,
          original_filename: selectedFile.name,
          file_size_bytes: selectedFile.size,
        }
      );

      setUploads((prev) => [confirmResponse.data, ...prev]);
      toast.success("File uploaded successfully.");
      setSelectedFile(null);
      setUploadType(null);
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setUploading(false);
      setUploadProgress(0);
    }
  }

  async function handleLinkSave() {
    if (!linkUrl.trim() || !uploadType) return;
    setLinkError("");

    try {
      new URL(linkUrl.trim());
    } catch {
      setLinkError("Please enter a valid URL (include https://).");
      return;
    }

    setLinkLoading(true);
    try {
      const { data: linkResponse } = await api.post<ApiSuccess<Upload>>(
        `/resources/companies/${company_id}/sections/${section_id}/uploads/add-link/`,
        {
          upload_type: uploadType,
          file_url: linkUrl.trim(),
        }
      );
      setUploads((prev) => [linkResponse.data, ...prev]);
      toast.success("Link saved.");
      setLinkUrl("");
      setUploadType(null);
    } catch (err) {
      setLinkError(getErrorMessage(err));
    } finally {
      setLinkLoading(false);
    }
  }

  async function handleDelete() {
    if (!deleteUpload) return;
    setDeleteLoading(true);
    try {
      await api.delete(
        `/resources/companies/${company_id}/sections/${section_id}/uploads/${deleteUpload.id}/`
      );
      setUploads((prev) => prev.filter((u) => u.id !== deleteUpload.id));
      toast.success("Upload deleted.");
      setDeleteUpload(null);
    } catch (err) {
      toast.error(getErrorMessage(err));
      setDeleteUpload(null);
    } finally {
      setDeleteLoading(false);
    }
  }

  const isFileType = uploadType
    ? FILE_UPLOAD_TYPES.includes(uploadType as typeof FILE_UPLOAD_TYPES[number])
    : false;
  const isLinkType = uploadType
    ? LINK_UPLOAD_TYPES.includes(uploadType as typeof LINK_UPLOAD_TYPES[number])
    : false;

  return (
    <AdminLayout>
      <PageWrapper>
        <PageHeader
          title={section?.section_name ?? "Uploads"}
          backHref={`/admin/companies/${company_id}`}
          breadcrumb={
            <span>
              <a
                href="/admin/companies"
                className="hover:underline"
              >
                Companies
              </a>
              {" › "}
              {company?.company_name}
            </span>
          }
          rightSlot={
            <div className="relative" ref={dropdownRef}>
              <Button
                variant="primary"
                onClick={() => setShowDropdown((v) => !v)}
                rightIcon={<ChevronDown size={14} />}
              >
                <UploadIcon size={14} />
                Upload
              </Button>

              {showDropdown && (
                <div className="absolute right-0 top-full mt-1 w-44 bg-white border border-[var(--color-border)] rounded-[var(--radius-md)] shadow-[var(--shadow-lg)] z-20 overflow-hidden">
                  {[...FILE_UPLOAD_TYPES, ...LINK_UPLOAD_TYPES].map((type) => (
                    <button
                      key={type}
                      onClick={() => selectUploadType(type)}
                      className="flex items-center gap-2.5 w-full px-3.5 py-2.5 text-sm text-[var(--color-text)] hover:bg-[var(--color-surface-hover)] transition-colors"
                    >
                      <UploadTypeIcon type={type} size={14} />
                      {UPLOAD_TYPE_LABELS[type]}
                    </button>
                  ))}
                </div>
              )}
            </div>
          }
        />

        {/* ── Active upload flow ──────────────────────────────────────────────── */}
        {uploadType && (
          <div className="mb-5 bg-[var(--color-info-bg)] border border-[var(--color-primary)]/20 rounded-[var(--radius-lg)] p-4">
            <div className="flex items-center gap-2 mb-3">
              <UploadTypeIcon type={uploadType} size={16} />
              <span className="text-sm font-medium text-[var(--color-text)]">
                {UPLOAD_TYPE_LABELS[uploadType]}
              </span>
              <button
                onClick={() => {
                  setUploadType(null);
                  setSelectedFile(null);
                  setLinkUrl("");
                  setLinkError("");
                }}
                className="ml-auto text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] underline"
              >
                Cancel
              </button>
            </div>

            {isFileType && (
              <>
                {selectedFile ? (
                  <div>
                    <div className="flex items-center justify-between mb-3 text-sm">
                      <span className="text-[var(--color-text)] font-medium truncate max-w-xs">
                        {selectedFile.name}
                      </span>
                      <span className="text-[var(--color-text-muted)] ml-3 shrink-0">
                        {formatBytes(selectedFile.size)}
                      </span>
                    </div>

                    {/* Progress bar */}
                    {uploading && (
                      <div className="mb-3">
                        <div className="h-2 bg-[var(--color-accent-light)] rounded-full overflow-hidden">
                          <div
                            className="h-full bg-[var(--color-accent)] transition-all duration-150"
                            style={{ width: `${uploadProgress}%` }}
                          />
                        </div>
                        <p className="text-xs text-[var(--color-text-muted)] mt-1">
                          {uploadProgress}%
                        </p>
                      </div>
                    )}

                    <div className="flex gap-2">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => setSelectedFile(null)}
                        disabled={uploading}
                      >
                        Change file
                      </Button>
                      <Button
                        size="sm"
                        loading={uploading}
                        onClick={handleFileUpload}
                      >
                        Upload
                      </Button>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-[var(--color-text-muted)]">
                    No file selected. Click{" "}
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      className="text-[var(--color-accent)] hover:underline"
                    >
                      here
                    </button>{" "}
                    to choose a file.
                  </p>
                )}
              </>
            )}

            {isLinkType && (
              <div>
                <Input
                  placeholder="https://..."
                  value={linkUrl}
                  onChange={(e) => setLinkUrl(e.target.value)}
                  error={linkError}
                  autoFocus
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleLinkSave();
                  }}
                />
                <Button
                  size="sm"
                  className="mt-1"
                  loading={linkLoading}
                  onClick={handleLinkSave}
                  disabled={!linkUrl.trim()}
                >
                  Save link
                </Button>
              </div>
            )}
          </div>
        )}

        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          accept={uploadType ? UPLOAD_ACCEPT_MAP[uploadType] : "*"}
          onChange={handleFileSelected}
        />

        {/* ── Upload list ─────────────────────────────────────────────────────── */}
        {loading ? (
          <div className="flex justify-center py-16">
            <LoadingSpinner size={28} />
          </div>
        ) : loadError ? (
          <EmptyState
            icon={AlertTriangle}
            title="Couldn't load uploads"
            subtitle="Something went wrong fetching this data — it may be temporary. Try again in a moment."
            action={{ label: "Retry", onClick: fetchData }}
          />
        ) : uploads.length === 0 && !uploadType ? (
          <EmptyState
            icon={UploadIcon}
            title="No Uploads Yet"
            subtitle="Add files or links to this section."
            action={{
              label: "Upload",
              onClick: () => setShowDropdown(true),
            }}
          />
        ) : (
          <div className="bg-white border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden">
            {uploads.length === 0 ? (
              <p className="text-sm text-[var(--color-text-muted)] text-center py-8">
                No uploads yet.
              </p>
            ) : (
              <ul className="divide-y divide-[var(--color-border)]">
                {uploads.map((upload) => (
                  <li
                    key={upload.id}
                    className="flex items-center gap-4 px-5 py-4 hover:bg-[var(--color-surface-secondary)] transition-colors"
                  >
                    {/* Icon */}
                    <div className="w-9 h-9 rounded-[var(--radius-md)] bg-[var(--color-surface-hover)] flex items-center justify-center shrink-0">
                      <UploadTypeIcon type={upload.upload_type} size={18} />
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-[var(--color-text)] truncate">
                        {upload.original_filename ?? upload.file_url}
                      </p>
                      <div className="flex items-center gap-2 mt-0.5">
                        <Badge variant={upload.upload_type}>
                          {UPLOAD_TYPE_LABELS[upload.upload_type]}
                        </Badge>
                        {upload.file_size_bytes && (
                          <span className="text-xs text-[var(--color-text-muted)]">
                            {formatBytes(upload.file_size_bytes)}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1 shrink-0">
                      {upload.read_url && (
                        <a
                          href={upload.read_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="p-1.5 rounded-[var(--radius-sm)] text-[var(--color-text-muted)] hover:bg-[var(--color-info-bg)] hover:text-[var(--color-info)] transition-colors"
                          aria-label="Open file"
                        >
                          <ExternalLink size={14} />
                        </a>
                      )}
                      <button
                        onClick={() => setDeleteUpload(upload)}
                        className="p-1.5 rounded-[var(--radius-sm)] text-[var(--color-text-muted)] hover:bg-[var(--color-danger-bg)] hover:text-[var(--color-danger)] transition-colors"
                        aria-label="Delete upload"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </PageWrapper>

      <ConfirmDialog
        isOpen={!!deleteUpload}
        onClose={() => setDeleteUpload(null)}
        onConfirm={handleDelete}
        title="Delete Upload"
        message={`Delete "${deleteUpload?.original_filename ?? deleteUpload?.file_url}"? This cannot be undone.`}
        confirmLabel="Delete"
        loading={deleteLoading}
      />
    </AdminLayout>
  );
}
