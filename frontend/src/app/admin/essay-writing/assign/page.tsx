"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  PlayCircle, StopCircle, RefreshCcw, Clock, ChevronDown, AlertTriangle,
} from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type {
  EssayPaper, EssayAssignment, Batch, ApiSuccess, PaginatedResponse,
} from "@/types";

// Single-step create form (unlike assessment-service's multi-step wizard) —
// essay-service's assignment model has no exam_duration_minutes/pass_cutoff/
// show_result_to_student fields to configure (Phase 3's own scope; see
// EssayAssignment's comment in @/types), so there's meaningfully less to
// collect. No live "eligible student count" preview either — a deliberate
// V1 simplification, not an oversight: it needs an extra user-service call
// this task didn't add, for a nice-to-have preview, not a functional
// requirement.

function StatusBadge({ status }: { status: EssayAssignment["status"] }) {
  const styles: Record<string, { bg: string; color: string }> = {
    SCHEDULED: { bg: "#FFF4E6", color: "#E8820C" },
    LIVE:      { bg: "#F0FDF4", color: "#16A34A" },
    CLOSED:    { bg: "#F3F4F6", color: "#6B7280" },
  };
  const s = styles[status] ?? styles.CLOSED;
  return (
    <span
      className="text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full"
      style={{ background: s.bg, color: s.color }}
    >
      {status}
    </span>
  );
}

export default function AdminEssayAssignPage() {
  const router = useRouter();
  const toast = useToast();

  const [papers, setPapers] = useState<EssayPaper[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [loadingOptions, setLoadingOptions] = useState(true);
  const [loadOptionsError, setLoadOptionsError] = useState(false);

  const [assignments, setAssignments] = useState<EssayAssignment[]>([]);
  const [loadingAssignments, setLoadingAssignments] = useState(true);
  const [loadAssignmentsError, setLoadAssignmentsError] = useState(false);

  const [formOpen, setFormOpen] = useState(false);
  const [paperId, setPaperId] = useState("");
  const [batchId, setBatchId] = useState("");
  const [expireTime, setExpireTime] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  const [actingOn, setActingOn] = useState<string | null>(null);
  const [resyncingId, setResyncingId] = useState<string | null>(null);
  const [confirmStart, setConfirmStart] = useState<EssayAssignment | null>(null);
  const [confirmClose, setConfirmClose] = useState<EssayAssignment | null>(null);

  const loadOptions = useCallback(() => {
    setLoadingOptions(true);
    setLoadOptionsError(false);
    Promise.all([
      api.get<PaginatedResponse<EssayPaper>>("/essay/admin/papers/"),
      api.get<ApiSuccess<Batch[]>>("/users/batches/"),
    ])
      .then(([papersRes, batchesRes]) => {
        setPapers(papersRes.data.results);
        setBatches(batchesRes.data.data);
      })
      .catch(() => setLoadOptionsError(true))
      .finally(() => setLoadingOptions(false));
  }, []);

  const loadAssignments = useCallback(() => {
    setLoadingAssignments(true);
    setLoadAssignmentsError(false);
    api.get<PaginatedResponse<EssayAssignment>>("/essay/admin/assignments/")
      .then(res => setAssignments(res.data.results))
      .catch(() => setLoadAssignmentsError(true))
      .finally(() => setLoadingAssignments(false));
  }, []);

  useEffect(loadOptions, [loadOptions]);
  useEffect(loadAssignments, [loadAssignments]);

  const batchName = (id: string) => batches.find(b => b.id === id)?.batch_name ?? id;
  const paperTitle = (id: string) => papers.find(p => p.id === id)?.title ?? id;

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!paperId || !batchId || !expireTime) {
      setCreateError("Paper, batch, and expiry time are all required.");
      return;
    }
    setCreating(true);
    setCreateError("");
    try {
      const res = await api.post<ApiSuccess<EssayAssignment>>("/essay/admin/assignments/", {
        paper: paperId, batch_id: batchId,
        global_expire_time: new Date(expireTime).toISOString(),
      });
      setAssignments(prev => [res.data.data, ...prev]);
      toast.success("Assignment created.");
      setFormOpen(false);
      setPaperId(""); setBatchId(""); setExpireTime("");
    } catch (err) {
      setCreateError(getErrorMessage(err));
    } finally {
      setCreating(false);
    }
  }

  async function handleStart(assignment: EssayAssignment) {
    setActingOn(assignment.id);
    try {
      const res = await api.patch<ApiSuccess<EssayAssignment>>(`/essay/admin/assignments/${assignment.id}/start/`);
      setAssignments(prev => prev.map(a => a.id === assignment.id ? res.data.data : a));
      toast.success("Assignment started — the global timer is now live.");
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setActingOn(null);
      setConfirmStart(null);
    }
  }

  async function handleClose(assignment: EssayAssignment) {
    setActingOn(assignment.id);
    try {
      const res = await api.patch<ApiSuccess<EssayAssignment>>(`/essay/admin/assignments/${assignment.id}/close/`);
      setAssignments(prev => prev.map(a => a.id === assignment.id ? res.data.data : a));
      toast.success("Assignment closed.");
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setActingOn(null);
      setConfirmClose(null);
    }
  }

  async function handleResync(assignment: EssayAssignment) {
    setResyncingId(assignment.id);
    try {
      const res = await api.post<ApiSuccess<{ new_allocations: number }>>(
        `/essay/admin/assignments/${assignment.id}/resync-roster/`
      );
      toast.success(
        res.data.data.new_allocations > 0
          ? `${res.data.data.new_allocations} new student(s) allocated.`
          : "Roster already up to date."
      );
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setResyncingId(null);
    }
  }

  return (
    <AdminLayout>
      <PageWrapper>
        <PageHeader
          title="Assessments Assigning"
          subtitle="Pick an essay paper and a batch, then create and manage assignments."
          backHref="/admin/essay-writing"
          rightSlot={
            <Button variant="primary" onClick={() => setFormOpen(v => !v)} rightIcon={<ChevronDown size={14} />}>
              + New Assignment
            </Button>
          }
        />

        {formOpen && (
          <div
            className="rounded-[var(--radius-xl)] p-5 mb-5"
            style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
          >
            <form onSubmit={handleCreate} className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Select
                  label="Essay paper"
                  value={paperId}
                  onChange={e => setPaperId(e.target.value)}
                  options={[
                    { value: "", label: loadingOptions ? "Loading…" : "Select an essay paper…" },
                    ...papers.map(p => ({ value: p.id, label: p.title })),
                  ]}
                />
                <Select
                  label="Batch"
                  value={batchId}
                  onChange={e => setBatchId(e.target.value)}
                  options={[
                    { value: "", label: "Select a batch…" },
                    ...batches.map(b => ({ value: b.id, label: b.batch_name })),
                  ]}
                />
              </div>
              {!loadingOptions && loadOptionsError && (
                <p className="text-xs" style={{ color: "var(--color-danger)" }}>
                  Couldn't load essay papers/batches — this may be temporary.{" "}
                  <button type="button" onClick={loadOptions} className="underline cursor-pointer">Retry</button>
                </p>
              )}
              {!loadingOptions && !loadOptionsError && papers.length === 0 && (
                <p className="text-xs" style={{ color: "var(--color-text-subtle)" }}>
                  No essay papers to assign yet — author one in Question Bank first.
                </p>
              )}

              <Input
                label="Global expire time"
                type="datetime-local"
                value={expireTime}
                onChange={e => setExpireTime(e.target.value)}
              />

              {createError && (
                <p className="text-xs" style={{ color: "var(--color-danger)" }}>{createError}</p>
              )}

              <div className="flex justify-end gap-3">
                <Button type="button" variant="secondary" onClick={() => setFormOpen(false)}>Cancel</Button>
                <Button type="submit" loading={creating}>Create assignment</Button>
              </div>
            </form>
          </div>
        )}

        <h3 className="text-sm font-semibold mb-3" style={{ color: "var(--color-text)" }}>Assignments</h3>
        {loadingAssignments ? (
          <Skeleton className="h-24 w-full rounded-[var(--radius-xl)]" />
        ) : loadAssignmentsError ? (
          <p className="text-sm flex items-center gap-2" style={{ color: "var(--color-danger)" }}>
            <AlertTriangle size={14} /> Couldn't load assignments — this may be temporary.{" "}
            <button type="button" onClick={loadAssignments} className="underline cursor-pointer">Retry</button>
          </p>
        ) : assignments.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--color-text-subtle)" }}>
            No assignments yet — create one above to get started.
          </p>
        ) : (
          <div className="space-y-3">
            {assignments.map(a => (
              <div
                key={a.id}
                className="rounded-[var(--radius-xl)] p-4"
                style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
              >
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <StatusBadge status={a.status} />
                      <span className="text-sm font-medium" style={{ color: "var(--color-text)" }}>{paperTitle(a.paper)}</span>
                    </div>
                    <p className="text-xs flex items-center gap-3 flex-wrap" style={{ color: "var(--color-text-subtle)" }}>
                      <span>{batchName(a.batch_id)}</span>
                      <span className="flex items-center gap-1">
                        <Clock size={11} /> expires {new Date(a.global_expire_time).toLocaleString()}
                      </span>
                      {a.departments.length > 0 && <span>Departments: {a.departments.join(", ")}</span>}
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    <Button
                      variant="secondary" size="sm"
                      leftIcon={<RefreshCcw size={13} />}
                      loading={resyncingId === a.id}
                      onClick={() => handleResync(a)}
                    >
                      Resync roster
                    </Button>
                    {a.status === "SCHEDULED" && (
                      <Button
                        variant="success" size="sm"
                        leftIcon={<PlayCircle size={13} />}
                        loading={actingOn === a.id}
                        onClick={() => setConfirmStart(a)}
                      >
                        Start
                      </Button>
                    )}
                    {a.status !== "CLOSED" && (
                      <Button
                        variant="danger" size="sm"
                        leftIcon={<StopCircle size={13} />}
                        loading={actingOn === a.id}
                        onClick={() => setConfirmClose(a)}
                      >
                        Close
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </PageWrapper>

      <ConfirmDialog
        isOpen={!!confirmStart}
        onClose={() => setConfirmStart(null)}
        onConfirm={() => confirmStart && handleStart(confirmStart)}
        title="Start this assignment?"
        message="The global timer becomes live immediately for every allocated student."
        confirmLabel="Start"
        loading={!!actingOn}
      />
      <ConfirmDialog
        isOpen={!!confirmClose}
        onClose={() => setConfirmClose(null)}
        onConfirm={() => confirmClose && handleClose(confirmClose)}
        title="Close this assignment?"
        message="This closes the assignment immediately. Students who haven't submitted yet will not be able to continue."
        confirmLabel="Close"
        confirmVariant="danger"
        loading={!!actingOn}
      />
    </AdminLayout>
  );
}
