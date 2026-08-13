"use client";

import { useEffect, useState, useCallback } from "react";
import { Inbox, RefreshCw, RotateCcw } from "lucide-react";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { Pagination } from "@/components/ui/Pagination";
import api, { getErrorMessage } from "@/lib/api";
import type { PaginatedResponse } from "@/types";

// ── Types ──────────────────────────────────────────────────────────────────────

interface OutboxEvent {
  id: string;
  event_type: string;
  payload: Record<string, unknown>;
  student_id: string;
  attempts: number;
  last_error: string;
  created_at: string;
  last_attempted_at: string | null;
}

interface OutboxHealth {
  pending: number;
  processing: number;
  done: number;
  dead_letter: number;
}

// ── Skeleton ───────────────────────────────────────────────────────────────────

function HealthSkeleton() {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className="rounded-xl p-4 animate-pulse"
          style={{ background: "#fff", border: "1px solid var(--color-border)" }}
        >
          <div className="h-3 rounded w-20 mb-3" style={{ background: "var(--color-surface-secondary)" }} />
          <div className="h-7 rounded w-10" style={{ background: "var(--color-surface-secondary)" }} />
        </div>
      ))}
    </div>
  );
}

function TableSkeleton() {
  return (
    <div className="animate-pulse space-y-3">
      {Array.from({ length: 5 }).map((_, i) => (
        <div
          key={i}
          className="h-16 rounded-xl"
          style={{ background: "var(--color-surface-secondary)" }}
        />
      ))}
    </div>
  );
}

// ── Health widget ──────────────────────────────────────────────────────────────

interface HealthCardProps {
  label: string;
  value: number;
  danger?: boolean;
}

function HealthCard({ label, value, danger }: HealthCardProps) {
  return (
    <div
      className="rounded-xl p-4 flex flex-col gap-1"
      style={{
        background: danger && value > 0 ? "var(--color-danger-bg)" : "#fff",
        border: `1px solid ${danger && value > 0 ? "var(--color-danger)" : "var(--color-border)"}`,
        boxShadow: "var(--shadow-sm)",
      }}
    >
      <span
        className="text-xs font-medium uppercase tracking-wide"
        style={{ color: danger && value > 0 ? "var(--color-danger)" : "var(--color-text-muted)" }}
      >
        {label}
      </span>
      <span
        className="text-2xl font-bold"
        style={{ color: danger && value > 0 ? "var(--color-danger)" : "var(--color-text)" }}
      >
        {value.toLocaleString()}
      </span>
    </div>
  );
}

// ── Retry button ───────────────────────────────────────────────────────────────

interface RetryButtonProps {
  eventId: string;
  onSuccess: () => void;
}

function RetryButton({ eventId, onSuccess }: RetryButtonProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleRetry() {
    setLoading(true);
    setError("");
    try {
      await api.post(`/users/admin/outbox/dead-letters/${eventId}/retry/`);
      onSuccess();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={handleRetry}
        disabled={loading}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all disabled:opacity-60"
        style={{
          background: "var(--color-accent)",
          color: "#fff",
          minWidth: 70,
          justifyContent: "center",
        }}
      >
        {loading ? (
          <span className="animate-spin inline-block w-3 h-3 border-2 border-white border-t-transparent rounded-full" />
        ) : (
          <RotateCcw size={11} />
        )}
        {loading ? "Retrying…" : "Retry"}
      </button>
      {error && (
        <span className="text-xs max-w-[160px] text-right" style={{ color: "var(--color-danger)" }}>
          {error}
        </span>
      )}
    </div>
  );
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function truncateUuid(id: string): string {
  return id.slice(0, 8) + "…";
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function SuperAdminDlqPage() {
  const [events, setEvents] = useState<OutboxEvent[]>([]);
  const [health, setHealth] = useState<OutboxHealth | null>(null);
  const [loadingEvents, setLoadingEvents] = useState(true);
  const [loadingHealth, setLoadingHealth] = useState(true);
  const [error, setError] = useState("");
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  const fetchHealth = useCallback(async () => {
    setLoadingHealth(true);
    try {
      const res = await api.get<{ data: OutboxHealth }>("/users/admin/outbox/health/");
      setHealth(res.data.data);
    } catch {
      // Health widget failure is non-fatal; table is the primary surface.
    } finally {
      setLoadingHealth(false);
    }
  }, []);

  const fetchEvents = useCallback(async () => {
    setLoadingEvents(true);
    setError("");
    try {
      const res = await api.get<PaginatedResponse<OutboxEvent>>(
        `/users/admin/outbox/dead-letters/?page=${page}`
      );
      setEvents(res.data.results);
      setTotalCount(res.data.count);
      setTotalPages(res.data.total_pages ?? Math.ceil(res.data.count / 50));
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoadingEvents(false);
    }
  }, [page]);

  function refresh() {
    fetchEvents();
    fetchHealth();
  }

  useEffect(() => { fetchHealth(); }, [fetchHealth]);
  useEffect(() => { fetchEvents(); }, [fetchEvents]);

  const isLoading = loadingEvents || loadingHealth;

  return (
    <PageWrapper>
      <PageHeader
        title="Dead Letter Queue"
        subtitle="Outbox events that exhausted all delivery retries — manual intervention required"
        rightSlot={
          !isLoading && (
            <button
              onClick={refresh}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all"
              style={{
                background: "var(--color-surface-secondary)",
                color: "var(--color-text-muted)",
                border: "1px solid var(--color-border)",
              }}
            >
              <RefreshCw size={12} />
              Refresh
            </button>
          )
        }
      />

      {/* Health summary */}
      {loadingHealth ? (
        <HealthSkeleton />
      ) : health ? (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
          <HealthCard label="Pending"     value={health.pending}    />
          <HealthCard label="Processing"  value={health.processing} />
          <HealthCard label="Done"        value={health.done}       />
          <HealthCard label="Dead Letter" value={health.dead_letter} danger />
        </div>
      ) : null}

      {/* Error state */}
      {error && !loadingEvents && (
        <div
          className="rounded-2xl p-5 flex items-center justify-between mb-5"
          style={{ background: "var(--color-danger-bg)", border: "1px solid var(--color-danger)20" }}
        >
          <p className="text-sm" style={{ color: "var(--color-danger)" }}>{error}</p>
          <button
            onClick={fetchEvents}
            className="text-sm font-semibold px-4 py-2 rounded-lg"
            style={{ background: "var(--color-danger)", color: "#fff" }}
          >
            Retry
          </button>
        </div>
      )}

      {/* Table */}
      {loadingEvents ? (
        <TableSkeleton />
      ) : events.length === 0 && !error ? (
        <EmptyState
          icon={Inbox}
          title="No Dead-Letter Events"
          subtitle="All outbox events have been delivered successfully. Nothing to action here."
        />
      ) : (
        <div
          className="rounded-2xl overflow-hidden"
          style={{ background: "#fff", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
        >
          <table className="w-full">
            <thead>
              <tr style={{ borderBottom: "1px solid var(--color-border)", background: "var(--color-surface-secondary)" }}>
                {["Event ID", "Type", "Student ID", "Attempts", "Last Error", "Created At", "Last Attempted", ""].map((h) => (
                  <th
                    key={h}
                    className="px-4 py-3 text-left text-xs font-semibold tracking-wide"
                    style={{ color: "var(--color-text-muted)" }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {events.map((ev, idx) => (
                <tr
                  key={ev.id}
                  style={{
                    borderBottom: idx < events.length - 1 ? "1px solid var(--color-border)" : "none",
                    background: "rgba(var(--color-danger-rgb, 220,38,38),0.03)",
                  }}
                >
                  {/* Event ID */}
                  <td className="px-4 py-4">
                    <span
                      className="font-mono text-xs px-2 py-1 rounded"
                      style={{
                        background: "var(--color-danger-bg)",
                        color: "var(--color-danger)",
                      }}
                      title={ev.id}
                    >
                      {truncateUuid(ev.id)}
                    </span>
                  </td>

                  {/* Type */}
                  <td className="px-4 py-4 text-xs" style={{ color: "var(--color-text-muted)" }}>
                    {ev.event_type}
                  </td>

                  {/* Student ID */}
                  <td className="px-4 py-4">
                    <span className="text-sm font-semibold" style={{ color: "var(--color-text)" }}>
                      {ev.student_id || "—"}
                    </span>
                  </td>

                  {/* Attempts */}
                  <td className="px-4 py-4">
                    <span
                      className="inline-flex items-center justify-center rounded-full text-xs font-bold"
                      style={{
                        width: 28,
                        height: 28,
                        background: "var(--color-danger-bg)",
                        color: "var(--color-danger)",
                      }}
                    >
                      {ev.attempts}
                    </span>
                  </td>

                  {/* Last Error */}
                  <td
                    className="px-4 py-4 text-xs max-w-[200px]"
                    style={{ color: "var(--color-danger)", fontFamily: "monospace" }}
                  >
                    <span
                      className="block truncate"
                      title={ev.last_error}
                    >
                      {ev.last_error || "—"}
                    </span>
                  </td>

                  {/* Created At */}
                  <td className="px-4 py-4 text-xs whitespace-nowrap" style={{ color: "var(--color-text-muted)" }}>
                    {fmtDate(ev.created_at)}
                  </td>

                  {/* Last Attempted */}
                  <td className="px-4 py-4 text-xs whitespace-nowrap" style={{ color: "var(--color-text-muted)" }}>
                    {fmtDate(ev.last_attempted_at)}
                  </td>

                  {/* Retry button */}
                  <td className="px-4 py-4">
                    <RetryButton eventId={ev.id} onSuccess={refresh} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <Pagination
            page={page}
            totalPages={totalPages}
            onPageChange={setPage}
            totalCount={totalCount}
          />
        </div>
      )}
    </PageWrapper>
  );
}
