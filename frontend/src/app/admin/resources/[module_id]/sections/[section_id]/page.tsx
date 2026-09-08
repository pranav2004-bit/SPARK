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
import type { Upload, UploadType, ApiSuccess, PaginatedResponse } from "@/types";


// ── Upload icons ──────────────────────────────────────────────────────────────
function UploadTypeIcon({ type, size = 16 }: { type: UploadType; size?: number }) {
  const icons: Record<UploadType, React.ReactNode> = {
    pdf:           <FileText size={size} className="text-red-500" />,
    audio:         <Music    size={size} className="text-purple-500" />,
    video:         <Video    size={size} className="text-blue-500" />,
    image:         <ImageIcon size={size} className="text-teal-500" />,
    video_link:    <Link2    size={size} className="text-[var(--color-primary)]" />,
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

const ICON_BG: Record<UploadType, string> = {
  pdf:           "var(--color-danger-bg)",
  audio:         "#faf5ff",
  video:         "#eff6ff",
  image:         "#f0fdfa",
  video_link:    "var(--color-primary-light)",
  external_link: "#f8fafc",
};

function splitFilename(name: string): { base: string; ext: string } {
  const lastDot = name.lastIndexOf(".");
  if (lastDot <= 0) return { base: name, ext: "" };
  return { base: name.slice(0, lastDot), ext: name.slice(lastDot) };
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function ResourceSectionUploadsPage() {
  const { module_id, section_id } = useParams<{
    module_id: string;
    section_id: string;
  }>();
  const router = useRouter();
  const { error: toastError, success: toastSuccess } = useToast();
  const { copy: copyLink, copiedId } = useCopyLink();

  // Names for breadcrumb
  const [moduleName,  setModuleName]  = useState<string>("");
  const [sectionName, setSectionName] = useState<string>("");
  const [uploads,     setUploads]     = useState<Upload[]>([]);
  const [loading,     setLoading]     = useState(true);
  const [loadError,   setLoadError]   = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Active upload flow state
  const [uploadType,      setUploadType]      = useState<UploadType | null>(null);
  const [selectedFile,    setSelectedFile]    = useState<File | null>(null);
  const [uploadProgress,  setUploadProgress]  = useState(0);
  const [uploading,       setUploading]       = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [linkUrl,    setLinkUrl]    = useState("");
  const [linkError,  setLinkError]  = useState("");
  const [linkLoading, setLinkLoading] = useState(false);

  // Delete
  const [deleteUpload,  setDeleteUpload]  = useState<Upload | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  // Rename
  const [editingUploadId, setEditingUploadId] = useState<string | null>(null);
  const [editingName,     setEditingName]     = useState("");
  const [editingExt,      setEditingExt]      = useState("");
  const [renameLoading,   setRenameLoading]   = useState(false);
  const [renameError,     setRenameError]     = useState("");

  // ── Resource-specific API base ────────────────────────────────────────────
  const UPLOAD_BASE = `/resources/modules/${module_id}/sections/${section_id}/uploads`;

  const fetchData = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const [moduleRes, uploadsRes] = await Promise.all([
        api.get(`/resources/modules/${module_id}/`),
        api.get<PaginatedResponse<Upload>>(`${UPLOAD_BASE}/`),
      ]);

      // Module detail returns { module, children, sections }
      const detail = moduleRes.data.data;
      setModuleName(detail.module?.name ?? "Module");

      // Find section name from the sections array
      const sec = (detail.sections as Array<{ id: string; name: string }>)
        .find((s) => s.id === section_id);
      setSectionName(sec?.name ?? "Section");

      setUploads(uploadsRes.data.results);
    } catch (err) {
      toastError(getErrorMessage(err));
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [module_id, section_id]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Close dropdown on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // ── Upload type selection ─────────────────────────────────────────────────
  function selectUploadType(type: UploadType) {
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

  function validateFile(file: File, type: UploadType): boolean {
    const ext = "." + file.name.split(".").pop()?.toLowerCase();
    const allowedExts  = ALLOWED_EXTENSIONS[type] ?? [];
    const allowedMimes = ALLOWED_MIME_TYPES[type] ?? [];
    if (allowedExts.length > 0 && !allowedExts.includes(ext)) {
      toastError(`Invalid file type "${ext}". Allowed formats for ${UPLOAD_TYPE_LABELS[type]}: ${allowedExts.join(", ")}`);
      return false;
    }
    if (file.type && allowedMimes.length > 0 && !allowedMimes.includes(file.type.toLowerCase())) {
      toastError(`This file doesn't appear to be a valid ${UPLOAD_TYPE_LABELS[type]}. Please check the file and try again.`);
      return false;
    }
    if (file.size === 0) {
      toastError("This file is empty. Please select a valid file.");
      return false;
    }
    const maxBytes = MAX_FILE_SIZES[type];
    if (maxBytes && file.size > maxBytes) {
      toastError(`File is too large (${formatBytes(file.size)}). Maximum allowed size for ${UPLOAD_TYPE_LABELS[type]} is ${MAX_FILE_SIZE_LABELS[type]}.`);
      return false;
    }
    return true;
  }

  function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file && uploadType) {
      if (uploads.length >= MAX_UPLOADS_PER_SECTION) {
        toastError(`Maximum ${MAX_UPLOADS_PER_SECTION} uploads per section reached.`);
        e.target.value = "";
        return;
      }
      if (validateFile(file, uploadType)) setSelectedFile(file);
    }
    e.target.value = "";
  }

  async function handleFileUpload() {
    if (!selectedFile || !uploadType) return;
    setUploading(true);
    setUploadProgress(0);
    try {
      // Step 1 — get presigned URL
      const { data: presignedResponse } = await api.post<ApiSuccess<{
        upload_url: string;
        file_key: string;
      }>>(
        `/resources/modules/${module_id}/sections/${section_id}/presign/`,
        {
          upload_type: uploadType,
          filename: selectedFile.name,
          content_type: selectedFile.type || "application/octet-stream",
        }
      );
      const presignedData = presignedResponse.data;

      // Step 2 — PUT directly to R2/MinIO (no auth header). Retries on
      // transient network drops — the presigned URL stays valid for its
      // full expiry window, so re-sending the same PUT is safe.
      await putFileWithRetry(presignedData.upload_url, selectedFile, setUploadProgress);

      // Step 3 — confirm / create DB record
      const { data: confirmResponse } = await api.post<ApiSuccess<Upload>>(
        `/resources/modules/${module_id}/sections/${section_id}/confirm/`,
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
    try {
      new URL(linkUrl.trim());
    } catch {
      setLinkError("Please enter a valid URL (include https://).");
      return;
    }
    setLinkLoading(true);
    try {
      const { data: linkResponse } = await api.post<ApiSuccess<Upload>>(
        `/resources/modules/${module_id}/sections/${section_id}/add-link/`,
        { upload_type: uploadType, file_url: linkUrl.trim() }
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
      await api.delete(`${UPLOAD_BASE}/${deleteUpload.id}/`);
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

  // ── Rename helpers ────────────────────────────────────────────────────────
  function getDisplayName(upload: Upload): string {
    if (upload.original_filename) return upload.original_filename;
    if (LINK_UPLOAD_TYPES.includes(upload.upload_type as typeof LINK_UPLOAD_TYPES[number])) {
      try { return new URL(upload.file_url ?? "").hostname.replace(/^www\./, ""); }
      catch { return upload.file_url ?? ""; }
    }
    return upload.file_url ?? "";
  }

  function openRename(upload: Upload) {
    const displayName = getDisplayName(upload);
    const isLink = LINK_UPLOAD_TYPES.includes(upload.upload_type as typeof LINK_UPLOAD_TYPES[number]);
    if (isLink) {
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
    if (!trimmedBase) { setRenameError("Name cannot be empty."); return; }
    const fullName = trimmedBase + editingExt;
    if (fullName.length > 500) { setRenameError("Name is too long (max 500 characters)."); return; }
    setRenameLoading(true);
    setRenameError("");
    try {
      const { data } = await api.patch<ApiSuccess<Upload>>(
        `${UPLOAD_BASE}/${upload.id}/`,
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

  const isFileType = uploadType ? FILE_UPLOAD_TYPES.includes(uploadType as typeof FILE_UPLOAD_TYPES[number]) : false;
  const isLinkType = uploadType ? LINK_UPLOAD_TYPES.includes(uploadType as typeof LINK_UPLOAD_TYPES[number]) : false;

  return (
    <AdminLayout>
      <PageWrapper className="py-6 sm:py-8">

        <PageHeader
          title={sectionName || ""}
          titleSkeleton={loading ? <Skeleton className="h-8 w-48" /> : undefined}
          subtitle={!loading ? `${uploads.length} ${uploads.length === 1 ? "upload" : "uploads"}` : undefined}
          backHref={`/admin/resources/${module_id}`}
          breadcrumb={
            <span>
              <span
                className="cursor-pointer hover:underline"
                onClick={() => router.push("/admin/resources")}
              >
                Resources
              </span>
              {" › "}
              <span
                className="cursor-pointer hover:underline"
                onClick={() => router.push(`/admin/resources/${module_id}`)}
              >
                {moduleName}
              </span>
            </span>
          }
          rightSlot={
            <div className="relative shrink-0" ref={dropdownRef}>
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
                  <div className="px-3 pt-2 pb-1">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.08em]"
                      style={{ color: "var(--color-text-subtle)" }}>
                      Files
                    </p>
                  </div>
                  {FILE_UPLOAD_TYPES.map((type) => (
                    <button
                      key={type}
                      onClick={() => selectUploadType(type)}
                      className="flex items-center gap-2.5 w-full px-3.5 py-2 text-sm text-[var(--color-text)] hover:bg-[var(--color-surface-hover)] transition-colors cursor-pointer"
                    >
                      <UploadTypeIcon type={type} size={14} />
                      {UPLOAD_TYPE_LABELS[type]}
                    </button>
                  ))}
                  <div className="my-1 mx-3" style={{ height: 1, background: "var(--color-border)" }} />
                  <div className="px-3 pt-1 pb-1">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.08em]"
                      style={{ color: "var(--color-text-subtle)" }}>
                      Links
                    </p>
                  </div>
                  {LINK_UPLOAD_TYPES.map((type) => (
                    <button
                      key={type}
                      onClick={() => selectUploadType(type)}
                      className="flex items-center gap-2.5 w-full px-3.5 py-2 text-sm text-[var(--color-text)] hover:bg-[var(--color-surface-hover)] transition-colors cursor-pointer"
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
                    {uploading && (
                      <div className="mb-3">
                        <div className="h-2 bg-[var(--color-accent-light)] rounded-full overflow-hidden">
                          <div
                            className="h-full bg-[var(--color-accent)] transition-all duration-150"
                            style={{ width: `${uploadProgress}%` }}
                          />
                        </div>
                        <p className="text-xs text-[var(--color-text-muted)] mt-1">{uploadProgress}%</p>
                      </div>
                    )}
                    <div className="flex gap-2">
                      <Button variant="secondary" size="sm" onClick={() => setSelectedFile(null)} disabled={uploading}>
                        Change file
                      </Button>
                      <Button size="sm" loading={uploading} onClick={handleFileUpload}>
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
                  onKeyDown={(e) => { if (e.key === "Enter") handleLinkSave(); }}
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
              <p className="text-sm text-[var(--color-text-muted)] text-center py-8">No uploads yet.</p>
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
                    {/* Icon */}
                    <div
                      className="w-9 h-9 rounded-[var(--radius-md)] flex items-center justify-center shrink-0"
                      style={{ background: ICON_BG[upload.upload_type] }}
                    >
                      <UploadTypeIcon type={upload.upload_type} size={18} />
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      {editingUploadId === upload.id ? (
                        <div>
                          <div className="flex items-center gap-1">
                            <input
                              autoFocus
                              value={editingName}
                              onChange={(e) => { setEditingName(e.target.value); setRenameError(""); }}
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
                              <span className="text-sm font-medium shrink-0 select-none"
                                style={{ color: "var(--color-text-muted)" }}>
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
                        <>
                          <p className="text-sm font-medium text-[var(--color-text)] truncate"
                            title={upload.original_filename ?? upload.file_url ?? ""}>
                            {upload.original_filename ?? (() => {
                              try { return new URL(upload.file_url ?? "").hostname.replace(/^www\./, ""); }
                              catch { return upload.file_url ?? ""; }
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
                        <>
                          <p className="text-sm font-medium text-[var(--color-text)] truncate"
                            title={upload.original_filename ?? upload.file_url ?? ""}>
                            {splitFilename(upload.original_filename ?? upload.file_url ?? "").base ||
                              (upload.original_filename ?? upload.file_url)}
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
                        <>
                          <button
                            onClick={() => handleRename(upload)}
                            disabled={renameLoading}
                            className="p-1.5 rounded-[var(--radius-sm)] transition-colors disabled:opacity-50"
                            style={{ color: "var(--color-success)" }}
                            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = "var(--color-success-bg)"; }}
                            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "transparent"; }}
                            aria-label="Save rename"
                          >
                            {renameLoading ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                          </button>
                          <button
                            onClick={cancelRename}
                            disabled={renameLoading}
                            className="p-1.5 rounded-[var(--radius-sm)] transition-colors disabled:opacity-50"
                            style={{ color: "var(--color-text-muted)" }}
                            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = "var(--color-surface-hover)"; }}
                            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "transparent"; }}
                            aria-label="Cancel rename"
                          >
                            <X size={14} />
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            onClick={() => openRename(upload)}
                            className="p-1.5 rounded-[var(--radius-sm)] transition-colors"
                            style={{ color: "var(--color-text-subtle)" }}
                            onMouseEnter={e => {
                              (e.currentTarget as HTMLButtonElement).style.background = "var(--color-surface-hover)";
                              (e.currentTarget as HTMLButtonElement).style.color = "var(--color-text)";
                            }}
                            onMouseLeave={e => {
                              (e.currentTarget as HTMLButtonElement).style.background = "transparent";
                              (e.currentTarget as HTMLButtonElement).style.color = "var(--color-text-subtle)";
                            }}
                            aria-label="Rename upload"
                          >
                            <Pencil size={14} />
                          </button>
                          {(() => {
                            const url = upload.read_url || upload.file_url;
                            if (!url) return null;
                            const isCopied = copiedId === url;
                            return (
                              <button
                                onClick={() => { copyLink(url); toastSuccess("Link copied to clipboard"); }}
                                className="p-1.5 rounded-[var(--radius-sm)] transition-colors"
                                style={{ color: isCopied ? "var(--color-success)" : "var(--color-text-subtle)" }}
                                onMouseEnter={e => {
                                  (e.currentTarget as HTMLButtonElement).style.background = isCopied ? "var(--color-success-bg)" : "var(--color-surface-hover)";
                                  if (!isCopied) (e.currentTarget as HTMLButtonElement).style.color = "var(--color-text)";
                                }}
                                onMouseLeave={e => {
                                  (e.currentTarget as HTMLButtonElement).style.background = "transparent";
                                  if (!isCopied) (e.currentTarget as HTMLButtonElement).style.color = "var(--color-text-subtle)";
                                }}
                                aria-label="Copy link"
                                title="Copy link"
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
                            >
                              <ExternalLink size={14} />
                            </a>
                          )}
                          <button
                            onClick={() => setDeleteUpload(upload)}
                            className="p-1.5 rounded-[var(--radius-sm)] transition-colors"
                            style={{ color: "var(--color-text-subtle)" }}
                            onMouseEnter={e => {
                              (e.currentTarget as HTMLButtonElement).style.background = "var(--color-danger-bg)";
                              (e.currentTarget as HTMLButtonElement).style.color = "var(--color-danger)";
                            }}
                            onMouseLeave={e => {
                              (e.currentTarget as HTMLButtonElement).style.background = "transparent";
                              (e.currentTarget as HTMLButtonElement).style.color = "var(--color-text-subtle)";
                            }}
                            aria-label="Delete upload"
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
