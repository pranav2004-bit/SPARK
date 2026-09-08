"use client";

import { useState, useCallback } from "react";
import { useForm } from "react-hook-form";
import {
  Building2, UserX, UserCheck, Plus,
  Pencil, Trash2, ChevronDown,
} from "lucide-react";
import { ITLayout } from "@/components/layout/ITLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Input";
import { SearchInput } from "@/components/ui/SearchInput";
import { useToast } from "@/components/ui/Toast";
import { broadcastAdminEvent } from "@/lib/adminChannel";
import { useDepartments } from "@/lib/departmentsContext";
import axios from "axios";
import api, { getErrorMessage } from "@/lib/api";
import type { DepartmentRecord } from "@/types";

// IT-exclusive CRUD (2026-08-20) — the canonical department list every other
// portal/page reads from (see @/lib/departmentsContext). A near-exact mirror
// of it/super-admins/page.tsx rather than a shared component, same reasoning
// as that file: these account/roster-style CRUD pages are similar-shaped but
// not identical, and a forced shared abstraction would cost more than it saves.

interface CreateDepartmentForm { code: string; name?: string }
interface EditDepartmentForm   { name: string }

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

interface ActionRowProps {
  department: DepartmentRecord;
  onEdit: () => void;
  onToggleActive: () => void;
  onDelete: () => void;
}

function ActionRow({ department, onEdit, onToggleActive, onDelete }: ActionRowProps) {
  return (
    <div className="flex items-center gap-0.5">
      <ActionIcon
        label="Edit"
        icon={<Pencil size={14} />}
        onClick={onEdit}
        hoverColor="var(--color-accent)"
        hoverBg="var(--color-primary-light)"
      />
      {department.is_active ? (
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
        label="Delete Department"
        icon={<Trash2 size={14} />}
        onClick={onDelete}
        hoverColor="var(--color-danger)"
        hoverBg="var(--color-danger-bg)"
      />
    </div>
  );
}

export default function ITDepartmentsPage() {
  const { success: toastSuccess, error: toastError } = useToast();
  const { departments, loading, error: loadError, refetch } = useDepartments();

  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"" | "active" | "inactive">("");

  const [showCreate, setShowCreate] = useState(false);
  const [createLoading, setCreateLoading] = useState(false);

  const [editTarget, setEditTarget] = useState<DepartmentRecord | null>(null);
  const [editLoading, setEditLoading] = useState(false);

  const [toggleTarget, setToggleTarget] = useState<DepartmentRecord | null>(null);
  const [toggleLoading, setToggleLoading] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<DepartmentRecord | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");

  const createForm = useForm<CreateDepartmentForm>();
  const editForm    = useForm<EditDepartmentForm>();

  const announceChange = useCallback(() => {
    refetch();
    broadcastAdminEvent({ type: "DEPARTMENTS_UPDATED" });
  }, [refetch]);

  function departmentLabel(d: DepartmentRecord | null) {
    if (!d) return "";
    return d.name || d.code;
  }

  async function onCreateDepartment(data: CreateDepartmentForm) {
    setCreateLoading(true);
    try {
      await api.post<{ data: DepartmentRecord }>("/auth/departments/", {
        code: data.code,
        name: data.name?.trim() ?? "",
      });
      announceChange();
      toastSuccess("Department created.");
      setShowCreate(false);
      createForm.reset();
    } catch (err) {
      createForm.setError("code", { message: extractError(err, "code") });
    } finally {
      setCreateLoading(false);
    }
  }

  function openEditModal(department: DepartmentRecord) {
    editForm.reset({ name: department.name });
    setEditTarget(department);
  }

  async function onEditDepartment(data: EditDepartmentForm) {
    if (!editTarget) return;
    setEditLoading(true);
    try {
      await api.patch<{ data: DepartmentRecord }>(`/auth/departments/${editTarget.id}/`, { name: data.name.trim() });
      announceChange();
      toastSuccess(`Name updated for ${editTarget.code}.`);
      setEditTarget(null);
    } catch (err) {
      editForm.setError("name", { message: extractError(err, "name") });
    } finally {
      setEditLoading(false);
    }
  }

  async function onToggleActive() {
    if (!toggleTarget) return;
    const newStatus = !toggleTarget.is_active;
    setToggleLoading(true);
    try {
      await api.patch<{ data: DepartmentRecord }>(`/auth/departments/${toggleTarget.id}/`, { is_active: newStatus });
      announceChange();
      toastSuccess(`${departmentLabel(toggleTarget)} has been ${newStatus ? "activated" : "deactivated"}.`);
      setToggleTarget(null);
    } catch (err) {
      toastError(extractError(err));
    } finally {
      setToggleLoading(false);
    }
  }

  async function onDelete() {
    if (!deleteTarget) return;
    setDeleteLoading(true);
    try {
      await api.delete(`/auth/departments/${deleteTarget.id}/`);
      announceChange();
      toastSuccess(`${departmentLabel(deleteTarget)} has been permanently deleted.`);
      setDeleteTarget(null);
      setDeleteConfirmText("");
    } catch (err) {
      toastError(extractError(err));
    } finally {
      setDeleteLoading(false);
    }
  }

  const q = searchQuery.trim().toLowerCase();
  const filteredDepartments = departments.filter((d) => {
    const matchesSearch = q
      ? d.code.toLowerCase().includes(q) || d.name.toLowerCase().includes(q)
      : true;
    const matchesStatus =
      statusFilter === "active" ? d.is_active : statusFilter === "inactive" ? !d.is_active : true;
    return matchesSearch && matchesStatus;
  });

  const isFiltered = q || statusFilter;
  const subtitleText = isFiltered
    ? `${filteredDepartments.length} of ${departments.length} ${departments.length === 1 ? "department" : "departments"}`
    : `${departments.length} ${departments.length === 1 ? "department" : "departments"}`;

  return (
    <ITLayout>
      <PageWrapper>
        <PageHeader
          title="Departments"
          subtitle={subtitleText}
          rightSlot={
            <Button variant="primary" onClick={() => setShowCreate(true)}>
              <Plus size={14} className="mr-1.5" />
              Add Department
            </Button>
          }
        />

        {!loading && departments.length > 0 && (
          <div
            className="flex flex-wrap items-center gap-3 rounded-xl px-4 py-3 mb-5"
            style={{ background: "#fff", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}
          >
            <SearchInput
              value={searchQuery}
              onChange={(val) => { setSearchQuery(val); }}
              placeholder="Search by code or name…"
              className="w-64 shrink-0"
            />

            <div className="hidden sm:block self-stretch w-px" style={{ background: "var(--color-border)" }} />

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

        {loadError && !loading && (
          <div className="rounded-2xl p-5 flex items-center justify-between mb-5"
            style={{ background: "var(--color-danger-bg)", border: "1px solid var(--color-danger)20" }}>
            <p className="text-sm" style={{ color: "var(--color-danger)" }}>{loadError}</p>
            <button onClick={refetch} className="text-sm font-semibold px-4 py-2 rounded-lg"
              style={{ background: "var(--color-danger)", color: "#fff" }}>Retry</button>
          </div>
        )}

        {loading ? (
          <TableSkeleton />
        ) : departments.length === 0 && !loadError ? (
          <EmptyState icon={Building2} title="No Departments Yet"
            subtitle="Create departments so they appear as options across the platform's forms and filters."
            action={{ label: "Add Department", onClick: () => setShowCreate(true) }} />
        ) : filteredDepartments.length === 0 ? (
          <EmptyState icon={Building2} title="No results"
            subtitle={`No departments match "${searchQuery}". Try a different code or name.`} />
        ) : (
          <div className="rounded-2xl overflow-hidden"
            style={{ background: "#fff", border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)" }}>
            <table className="w-full">
              <thead>
                <tr style={{ borderBottom: "1px solid var(--color-border)", background: "var(--color-surface-secondary)" }}>
                  {["Code", "Name", "Status", "Actions"].map((h) => (
                    <th key={h} className="px-5 py-3 text-left text-xs font-semibold tracking-wide"
                      style={{ color: "var(--color-text-muted)" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredDepartments.map((department, idx) => (
                  <tr key={department.id} style={{ borderBottom: idx < filteredDepartments.length - 1 ? "1px solid var(--color-border)" : "none" }}>
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-3">
                        <span className="flex items-center justify-center rounded-full text-xs font-bold shrink-0"
                          style={{ width: 32, height: 32, background: "var(--color-primary-light)", color: "var(--color-primary)" }}>
                          {department.code.charAt(0).toUpperCase()}
                        </span>
                        <span className="text-sm font-semibold" style={{ color: "var(--color-text)" }}>{department.code}</span>
                      </div>
                    </td>
                    <td className="px-5 py-4 text-sm" style={{ color: "var(--color-text-muted)" }}>
                      {department.name || <span style={{ fontStyle: "italic" }}>No name</span>}
                    </td>
                    <td className="px-5 py-4"><StatusBadge active={department.is_active} /></td>
                    <td className="px-5 py-4">
                      <ActionRow
                        department={department}
                        onEdit={() => openEditModal(department)}
                        onToggleActive={() => setToggleTarget(department)}
                        onDelete={() => { setDeleteTarget(department); setDeleteConfirmText(""); }}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* ── Create Department Modal ────────────────────────────────────────────── */}
        <Modal isOpen={showCreate} onClose={() => { setShowCreate(false); createForm.reset(); }} title="Add Department">
          <form onSubmit={createForm.handleSubmit(onCreateDepartment)}>
            <div className="space-y-4">
              <Input
                label="Code"
                placeholder="e.g. CSE"
                error={createForm.formState.errors.code?.message}
                {...createForm.register("code", {
                  required: "Code is required.",
                  maxLength: { value: 20, message: "Code is too long (max 20 characters)." },
                })}
              />
              <Input
                label="Full Name"
                placeholder="e.g. Computer Science and Engineering (optional)"
                error={createForm.formState.errors.name?.message}
                {...createForm.register("name")}
              />
              <p className="text-xs" style={{ color: "var(--color-text-muted)" }}>
                The code appears everywhere this department is offered as an option. It can&apos;t be changed after creation.
              </p>
            </div>
            <div className="flex justify-end gap-3 mt-5">
              <Button variant="secondary" type="button" onClick={() => { setShowCreate(false); createForm.reset(); }}>Cancel</Button>
              <Button type="submit" loading={createLoading}>Create Department</Button>
            </div>
          </form>
        </Modal>

        {/* ── Edit Modal ─────────────────────────────────────────────────────────── */}
        <Modal isOpen={!!editTarget} onClose={() => { setEditTarget(null); }} title="Edit Department" maxWidth="sm">
          <form onSubmit={editForm.handleSubmit(onEditDepartment)}>
            <div className="space-y-4">
              <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
                Editing <strong style={{ color: "var(--color-text)" }}>{editTarget?.code}</strong>
              </p>
              <Input
                label="Full Name"
                placeholder="e.g. Computer Science and Engineering (optional)"
                error={editForm.formState.errors.name?.message}
                {...editForm.register("name", {
                  maxLength: { value: 150, message: "Name is too long (max 150 characters)." },
                })}
              />
              <p className="text-xs" style={{ color: "var(--color-text-muted)" }}>
                The code ({editTarget?.code}) can&apos;t be changed — other records may already reference it.
              </p>
            </div>
            <div className="flex justify-end gap-3 mt-5">
              <Button variant="secondary" type="button" onClick={() => setEditTarget(null)}>Cancel</Button>
              <Button type="submit" loading={editLoading}>Save</Button>
            </div>
          </form>
        </Modal>

        {/* ── Activate / Deactivate Modal ────────────────────────────────────────── */}
        <Modal
          isOpen={!!toggleTarget}
          onClose={() => setToggleTarget(null)}
          title={toggleTarget?.is_active ? "Deactivate Department" : "Activate Department"}
          maxWidth="sm"
        >
          <p className="text-sm mb-6" style={{ color: "var(--color-text-muted)" }}>
            {toggleTarget?.is_active ? (
              <>
                Deactivate <strong style={{ color: "var(--color-text)" }}>{departmentLabel(toggleTarget)}</strong>?
                It will no longer appear as an option in create/assign forms, but existing records that already use it are unaffected.
              </>
            ) : (
              <>
                Re-activate <strong style={{ color: "var(--color-text)" }}>{departmentLabel(toggleTarget)}</strong>?
                It will appear as an option again.
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
        <Modal isOpen={!!deleteTarget} onClose={() => { setDeleteTarget(null); setDeleteConfirmText(""); }} title="Delete Department" maxWidth="sm">
          <div className="space-y-4">
            <div className="rounded-xl p-4" style={{ background: "var(--color-danger-bg)", border: "1px solid var(--color-danger)20" }}>
              <p className="text-sm font-semibold mb-1" style={{ color: "var(--color-danger)" }}>This action is permanent and cannot be undone.</p>
              <p className="text-sm" style={{ color: "var(--color-danger)" }}>
                <strong>{departmentLabel(deleteTarget)}</strong> will be permanently removed from the list. Students, admins, or assessment
                records that already reference this code are not changed — this only affects future selection.
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
    </ITLayout>
  );
}
