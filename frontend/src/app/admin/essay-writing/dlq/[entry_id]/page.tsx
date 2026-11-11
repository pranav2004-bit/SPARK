"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { RefreshCcw, CheckCircle2, AlertTriangle } from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { ApiSuccess, EssayDLQEntryDetail } from "@/types";

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "medium" });
}

function ReasonField({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <textarea
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      rows={3}
      className="w-full rounded-[var(--radius-md)] border px-3 py-2 text-sm outline-none transition-colors resize-none"
      style={{ borderColor: "var(--color-border)", color: "var(--color-text)" }}
    />
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide mb-1" style={{ color: "var(--color-text-subtle)" }}>{label}</p>
      <div className="text-sm" style={{ color: "var(--color-text)" }}>{children}</div>
    </div>
  );
}

export default function AdminDLQDetailPage() {
  const { entry_id } = useParams<{ entry_id: string }>();
  const toast = useToast();

  const [entry, setEntry] = useState<EssayDLQEntryDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  const [actionKind, setActionKind] = useState<"retry" | "resolve" | null>(null);
  const [actionReason, setActionReason] = useState("");
  const [actionSubmitting, setActionSubmitting] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setLoadError(false);
    api.get<ApiSuccess<EssayDLQEntryDetail>>(`/essay/admin/dlq/${entry_id}/`)
      .then(res => setEntry(res.data.data))
      .catch(err => { toast.error(getErrorMessage(err)); setLoadError(true); })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entry_id]);

  useEffect(load, [load]);

  function openAction(kind: "retry" | "resolve") {
    setActionKind(kind);
    setActionReason("");
  }

  async function submitAction() {
    if (!actionKind || !entry) return;
    if (!actionReason.trim()) {
      toast.error(`A reason is required to ${actionKind} a DLQ entry.`);
      return;
    }
    setActionSubmitting(true);
    try {
      const path = actionKind === "retry"
        ? `/essay/admin/dlq/${entry.id}/retry/`
        : `/essay/admin/dlq/${entry.id}/resolve/`;
      const res = await api.post<ApiSuccess<null>>(path, { reason: actionReason.trim() });
      toast.success(res.data.message ?? "Done.");
      setActionKind(null);
      load();
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setActionSubmitting(false);
    }
  }

  return (
    <AdminLayout>
      <PageWrapper>
        <PageHeader
          title={entry?.task_name ?? "DLQ Entry"}
          subtitle="Full original task payload for diagnosing this failure."
          backHref="/admin/essay-writing/dlq"
          rightSlot={entry && (
            <div className="flex items-center gap-2">
              <Button variant="secondary" leftIcon={<CheckCircle2 size={14} />} disabled={entry.resolved} onClick={() => openAction("resolve")}>
                Resolve
              </Button>
              <Button variant="primary" leftIcon={<RefreshCcw size={14} />} disabled={entry.resolved} onClick={() => openAction("retry")}>
                Retry
              </Button>
            </div>
          )}
        />

        {loading ? (
          <div className="space-y-4">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-40 w-full" />
          </div>
        ) : loadError || !entry ? (
          <EmptyState icon={AlertTriangle} title="Couldn't load this entry" subtitle="Please try again." />
        ) : (
          <div className="space-y-4">
            <div className="rounded-[var(--radius-xl)] p-5 grid grid-cols-2 sm:grid-cols-3 gap-4" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
              <Field label="Status">
                <span
                  className="text-[11px] font-semibold px-2 py-0.5 rounded-full"
                  style={entry.resolved ? { background: "#F3F4F6", color: "#6B7280" } : { background: "#FEF2F2", color: "#DC2626" }}
                >
                  {entry.resolved ? "Resolved" : "Unresolved"}
                </span>
              </Field>
              <Field label="Attempts">{entry.attempts}</Field>
              <Field label="Automatic sweeper retries">{entry.dlq_retry_count}</Field>
              <Field label="Created">{formatDateTime(entry.created_at)}</Field>
              <Field label="Resolved">{formatDateTime(entry.resolved_at)}</Field>
              <Field label="Task ID">
                <span className="font-mono text-xs">{entry.task_id || "—"}</span>
              </Field>
            </div>

            <div className="rounded-[var(--radius-xl)] p-5" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
              <p className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--color-text-subtle)" }}>Error</p>
              <p className="text-sm" style={{ color: "var(--color-text)" }}>{entry.error}</p>
            </div>

            <div className="rounded-[var(--radius-xl)] p-5" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
              <p className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--color-text-subtle)" }}>Args / Kwargs</p>
              <pre className="text-xs rounded-[var(--radius-md)] p-3 overflow-x-auto" style={{ background: "var(--color-surface-subtle)", color: "var(--color-text)" }}>
                {JSON.stringify({ args: entry.args, kwargs: entry.kwargs }, null, 2)}
              </pre>
            </div>

            {entry.traceback && (
              <div className="rounded-[var(--radius-xl)] p-5" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}>
                <p className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--color-text-subtle)" }}>Traceback</p>
                <pre className="text-xs rounded-[var(--radius-md)] p-3 overflow-x-auto whitespace-pre-wrap" style={{ background: "var(--color-surface-subtle)", color: "var(--color-text)" }}>
                  {entry.traceback}
                </pre>
              </div>
            )}
          </div>
        )}

        <Modal
          isOpen={!!actionKind}
          onClose={() => !actionSubmitting && setActionKind(null)}
          title={actionKind === "retry" ? "Retry DLQ Entry" : "Resolve DLQ Entry"}
          maxWidth="sm"
        >
          <div className="space-y-3">
            <p className="text-sm" style={{ color: "var(--color-text-subtle)" }}>
              {actionKind === "retry"
                ? "This re-dispatches the exact original task. A reason is required for the audit log."
                : "This marks the entry done WITHOUT retrying — use this once you've handled it another way. A reason is required for the audit log."}
            </p>
            <ReasonField value={actionReason} onChange={setActionReason} placeholder="Why?" />
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="secondary" size="sm" onClick={() => setActionKind(null)} disabled={actionSubmitting}>Cancel</Button>
              <Button variant="primary" size="sm" loading={actionSubmitting} onClick={submitAction}>
                {actionKind === "retry" ? "Retry" : "Resolve"}
              </Button>
            </div>
          </div>
        </Modal>
      </PageWrapper>
    </AdminLayout>
  );
}
