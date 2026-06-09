"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { createPortal } from "react-dom";
import {
  X,
  Upload,
  FileText,
  Download,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ChevronDown,
  Loader2,
  Users,
} from "lucide-react";
import api, { getErrorMessage } from "@/lib/api";
import { DEPARTMENTS } from "@/lib/constants";
import type { Batch } from "@/types";

// ── Types ─────────────────────────────────────────────────────────────────────

interface ParseResult {
  validIds: string[];
  skippedEmpty: number;
  duplicatesInFile: number;
  skippedInvalid: number;
}

interface BulkResultRow {
  student_id: string;
  status: "created" | "rejected";
  reason?: string;
}

interface BulkImportResult {
  total: number;
  created: number;
  rejected: number;
  results: BulkResultRow[];
}

type ModalStep = "configure" | "importing" | "results";

interface BulkImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onImportComplete: () => void;
  batches: Batch[];
}

// ── CSV helpers ───────────────────────────────────────────────────────────────

/** Extract the first column value from a CSV line (handles RFC-4180 quoting). */
function parseFirstColumn(line: string): string {
  const trimmed = line.trim();
  if (!trimmed) return "";
  if (trimmed.startsWith('"')) {
    const closeIdx = trimmed.indexOf('"', 1);
    const raw = closeIdx === -1 ? trimmed.slice(1) : trimmed.slice(1, closeIdx);
    return raw.replace(/""/g, '"').trim();
  }
  const commaIdx = trimmed.indexOf(",");
  return commaIdx === -1 ? trimmed : trimmed.slice(0, commaIdx).trim();
}

/** Parse a CSV text blob → list of sanitised, uppercased student IDs. */
function parseCSVText(text: string): ParseResult {
  // Strip UTF-8 BOM that Excel adds to CSV exports
  const clean = text.replace(/^\uFEFF/, "");
  const lines = clean.split(/\r\n|\r|\n/);

  const validIds: string[] = [];
  let skippedEmpty = 0;
  let duplicatesInFile = 0;
  let skippedInvalid = 0;
  const seen = new Set<string>();
  let headerConsumed = false;

  for (const line of lines) {
    const raw = parseFirstColumn(line);

    if (!raw) {
      // Count non-blank lines as empty (blank lines don't count)
      if (line.trim()) skippedEmpty++;
      continue;
    }

    // Skip the header row (case-insensitive)
    if (!headerConsumed && raw.toLowerCase() === "student_id") {
      headerConsumed = true;
      continue;
    }

    const id = raw.toUpperCase();

    // Hard length limit
    if (id.length > 100) {
      skippedInvalid++;
      continue;
    }

    // Must contain at least one alphanumeric character
    if (!/[A-Z0-9]/.test(id)) {
      skippedInvalid++;
      continue;
    }

    // In-file duplicate
    if (seen.has(id)) {
      duplicatesInFile++;
      continue;
    }

    seen.add(id);
    validIds.push(id);
  }

  return { validIds, skippedEmpty, duplicatesInFile, skippedInvalid };
}

/** Trigger a CSV download in the browser without any external dependency. */
function triggerCSVDownload(content: string, filename: string) {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Short delay before revoke so Safari has time to initiate the download
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function downloadTemplate() {
  const csv =
    "student_id\n" +
    "A23126551001\n" +
    "A23126551002\n" +
    "A23126551003\n";
  triggerCSVDownload(csv, "student_import_template.csv");
}

function exportRejected(rows: BulkResultRow[]) {
  const rejected = rows.filter((r) => r.status === "rejected");
  if (!rejected.length) return;
  const header = "student_id,reason\n";
  const body = rejected
    .map((r) => `${r.student_id},"${(r.reason ?? "").replace(/"/g, '""')}"`)
    .join("\n");
  // Include BOM so Excel opens it correctly
  triggerCSVDownload("\uFEFF" + header + body, "rejected_students.csv");
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatCard({
  value,
  label,
  color,
}: {
  value: number;
  label: string;
  color: "neutral" | "success" | "danger";
}) {
  const styles: Record<typeof color, React.CSSProperties> = {
    neutral: {
      background: "var(--color-surface-secondary)",
      border: "1px solid var(--color-border)",
      color: "var(--color-text)",
    },
    success: {
      background: "var(--color-success-bg, #f0fdf4)",
      border: "1px solid var(--color-success, #22c55e)",
      color: "var(--color-success, #16a34a)",
    },
    danger: {
      background: "var(--color-danger-bg, #fef2f2)",
      border: "1px solid var(--color-danger, #ef4444)",
      color: "var(--color-danger, #dc2626)",
    },
  };

  return (
    <div
      className="flex-1 rounded-xl px-4 py-3 text-center"
      style={styles[color]}
    >
      <p
        className="text-2xl font-bold tabular-nums"
        style={{ color: styles[color].color }}
      >
        {value.toLocaleString()}
      </p>
      <p className="text-xs font-medium mt-0.5" style={{ color: "var(--color-text-muted)" }}>
        {label}
      </p>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function BulkImportModal({
  isOpen,
  onClose,
  onImportComplete,
  batches,
}: BulkImportModalProps) {
  // Step state
  const [step, setStep] = useState<ModalStep>("configure");

  // Configure step state
  const [file, setFile] = useState<File | null>(null);
  const [parseResult, setParseResult] = useState<ParseResult | null>(null);
  const [department, setDepartment] = useState("");
  const [batchId, setBatchId] = useState("");
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Results step state
  const [importResult, setImportResult] = useState<BulkImportResult | null>(null);
  const [apiError, setApiError] = useState("");

  // ── Reset when modal opens/closes ──────────────────────────────────────────
  useEffect(() => {
    if (!isOpen) {
      // Delay reset so close animation can finish
      const t = setTimeout(() => {
        setStep("configure");
        setFile(null);
        setParseResult(null);
        setDepartment("");
        setBatchId("");
        setIsDragOver(false);
        setImportResult(null);
        setApiError("");
      }, 200);
      return () => clearTimeout(t);
    }
  }, [isOpen]);

  // ── ESC key + body scroll lock ─────────────────────────────────────────────
  useEffect(() => {
    if (!isOpen) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && step !== "importing") handleClose();
    };
    document.addEventListener("keydown", handleKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKey);
      document.body.style.overflow = "";
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, step]);

  // ── File handling ──────────────────────────────────────────────────────────

  const processFile = useCallback((f: File) => {
    // Type check
    if (!f.name.toLowerCase().endsWith(".csv")) {
      setApiError("Only CSV files are supported. Please download the template and save as .csv");
      return;
    }
    // Size check: 10 MB
    if (f.size > 10 * 1024 * 1024) {
      setApiError("File is too large. Maximum size is 10 MB.");
      return;
    }
    setApiError("");
    setFile(f);

    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      if (!text) {
        setParseResult({ validIds: [], skippedEmpty: 0, duplicatesInFile: 0, skippedInvalid: 0 });
        return;
      }
      setParseResult(parseCSVText(text));
    };
    reader.onerror = () => {
      setApiError("Failed to read file. Please try again.");
    };
    reader.readAsText(f, "utf-8");
  }, []);

  function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) processFile(f);
    // Reset input so the same file can be re-selected after removal
    e.target.value = "";
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) processFile(f);
  }

  function removeFile() {
    setFile(null);
    setParseResult(null);
    setApiError("");
  }

  // ── Import ─────────────────────────────────────────────────────────────────

  async function handleImport() {
    if (!parseResult || !department || !batchId) return;

    setStep("importing");
    setApiError("");

    try {
      const res = await api.post<{ data: BulkImportResult }>(
        "/admin/students/bulk-create/",
        {
          student_ids: parseResult.validIds,
          department,
          batch_id: batchId,
        }
      );
      setImportResult(res.data.data);
      setStep("results");
    } catch (err) {
      setApiError(getErrorMessage(err));
      setStep("configure");
    }
  }

  // ── Close ──────────────────────────────────────────────────────────────────

  function handleClose() {
    if (step === "importing") return; // prevent accidental close
    if (step === "results" && importResult && importResult.created > 0) {
      onImportComplete();
    }
    onClose();
  }

  // ── Derived ────────────────────────────────────────────────────────────────

  const canImport =
    !!parseResult &&
    parseResult.validIds.length > 0 &&
    !!department &&
    !!batchId;

  const rejectedRows = importResult?.results.filter((r) => r.status === "rejected") ?? [];

  // ── Render ─────────────────────────────────────────────────────────────────

  if (!isOpen) return null;

  const modalTitle =
    step === "results"
      ? importResult?.rejected === 0
        ? "Import Complete ✓"
        : "Import Complete"
      : "Import Students";

  const content = (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={step !== "importing" ? handleClose : undefined}
        aria-hidden="true"
      />

      {/* Panel */}
      <div
        className="relative w-full bg-white rounded-2xl flex flex-col"
        style={{
          maxWidth: 580,
          maxHeight: "90vh",
          boxShadow: "0 24px 64px rgba(0,0,0,0.18)",
        }}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="bulk-modal-title"
      >
        {/* ── Header ──────────────────────────────────────────────────── */}
        <div
          className="flex items-center justify-between px-6 py-4 shrink-0"
          style={{ borderBottom: "1px solid var(--color-border)" }}
        >
          <div className="flex items-center gap-2.5">
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
              style={{ background: "var(--color-primary-light, #eef2ff)", color: "var(--color-primary)" }}
            >
              <Users size={16} />
            </div>
            <h2
              id="bulk-modal-title"
              className="text-base font-semibold"
              style={{ color: "var(--color-text)" }}
            >
              {modalTitle}
            </h2>
          </div>
          {step !== "importing" && (
            <button
              onClick={handleClose}
              className="p-1.5 rounded-lg transition-colors"
              style={{ color: "var(--color-text-subtle)" }}
              onMouseEnter={e => {
                (e.currentTarget as HTMLButtonElement).style.background = "var(--color-surface-secondary)";
                (e.currentTarget as HTMLButtonElement).style.color = "var(--color-text)";
              }}
              onMouseLeave={e => {
                (e.currentTarget as HTMLButtonElement).style.background = "transparent";
                (e.currentTarget as HTMLButtonElement).style.color = "var(--color-text-subtle)";
              }}
              aria-label="Close"
            >
              <X size={16} />
            </button>
          )}
        </div>

        {/* ── Body ────────────────────────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto px-6 py-5">

          {/* ═══════════════════════════════ STEP: configure ═══════════ */}
          {step === "configure" && (
            <div className="space-y-5">

              {/* Template download */}
              <div
                className="flex items-center justify-between rounded-xl px-4 py-3"
                style={{
                  background: "var(--color-surface-secondary)",
                  border: "1px solid var(--color-border)",
                }}
              >
                <div>
                  <p className="text-sm font-semibold" style={{ color: "var(--color-text)" }}>
                    Download template
                  </p>
                  <p className="text-xs mt-0.5" style={{ color: "var(--color-text-muted)" }}>
                    Fill student IDs in the{" "}
                    <code className="font-mono">student_id</code> column, then upload below.
                  </p>
                </div>
                <button
                  onClick={downloadTemplate}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all shrink-0 ml-4"
                  style={{
                    background: "var(--color-primary)",
                    color: "#fff",
                  }}
                  onMouseEnter={e => {
                    (e.currentTarget as HTMLButtonElement).style.background = "var(--color-primary-hover, #1e293b)";
                  }}
                  onMouseLeave={e => {
                    (e.currentTarget as HTMLButtonElement).style.background = "var(--color-primary)";
                  }}
                >
                  <Download size={12} />
                  Template
                </button>
              </div>

              {/* File drop zone */}
              <div>
                <p className="text-sm font-semibold mb-2" style={{ color: "var(--color-text)" }}>
                  Upload CSV file
                </p>

                {file ? (
                  /* File selected — show summary */
                  <div
                    className="rounded-xl px-4 py-3"
                    style={{
                      border: "1px solid var(--color-border)",
                      background: "#fff",
                    }}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-2.5">
                        <div
                          className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
                          style={{
                            background: "var(--color-success-bg, #f0fdf4)",
                            color: "var(--color-success, #16a34a)",
                          }}
                        >
                          <FileText size={16} />
                        </div>
                        <div className="min-w-0">
                          <p
                            className="text-sm font-medium truncate"
                            style={{ color: "var(--color-text)" }}
                          >
                            {file.name}
                          </p>
                          <p className="text-xs mt-0.5" style={{ color: "var(--color-text-muted)" }}>
                            {(file.size / 1024).toFixed(1)} KB
                          </p>
                        </div>
                      </div>
                      <button
                        onClick={removeFile}
                        className="p-1 rounded-md shrink-0 transition-colors"
                        style={{ color: "var(--color-text-subtle)" }}
                        onMouseEnter={e => {
                          (e.currentTarget as HTMLButtonElement).style.color = "var(--color-danger)";
                          (e.currentTarget as HTMLButtonElement).style.background = "var(--color-danger-bg)";
                        }}
                        onMouseLeave={e => {
                          (e.currentTarget as HTMLButtonElement).style.color = "var(--color-text-subtle)";
                          (e.currentTarget as HTMLButtonElement).style.background = "transparent";
                        }}
                        title="Remove file"
                      >
                        <X size={14} />
                      </button>
                    </div>

                    {/* Parse summary */}
                    {parseResult && (
                      <div
                        className="mt-3 pt-3 space-y-1.5"
                        style={{ borderTop: "1px solid var(--color-border)" }}
                      >
                        <div className="flex items-center gap-2">
                          {parseResult.validIds.length > 0 ? (
                            <CheckCircle2 size={13} style={{ color: "var(--color-success, #16a34a)", flexShrink: 0 }} />
                          ) : (
                            <XCircle size={13} style={{ color: "var(--color-danger)", flexShrink: 0 }} />
                          )}
                          <span className="text-xs" style={{ color: "var(--color-text)" }}>
                            <strong>{parseResult.validIds.length.toLocaleString()}</strong> student ID
                            {parseResult.validIds.length !== 1 ? "s" : ""} ready to import
                          </span>
                        </div>
                        {parseResult.duplicatesInFile > 0 && (
                          <div className="flex items-center gap-2">
                            <AlertTriangle size={13} style={{ color: "var(--color-warning, #f59e0b)", flexShrink: 0 }} />
                            <span className="text-xs" style={{ color: "var(--color-text-muted)" }}>
                              {parseResult.duplicatesInFile} duplicate
                              {parseResult.duplicatesInFile !== 1 ? "s" : ""} removed (kept first occurrence)
                            </span>
                          </div>
                        )}
                        {parseResult.skippedInvalid > 0 && (
                          <div className="flex items-center gap-2">
                            <AlertTriangle size={13} style={{ color: "var(--color-warning, #f59e0b)", flexShrink: 0 }} />
                            <span className="text-xs" style={{ color: "var(--color-text-muted)" }}>
                              {parseResult.skippedInvalid} row
                              {parseResult.skippedInvalid !== 1 ? "s" : ""} skipped (invalid format)
                            </span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ) : (
                  /* Drop zone */
                  <div
                    onClick={() => fileInputRef.current?.click()}
                    onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
                    onDragLeave={() => setIsDragOver(false)}
                    onDrop={handleDrop}
                    className="cursor-pointer rounded-xl flex flex-col items-center justify-center gap-2 py-8 transition-all"
                    style={{
                      border: `2px dashed ${isDragOver ? "var(--color-accent)" : "var(--color-border)"}`,
                      background: isDragOver ? "var(--color-accent-light, #eff6ff)" : "var(--color-surface-secondary)",
                    }}
                  >
                    <Upload
                      size={24}
                      style={{
                        color: isDragOver ? "var(--color-accent)" : "var(--color-text-subtle)",
                      }}
                    />
                    <div className="text-center">
                      <p
                        className="text-sm font-medium"
                        style={{ color: isDragOver ? "var(--color-accent)" : "var(--color-text)" }}
                      >
                        Drop CSV here or{" "}
                        <span style={{ color: "var(--color-accent)", textDecoration: "underline" }}>
                          browse
                        </span>
                      </p>
                      <p className="text-xs mt-1" style={{ color: "var(--color-text-subtle)" }}>
                        .csv only · max 10 MB · up to 2,000 IDs
                      </p>
                    </div>
                  </div>
                )}

                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv"
                  className="hidden"
                  onChange={handleFileInput}
                />
              </div>

              {/* Department + Batch row */}
              <div className="grid grid-cols-2 gap-3">
                {/* Department */}
                <div>
                  <label
                    className="block text-sm font-semibold mb-1.5"
                    style={{ color: "var(--color-text)" }}
                  >
                    Department <span style={{ color: "var(--color-danger)" }}>*</span>
                  </label>
                  <div className="relative">
                    <select
                      value={department}
                      onChange={(e) => setDepartment(e.target.value)}
                      className="w-full h-9 pl-3 pr-8 text-sm rounded-[var(--radius-md)] border bg-white appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
                      style={{
                        borderColor: "var(--color-border)",
                        color: "var(--color-text)",
                      }}
                    >
                      <option value="" disabled>Select department</option>
                      {DEPARTMENTS.map((d) => (
                        <option key={d} value={d}>{d}</option>
                      ))}
                    </select>
                    <ChevronDown
                      size={14}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none"
                      style={{ color: "var(--color-text-muted)" }}
                    />
                  </div>
                </div>

                {/* Batch */}
                <div>
                  <label
                    className="block text-sm font-semibold mb-1.5"
                    style={{ color: "var(--color-text)" }}
                  >
                    Batch <span style={{ color: "var(--color-danger)" }}>*</span>
                  </label>
                  <div className="relative">
                    <select
                      value={batchId}
                      onChange={(e) => setBatchId(e.target.value)}
                      className="w-full h-9 pl-3 pr-8 text-sm rounded-[var(--radius-md)] border bg-white appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
                      style={{
                        borderColor: "var(--color-border)",
                        color: "var(--color-text)",
                      }}
                    >
                      <option value="" disabled>Select batch</option>
                      {batches.map((b) => (
                        <option key={b.id} value={b.id}>{b.batch_name}</option>
                      ))}
                    </select>
                    <ChevronDown
                      size={14}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none"
                      style={{ color: "var(--color-text-muted)" }}
                    />
                  </div>
                </div>
              </div>

              {/* API / file error */}
              {apiError && (
                <div
                  className="flex items-start gap-2.5 rounded-xl px-4 py-3 text-sm"
                  style={{
                    background: "var(--color-danger-bg)",
                    color: "var(--color-danger)",
                    border: "1px solid var(--color-danger)",
                  }}
                >
                  <XCircle size={14} className="shrink-0 mt-0.5" />
                  {apiError}
                </div>
              )}
            </div>
          )}

          {/* ═══════════════════════════════ STEP: importing ═══════════ */}
          {step === "importing" && (
            <div className="flex flex-col items-center justify-center py-12 gap-4">
              <Loader2
                size={36}
                className="animate-spin"
                style={{ color: "var(--color-primary)" }}
              />
              <div className="text-center">
                <p className="text-sm font-semibold" style={{ color: "var(--color-text)" }}>
                  Importing {parseResult?.validIds.length.toLocaleString()} students…
                </p>
                <p className="text-xs mt-1" style={{ color: "var(--color-text-muted)" }}>
                  Please wait — do not close this window.
                </p>
              </div>
            </div>
          )}

          {/* ═══════════════════════════════ STEP: results ═══════════ */}
          {step === "results" && importResult && (
            <div className="space-y-5">

              {/* Stat cards */}
              <div className="flex gap-3">
                <StatCard value={importResult.total} label="Total" color="neutral" />
                <StatCard value={importResult.created} label="Created" color="success" />
                <StatCard value={importResult.rejected} label="Rejected" color={importResult.rejected > 0 ? "danger" : "neutral"} />
              </div>

              {/* Rejected table */}
              {rejectedRows.length > 0 && (
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-sm font-semibold" style={{ color: "var(--color-text)" }}>
                      Rejected students ({rejectedRows.length.toLocaleString()})
                    </p>
                    <button
                      onClick={() => exportRejected(importResult.results)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all"
                      style={{
                        background: "var(--color-surface-secondary)",
                        color: "var(--color-text-muted)",
                        border: "1px solid var(--color-border)",
                      }}
                      onMouseEnter={e => {
                        (e.currentTarget as HTMLButtonElement).style.background = "var(--color-primary)";
                        (e.currentTarget as HTMLButtonElement).style.color = "#fff";
                        (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--color-primary)";
                      }}
                      onMouseLeave={e => {
                        (e.currentTarget as HTMLButtonElement).style.background = "var(--color-surface-secondary)";
                        (e.currentTarget as HTMLButtonElement).style.color = "var(--color-text-muted)";
                        (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--color-border)";
                      }}
                    >
                      <Download size={12} />
                      Export CSV
                    </button>
                  </div>

                  <div
                    className="rounded-xl overflow-hidden"
                    style={{ border: "1px solid var(--color-border)" }}
                  >
                    {/* Table header */}
                    <div
                      className="grid text-[11px] font-semibold uppercase tracking-[0.07em] px-4 py-2"
                      style={{
                        gridTemplateColumns: "160px 1fr",
                        background: "var(--color-surface-secondary)",
                        borderBottom: "1px solid var(--color-border)",
                        color: "var(--color-text-subtle)",
                      }}
                    >
                      <span>Student ID</span>
                      <span>Reason</span>
                    </div>

                    {/* Table rows — scrollable */}
                    <div className="overflow-y-auto" style={{ maxHeight: 260 }}>
                      {rejectedRows.map((row, idx) => (
                        <div
                          key={`${row.student_id}-${idx}`}
                          className="grid px-4 py-2.5 text-sm transition-colors"
                          style={{
                            gridTemplateColumns: "160px 1fr",
                            borderTop: idx > 0 ? "1px solid var(--color-border)" : undefined,
                            background: "#fff",
                          }}
                          onMouseEnter={(e) => {
                            (e.currentTarget as HTMLDivElement).style.background =
                              "var(--color-surface-secondary)";
                          }}
                          onMouseLeave={(e) => {
                            (e.currentTarget as HTMLDivElement).style.background = "#fff";
                          }}
                        >
                          <span
                            className="font-mono text-xs font-semibold"
                            style={{ color: "var(--color-danger)" }}
                          >
                            {row.student_id}
                          </span>
                          <span style={{ color: "var(--color-text-muted)" }}>
                            {row.reason ?? "Unknown error"}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* All-success message */}
              {importResult.rejected === 0 && (
                <div
                  className="flex items-center gap-3 rounded-xl px-4 py-3"
                  style={{
                    background: "var(--color-success-bg, #f0fdf4)",
                    border: "1px solid var(--color-success, #22c55e)",
                  }}
                >
                  <CheckCircle2 size={18} style={{ color: "var(--color-success, #16a34a)", flexShrink: 0 }} />
                  <p className="text-sm font-medium" style={{ color: "var(--color-success, #16a34a)" }}>
                    All {importResult.created.toLocaleString()} students created successfully!
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Footer ──────────────────────────────────────────────────── */}
        {step !== "importing" && (
          <div
            className="flex items-center justify-end gap-3 px-6 py-4 shrink-0"
            style={{ borderTop: "1px solid var(--color-border)" }}
          >
            {step === "configure" && (
              <>
                <button
                  onClick={handleClose}
                  className="px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                  style={{
                    color: "var(--color-text-muted)",
                    border: "1px solid var(--color-border)",
                    background: "#fff",
                  }}
                  onMouseEnter={e => {
                    (e.currentTarget as HTMLButtonElement).style.background = "var(--color-surface-secondary)";
                  }}
                  onMouseLeave={e => {
                    (e.currentTarget as HTMLButtonElement).style.background = "#fff";
                  }}
                >
                  Cancel
                </button>
                <button
                  onClick={handleImport}
                  disabled={!canImport}
                  className="px-5 py-2 rounded-lg text-sm font-semibold transition-all"
                  style={{
                    background: canImport ? "var(--color-primary)" : "var(--color-border)",
                    color: canImport ? "#fff" : "var(--color-text-subtle)",
                    cursor: canImport ? "pointer" : "not-allowed",
                  }}
                  onMouseEnter={e => {
                    if (!canImport) return;
                    (e.currentTarget as HTMLButtonElement).style.background = "var(--color-primary-hover, #1e293b)";
                  }}
                  onMouseLeave={e => {
                    if (!canImport) return;
                    (e.currentTarget as HTMLButtonElement).style.background = "var(--color-primary)";
                  }}
                >
                  Import{" "}
                  {parseResult && parseResult.validIds.length > 0
                    ? `${parseResult.validIds.length.toLocaleString()} Students`
                    : "Students"}
                </button>
              </>
            )}

            {step === "results" && (
              <button
                onClick={handleClose}
                className="px-6 py-2 rounded-lg text-sm font-semibold text-white transition-all"
                style={{ background: "var(--color-primary)" }}
                onMouseEnter={e => {
                  (e.currentTarget as HTMLButtonElement).style.background = "var(--color-primary-hover, #1e293b)";
                }}
                onMouseLeave={e => {
                  (e.currentTarget as HTMLButtonElement).style.background = "var(--color-primary)";
                }}
              >
                Done
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );

  return createPortal(content, document.body);
}
