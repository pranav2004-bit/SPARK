"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowDown, ArrowUp, FileText, Layers, Plus } from "lucide-react";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useToast } from "@/components/ui/Toast";
import {
  contentApi, messageFor, STATUS_TEXT,
  type ContentNode, type ContentQuestion,
} from "@/lib/contentApi";

const LETTERS = ["A", "B", "C", "D"];

export default function AdminContentNodePage() {
  const { node_id } = useParams<{ node_id: string }>();
  const toast = useToast();
  const router = useRouter();
  const [node, setNode] = useState<ContentNode | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const [renameError, setRenameError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [parent, setParent] = useState<ContentNode | null>(null);
  const [children, setChildren] = useState<ContentNode[]>([]);
  const [questions, setQuestions] = useState<ContentQuestion[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [childName, setChildName] = useState("");
  const [childError, setChildError] = useState<string | null>(null);
  const [qText, setQText] = useState("");
  const [qOptions, setQOptions] = useState(["", "", "", ""]);
  const [qCorrect, setQCorrect] = useState(0);
  const [qError, setQError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const isTopicLevel = node?.parent_id !== null && node?.parent_id !== undefined;

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const { data: current } = await contentApi.getNode(node_id);
      setNode(current);
      if (current.parent_id) {
        const { data: p } = await contentApi.getNode(current.parent_id);
        setParent(p);
      } else {
        setParent(null);
      }
      if (current.parent_id === null) {
        const { data } = await contentApi.listNodes(current.id);
        setChildren(data.results);
        setQuestions([]);
      } else {
        const { data } = await contentApi.listQuestions(current.id);
        setQuestions(data.results);
        setChildren([]);
      }
    } catch (err) {
      setLoadError(messageFor(err));
    }
  }, [node_id]);

  useEffect(() => {
    load();
  }, [load]);

  async function addTopic(e: React.FormEvent) {
    e.preventDefault();
    setChildError(null);
    if (!childName.trim()) {
      setChildError("Enter a topic name.");
      return;
    }
    setBusy(true);
    try {
      await contentApi.createNode(childName.trim(), node_id);
      setChildName("");
      toast.success("Topic added.");
      await load();
    } catch (err) {
      setChildError(messageFor(err));
    } finally {
      setBusy(false);
    }
  }

  async function addQuestion(e: React.FormEvent) {
    e.preventDefault();
    setQError(null);
    if (!qText.trim()) {
      setQError("Enter the question text.");
      return;
    }
    const options = qOptions
      .map((text, idx) => ({ option_text: text.trim(), is_correct: idx === qCorrect, display_order: idx + 1, label: LETTERS[idx] }))
      .filter((o) => o.option_text.length > 0);
    setBusy(true);
    try {
      await contentApi.createQuestion(node_id, qText.trim(), options, "");
      setQText("");
      setQOptions(["", "", "", ""]);
      setQCorrect(0);
      toast.success("Question saved as draft.");
      await load();
    } catch (err) {
      setQError(messageFor(err));
    } finally {
      setBusy(false);
    }
  }

  async function nodeAction(action: "publish" | "retire" | "restore") {
    if (!node) return;
    try {
      const { data } = await contentApi.nodeAction(node.id, action);
      setNode(data);
      toast.success(`Topic ${action === "publish" ? "published" : action === "retire" ? "retired" : "restored"}.`);
    } catch (err) {
      toast.error(messageFor(err));
    }
  }

  async function saveRename(e: React.FormEvent) {
    e.preventDefault();
    if (!node) return;
    setRenameError(null);
    if (!renameValue.trim()) {
      setRenameError("Enter a name.");
      return;
    }
    setBusy(true);
    try {
      const { data } = await contentApi.renameNode(node.id, renameValue.trim());
      setNode(data);
      setRenaming(false);
      toast.success("Renamed.");
    } catch (err) {
      setRenameError(messageFor(err));
    } finally {
      setBusy(false);
    }
  }

  async function deleteNode() {
    if (!node) return;
    setBusy(true);
    try {
      await contentApi.deleteNode(node.id);
      toast.success("Deleted.");
      router.push(parent ? `/admin/content/nodes/${parent.id}` : "/admin/content");
    } catch (err) {
      // A node with children or questions is refused by the server; show why.
      toast.error(messageFor(err));
    } finally {
      setBusy(false);
      setConfirmDelete(false);
    }
  }

  async function move(list: "nodes" | "questions", index: number, direction: -1 | 1) {
    const items = list === "nodes" ? children : questions;
    const target = index + direction;
    if (target < 0 || target >= items.length) return;
    const ids = items.map((i) => i.id);
    [ids[index], ids[target]] = [ids[target], ids[index]];
    try {
      if (list === "nodes") {
        await contentApi.reorderNodes(node_id, ids);
      } else {
        await contentApi.reorderQuestions(node_id, ids);
      }
      await load();
    } catch (err) {
      toast.error(messageFor(err));
    }
  }

  if (loadError) {
    return (
      <AdminLayout>
        <PageWrapper>
          <EmptyState icon={Layers} title="Could not load this node" subtitle={loadError} action={{ label: "Try again", onClick: load }} />
        </PageWrapper>
      </AdminLayout>
    );
  }

  return (
    <AdminLayout>
      <PageWrapper>
        <nav aria-label="Breadcrumb" className="text-xs mb-3" style={{ color: "var(--color-text-muted)" }}>
          <Link href="/admin/content" className="underline-offset-2 hover:underline">Content</Link>
          {parent && (
            <>
              {" / "}
              <Link href={`/admin/content/nodes/${parent.id}`} className="underline-offset-2 hover:underline">{parent.name}</Link>
            </>
          )}
        </nav>

        {node === null ? (
          <Skeleton className="h-10 w-64" />
        ) : (
          <PageHeader
            title={node.name}
            subtitle={`${isTopicLevel ? "Topic" : "Subject"} · ${STATUS_TEXT[node.status]}`}
            rightSlot={
              <div className="flex flex-wrap gap-2">
                {node.status === "draft" && <Button size="sm" variant="secondary" onClick={() => nodeAction("publish")}>Publish</Button>}
                {node.status === "published" && <Button size="sm" variant="warning" onClick={() => nodeAction("retire")}>Unpublish</Button>}
                {node.status === "retired" && <Button size="sm" variant="secondary" onClick={() => nodeAction("restore")}>Publish</Button>}
                <Button size="sm" variant="ghost" disabled={busy} onClick={() => { setRenameValue(node.name); setRenameError(null); setRenaming(true); }}>Rename</Button>
                <Button size="sm" variant="danger" disabled={busy} onClick={() => setConfirmDelete(true)}>Delete</Button>
              </div>
            }
          />
        )}

        {node && renaming && (
          <form onSubmit={saveRename} className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end" aria-label="Rename">
            <div className="flex-1 min-w-0">
              <Input label="Name" value={renameValue} onChange={(e) => setRenameValue(e.target.value)} error={renameError ?? undefined} maxLength={200} />
            </div>
            <Button type="submit" variant="primary" loading={busy}>Save name</Button>
            <Button type="button" variant="ghost" onClick={() => setRenaming(false)}>Cancel</Button>
          </form>
        )}

        <ConfirmDialog
          isOpen={confirmDelete}
          onClose={() => setConfirmDelete(false)}
          onConfirm={deleteNode}
          title="Delete this item?"
          message="Only empty items can be deleted. An item with topics or questions must be emptied first. Items that were used in an exam cannot be deleted; retire them instead."
          confirmLabel="Delete"
          confirmVariant="danger"
          loading={busy}
        />

        {node && !isTopicLevel && (
          <section aria-labelledby="topics-heading" className="mt-6">
            <h2 id="topics-heading" className="text-sm font-semibold mb-3">Topics</h2>
            <form onSubmit={addTopic} className="flex flex-col gap-3 sm:flex-row sm:items-end mb-4" aria-label="New topic">
              <div className="flex-1 min-w-0">
                <Input label="New topic name" value={childName} onChange={(e) => setChildName(e.target.value)} error={childError ?? undefined} maxLength={200} />
              </div>
              <Button type="submit" variant="primary" loading={busy} leftIcon={<Plus size={14} />} fullWidth className="sm:w-auto">Add topic</Button>
            </form>
            {children.length === 0 ? (
              <EmptyState icon={Layers} title="No topics yet" subtitle="Add a topic, then add questions inside it." />
            ) : (
              <ul className="space-y-2" aria-label="Topics">
                {children.map((c, i) => (
                  <li key={c.id} className="flex items-center justify-between gap-2 rounded-[var(--radius-lg)] p-3" style={{ border: "1px solid var(--color-border)" }}>
                    <Link href={`/admin/content/nodes/${c.id}`} className="min-w-0 break-words font-medium underline-offset-2 hover:underline">
                      {c.name} <span className="text-xs" style={{ color: "var(--color-text-muted)" }}>· {STATUS_TEXT[c.status]} · {c.question_count} question{c.question_count === 1 ? "" : "s"}</span>
                    </Link>
                    <div className="flex shrink-0 gap-1">
                      <Button size="sm" variant="ghost" aria-label={`Move ${c.name} up`} onClick={() => move("nodes", i, -1)} disabled={i === 0}><ArrowUp size={14} /></Button>
                      <Button size="sm" variant="ghost" aria-label={`Move ${c.name} down`} onClick={() => move("nodes", i, 1)} disabled={i === children.length - 1}><ArrowDown size={14} /></Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {node && isTopicLevel && (
          <section aria-labelledby="questions-heading" className="mt-6">
            <h2 id="questions-heading" className="text-sm font-semibold mb-3">Questions</h2>
            <form onSubmit={addQuestion} className="space-y-3 rounded-[var(--radius-xl)] p-4 mb-6" aria-label="New question" style={{ border: "1px solid var(--color-border)" }}>
              <Input label="Question text" value={qText} onChange={(e) => setQText(e.target.value)} error={qError ?? undefined} maxLength={2000} />
              <fieldset>
                <legend className="text-xs font-medium mb-2">Options (mark the one correct answer)</legend>
                <div className="space-y-2">
                  {qOptions.map((text, idx) => (
                    <div key={LETTERS[idx]} className="flex items-center gap-2">
                      <input
                        type="radio"
                        name="correct"
                        aria-label={`Option ${LETTERS[idx]} is correct`}
                        checked={qCorrect === idx}
                        onChange={() => setQCorrect(idx)}
                        className="h-5 w-5 shrink-0"
                      />
                      <div className="flex-1 min-w-0">
                        <Input
                          aria-label={`Option ${LETTERS[idx]} text`}
                          value={text}
                          onChange={(e) => setQOptions(qOptions.map((o, j) => (j === idx ? e.target.value : o)))}
                          maxLength={500}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </fieldset>
              <Button type="submit" variant="primary" loading={busy} leftIcon={<Plus size={14} />} fullWidth className="sm:w-auto">Save as draft</Button>
            </form>

            {questions.length === 0 ? (
              <EmptyState icon={FileText} title="No questions yet" subtitle="Save a question above. It stays a draft until you publish it." />
            ) : (
              <ul className="space-y-2" aria-label="Questions">
                {questions.map((q, i) => (
                  <li key={q.id} className="flex items-center justify-between gap-2 rounded-[var(--radius-lg)] p-3" style={{ border: "1px solid var(--color-border)" }}>
                    <Link href={`/admin/content/questions/${q.id}`} className="min-w-0 break-words underline-offset-2 hover:underline">
                      <span className="font-mono text-xs mr-2">{q.display_order}.</span>
                      {q.editable_version?.question_text ?? "(no text)"}
                      <span className="block text-xs mt-1" style={{ color: "var(--color-text-muted)" }}>{STATUS_TEXT[q.status]}</span>
                    </Link>
                    <div className="flex shrink-0 gap-1">
                      <Button size="sm" variant="ghost" aria-label={`Move question ${q.display_order} up`} onClick={() => move("questions", i, -1)} disabled={i === 0}><ArrowUp size={14} /></Button>
                      <Button size="sm" variant="ghost" aria-label={`Move question ${q.display_order} down`} onClick={() => move("questions", i, 1)} disabled={i === questions.length - 1}><ArrowDown size={14} /></Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}
      </PageWrapper>
    </AdminLayout>
  );
}
