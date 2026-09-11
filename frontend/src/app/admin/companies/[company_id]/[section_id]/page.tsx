"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
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
  Pencil,
  Check,
  Loader2,
  X,
  AlertTriangle,
} from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useCopyLink } from "@/hooks/useCopyLink";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { Badge } from "@/components/ui/Badge";
import { UploadListSkeleton, Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import { putFileWithRetry } from "@/lib/uploadRetry";
import {
  UPLOAD_TYPE_LABELS,
  UPLOAD_ACCEPT_MAP,
  FILE_UPLOAD_TYPES,
  LINK_UPLOAD_TYPES,
  MAX_FILE_SIZES,
  MAX_FILE_SIZE_LABELS,
  ALLOWED_EXTENSIONS,
  ALLOWED_MIME_TYPES,
  MAX_UPLOADS_PER_SECTION,
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

// Per-type icon container background — mirrors the Badge color system
const ICON_BG: Record<UploadType, string> = {
  pdf:           "var(--color-danger-bg)",      // red-50  → matches pdf badge
  audio:         "#faf5ff",                     // purple-50 → matches audio badge
  video:         "#eff6ff",                     // blue-50  → matches video badge
  image:         "#f0fdfa",                     // teal-50  → matches image badge
  video_link:    "var(--color-primary-light)",  // #e8eef5  → matches video_link badge
  external_link: "#f8fafc",                     // slate-50 → matches external_link badge
};

// ── Main page ─────────────────────────────────────────────────────────────────
export default function UploadsPage() {
  const router = useRouter();
  const { company_id, section_id } = useParams<{
    company_id: string;
    section_id: string;
  }>();
  const { error: toastError, success: toastSuccess } = useToast();
  const { copy: copyLink, copiedId } = useCopyLink();

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

  // Rename
  const [editingUploadId, setEditingUploadId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");   // base name only (no extension)
  const [editingExt, setEditingExt] = useState("");     // fixed extension e.g. ".pdf"
  const [renameLoading, setRenameLoading] = useState(false);
  const [renameError, setRenameError] = useState("");

  const fetchData = useCallback(async () => {
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
      toastError(getErrorMessage(err));
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [company_id, section_id, toastError]);

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
    // Guard: enforce per-section upload count limit
    if (uploads.length >= MAX_UPLOADS_PER_SECTION) {
      toastError(`This section has reached the maximum of ${MAX_UPLOADS_PER_SECTION} uploads.`);
      setShowDropdown(false);
      return;
    }

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

  /**
   * Validate a selected file before accepting it.
   * Checks (in order): extension → MIME type → empty file → size limit.
   * Returns true if valid, false + toast if rejected.
   */
  function validateFile(file: File, type: UploadType): boolean {
    const ext = "." + file.name.split(".").pop()?.toLowerCase();
    const allowedExts = ALLOWED_EXTENSIONS[type] ?? [];
    const allowedMimes = ALLOWED_MIME_TYPES[type] ?? [];

    // 1. Extension check — primary gate
    if (allowedExts.length > 0 && !allowedExts.includes(ext)) {
      toastError(
        `Invalid file type "${ext}". Allowed formats for ${UPLOAD_TYPE_LABELS[type]}: ${allowedExts.join(", ")}`
      );
      return false;
    }

    // 2. MIME type check — secondary gate (skip if browser can't determine)
    if (file.type && allowedMimes.length > 0 && !allowedMimes.includes(file.type.toLowerCase())) {
      toastError(
        `This file doesn't appear to be a valid ${UPLOAD_TYPE_LABELS[type]}. Please check the file and try again.`
      );
      return false;
    }

    // 3. Empty file check
    if (file.size === 0) {
      toastError("This file is empty. Please select a valid file.");
      return false;
    }

    // 4. Size limit check
    const maxBytes = MAX_FILE_SIZES[type];
    if (maxBytes && file.size > maxBytes) {
      toastError(
        `File is too large (${formatBytes(file.size)}). Maximum allowed size for ${UPLOAD_TYPE_LABELS[type]} is ${MAX_FILE_SIZE_LABELS[type]}.`
      );
      return false;
    }

    return true;
  }

  function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file && uploadType) {
      // Re-check count limit (race-condition guard)
      if (uploads.length >= MAX_UPLOADS_PER_SECTION) {
        toastError(`Maximum ${MAX_UPLOADS_PER_SECTION} uploads per section reached.`);
        e.target.value = "";
        return;
      }
      if (validateFile(file, uploadType)) {
        setSelectedFile(file);
      }
    }
    // Always reset so same file can be re-selected after removal
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

      // Step 2: PUT file directly to R2/MinIO (raw axios, no auth header).
      // Retries on transient network drops — the presigned URL stays valid
      // for its full expiry window, so re-sending the same PUT is safe.
      await putFileWithRetry(presignedData.upload_url, selectedFile, setUploadProgress);

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
      toastSuccess("File uploaded successfully.");
      setSelectedFile(null);
      setUploadType(null);
    } catch (err) {
      toastError(getErrorMessage(err));
    } finally {
      setUploading(false);
      setUploadProgress(0);
    }
  }

  async function handleLinkSave() {
    if (!linkUrl.trim() || !uploadType) return;
    setLinkError("");

    // Validate URL
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
      toastSuccess("Link saved.");
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
      toastSuccess("Upload deleted.");
      setDeleteUpload(null);
    } catch (err) {
      toastError(getErrorMessage(err));
      setDeleteUpload(null);
    } finally {
      setDeleteLoading(false);
    }
  }

  // ── Rename helpers ────────────────────────────────────────────────────────────

  /** Derive the user-facing display name for an upload — used to prefill the rename input. */
  function getDisplayName(upload: Upload): string {
    if (upload.original_filename) return upload.original_filename;
    if (LINK_UPLOAD_TYPES.includes(upload.upload_type as typeof LINK_UPLOAD_TYPES[number])) {
      try {
        return new URL(upload.file_url ?? "").hostname.replace(/^www\./, "");
      } catch {
        return upload.file_url ?? "";
      }
    }
    return upload.file_url ?? "";
  }

  /**
   * Split a filename into base and extension.
   * - "brochure.pdf"      → { base: "brochure",    ext: ".pdf" }
   * - "my.backup.tar.gz"  → { base: "my.backup.tar", ext: ".gz" }
   * - ".gitignore"        → { base: ".gitignore",  ext: "" }   (dot-files: no ext)
   * - "README"            → { base: "README",      ext: "" }
   */
  function splitFilename(name: string): { base: string; ext: string } {
    const lastDot = name.lastIndexOf(".");
    // lastDot <= 0 covers no-extension AND dot-files like ".gitignore"
    if (lastDot <= 0) return { base: name, ext: "" };
    return { base: name.slice(0, lastDot), ext: name.slice(lastDot) };
  }

  function openRename(upload: Upload) {
    const displayName = getDisplayName(upload);
    const isLink = LINK_UPLOAD_TYPES.includes(upload.upload_type as typeof LINK_UPLOAD_TYPES[number]);
    if (isLink) {
      // Links have no file extension to preserve
      setEditingName(displayName);
      setEditingExt("");
    } else {
      const { base, ext } = splitFilename(displayName);
      setEditingName(base);
      setEditingExt(ext);
    }
    setEditingUploadId(upload.id);
    setRenameError("");
  }

  function cancelRename() {
    setEditingUploadId(null);
    setEditingName("");
    setEditingExt("");
    setRenameError("");
  }

  async function handleRename(upload: Upload) {
    const trimmedBase = editingName.trim();

    if (!trimmedBase) {
      setRenameError("Name cannot be empty.");
      return;
    }

    const fullName = trimmedBase + editingExt;  // rejoin: "brochure" + ".pdf"
    if (fullName.length > 500) {
      setRenameError("Name is too long (max 500 characters).");
      return;
    }

    setRenameLoading(true);
    setRenameError("");
    try {
      const { data } = await api.patch<ApiSuccess<Upload>>(
        `/resources/companies/${company_id}/sections/${section_id}/uploads/${upload.id}/`,
        { original_filename: fullName }
      );
      setUploads((prev) => prev.map((u) => (u.id === upload.id ? data.data : u)));
      toastSuccess("Upload renamed.");
      cancelRename();
    } catch (err) {
      setRenameError(getErrorMessage(err));
    } finally {
      setRenameLoading(false);
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
          title={section?.section_name ?? ""}
          titleSkeleton={loading ? <Skeleton className="h-7 w-44" /> : undefined}
          subtitle={
            !loading
              ? `${uploads.length} ${uploads.length === 1 ? "upload" : "uploads"}`
              : undefined
          }
          backHref={`/admin/companies/${company_id}`}
          breadcrumb={
            <span>
              <span
                className="hover:underline cursor-pointer"
                onClick={() => router.push("/admin/companies")}
              >
                Companies
              </span>
              {" › "}
              {company?.company_name}
            </span>
          }
          rightSlot={
            <div className="relative" ref={dropdownRef}>
              <Button
                variant="primary"
                onClick={() => setShowDropdown((v) => !v)}
                leftIcon={<UploadIcon size={14} />}
                rightIcon={<ChevronDown size={14} />}
              >
                Upload
              </Button>

              {showDropdown && (
                <div className="absolute right-0 top-full mt-1 w-44 bg-white border border-[var(--color-border)] rounded-[var(--radius-md)] shadow-[var(--shadow-lg)] z-20 overflow-hidden">
                  {/* File uploads */}
                  <div className="px-3 pt-2 pb-1">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.08em]" style={{ color: "var(--color-text-subtle)" }}>
                      Files
                    </p>
                  </div>
                  {FILE_UPLOAD_TYPES.map((type) => (
                    <button
                      key={type}
                      onClick={() => selectUploadType(type)}
                      className="flex items-center gap-2.5 w-full px-3.5 py-2 text-sm text-[var(--color-text)] hover:bg-[var(--color-surface-hover)] transition-colors"
                    >
                      <UploadTypeIcon type={type} size={14} />
                      {UPLOAD_TYPE_LABELS[type]}
                    </button>
                  ))}
                  {/* Separator */}
                  <div className="my-1 mx-3" style={{ height: 1, background: "var(--color-border)" }} />
                  {/* Link uploads */}
                  <div className="px-3 pt-1 pb-1">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.08em]" style={{ color: "var(--color-text-subtle)" }}>
                      Links
                    </p>
                  </div>
                  {LINK_UPLOAD_TYPES.map((type) => (
                    <button
                      key={type}
                      onClick={() => selectUploadType(type)}
                      className="flex items-center gap-2.5 w-full px-3.5 py-2 text-sm text-[var(--color-text)] hover:bg-[var(--color-surface-hover)] transition-colors"
                    >
                      <UploadTypeIcon type={type} size={14} />
                      {UPLOAD_TYPE_LABELS[type]}
                    </button>
                  ))}
                  <div className="pb-1" />
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
          <UploadListSkeleton rows={4} />
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
              icon: UploadIcon,
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
                    onClick={() => {
                      if (editingUploadId === upload.id) return;
                      const url = upload.read_url || upload.file_url;
                      if (url) window.open(url, "_blank", "noopener,noreferrer");
                    }}
                    className={`flex items-center gap-4 px-5 py-4 hover:bg-[var(--color-surface-secondary)] transition-colors ${
                      editingUploadId !== upload.id && (upload.read_url || upload.file_url)
                        ? "cursor-pointer"
                        : "cursor-default"
                    }`}
                  >
                    {/* Icon — color-coded background matches badge system */}
                    <div
                      className="w-9 h-9 rounded-[var(--radius-md)] flex items-center justify-center shrink-0"
                      style={{ background: ICON_BG[upload.upload_type] }}
                    >
                      <UploadTypeIcon type={upload.upload_type} size={18} />
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      {editingUploadId === upload.id ? (
                        /* ── Inline rename input ── */
                        <div>
                          <div className="flex items-center gap-1">
                            <input
                              autoFocus
                              value={editingName}
                              onChange={(e) => {
                                setEditingName(e.target.value);
                                setRenameError("");
                              }}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") handleRename(upload);
                                if (e.key === "Escape") cancelRename();
                              }}
                              maxLength={500 - editingExt.length}
                              placeholder="Enter name"
                              disabled={renameLoading}
                              className="min-w-0 flex-1 h-8 px-2.5 text-sm rounded-[var(--radius-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
                              style={{
                                border: `1px solid ${renameError ? "var(--color-danger)" : "var(--color-border)"}`,
                                color: "var(--color-text)",
                                background: "#fff",
                              }}
                            />
                            {editingExt && (
                              <span
                                className="text-sm font-medium shrink-0 select-none"
                                style={{ color: "var(--color-text-muted)" }}
                              >
                                {editingExt}
                              </span>
                            )}
                          </div>
                          {renameError && (
                            <p className="text-xs mt-1" style={{ color: "var(--color-danger)" }}>
                              {renameError}
                            </p>
                          )}
                        </div>
                      ) : LINK_UPLOAD_TYPES.includes(upload.upload_type as typeof LINK_UPLOAD_TYPES[number]) ? (
                        /* ── Link upload display ── */
                        <>
                          <p
                            className="text-sm font-medium text-[var(--color-text)] truncate"
                            title={upload.original_filename ?? upload.file_url ?? ""}
                          >
                            {upload.original_filename ?? (() => {
                              try {
                                return new URL(upload.file_url ?? "").hostname.replace(/^www\./, "");
                              } catch {
                                return upload.file_url ?? "";
                              }
                            })()}
                          </p>
                          <div className="flex items-center gap-2 mt-0.5 min-w-0">
                            <Badge variant={upload.upload_type}>
                              {UPLOAD_TYPE_LABELS[upload.upload_type]}
                            </Badge>
                            <span
                              className="text-xs truncate min-w-0 flex-1"
                              style={{ color: "var(--color-text-subtle)" }}
                              title={upload.file_url ?? ""}
                            >
                              {upload.file_url}
                            </span>
                          </div>
                        </>
                      ) : (
                        /* ── File upload display ── */
                        <>
                          <p
                            className="text-sm font-medium text-[var(--color-text)] truncate"
                            title={upload.original_filename ?? upload.file_url ?? ""}
                          >
                            {splitFilename(upload.original_filename ?? upload.file_url ?? "").base || (upload.original_filename ?? upload.file_url)}
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
                            {upload.scan_status === "pending" && (
                              <span className="inline-flex items-center gap-1 text-xs font-medium" style={{ color: "var(--color-text-subtle)" }}>
                                <Loader2 size={10} className="animate-spin" /> Scanning…
                              </span>
                            )}
                            {upload.scan_status === "error" && (
                              <span className="text-xs font-medium" style={{ color: "var(--color-danger)" }}>
                                Scan failed — hidden from students
                              </span>
                            )}
                          </div>
                        </>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-0.5 shrink-0" onClick={(e) => e.stopPropagation()}>
                      {editingUploadId === upload.id ? (
                        /* ── Confirm / Cancel rename ── */
                        <>
                          <button
                            onClick={() => handleRename(upload)}
                            disabled={renameLoading}
                            className="p-1.5 rounded-[var(--radius-sm)] transition-colors disabled:opacity-50"
                            style={{ color: "var(--color-success)" }}
                            onMouseEnter={(e) => {
                              (e.currentTarget as HTMLButtonElement).style.background = "var(--color-success-bg)";
                            }}
                            onMouseLeave={(e) => {
                              (e.currentTarget as HTMLButtonElement).style.background = "transparent";
                            }}
                            aria-label="Save rename"
                          >
                            {renameLoading
                              ? <Loader2 size={14} className="animate-spin" />
                              : <Check size={14} />
                            }
                          </button>
                          <button
                            onClick={cancelRename}
                            disabled={renameLoading}
                            className="p-1.5 rounded-[var(--radius-sm)] transition-colors disabled:opacity-50"
                            style={{ color: "var(--color-text-muted)" }}
                            onMouseEnter={(e) => {
                              (e.currentTarget as HTMLButtonElement).style.background = "var(--color-surface-hover)";
                            }}
                            onMouseLeave={(e) => {
                              (e.currentTarget as HTMLButtonElement).style.background = "transparent";
                            }}
                            aria-label="Cancel rename"
                          >
                            <X size={14} />
                          </button>
                        </>
                      ) : (
                        /* ── Normal row actions ── */
                        <>
                          <button
                            onClick={() => openRename(upload)}
                            className="p-1.5 rounded-[var(--radius-sm)] transition-colors"
                            style={{ color: "var(--color-text-subtle)" }}
                            onMouseEnter={(e) => {
                              (e.currentTarget as HTMLButtonElement).style.background = "var(--color-surface-hover)";
                              (e.currentTarget as HTMLButtonElement).style.color = "var(--color-text)";
                            }}
                            onMouseLeave={(e) => {
                              (e.currentTarget as HTMLButtonElement).style.background = "transparent";
                              (e.currentTarget as HTMLButtonElement).style.color = "var(--color-text-subtle)";
                            }}
                            aria-label="Rename upload"
                            title="Rename"
                          >
                            <Pencil size={14} />
                          </button>
                          {(() => {
                            const url = upload.read_url || upload.file_url;
                            if (!url) return null;
                            const isCopied = copiedId === url;
                            return (
                              <button
                                onClick={() => {
                                  copyLink(url);
                                  toastSuccess("Link copied to clipboard");
                                }}
                                className="p-1.5 rounded-[var(--radius-sm)] transition-colors"
                                style={{ color: isCopied ? "var(--color-success)" : "var(--color-text-subtle)" }}
                                onMouseEnter={(e) => {
                                  (e.currentTarget as HTMLButtonElement).style.background = isCopied ? "var(--color-success-bg)" : "var(--color-surface-hover)";
                                  if (!isCopied) (e.currentTarget as HTMLButtonElement).style.color = "var(--color-text)";
                                }}
                                onMouseLeave={(e) => {
                                  (e.currentTarget as HTMLButtonElement).style.background = "transparent";
                                  if (!isCopied) (e.currentTarget as HTMLButtonElement).style.color = "var(--color-text-subtle)";
                                }}
                                aria-label="Copy file link"
                                title="Copy file link"
                              >
                                {isCopied ? <Check size={14} /> : <Link2 size={14} />}
                              </button>
                            );
                          })()}
                          {upload.read_url && (
                            <a
                              href={upload.read_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="p-1.5 rounded-[var(--radius-sm)] text-[var(--color-text-muted)] hover:bg-[var(--color-info-bg)] hover:text-[var(--color-info)] transition-colors"
                              aria-label="Open file"
                              title="Open in new tab"
                            >
                              <ExternalLink size={14} />
                            </a>
                          )}
                          <button
                            onClick={() => setDeleteUpload(upload)}
                            className="p-1.5 rounded-[var(--radius-sm)] transition-colors"
                            style={{ color: "var(--color-text-subtle)" }}
                            onMouseEnter={(e) => {
                              (e.currentTarget as HTMLButtonElement).style.background = "var(--color-danger-bg)";
                              (e.currentTarget as HTMLButtonElement).style.color = "var(--color-danger)";
                            }}
                            onMouseLeave={(e) => {
                              (e.currentTarget as HTMLButtonElement).style.background = "transparent";
                              (e.currentTarget as HTMLButtonElement).style.color = "var(--color-text-subtle)";
                            }}
                            aria-label="Delete upload"
                            title="Delete"
                          >
                            <Trash2 size={14} />
                          </button>
                        </>
                      )}
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
