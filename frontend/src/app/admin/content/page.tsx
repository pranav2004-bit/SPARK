"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Layers, Pencil, Plus, Trash2 } from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { Modal } from "@/components/ui/Modal";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useToast } from "@/components/ui/Toast";
import { contentApi, messageFor, STATUS_TEXT, type ContentNode } from "@/lib/contentApi";

const MAX_PAGES = 50;
const MAX_QUERY = 200;

type StatusFilter = "all" | "published" | "draft" | "retired";
const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "published", label: "Published" },
  { value: "draft", label: "Draft" },
  { value: "retired", label: "Unpublished" },
];

// Turns raw search text into a safe, comparable form. The query is only ever compared as
// plain text (never as a pattern or markup), control characters are removed, length is capped,
// and it is never sent to the server.
function normaliseQuery(raw: string): string {
  return raw
    .normalize("NFKC")
    .replace(/[\u0000-\u001F\u007F]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, MAX_QUERY)
    .toLocaleLowerCase("en");
}

function nameMatches(name: string, query: string): boolean {
  if (query === "") return true;
  return name.normalize("NFKC").toLocaleLowerCase("en").includes(query);
}

export default function AdminContentRootPage() {
  const toast = useToast();
  const [subjects, setSubjects] = useState<ContentNode[] | null>(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [nameError, setNameError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<ContentNode | null>(null);
  const [editName, setEditName] = useState("");
  const [editError, setEditError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<ContentNode | null>(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      // Search and filter run on the client, so load every page of subjects first.
      // The cap stops a runaway loop if the server ever returns a bad "next" link.
      const all: ContentNode[] = [];
      for (let pageNo = 1; pageNo <= MAX_PAGES; pageNo += 1) {
        const page = await contentApi.listNodes(null, pageNo);
        all.push(...page.data.results);
        if (page.data.next === null) break;
      }
      setSubjects(all);
    } catch (err) {
      setLoadError(messageFor(err));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function createSubject(e: React.FormEvent) {
    e.preventDefault();
    setNameError(null);
    if (!name.trim()) {
      setNameError("Enter a subject name.");
      return;
    }
    setBusy(true);
    try {
      await contentApi.createNode(name.trim(), null);
      setName("");
      setCreateOpen(false);
      toast.success("Subject created.");
      await load();
    } catch (err) {
      setNameError(messageFor(err));
    } finally {
      setBusy(false);
    }
  }

  function openEdit(node: ContentNode) {
    setEditing(node);
    setEditName(node.name);
    setEditError(null);
  }

  async function saveEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!editing) return;
    setEditError(null);
    if (!editName.trim()) {
      setEditError("Enter a subject name.");
      return;
    }
    setBusy(true);
    try {
      await contentApi.renameNode(editing.id, editName.trim());
      setEditing(null);
      toast.success("Subject renamed.");
      await load();
    } catch (err) {
      setEditError(messageFor(err));
    } finally {
      setBusy(false);
    }
  }

  async function confirmDelete() {
    if (!deleting) return;
    setBusy(true);
    try {
      await contentApi.deleteNode(deleting.id);
      toast.success("Subject deleted.");
      setDeleting(null);
      await load();
    } catch (err) {
      // A subject with topics is refused by the server; the message says why.
      toast.error(messageFor(err));
      setDeleting(null);
    } finally {
      setBusy(false);
    }
  }

  async function act(node: ContentNode, action: "publish" | "retire" | "restore") {
    try {
      await contentApi.nodeAction(node.id, action);
      toast.success(`Subject ${action === "publish" ? "published" : action === "retire" ? "retired" : "restored"}.`);
      await load();
    } catch (err) {
      toast.error(messageFor(err));
    }
  }

  const normalisedQuery = normaliseQuery(query);
  const visible = (subjects ?? []).filter(
    (s) => (statusFilter === "all" || s.status === statusFilter) && nameMatches(s.name, normalisedQuery),
  );
  const filtersActive = query.trim() !== "" || statusFilter !== "all";

  // Search and status filter sit in the header row, between the title and the Add subject button.
  const searchAndFilter = (
    <div className="flex w-full min-w-0 items-center gap-2 sm:max-w-xl">
      <input
        type="search"
        aria-label="Search subjects"
        placeholder="Search subjects"
        value={query}
        maxLength={MAX_QUERY}
        autoComplete="off"
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") setQuery("");
        }}
        className="min-w-0 flex-1 rounded-[var(--radius-md)] border border-[var(--color-border-strong)] bg-white px-3 py-2 text-sm text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
      />
      <select
        aria-label="Filter by status"
        value={statusFilter}
        onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
        className="cursor-pointer rounded-[var(--radius-md)] border border-[var(--color-border-strong)] bg-white px-3 py-2 text-sm text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
      >
        {STATUS_FILTERS.map((f) => (
          <option key={f.value} value={f.value}>{f.label}</option>
        ))}
      </select>
    </div>
  );

  const addSubjectButton = (
    <Button variant="primary" leftIcon={<Plus size={14} />} onClick={() => setCreateOpen(true)}>
      Add subject
    </Button>
  );

  return (
    <AdminLayout>
      <PageWrapper>
        <PageHeader
          title="Content"
          subtitle="Subjects, topics and questions for the question bank."
          centerSlot={subjects !== null && subjects.length > 0 ? searchAndFilter : undefined}
          rightSlot={addSubjectButton}
        />

        {loadError ? (
          <EmptyState icon={Layers} title="Could not load content" subtitle={loadError} action={{ label: "Try again", onClick: load }} />
        ) : subjects === null ? (
          <div className="space-y-3">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
        ) : subjects.length === 0 ? (
          <EmptyState
            icon={Layers}
            title="No subjects yet"
            subtitle="Create your first subject to start building the question bank."
            action={{ label: "Add subject", onClick: () => setCreateOpen(true) }}
          />
        ) : visible.length === 0 ? (
          <EmptyState
            icon={Layers}
            title="No subjects match"
            subtitle="Try a different name or status."
            action={filtersActive ? { label: "Clear search and filters", onClick: () => { setQuery(""); setStatusFilter("all"); } } : undefined}
          />
        ) : (
          <>
          <p className="mb-3 text-xs" style={{ color: "var(--color-text-muted)" }} aria-live="polite">
            Showing {visible.length} of {subjects.length}
          </p>
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4" aria-label="Subjects">
            {visible.map((s) => (
              <li
                key={s.id}
                className="relative flex min-h-[120px] cursor-pointer flex-col justify-between gap-3 rounded-[var(--radius-lg)] p-4 transition duration-150 hover:shadow-md"
                style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <Link href={`/admin/content/nodes/${s.id}`} className="block font-semibold break-words underline-offset-2 after:absolute after:inset-0 after:rounded-[var(--radius-lg)] after:content-[''] hover:underline">
                      {s.name}
                    </Link>
                    <p className="mt-1 text-xs" style={{ color: "var(--color-text-muted)" }}>
                      {s.child_count} topic{s.child_count === 1 ? "" : "s"}
                    </p>
                  </div>
                  <div className="relative z-10 flex shrink-0 items-center gap-1">
                    <button
                      type="button"
                      aria-label="Edit"
                      title="Edit subject"
                      onClick={() => openEdit(s)}
                      className="rounded-[var(--radius-md)] p-1.5 hover:bg-[var(--color-surface-hover)]"
                      style={{ color: "var(--color-text-muted)" }}
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      type="button"
                      aria-label="Delete"
                      title="Delete subject"
                      onClick={() => setDeleting(s)}
                      className="rounded-[var(--radius-md)] p-1.5 hover:bg-[var(--color-surface-hover)]"
                      style={{ color: "var(--color-danger)" }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
                <div className="relative z-10 flex items-center justify-between gap-2">
                  <span
                    className="rounded-full px-2 py-0.5 text-xs font-medium capitalize"
                    style={
                      s.status === "published"
                        ? { background: "var(--color-success-light, #dcfce7)", color: "var(--color-text)" }
                        : s.status === "retired"
                          ? { background: "var(--color-surface-hover)", color: "var(--color-text-muted)" }
                          : { background: "var(--color-accent-light)", color: "var(--color-text)" }
                    }
                  >
                    {STATUS_TEXT[s.status]}
                  </span>
                  {s.status === "draft" && (
                    <TileAction onClick={() => act(s, "publish")}>Publish</TileAction>
                  )}
                  {s.status === "published" && (
                    <TileAction onClick={() => act(s, "retire")}>Unpublish</TileAction>
                  )}
                  {s.status === "retired" && (
                    <TileAction onClick={() => act(s, "restore")}>Publish</TileAction>
                  )}
                </div>
              </li>
            ))}
          </ul>
          </>
        )}
        <Modal isOpen={createOpen} onClose={() => setCreateOpen(false)} title="New subject" maxWidth="sm">
          <form onSubmit={createSubject} className="flex flex-col gap-4" aria-label="New subject">
            <Input
              label="Subject name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              error={nameError ?? undefined}
              maxLength={200}
              className="border-[var(--color-border-strong)] focus:border-[var(--color-accent)]"
            />
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={() => setCreateOpen(false)}>Cancel</Button>
              {/* Shown only once the name has text, so an empty form never offers a create action. */}
              {name.trim() !== "" && (
                <Button type="submit" variant="primary" loading={busy} leftIcon={<Plus size={14} />}>Create subject</Button>
              )}
            </div>
          </form>
        </Modal>

        <Modal isOpen={editing !== null} onClose={() => setEditing(null)} title="Edit subject" maxWidth="sm">
          <form onSubmit={saveEdit} className="flex flex-col gap-4" aria-label="Edit subject">
            <Input
              label="Subject name"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              error={editError ?? undefined}
              maxLength={200}
              className="border-[var(--color-border-strong)] focus:border-[var(--color-accent)]"
            />
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
              {editName.trim() !== "" && (
                <Button type="submit" variant="primary" loading={busy}>Save changes</Button>
              )}
            </div>
          </form>
        </Modal>

        <ConfirmDialog
          isOpen={deleting !== null}
          onClose={() => setDeleting(null)}
          onConfirm={confirmDelete}
          title="Delete this subject?"
          message="A subject can only be deleted when it has no topics. Otherwise unpublish it instead."
          confirmLabel="Delete"
          confirmVariant="danger"
          requireTypedConfirmation="delete"
          loading={busy}
        />
      </PageWrapper>
    </AdminLayout>
  );
}

// Visible action button for a subject tile. The shared Button's ghost styling hides the
// tint, so this sets the colours itself: tinted fill, dark text, thin accent border.
function TileAction({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="cursor-pointer rounded-[var(--radius-md)] px-3 py-1.5 text-xs font-semibold shadow-sm transition duration-150 hover:-translate-y-px hover:shadow-md active:translate-y-0 active:scale-[0.97] active:shadow-none"
      style={{
        background: "var(--color-accent-light)",
        color: "var(--color-text)",
        border: "1px solid var(--color-accent)",
      }}
    >
      {children}
    </button>
  );
}
