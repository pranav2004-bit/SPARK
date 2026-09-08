"use client";

import { useEffect, useState, useCallback } from "react";
import { useForm } from "react-hook-form";
import {
  ShieldCheck, UserX, UserCheck, UserPlus, Upload,
  Pencil, Trash2, RotateCcw, ChevronDown,
} from "lucide-react";
import { ITLayout } from "@/components/layout/ITLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { SearchInput } from "@/components/ui/SearchInput";
import { useToast } from "@/components/ui/Toast";
import { listenAdminChannel, broadcastAdminEvent } from "@/lib/adminChannel";
import axios from "axios";
import api, { getErrorMessage } from "@/lib/api";
import { useDepartments } from "@/lib/departmentsContext";
import { BulkAccountImportModal } from "@/components/admin/BulkAccountImportModal";

// IT-exclusive CRUD (2026-08-20) — IT is now the platform's bootstrapped
// root (see create_default_it) and provisions Super Admin accounts the same
// way it/admins/page.tsx provisions Admin accounts. Unlike Admin, Super
// Admin has NO read-only remnant of its own — zero access to this roster,
// same as an Admin has zero visibility into other Admin accounts. Kept as a
// near-exact mirror of it/admins/page.tsx rather than a shared component,
// same reasoning as that file.

// ── Types ──────────────────────────────────────────────────────────────────────

interface SuperAdminRecord {
  id: string;
  email: string;
  name: string;
  department?: string;
  is_active: boolean;
  created_at: string;
}

interface CreateSuperAdminForm  { name?: string; email: string; department: string }
interface EditSuperAdminForm    { name: string; department: string }

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
  superAdmin: SuperAdminRecord;
  onEdit: () => void;
  onResetDefault: () => void;
  onToggleActive: () => void;
  onDelete: () => void;
}

function ActionRow({ superAdmin, onEdit, onResetDefault, onToggleActive, onDelete }: ActionRowProps) {
  return (
    <div className="flex items-center gap-0.5">
      <ActionIcon
        label="Edit"
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
      {superAdmin.is_active ? (
        <ActionIcon
          label="Deactivate"
          icon={<UserX size={14} />}
          onClick={onToggleActive}
          hoverColor="var(--color-danger)"
          hoverBg="var(--color-danger-bg)"
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
        label="Delete Super Admin"
        icon={<Trash2 size={14} />}
        onClick={onDelete}
        hoverColor="var(--color-danger)"
        hoverBg="var(--color-danger-bg)"
      />
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function ITSuperAdminsPage() {
  const { success: toastSuccess, error: toastError } = useToast();
  const { activeDepartments } = useDepartments();

  const [superAdmins, setSuperAdmins] = useState<SuperAdminRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"" | "active" | "inactive">("");

  // ── Modal targets ─────────────────────────────────────────────────────────────
  const [showCreate, setShowCreate] = useState(false);
  const [createLoading, setCreateLoading] = useState(false);
  const [showBulkImport, setShowBulkImport] = useState(false);

  const [editTarget, setEditTarget] = useState<SuperAdminRecord | null>(null);
  const [editLoading, setEditLoading] = useState(false);

  const [resetDefaultTarget, setResetDefaultTarget] = useState<SuperAdminRecord | null>(null);
  const [resetDefaultLoading, setResetDefaultLoading] = useState(false);

  const [toggleTarget, setToggleTarget] = useState<SuperAdminRecord | null>(null);
  const [toggleLoading, setToggleLoading] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<SuperAdminRecord | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");

  // ── Forms ─────────────────────────────────────────────────────────────────────
  const createForm = useForm<CreateSuperAdminForm>();
  const editForm    = useForm<EditSuperAdminForm>();

  // ── Fetch ─────────────────────────────────────────────────────────────────────
  const fetchSuperAdmins = useCallback(async () => {
    setLoading(true);
    setPageError("");
    try {
      const res = await api.get<{ data: SuperAdminRecord[] }>("/auth/super-admins/");
      setSuperAdmins(res.data.data ?? []);
    } catch (err) {
      setPageError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchSuperAdmins(); }, [fetchSuperAdmins]);

  // ── Cross-tab sync: react to super admin profile self-updates ─────────────────
  useEffect(() => {
    const cleanup = listenAdminChannel((event) => {
      if (event.type === "PROFILE_UPDATED") {
        setSuperAdmins((prev) =>
          prev.map((a) => a.id === event.id ? { ...a, name: event.name } : a)
        );
      }
    });
    return cleanup;
  }, []);

  // ── Display helpers ───────────────────────────────────────────────────────────
  function superAdminLabel(a: SuperAdminRecord | null) {
    if (!a) return "";
    return a.name || a.email;
  }

  // ── Create ────────────────────────────────────────────────────────────────────
  async function onCreateSuperAdmin(data: CreateSuperAdminForm) {
    setCreateLoading(true);
    try {
      const res = await api.post<{ data: SuperAdminRecord }>("/auth/super-admins/", {
        name: data.name?.trim() ?? "",
        email: data.email,
        department: data.department,
      });
      setSuperAdmins((prev) => [res.data.data, ...prev]);
      toastSuccess("Super admin account created.");
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
  function openEditModal(superAdmin: SuperAdminRecord) {
    editForm.reset({ name: superAdmin.name, department: superAdmin.department ?? "" });
    setEditTarget(superAdmin);
  }

  async function onEditSuperAdmin(data: EditSuperAdminForm) {
    if (!editTarget) return;
    setEditLoading(true);
    try {
      const res = await api.patch<{ data: SuperAdminRecord }>(`/auth/super-admins/${editTarget.id}/`, {
        name: data.name.trim(),
        department: data.department,
      });
      const updated = res.data.data;
      setSuperAdmins((prev) => prev.map((a) => a.id === updated.id ? updated : a));
      broadcastAdminEvent({ type: "ADMIN_UPDATED", data: { id: updated.id, name: updated.name, is_active: updated.is_active } });
      toastSuccess(`Details updated for ${updated.email}.`);
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
      await api.post(`/auth/super-admins/${resetDefaultTarget.id}/reset-default-password/`);
      broadcastAdminEvent({ type: "ADMIN_PASSWORD_RESET", id: resetDefaultTarget.id });
      toastSuccess(`Password reset to default for ${superAdminLabel(resetDefaultTarget)}.`);
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
      const res = await api.patch<{ data: SuperAdminRecord }>(`/auth/super-admins/${toggleTarget.id}/`, { is_active: newStatus });
      const updated = res.data.data;
      setSuperAdmins((prev) => prev.map((a) => a.id === updated.id ? updated : a));
      broadcastAdminEvent({ type: "ADMIN_UPDATED", data: { id: updated.id, name: updated.name, is_active: updated.is_active } });
      toastSuccess(`${superAdminLabel(toggleTarget)} has been ${newStatus ? "activated" : "deactivated"}.`);
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
      await api.delete(`/auth/super-admins/${deleteTarget.id}/`);
      setSuperAdmins((prev) => prev.filter((a) => a.id !== deleteTarget.id));
      broadcastAdminEvent({ type: "ADMIN_DELETED", id: deleteTarget.id });
      toastSuccess(`${superAdminLabel(deleteTarget)} has been permanently deleted.`);
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
  const filteredSuperAdmins = superAdmins.filter((a) => {
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
    ? `${filteredSuperAdmins.length} of ${superAdmins.length} ${superAdmins.length === 1 ? "super admin" : "super admins"}`
    : `${superAdmins.length} ${superAdmins.length === 1 ? "super admin" : "super admins"}`;

  // ── Render ────────────────────────────────────────────────────────────────────
  return (
    <ITLayout>
      <PageWrapper>
        <PageHeader
          title="Super Admins"
          subtitle={subtitleText}
          rightSlot={
            <div className="flex items-center gap-2">
              <Button variant="secondary" onClick={() => setShowBulkImport(true)}>
                <Upload size={14} className="mr-1.5" />
                Import CSV
              </Button>
              <Button variant="primary" onClick={() => setShowCreate(true)}>
                <UserPlus size={14} className="mr-1.5" />
                Add Super Admin
              </Button>
            </div>
          }
        />

        {/* Filter toolbar — matches it/admins page pattern */}
        {!loading && superAdmins.length > 0 && (
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
            <button onClick={fetchSuperAdmins} className="text-sm font-semibold px-4 py-2 rounded-lg"
              style={{ background: "var(--color-danger)", color: "#fff" }}>Retry</button>
          </div>
        )}

        {/* Table */}
        {loading ? (
          <TableSkeleton />
        ) : superAdmins.length === 0 && !pageError ? (
          <EmptyState icon={ShieldCheck} title="No Super Admins Yet"
            subtitle="Create super admin accounts to give institution leadership oversight access."
            action={{ label: "Add Super Admin", onClick: () => setShowCreate(true) }} />
        ) : filteredSuperAdmins.length === 0 ? (
          <EmptyState icon={ShieldCheck} title="No results"
            subtitle={`No super admins match "${searchQuery}". Try a different name or email.`} />
        ) : (
          <div className="rounded-2xl overflow-hidden"
            style={{ background: "#fff", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}>
            <table className="w-full">
              <thead>
                <tr style={{ borderBottom: "1px solid var(--color-border)", background: "var(--color-surface-secondary)" }}>
                  {["Name", "Email", "Department", "Status", "Actions"].map((h) => (
                    <th key={h} className="px-5 py-3 text-left text-xs font-semibold tracking-wide"
                      style={{ color: "var(--color-text-muted)" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredSuperAdmins.map((superAdmin, idx) => (
                  <tr key={superAdmin.id} style={{ borderBottom: idx < filteredSuperAdmins.length - 1 ? "1px solid var(--color-border)" : "none" }}>
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-3">
                        <span className="flex items-center justify-center rounded-full text-xs font-bold shrink-0"
                          style={{ width: 32, height: 32, background: "var(--color-primary-light)", color: "var(--color-primary)" }}>
                          {(superAdmin.name || superAdmin.email).charAt(0).toUpperCase()}
                        </span>
                        <span className="text-sm font-semibold" style={{ color: "var(--color-text)" }}>
                          {superAdmin.name || <span style={{ color: "var(--color-text-muted)", fontStyle: "italic" }}>No name</span>}
                        </span>
                      </div>
                    </td>
                    <td className="px-5 py-4 text-sm" style={{ color: "var(--color-text-muted)" }}>{superAdmin.email}</td>
                    <td className="px-5 py-4 text-sm" style={{ color: "var(--color-text-muted)" }}>
                      {superAdmin.department || <span style={{ fontStyle: "italic" }}>Unassigned</span>}
                    </td>
                    <td className="px-5 py-4"><StatusBadge active={superAdmin.is_active} /></td>
                    <td className="px-5 py-4">
                      <ActionRow
                        superAdmin={superAdmin}
                        onEdit={() => openEditModal(superAdmin)}
                        onResetDefault={() => setResetDefaultTarget(superAdmin)}
                        onToggleActive={() => setToggleTarget(superAdmin)}
                        onDelete={() => { setDeleteTarget(superAdmin); setDeleteConfirmText(""); }}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* ── Create Super Admin Modal ───────────────────────────────────────────── */}
        <Modal isOpen={showCreate} onClose={() => { setShowCreate(false); createForm.reset(); }} title="Add Super Admin">
          <form onSubmit={createForm.handleSubmit(onCreateSuperAdmin)}>
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
                placeholder="superadmin@institution.edu"
                error={createForm.formState.errors.email?.message}
                {...createForm.register("email", {
                  required: "Email is required.",
                  pattern: { value: /^[^\s@]+@[^\s@]+\.[^\s@]+$/, message: "Enter a valid email address." },
                })}
              />
              <Select
                label="Department"
                placeholder="Select department"
                options={activeDepartments.map((d) => ({ value: d.code, label: d.name || d.code }))}
                error={createForm.formState.errors.department?.message}
                {...createForm.register("department", {
                  required: "Department is required.",
                })}
              />
              <p className="text-xs" style={{ color: "var(--color-text-muted)" }}>
                Default password <strong>spark@123</strong> will be assigned. The super admin can change it after first login.
              </p>
            </div>
            <div className="flex justify-end gap-3 mt-5">
              <Button variant="secondary" type="button" onClick={() => { setShowCreate(false); createForm.reset(); }}>Cancel</Button>
              <Button type="submit" loading={createLoading}>Create Super Admin</Button>
            </div>
          </form>
        </Modal>

        {/* ── Edit Modal ─────────────────────────────────────────────────────────── */}
        <Modal isOpen={!!editTarget} onClose={() => { setEditTarget(null); }} title="Edit Super Admin" maxWidth="sm">
          <form onSubmit={editForm.handleSubmit(onEditSuperAdmin)}>
            <div className="space-y-4">
              <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
                Editing details for <strong style={{ color: "var(--color-text)" }}>{editTarget?.email}</strong>
              </p>
              <Input
                label="Full Name"
                placeholder="e.g. Dr. Rajan Kumar (optional)"
                error={editForm.formState.errors.name?.message}
                {...editForm.register("name", {
                  maxLength: { value: 150, message: "Name is too long (max 150 characters)." },
                })}
              />
              <Select
                label="Department"
                placeholder="Select department"
                options={activeDepartments.map((d) => ({ value: d.code, label: d.name || d.code }))}
                error={editForm.formState.errors.department?.message}
                {...editForm.register("department", {
                  required: "Department is required.",
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
              <strong style={{ color: "var(--color-text)" }}>{superAdminLabel(resetDefaultTarget)}</strong>{" "}
              back to <strong>spark@123</strong>.
            </p>
            <div className="rounded-xl p-4" style={{ background: "var(--color-warning-bg, #fef9c3)", border: "1px solid var(--color-warning, #ca8a04)20" }}>
              <p className="text-xs" style={{ color: "var(--color-warning, #92400e)" }}>
                The super admin will be logged out of all active sessions and must use the default password to log back in.
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
          title={toggleTarget?.is_active ? "Deactivate Super Admin" : "Activate Super Admin"}
          maxWidth="sm"
        >
          <p className="text-sm mb-6" style={{ color: "var(--color-text-muted)" }}>
            {toggleTarget?.is_active ? (
              <>
                Are you sure you want to deactivate{" "}
                <strong style={{ color: "var(--color-text)" }}>{superAdminLabel(toggleTarget)}</strong>?
                They will lose access immediately and be logged out.
              </>
            ) : (
              <>
                Re-activate{" "}
                <strong style={{ color: "var(--color-text)" }}>{superAdminLabel(toggleTarget)}</strong>?
                They will regain access to the super admin portal.
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
        <Modal isOpen={!!deleteTarget} onClose={() => { setDeleteTarget(null); setDeleteConfirmText(""); }} title="Delete Super Admin" maxWidth="sm">
          <div className="space-y-4">
            <div className="rounded-xl p-4" style={{ background: "var(--color-danger-bg)", border: "1px solid var(--color-danger)20" }}>
              <p className="text-sm font-semibold mb-1" style={{ color: "var(--color-danger)" }}>This action is permanent and cannot be undone.</p>
              <p className="text-sm" style={{ color: "var(--color-danger)" }}>
                The account for <strong>{superAdminLabel(deleteTarget)}</strong> will be permanently deleted along with all their access rights.
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

        <BulkAccountImportModal
          isOpen={showBulkImport}
          onClose={() => setShowBulkImport(false)}
          onImportComplete={fetchSuperAdmins}
          role="super_admin"
        />

      </PageWrapper>
    </ITLayout>
  );
}
