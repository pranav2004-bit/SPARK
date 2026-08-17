"use client";

import { useEffect, useState, useCallback } from "react";
import {
  MessageSquare, CheckCheck, Clock,
  Mail, User, GraduationCap, BookOpen, Loader2, AlertTriangle,
} from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { Pagination } from "@/components/ui/Pagination";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { Inquiry, PaginatedResponse } from "@/types";

// ── Helpers ───────────────────────────────────────────────────────────────────
function formatDate(iso: string) {
  return new Date(iso).toLocaleString("en-IN", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit", hour12: true,
  }).replace("am", "AM").replace("pm", "PM");
}

// ── Skeleton card ─────────────────────────────────────────────────────────────
function SkeletonCard() {
  return (
    <div className="bg-white border border-[var(--color-border)] rounded-[var(--radius-xl)] overflow-hidden shadow-[var(--shadow-sm)]">
      <div className="px-5 py-4 border-b border-[var(--color-border)] flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <Skeleton className="h-8 w-8 rounded-full shrink-0" />
          <div className="space-y-1.5">
            <Skeleton className="h-3.5 w-36" />
            <Skeleton className="h-3 w-48" />
          </div>
        </div>
        <Skeleton className="h-5 w-16 rounded-full shrink-0" />
      </div>
      <div className="px-5 py-4 space-y-2">
        <Skeleton className="h-3.5 w-full" />
        <Skeleton className="h-3.5 w-4/5" />
        <Skeleton className="h-3.5 w-2/3" />
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function InquiriesPage() {
  const toast = useToast();
  const [inquiries, setInquiries] = useState<Inquiry[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [markingId, setMarkingId] = useState<string | null>(null);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  const fetchInquiries = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const params = new URLSearchParams();
      if (unreadOnly) params.set("unread", "true");
      params.set("page", String(page));
      const res = await api.get<PaginatedResponse<Inquiry>>(
        `/users/inquiries/?${params.toString()}`
      );
      setInquiries(res.data.results);
      setTotalCount(res.data.count);
      setTotalPages(res.data.total_pages);
    } catch (err) {
      toast.error(getErrorMessage(err));
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [unreadOnly, page, toast]);

  useEffect(() => { fetchInquiries(); }, [fetchInquiries]);

  // Reset to page 1 whenever the filter changes
  useEffect(() => { setPage(1); }, [unreadOnly]);

  async function markRead(id: string) {
    setMarkingId(id);
    try {
      await api.patch(`/users/inquiries/${id}/mark-read/`);
      setInquiries((prev) =>
        prev.map((inq) => (inq.id === id ? { ...inq, is_read: true } : inq))
      );
      toast.success("Marked as read.");
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setMarkingId(null);
    }
  }

  const unreadCount = inquiries.filter((i) => !i.is_read).length;

  return (
    <AdminLayout>
      <PageWrapper className="max-w-5xl py-8">

        {/* ── Page header ──────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between gap-4 mb-7">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-[var(--color-text)]">
              Inquiries
            </h1>
            <p className="text-sm text-[var(--color-text-muted)] mt-0.5">
              {loading
                ? "Loading…"
                : loadError
                  ? "Couldn't load inquiries."
                  : totalCount === 0
                    ? "No inquiries yet."
                    : `${totalCount} total${unreadCount > 0 ? ` · ${unreadCount} unread` : " · all read"}`
              }
            </p>
          </div>

          {/* Unread filter toggle */}
          <button
            onClick={() => setUnreadOnly((v) => !v)}
            className="shrink-0 inline-flex items-center gap-1.5 px-3.5 py-2 rounded-[var(--radius-md)] text-sm font-medium transition-all duration-150 border"
            style={{
              background: unreadOnly ? "var(--color-accent-light)" : "#fff",
              color: unreadOnly ? "var(--color-accent)" : "var(--color-text-muted)",
              borderColor: unreadOnly ? "var(--color-accent)" : "var(--color-border)",
              boxShadow: "var(--shadow-sm)",
            }}
          >
            <Clock size={13} className="shrink-0" />
            Unread only
          </button>
        </div>

        {/* ── Content ──────────────────────────────────────────────────────── */}
        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => <SkeletonCard key={i} />)}
          </div>

        ) : loadError ? (
          <EmptyState
            icon={AlertTriangle}
            title="Couldn't load inquiries"
            subtitle="Something went wrong fetching this data — it may be temporary. Try again in a moment."
            action={{ label: "Retry", onClick: fetchInquiries }}
          />

        ) : inquiries.length === 0 ? (
          <EmptyState
            icon={MessageSquare}
            title={unreadOnly ? "No unread inquiries" : "No inquiries yet"}
            subtitle={
              unreadOnly
                ? "All inquiries have been read."
                : "Student inquiries will appear here once submitted."
            }
          />

        ) : (
          <div className="space-y-3">
            {inquiries.map((inq) => (
              <div
                key={inq.id}
                className="bg-white rounded-[var(--radius-xl)] overflow-hidden shadow-[var(--shadow-sm)] transition-shadow duration-150 hover:shadow-[var(--shadow-md)]"
                style={{
                  border: "1px solid var(--color-border)",
                  borderLeft: inq.is_read
                    ? "1px solid var(--color-border)"
                    : "3px solid var(--color-accent)",
                }}
              >
                {/* ── Card header ─────────────────────────────────────────── */}
                <div
                  className="px-5 py-3.5 flex items-center justify-between gap-4"
                  style={{ borderBottom: "1px solid var(--color-border)" }}
                >
                  {/* Left: avatar + name + meta */}
                  <div className="flex items-center gap-3 min-w-0">
                    {/* Avatar */}
                    <div
                      className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 text-sm font-bold text-white"
                      style={{ background: "var(--color-accent)" }}
                    >
                      {(inq.fullname || inq.student_id)[0].toUpperCase()}
                    </div>

                    {/* Name + meta row */}
                    <div className="min-w-0">
                      {/* Row 1: name + ID */}
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-semibold text-[var(--color-text)] truncate">
                          {inq.fullname || inq.student_id}
                        </span>
                        <span className="text-xs text-[var(--color-text-muted)] shrink-0">
                          {inq.student_id}
                        </span>
                      </div>
                      {/* Row 2: email · dept · batch */}
                      <div className="flex items-center gap-3 mt-0.5 flex-wrap">
                        {inq.college_email_id && (
                          <div className="flex items-center gap-1 min-w-0">
                            <Mail size={11} className="text-[var(--color-text-subtle)] shrink-0" />
                            <span className="text-xs text-[var(--color-text-muted)] truncate max-w-[160px]">
                              {inq.college_email_id}
                            </span>
                          </div>
                        )}
                        <div className="flex items-center gap-1">
                          <BookOpen size={11} className="text-[var(--color-text-subtle)] shrink-0" />
                          <span className="text-xs text-[var(--color-text-muted)]">{inq.department}</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <GraduationCap size={11} className="text-[var(--color-text-subtle)] shrink-0" />
                          <span className="text-xs text-[var(--color-text-muted)]">{inq.batch_name}</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Right: timestamp + badge + action — all in one row */}
                  <div className="flex items-center gap-3 shrink-0">
                    <span className="text-[11px] text-[var(--color-text-subtle)] whitespace-nowrap hidden sm:block">
                      {formatDate(inq.created_at)}
                    </span>

                    {inq.is_read ? (
                      <span
                        className="inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full"
                        style={{
                          background: "var(--color-surface-hover)",
                          color: "var(--color-text-subtle)",
                        }}
                      >
                        <CheckCheck size={10} />
                        Read
                      </span>
                    ) : (
                      <>
                        <span
                          className="inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-full"
                          style={{
                            background: "var(--color-accent-light)",
                            color: "var(--color-accent)",
                          }}
                        >
                          New
                        </span>

                        {/* Mark as read — in header, not footer */}
                        <button
                          onClick={() => markRead(inq.id)}
                          disabled={markingId === inq.id}
                          className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-[var(--radius-md)] transition-colors disabled:opacity-60 border"
                          style={{
                            color: "var(--color-text-muted)",
                            background: "#fff",
                            borderColor: "var(--color-border)",
                          }}
                          onMouseEnter={e => {
                            if (markingId !== inq.id) {
                              e.currentTarget.style.background = "var(--color-surface-hover)";
                              e.currentTarget.style.color = "var(--color-text)";
                            }
                          }}
                          onMouseLeave={e => {
                            e.currentTarget.style.background = "#fff";
                            e.currentTarget.style.color = "var(--color-text-muted)";
                          }}
                        >
                          {markingId === inq.id
                            ? <><Loader2 size={12} className="animate-spin" /> Marking…</>
                            : <><CheckCheck size={12} /> Mark as read</>
                          }
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {/* ── Message body ─────────────────────────────────────────── */}
                <div
                  className="px-5 py-4"
                  style={{
                    background: inq.is_read ? "#fff" : "var(--color-accent-light)",
                  }}
                >
                  {/* Timestamp on mobile */}
                  <p className="text-[11px] text-[var(--color-text-subtle)] mb-2 sm:hidden">
                    {formatDate(inq.created_at)}
                  </p>
                  <p className="text-sm text-[var(--color-text)] leading-relaxed whitespace-pre-wrap break-words">
                    {inq.message}
                  </p>
                </div>

              </div>
            ))}
          </div>
        )}

        {/* ── Pagination ───────────────────────────────────────────────────── */}
        {!loading && totalPages > 1 && (
          <div className="mt-4">
            <Pagination
              page={page}
              totalPages={totalPages}
              totalCount={totalCount}
              pageSize={50}
              onPageChange={(p) => {
                setPage(p);
                window.scrollTo({ top: 0, behavior: "smooth" });
              }}
            />
          </div>
        )}

      </PageWrapper>
    </AdminLayout>
  );
}
