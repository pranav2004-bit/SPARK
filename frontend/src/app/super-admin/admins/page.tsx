"use client";

import { useEffect, useState, useCallback } from "react";
import { useForm } from "react-hook-form";
import {
  Users, UserX, UserCheck, UserPlus,
  Pencil, Trash2, RotateCcw, ChevronDown,
} from "lucide-react";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Input";
import { SearchInput } from "@/components/ui/SearchInput";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { listenAdminChannel, broadcastAdminEvent } from "@/lib/adminChannel";
import axios from "axios";
import api, { getErrorMessage } from "@/lib/api";
import type { SuperAdminUser } from "@/types";

// ── Types ──────────────────────────────────────────────────────────────────────

interface AdminRecord {
  id: string;
  email: string;
  name: string;
  department?: string;
  is_active: boolean;
  created_at: string;
}

interface CreateAdminForm  { name?: string; email: string }
interface EditNameForm     { name: string }

// ── Error extraction ──────────────────────────────────────────────────────────

function extractError(err: unknown, field?: string): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data;
    if (field && data?.errors?.[field]?.[0]) return data.errors[field][0];
    if (data?.errors?.non_field_errors?.[0]) return data.errors.non_field_errors[0];
    if (data?.errors && typeof data.errors === "object") {
      const first = Object.values(data.errors as Record<string, string[]>)[0];
      if (Array.isArray(first) && first[0]) return first[0];
    }
    if (data?.message) return data.message;
  }
  return getErrorMessage(err);
}

// ── UI helpers ─────────────────────────────────────────────────────────────────

function TableSkeleton() {
  return (
    <div className="animate-pulse space-y-3">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="h-14 rounded-xl" style={{ background: "var(--color-surface-secondary)" }} />
      ))}
    </div>
  );
}

function StatusBadge({ active }: { active: boolean }) {
  return (
    <span
      className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold"
      style={{
        background: active ? "var(--color-success-bg)" : "var(--color-surface-secondary)",
        color: active ? "var(--color-success)" : "var(--color-text-muted)",
        border: `1px solid ${active ? "var(--color-success)30" : "var(--color-border)"}`,
      }}
    >
      {active ? "Active" : "Inactive"}
    </span>
  );
}

// ── Tooltip ───────────────────────────────────────────────────────────────────

function Tooltip({ label, children }: { label: string; children: React.ReactNode }) {
  const [visible, setVisible] = useState(false);
  return (
    <div
      className="relative inline-flex"
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
    >
      {children}
      {visible && (
        <div
          className="absolute bottom-full left-1/2 mb-2 px-2.5 py-1 rounded-lg text-xs font-medium whitespace-nowrap pointer-events-none z-50"
          style={{
            transform: "translateX(-50%)",
            background: "var(--color-primary)",
            color: "#fff",
            boxShadow: "0 2px 8px rgba(0,0,0,0.18)",
          }}
        >
          {label}
          {/* Arrow */}
          <span
            className="absolute left-1/2 top-full"
            style={{
              transform: "translateX(-50%)",
              width: 0, height: 0,
              borderLeft: "5px solid transparent",
              borderRight: "5px solid transparent",
              borderTop: "5px solid var(--color-primary)",
            }}
          />
        </div>
      )}
    </div>
  );
}

// ── Action icon button ────────────────────────────────────────────────────────

interface ActionIconProps {
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
  color?: string;
  hoverBg?: string;
  hoverColor?: string;
  disabled?: boolean;
}

function ActionIcon({ label, icon, onClick, color, hoverBg, hoverColor, disabled = false }: ActionIconProps) {
  const [hovered, setHovered] = useState(false);
  const base: React.CSSProperties = {
    width: 30, height: 30,
    display: "flex", alignItems: "center", justifyContent: "center",
    borderRadius: 8,
    border: "1px solid transparent",
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.4 : 1,
    transition: "background 0.15s, border-color 0.15s, color 0.15s",
    color: hovered && !disabled ? (hoverColor ?? color ?? "var(--color-text-muted)") : (color ?? "var(--color-text-muted)"),
    background: hovered && !disabled ? (hoverBg ?? "var(--color-surface-secondary)") : "transparent",
    borderColor: hovered && !disabled ? "var(--color-border)" : "transparent",
  };
  return (
    <Tooltip label={label}>
      <button
        onClick={disabled ? undefined : onClick}
        disabled={disabled}
        style={base}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        aria-label={label}
      >
        {icon}
      </button>
    </Tooltip>
  );
}

// ── Per-row action icons ──────────────────────────────────────────────────────

interface ActionRowProps {
  admin: AdminRecord;
  isSelf: boolean;
  onEdit: () => void;
  onResetDefault: () => void;
  onToggleActive: () => void;
  onDelete: () => void;
}

function ActionRow({ admin, isSelf, onEdit, onResetDefault, onToggleActive, onDelete }: ActionRowProps) {
  return (
    <div className="flex items-center gap-0.5">
      <ActionIcon
        label="Edit Name"
        icon={<Pencil size={14} />}
        onClick={onEdit}
        hoverColor="var(--color-accent)"
        hoverBg="var(--color-primary-light)"
      />
      <ActionIcon
        label="Reset to Default Password"
        icon={<RotateCcw size={14} />}
        onClick={onResetDefault}
        hoverColor="var(--color-warning, #b45309)"
        hoverBg="var(--color-warning-bg, #fef9c3)"
      />
      {admin.is_active ? (
        <ActionIcon
          label="Deactivate"
          icon={<UserX size={14} />}
          onClick={onToggleActive}
          hoverColor="var(--color-danger)"
          hoverBg="var(--color-danger-bg)"
          disabled={isSelf}
        />
      ) : (
        <ActionIcon
          label="Activate"
          icon={<UserCheck size={14} />}
          onClick={onToggleActive}
          hoverColor="var(--color-success)"
          hoverBg="var(--color-success-bg)"
        />
      )}
      <ActionIcon
        label="Delete Admin"
        icon={<Trash2 size={14} />}
        onClick={onDelete}
        hoverColor="var(--color-danger)"
        hoverBg="var(--color-danger-bg)"
        disabled={isSelf}
      />
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function SuperAdminAdminsPage() {
  const { success: toastSuccess, error: toastError } = useToast();
  const { user } = useAuth();
  const currentUserId = user?.role === "super_admin" ? (user as SuperAdminUser).id : null;

  const [admins, setAdmins] = useState<AdminRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"" | "active" | "inactive">("");

  // ── Modal targets ─────────────────────────────────────────────────────────────
  const [showCreate, setShowCreate] = useState(false);
  const [createLoading, setCreateLoading] = useState(false);

  const [editTarget, setEditTarget] = useState<AdminRecord | null>(null);
  const [editLoading, setEditLoading] = useState(false);

  const [resetDefaultTarget, setResetDefaultTarget] = useState<AdminRecord | null>(null);
  const [resetDefaultLoading, setResetDefaultLoading] = useState(false);

  const [toggleTarget, setToggleTarget] = useState<AdminRecord | null>(null);
  const [toggleLoading, setToggleLoading] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<AdminRecord | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");

  // ── Forms ─────────────────────────────────────────────────────────────────────
  const createForm = useForm<CreateAdminForm>();
  const editForm   = useForm<EditNameForm>();

  // ── Fetch ─────────────────────────────────────────────────────────────────────
  const fetchAdmins = useCallback(async () => {
    setLoading(true);
    setPageError("");
    try {
      const res = await api.get<{ data: AdminRecord[] }>("/auth/admins/");
      setAdmins(res.data.data ?? []);
    } catch (err) {
      setPageError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAdmins(); }, [fetchAdmins]);

  // ── Cross-tab sync: react to admin profile self-updates ───────────────────────
  useEffect(() => {
    const cleanup = listenAdminChannel((event) => {
      if (event.type === "PROFILE_UPDATED") {
        setAdmins((prev) =>
          prev.map((a) => a.id === event.id ? { ...a, name: event.name } : a)
        );
      }
    });
    return cleanup;
  }, []);

  // ── Display helpers ───────────────────────────────────────────────────────────
  function adminLabel(a: AdminRecord | null) {
    if (!a) return "";
    return a.name || a.email;
  }

  // ── Create ────────────────────────────────────────────────────────────────────
  async function onCreateAdmin(data: CreateAdminForm) {
    setCreateLoading(true);
    try {
      const res = await api.post<{ data: AdminRecord }>("/auth/admins/", {
        name: data.name?.trim() ?? "",
        email: data.email,
      });
      setAdmins((prev) => [res.data.data, ...prev]);
      toastSuccess("Admin account created.");
      setShowCreate(false);
      createForm.reset();
    } catch (err) {
      let msg = extractError(err, "email");
      createForm.setError("email", { message: msg });
    } finally {
      setCreateLoading(false);
    }
  }

  // ── Edit name ─────────────────────────────────────────────────────────────────
  function openEditModal(admin: AdminRecord) {
    editForm.reset({ name: admin.name });
    setEditTarget(admin);
  }

  async function onEditName(data: EditNameForm) {
    if (!editTarget) return;
    setEditLoading(true);
    try {
      const res = await api.patch<{ data: AdminRecord }>(`/auth/admins/${editTarget.id}/`, { name: data.name.trim() });
      const updated = res.data.data;
      setAdmins((prev) => prev.map((a) => a.id === updated.id ? updated : a));
      broadcastAdminEvent({ type: "ADMIN_UPDATED", data: { id: updated.id, name: updated.name, is_active: updated.is_active } });
      toastSuccess(`Name updated for ${updated.email}.`);
      setEditTarget(null);
    } catch (err) {
      editForm.setError("name", { message: extractError(err, "name") });
    } finally {
      setEditLoading(false);
    }
  }

  // ── Reset to default password ─────────────────────────────────────────────────
  async function onResetDefault() {
    if (!resetDefaultTarget) return;
    setResetDefaultLoading(true);
    try {
      await api.post(`/auth/admins/${resetDefaultTarget.id}/reset-default-password/`);
      broadcastAdminEvent({ type: "ADMIN_PASSWORD_RESET", id: resetDefaultTarget.id });
      toastSuccess(`Password reset to default for ${adminLabel(resetDefaultTarget)}.`);
      setResetDefaultTarget(null);
    } catch (err) {
      toastError(extractError(err));
    } finally {
      setResetDefaultLoading(false);
    }
  }

  // ── Toggle active ─────────────────────────────────────────────────────────────
  async function onToggleActive() {
    if (!toggleTarget) return;
    const newStatus = !toggleTarget.is_active;
    setToggleLoading(true);
    try {
      const res = await api.patch<{ data: AdminRecord }>(`/auth/admins/${toggleTarget.id}/`, { is_active: newStatus });
      const updated = res.data.data;
      setAdmins((prev) => prev.map((a) => a.id === updated.id ? updated : a));
      broadcastAdminEvent({ type: "ADMIN_UPDATED", data: { id: updated.id, name: updated.name, is_active: updated.is_active } });
      toastSuccess(`${adminLabel(toggleTarget)} has been ${newStatus ? "activated" : "deactivated"}.`);
      setToggleTarget(null);
    } catch (err) {
      toastError(extractError(err));
    } finally {
      setToggleLoading(false);
    }
  }

  // ── Delete ────────────────────────────────────────────────────────────────────
  async function onDelete() {
    if (!deleteTarget) return;
    setDeleteLoading(true);
    try {
      await api.delete(`/auth/admins/${deleteTarget.id}/`);
      setAdmins((prev) => prev.filter((a) => a.id !== deleteTarget.id));
      broadcastAdminEvent({ type: "ADMIN_DELETED", id: deleteTarget.id });
      toastSuccess(`${adminLabel(deleteTarget)} has been permanently deleted.`);
      setDeleteTarget(null);
      setDeleteConfirmText("");
    } catch (err) {
      toastError(extractError(err));
    } finally {
      setDeleteLoading(false);
    }
  }

  // ── Filtered list (client-side) ───────────────────────────────────────────────
  const q = searchQuery.trim().toLowerCase();
  const filteredAdmins = admins.filter((a) => {
    const matchesSearch = q
      ? a.name.toLowerCase().includes(q) || a.email.toLowerCase().includes(q)
      : true;
    const matchesStatus =
      statusFilter === "active"
        ? a.is_active
        : statusFilter === "inactive"
        ? !a.is_active
        : true;
    return matchesSearch && matchesStatus;
  });

  const isFiltered = q || statusFilter;
  const subtitleText = isFiltered
    ? `${filteredAdmins.length} of ${admins.length} ${admins.length === 1 ? "admin" : "admins"}`
    : `${admins.length} ${admins.length === 1 ? "admin" : "admins"}`;

  // ── Render ────────────────────────────────────────────────────────────────────
  return (
    <PageWrapper>
      <PageHeader
        title="Admins"
        subtitle={subtitleText}
        rightSlot={
          <Button variant="primary" onClick={() => setShowCreate(true)}>
            <UserPlus size={14} className="mr-1.5" />
            Add Admin
          </Button>
        }
      />

      {/* Filter toolbar — matches admin/students page pattern */}
      {!loading && admins.length > 0 && (
        <div
          className="flex flex-wrap items-center gap-3 rounded-xl px-4 py-3 mb-5"
          style={{ background: "#fff", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
        >
          <SearchInput
            value={searchQuery}
            onChange={(val) => { setSearchQuery(val); }}
            placeholder="Search by name or email…"
            className="w-64 shrink-0"
          />

          {/* Divider */}
          <div className="hidden sm:block self-stretch w-px" style={{ background: "var(--color-border)" }} />

          {/* Status filter */}
          <div className="relative shrink-0">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as "" | "active" | "inactive")}
              className="h-9 pl-3 pr-8 text-sm rounded-[var(--radius-md)] border bg-white appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
              style={{ borderColor: "var(--color-border)", color: "var(--color-text)", minWidth: 140 }}
            >
              <option value="">All statuses</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
            <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: "var(--color-text-muted)" }} />
          </div>

          {/* Always rendered — visibility toggle prevents toolbar reflow */}
          <button
            onClick={() => { setSearchQuery(""); setStatusFilter(""); }}
            className="ml-auto text-xs font-medium px-3 py-1.5 rounded-lg transition-colors shrink-0"
            style={{
              color: "var(--color-text-muted)",
              background: "var(--color-surface-secondary)",
              border: "1px solid var(--color-border)",
              visibility: isFiltered ? "visible" : "hidden",
              pointerEvents: isFiltered ? "auto" : "none",
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.color = "var(--color-danger)"; (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--color-danger)"; }}
            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.color = "var(--color-text-muted)"; (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--color-border)"; }}
          >
            Clear filters
          </button>
        </div>
      )}

      {/* Page-level error */}
      {pageError && !loading && (
        <div className="rounded-2xl p-5 flex items-center justify-between mb-5"
          style={{ background: "var(--color-danger-bg)", border: "1px solid var(--color-danger)20" }}>
          <p className="text-sm" style={{ color: "var(--color-danger)" }}>{pageError}</p>
          <button onClick={fetchAdmins} className="text-sm font-semibold px-4 py-2 rounded-lg"
            style={{ background: "var(--color-danger)", color: "#fff" }}>Retry</button>
        </div>
      )}

      {/* Table */}
      {loading ? (
        <TableSkeleton />
      ) : admins.length === 0 && !pageError ? (
        <EmptyState icon={Users} title="No Admins Yet"
          subtitle="Create admin accounts to let them manage their batches and students."
          action={{ label: "Add Admin", onClick: () => setShowCreate(true) }} />
      ) : filteredAdmins.length === 0 ? (
        <EmptyState icon={Users} title="No results"
          subtitle={`No admins match "${searchQuery}". Try a different name or email.`} />
      ) : (
        <div className="rounded-2xl overflow-hidden"
          style={{ background: "#fff", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}>
          <table className="w-full">
            <thead>
              <tr style={{ borderBottom: "1px solid var(--color-border)", background: "var(--color-surface-secondary)" }}>
                {["Name", "Email", "Status", "Actions"].map((h) => (
                  <th key={h} className="px-5 py-3 text-left text-xs font-semibold tracking-wide"
                    style={{ color: "var(--color-text-muted)" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredAdmins.map((admin, idx) => (
                <tr key={admin.id} style={{ borderBottom: idx < filteredAdmins.length - 1 ? "1px solid var(--color-border)" : "none" }}>
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-3">
                      <span className="flex items-center justify-center rounded-full text-xs font-bold shrink-0"
                        style={{ width: 32, height: 32, background: "var(--color-primary-light)", color: "var(--color-primary)" }}>
                        {(admin.name || admin.email).charAt(0).toUpperCase()}
                      </span>
                      <span className="text-sm font-semibold" style={{ color: "var(--color-text)" }}>
                        {admin.name || <span style={{ color: "var(--color-text-muted)", fontStyle: "italic" }}>No name</span>}
                      </span>
                    </div>
                  </td>
                  <td className="px-5 py-4 text-sm" style={{ color: "var(--color-text-muted)" }}>{admin.email}</td>
                  <td className="px-5 py-4"><StatusBadge active={admin.is_active} /></td>
                  <td className="px-5 py-4">
                    <ActionRow
                      admin={admin}
                      isSelf={admin.id === currentUserId}
                      onEdit={() => openEditModal(admin)}
                      onResetDefault={() => setResetDefaultTarget(admin)}
                      onToggleActive={() => setToggleTarget(admin)}
                      onDelete={() => { setDeleteTarget(admin); setDeleteConfirmText(""); }}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Create Admin Modal ─────────────────────────────────────────────────── */}
      <Modal isOpen={showCreate} onClose={() => { setShowCreate(false); createForm.reset(); }} title="Add Admin">
        <form onSubmit={createForm.handleSubmit(onCreateAdmin)}>
          <div className="space-y-4">
            <Input
              label="Full Name"
              placeholder="e.g. Dr. Rajan Kumar (optional)"
              error={createForm.formState.errors.name?.message}
              {...createForm.register("name")}
            />
            <Input
              label="Email Address"
              type="email"
              placeholder="admin@institution.edu"
              error={createForm.formState.errors.email?.message}
              {...createForm.register("email", {
                required: "Email is required.",
                pattern: { value: /^[^\s@]+@[^\s@]+\.[^\s@]+$/, message: "Enter a valid email address." },
              })}
            />
            <p className="text-xs" style={{ color: "var(--color-text-muted)" }}>
              Default password <strong>spark@123</strong> will be assigned. The admin can change it after first login.
            </p>
          </div>
          <div className="flex justify-end gap-3 mt-5">
            <Button variant="secondary" type="button" onClick={() => { setShowCreate(false); createForm.reset(); }}>Cancel</Button>
            <Button type="submit" loading={createLoading}>Create Admin</Button>
          </div>
        </form>
      </Modal>

      {/* ── Edit Name Modal ────────────────────────────────────────────────────── */}
      <Modal isOpen={!!editTarget} onClose={() => { setEditTarget(null); }} title="Edit Admin Name" maxWidth="sm">
        <form onSubmit={editForm.handleSubmit(onEditName)}>
          <div className="space-y-4">
            <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
              Editing name for <strong style={{ color: "var(--color-text)" }}>{editTarget?.email}</strong>
            </p>
            <Input
              label="Full Name"
              placeholder="e.g. Dr. Rajan Kumar (optional)"
              error={editForm.formState.errors.name?.message}
              {...editForm.register("name", {
                maxLength: { value: 150, message: "Name is too long (max 150 characters)." },
              })}
            />
          </div>
          <div className="flex justify-end gap-3 mt-5">
            <Button variant="secondary" type="button" onClick={() => setEditTarget(null)}>Cancel</Button>
            <Button type="submit" loading={editLoading}>Save</Button>
          </div>
        </form>
      </Modal>

      {/* ── Reset to Default Password Modal ───────────────────────────────────── */}
      <Modal isOpen={!!resetDefaultTarget} onClose={() => setResetDefaultTarget(null)} title="Reset to Default Password" maxWidth="sm">
        <div className="space-y-4">
          <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
            This will reset the password for{" "}
            <strong style={{ color: "var(--color-text)" }}>{adminLabel(resetDefaultTarget)}</strong>{" "}
            back to <strong>spark@123</strong>.
          </p>
          <div className="rounded-xl p-4" style={{ background: "var(--color-warning-bg, #fef9c3)", border: "1px solid var(--color-warning, #ca8a04)20" }}>
            <p className="text-xs" style={{ color: "var(--color-warning, #92400e)" }}>
              The admin will be logged out of all active sessions and must use the default password to log back in.
            </p>
          </div>
        </div>
        <div className="flex justify-end gap-3 mt-5">
          <Button variant="secondary" onClick={() => setResetDefaultTarget(null)}>Cancel</Button>
          <Button variant="warning" onClick={onResetDefault} loading={resetDefaultLoading}>Reset to Default</Button>
        </div>
      </Modal>


      {/* ── Activate / Deactivate Modal ────────────────────────────────────────── */}
      <Modal
        isOpen={!!toggleTarget}
        onClose={() => setToggleTarget(null)}
        title={toggleTarget?.is_active ? "Deactivate Admin" : "Activate Admin"}
        maxWidth="sm"
      >
        <p className="text-sm mb-6" style={{ color: "var(--color-text-muted)" }}>
          {toggleTarget?.is_active ? (
            <>
              Are you sure you want to deactivate{" "}
              <strong style={{ color: "var(--color-text)" }}>{adminLabel(toggleTarget)}</strong>?
              They will lose access immediately and be logged out.
            </>
          ) : (
            <>
              Re-activate{" "}
              <strong style={{ color: "var(--color-text)" }}>{adminLabel(toggleTarget)}</strong>?
              They will regain access to the admin portal.
            </>
          )}
        </p>
        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={() => setToggleTarget(null)}>Cancel</Button>
          <Button
            variant={toggleTarget?.is_active ? "danger" : "success"}
            onClick={onToggleActive}
            loading={toggleLoading}
          >
            {toggleTarget?.is_active ? "Deactivate" : "Activate"}
          </Button>
        </div>
      </Modal>

      {/* ── Delete Modal ───────────────────────────────────────────────────────── */}
      <Modal isOpen={!!deleteTarget} onClose={() => { setDeleteTarget(null); setDeleteConfirmText(""); }} title="Delete Admin" maxWidth="sm">
        <div className="space-y-4">
          <div className="rounded-xl p-4" style={{ background: "var(--color-danger-bg)", border: "1px solid var(--color-danger)20" }}>
            <p className="text-sm font-semibold mb-1" style={{ color: "var(--color-danger)" }}>This action is permanent and cannot be undone.</p>
            <p className="text-sm" style={{ color: "var(--color-danger)" }}>
              The account for <strong>{adminLabel(deleteTarget)}</strong> will be permanently deleted along with all their access rights.
            </p>
          </div>
          <div>
            <p className="text-sm mb-2" style={{ color: "var(--color-text-muted)" }}>
              Type <strong style={{ color: "var(--color-text)" }}>DELETE</strong> to confirm.
            </p>
            <Input
              placeholder="Type DELETE to confirm"
              value={deleteConfirmText}
              onChange={(e) => setDeleteConfirmText((e.target as HTMLInputElement).value)}
            />
          </div>
        </div>
        <div className="flex justify-end gap-3 mt-5">
          <Button variant="secondary" onClick={() => { setDeleteTarget(null); setDeleteConfirmText(""); }}>Cancel</Button>
          <Button
            variant="danger"
            onClick={onDelete}
            loading={deleteLoading}
            disabled={deleteConfirmText !== "DELETE"}
          >
            Permanently Delete
          </Button>
        </div>
      </Modal>

    </PageWrapper>
  );
}
