"use client";

import { useEffect, useState } from "react";
import {
  Plus, Trash2, Pencil,
  ChevronUp, ChevronDown, Link2,
  ArrowLeft, ArrowRight, Save, Loader2, GripVertical,
} from "lucide-react";
import api from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { AdminLayout } from "@/components/layout/AdminLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import type { ScrollConfig, ScrollUpdate } from "@/types";

// ── Helpers ───────────────────────────────────────────────────────────────────

function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={() => !disabled && onChange(!checked)}
      aria-pressed={checked}
      disabled={disabled}
      style={{
        display: "inline-flex",
        alignItems: "center",
        width: 48,
        height: 26,
        borderRadius: 99,
        padding: "0 3px",
        border: "none",
        cursor: disabled ? "not-allowed" : "pointer",
        background: checked ? "#FF8C00" : "#d1d5db",
        transition: "background 0.2s",
        flexShrink: 0,
        opacity: disabled ? 0.55 : 1,
      }}
    >
      <span
        style={{
          width: 20,
          height: 20,
          borderRadius: "50%",
          background: "#fff",
          boxShadow: "0 1px 4px rgba(0,0,0,0.18)",
          transform: checked ? "translateX(22px)" : "translateX(0)",
          transition: "transform 0.2s cubic-bezier(0.4,0,0.2,1)",
          display: "block",
        }}
      />
    </button>
  );
}

// ── Edit row state ─────────────────────────────────────────────────────────────

interface DraftItem {
  text: string;
  link: string;
  show_new_badge: boolean;
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function AdminScrollPage() {
  const { showToast } = useToast();

  // Config
  const [config, setConfig]         = useState<ScrollConfig | null>(null);
  const [configSaving, setConfigSaving] = useState(false);

  // Updates list
  const [updates, setUpdates]       = useState<ScrollUpdate[]>([]);
  const [loading, setLoading]       = useState(true);

  // New item form
  const [showAdd, setShowAdd]       = useState(false);
  const [newText, setNewText]       = useState("");
  const [newLink, setNewLink]       = useState("");
  const [newBadge, setNewBadge]     = useState(false);
  const [adding, setAdding]         = useState(false);

  // Inline edit
  const [editingId, setEditingId]   = useState<string | null>(null);
  const [draft, setDraft]           = useState<DraftItem>({ text: "", link: "", show_new_badge: false });
  const [editSaving, setEditSaving] = useState(false);

  // Delete
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Reorder
  const [reordering, setReordering] = useState(false);

  // ── Load ──────────────────────────────────────────────────────────────────

  useEffect(() => {
    async function load() {
      try {
        const [cfgRes, updRes] = await Promise.all([
          api.get("/users/scroll/config/"),
          api.get("/users/scroll/updates/"),
        ]);
        setConfig(cfgRes.data.data);
        setUpdates(updRes.data.data ?? []);
      } catch {
        showToast("error", "Failed to load scroll settings.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [showToast]);

  // ── Config patch ──────────────────────────────────────────────────────────

  async function patchConfig(patch: Partial<ScrollConfig>) {
    if (!config) return;
    const optimistic = { ...config, ...patch };
    setConfig(optimistic);
    setConfigSaving(true);
    try {
      const res = await api.patch("/users/scroll/config/", patch);
      setConfig(res.data.data);
    } catch {
      setConfig(config); // rollback
      showToast("error", "Failed to update configuration.");
    } finally {
      setConfigSaving(false);
    }
  }

  // ── Add new item ──────────────────────────────────────────────────────────

  async function handleAdd() {
    if (!newText.trim()) return;
    setAdding(true);
    try {
      const res = await api.post("/users/scroll/updates/", {
        text: newText.trim(),
        link: newLink.trim(),
        show_new_badge: newBadge,
      });
      setUpdates((prev) => [...prev, res.data.data]);
      setNewText("");
      setNewLink("");
      setNewBadge(false);
      setShowAdd(false);
      showToast("success", "Update added.");
    } catch {
      showToast("error", "Failed to add update.");
    } finally {
      setAdding(false);
    }
  }

  // ── Inline edit ───────────────────────────────────────────────────────────

  function startEdit(item: ScrollUpdate) {
    setEditingId(item.id);
    setDraft({ text: item.text, link: item.link, show_new_badge: item.show_new_badge });
  }

  function cancelEdit() {
    setEditingId(null);
  }

  async function saveEdit(id: string) {
    if (!draft.text.trim()) return;
    setEditSaving(true);
    try {
      const res = await api.patch(`/users/scroll/updates/${id}/`, {
        text: draft.text.trim(),
        link: draft.link.trim(),
        show_new_badge: draft.show_new_badge,
      });
      setUpdates((prev) =>
        prev.map((u) => (u.id === id ? res.data.data : u))
      );
      setEditingId(null);
      showToast("success", "Update saved.");
    } catch {
      showToast("error", "Failed to save update.");
    } finally {
      setEditSaving(false);
    }
  }

  // ── Delete ────────────────────────────────────────────────────────────────

  async function handleDelete(id: string) {
    setDeletingId(id);
    try {
      await api.delete(`/users/scroll/updates/${id}/`);
      setUpdates((prev) => prev.filter((u) => u.id !== id));
      showToast("success", "Update deleted.");
    } catch {
      showToast("error", "Failed to delete update.");
    } finally {
      setDeletingId(null);
    }
  }

  // ── Reorder (move up/down) ────────────────────────────────────────────────

  async function move(index: number, dir: -1 | 1) {
    const newArr = [...updates];
    const target = index + dir;
    if (target < 0 || target >= newArr.length) return;
    [newArr[index], newArr[target]] = [newArr[target], newArr[index]];
    setUpdates(newArr);
    setReordering(true);
    try {
      const res = await api.post("/users/scroll/reorder/", {
        ids: newArr.map((u) => u.id),
      });
      setUpdates(res.data.data ?? newArr);
    } catch {
      setUpdates(updates); // rollback
      showToast("error", "Failed to save order.");
    } finally {
      setReordering(false);
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <AdminLayout>
    <PageWrapper>
    <div style={{ maxWidth: 720, margin: "0 auto", padding: "8px 0 64px" }}>

      {/* Page title */}
      <div style={{ marginBottom: 28 }}>
        <h1
          style={{
            fontSize: 22,
            fontWeight: 700,
            color: "#1A3150",
            letterSpacing: "-0.02em",
            lineHeight: 1.2,
          }}
        >
          Scrolling Updates
        </h1>
        <p style={{ fontSize: 13, color: "#8fa3b8", marginTop: 4 }}>
          Manage the live announcement bar shown to all students below the header.
        </p>
      </div>

      {loading ? (
        <div style={{ display: "flex", alignItems: "center", gap: 10, color: "#8fa3b8", fontSize: 14, paddingTop: 24 }}>
          <Loader2 size={18} className="animate-spin" />
          Loading…
        </div>
      ) : (
        <>
          {/* ── Configuration card ─────────────────────────────────────────── */}
          <div
            style={{
              background: "#fff",
              border: "1px solid #e6e3df",
              borderRadius: 14,
              padding: "20px 22px",
              marginBottom: 24,
              boxShadow: "0 1px 4px rgba(0,0,0,0.04)",
            }}
          >
            <p style={{ fontSize: 11, fontWeight: 600, color: "#8fa3b8", letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 16 }}>
              Configuration
            </p>

            {/* Enable / disable */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", paddingBottom: 16, borderBottom: "1px solid #f3f4f6" }}>
              <div>
                <p style={{ fontSize: 14, fontWeight: 600, color: "#1A3150" }}>Show scrolling bar</p>
                <p style={{ fontSize: 12, color: "#8fa3b8", marginTop: 2 }}>
                  Toggle visibility for all students instantly.
                </p>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                {configSaving && <Loader2 size={14} className="animate-spin" style={{ color: "#8fa3b8" }} />}
                <Toggle
                  checked={config?.is_enabled ?? false}
                  onChange={(v) => patchConfig({ is_enabled: v })}
                  disabled={configSaving}
                />
              </div>
            </div>

            {/* Direction */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", paddingTop: 14 }}>
              <div>
                <p style={{ fontSize: 14, fontWeight: 600, color: "#1A3150" }}>Scroll direction</p>
                <p style={{ fontSize: 12, color: "#8fa3b8", marginTop: 2 }}>
                  Direction the updates move across the screen.
                </p>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                {(["left", "right"] as const).map((dir) => (
                  <button
                    key={dir}
                    onClick={() => patchConfig({ direction: dir })}
                    disabled={configSaving}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      padding: "7px 14px",
                      borderRadius: 8,
                      border: "1px solid",
                      borderColor: config?.direction === dir ? "#FF8C00" : "#e6e3df",
                      background: config?.direction === dir ? "#FFF4E6" : "#fff",
                      color: config?.direction === dir ? "#E8820C" : "#6b7280",
                      fontSize: 13,
                      fontWeight: config?.direction === dir ? 600 : 400,
                      cursor: configSaving ? "not-allowed" : "pointer",
                      transition: "all 0.15s",
                      fontFamily: "inherit",
                    }}
                  >
                    {dir === "left" ? <ArrowLeft size={13} /> : <ArrowRight size={13} />}
                    {dir === "left" ? "Left" : "Right"}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* ── Updates list ───────────────────────────────────────────────── */}
          <div
            style={{
              background: "#fff",
              border: "1px solid #e6e3df",
              borderRadius: 14,
              overflow: "hidden",
              boxShadow: "0 1px 4px rgba(0,0,0,0.04)",
            }}
          >
            {/* List header */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "16px 20px",
                borderBottom: "1px solid #f3f4f6",
              }}
            >
              <div>
                <p style={{ fontSize: 11, fontWeight: 600, color: "#8fa3b8", letterSpacing: "0.06em", textTransform: "uppercase" }}>
                  Updates · {updates.length}
                </p>
              </div>
              <button
                onClick={() => { setShowAdd(true); setEditingId(null); }}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "7px 14px",
                  borderRadius: 8,
                  border: "none",
                  background: "#FF8C00",
                  color: "#fff",
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: "pointer",
                  fontFamily: "inherit",
                  boxShadow: "0 2px 8px rgba(255,140,0,0.24)",
                  transition: "background 0.15s",
                }}
              >
                <Plus size={14} />
                Add Update
              </button>
            </div>

            {/* Add form */}
            {showAdd && (
              <div
                style={{
                  padding: "16px 20px",
                  background: "#FFFBF5",
                  borderBottom: "1px solid #fde8c4",
                }}
              >
                <p style={{ fontSize: 12, fontWeight: 600, color: "#E8820C", marginBottom: 12 }}>
                  New update
                </p>
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <textarea
                    value={newText}
                    onChange={(e) => setNewText(e.target.value)}
                    placeholder="Update text (max 300 characters)…"
                    maxLength={300}
                    rows={2}
                    style={{
                      width: "100%",
                      padding: "10px 12px",
                      borderRadius: 8,
                      border: "1px solid #e6e3df",
                      fontSize: 13,
                      fontFamily: "inherit",
                      resize: "none",
                      outline: "none",
                      color: "#1A3150",
                      background: "#fff",
                      boxSizing: "border-box",
                    }}
                  />
                  <input
                    type="url"
                    value={newLink}
                    onChange={(e) => setNewLink(e.target.value)}
                    placeholder="Link URL (optional)"
                    style={{
                      width: "100%",
                      padding: "9px 12px",
                      borderRadius: 8,
                      border: "1px solid #e6e3df",
                      fontSize: 13,
                      fontFamily: "inherit",
                      outline: "none",
                      color: "#1A3150",
                      background: "#fff",
                      boxSizing: "border-box",
                    }}
                  />
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                      <Toggle checked={newBadge} onChange={setNewBadge} />
                      <span style={{ fontSize: 13, color: "#5c6e82" }}>Show "NEW" badge</span>
                    </label>
                    <div style={{ display: "flex", gap: 8 }}>
                      <button
                        onClick={() => { setShowAdd(false); setNewText(""); setNewLink(""); setNewBadge(false); }}
                        style={{
                          padding: "7px 14px",
                          borderRadius: 8,
                          border: "1px solid #e6e3df",
                          background: "#fff",
                          color: "#6b7280",
                          fontSize: 13,
                          fontFamily: "inherit",
                          cursor: "pointer",
                        }}
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleAdd}
                        disabled={adding || !newText.trim()}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                          padding: "7px 16px",
                          borderRadius: 8,
                          border: "none",
                          background: adding || !newText.trim() ? "#fcd8a0" : "#FF8C00",
                          color: "#fff",
                          fontSize: 13,
                          fontWeight: 600,
                          fontFamily: "inherit",
                          cursor: adding || !newText.trim() ? "not-allowed" : "pointer",
                        }}
                      >
                        {adding ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
                        Add
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Empty state */}
            {updates.length === 0 && !showAdd && (
              <div
                style={{
                  padding: "48px 20px",
                  textAlign: "center",
                  color: "#8fa3b8",
                }}
              >
                <div
                  style={{
                    width: 48,
                    height: 48,
                    borderRadius: 12,
                    background: "#f3f4f6",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    margin: "0 auto 12px",
                  }}
                >
                  <GripVertical size={20} style={{ color: "#d1d5db" }} />
                </div>
                <p style={{ fontSize: 14, fontWeight: 500, color: "#6b7280" }}>No updates yet</p>
                <p style={{ fontSize: 12, marginTop: 4 }}>
                  Click "Add Update" to create your first announcement.
                </p>
              </div>
            )}

            {/* Update rows */}
            {updates.map((item, idx) => (
              <div
                key={item.id}
                style={{
                  borderBottom: idx < updates.length - 1 ? "1px solid #f3f4f6" : "none",
                  background: editingId === item.id ? "#FFFBF5" : "#fff",
                  transition: "background 0.15s",
                }}
              >
                {editingId === item.id ? (
                  /* ── Edit mode ──────────────────────────────────────────── */
                  <div style={{ padding: "14px 20px" }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      <textarea
                        value={draft.text}
                        onChange={(e) => setDraft((d) => ({ ...d, text: e.target.value }))}
                        maxLength={300}
                        rows={2}
                        autoFocus
                        style={{
                          width: "100%",
                          padding: "9px 11px",
                          borderRadius: 8,
                          border: "1.5px solid #FF8C00",
                          fontSize: 13,
                          fontFamily: "inherit",
                          resize: "none",
                          outline: "none",
                          color: "#1A3150",
                          background: "#fff",
                          boxSizing: "border-box",
                        }}
                      />
                      <input
                        type="url"
                        value={draft.link}
                        onChange={(e) => setDraft((d) => ({ ...d, link: e.target.value }))}
                        placeholder="Link URL (optional)"
                        style={{
                          width: "100%",
                          padding: "8px 11px",
                          borderRadius: 8,
                          border: "1px solid #e6e3df",
                          fontSize: 13,
                          fontFamily: "inherit",
                          outline: "none",
                          color: "#1A3150",
                          background: "#fff",
                          boxSizing: "border-box",
                        }}
                      />
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                        <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                          <Toggle
                            checked={draft.show_new_badge}
                            onChange={(v) => setDraft((d) => ({ ...d, show_new_badge: v }))}
                          />
                          <span style={{ fontSize: 13, color: "#5c6e82" }}>Show "NEW" badge</span>
                        </label>
                        <div style={{ display: "flex", gap: 8 }}>
                          <button
                            onClick={cancelEdit}
                            style={{
                              padding: "7px 12px",
                              borderRadius: 8,
                              border: "1px solid #e6e3df",
                              background: "#fff",
                              color: "#6b7280",
                              fontSize: 13,
                              fontFamily: "inherit",
                              cursor: "pointer",
                            }}
                          >
                            Cancel
                          </button>
                          <button
                            onClick={() => saveEdit(item.id)}
                            disabled={editSaving || !draft.text.trim()}
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: 6,
                              padding: "7px 14px",
                              borderRadius: 8,
                              border: "none",
                              background: editSaving || !draft.text.trim() ? "#fcd8a0" : "#FF8C00",
                              color: "#fff",
                              fontSize: 13,
                              fontWeight: 600,
                              fontFamily: "inherit",
                              cursor: editSaving || !draft.text.trim() ? "not-allowed" : "pointer",
                            }}
                          >
                            {editSaving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                            Save
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  /* ── View mode ──────────────────────────────────────────── */
                  <div
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: 12,
                      padding: "14px 20px",
                    }}
                  >
                    {/* Order controls */}
                    <div
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: 2,
                        flexShrink: 0,
                        marginTop: 2,
                      }}
                    >
                      <button
                        onClick={() => move(idx, -1)}
                        disabled={idx === 0 || reordering}
                        style={{
                          width: 22,
                          height: 22,
                          borderRadius: 5,
                          border: "1px solid #e6e3df",
                          background: "#fff",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          cursor: idx === 0 || reordering ? "not-allowed" : "pointer",
                          opacity: idx === 0 ? 0.3 : 1,
                          color: "#6b7280",
                        }}
                      >
                        <ChevronUp size={12} />
                      </button>
                      <button
                        onClick={() => move(idx, 1)}
                        disabled={idx === updates.length - 1 || reordering}
                        style={{
                          width: 22,
                          height: 22,
                          borderRadius: 5,
                          border: "1px solid #e6e3df",
                          background: "#fff",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          cursor: idx === updates.length - 1 || reordering ? "not-allowed" : "pointer",
                          opacity: idx === updates.length - 1 ? 0.3 : 1,
                          color: "#6b7280",
                        }}
                      >
                        <ChevronDown size={12} />
                      </button>
                    </div>

                    {/* Content */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                        <p
                          style={{
                            fontSize: 14,
                            color: "#1A3150",
                            fontWeight: 500,
                            lineHeight: 1.45,
                            wordBreak: "break-word",
                          }}
                        >
                          {item.text}
                        </p>
                        {item.show_new_badge && (
                          <span
                            style={{
                              fontSize: 9,
                              fontWeight: 700,
                              letterSpacing: "0.06em",
                              padding: "2px 6px",
                              borderRadius: 99,
                              background: "#FFF4E6",
                              color: "#E8820C",
                              border: "1px solid #fde8c4",
                              flexShrink: 0,
                            }}
                          >
                            NEW
                          </span>
                        )}
                      </div>
                      {item.link && (
                        <p
                          style={{
                            fontSize: 11,
                            color: "#8fa3b8",
                            marginTop: 3,
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                        >
                          <Link2 size={10} style={{ display: "inline", marginRight: 4, verticalAlign: "middle" }} />
                          {item.link}
                        </p>
                      )}
                    </div>

                    {/* Actions */}
                    <div style={{ display: "flex", gap: 6, flexShrink: 0, marginTop: 2 }}>
                      <button
                        onClick={() => startEdit(item)}
                        style={{
                          width: 30,
                          height: 30,
                          borderRadius: 7,
                          border: "1px solid #e6e3df",
                          background: "#fff",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          cursor: "pointer",
                          color: "#6b7280",
                          transition: "background 0.15s",
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = "#f9fafb")}
                        onMouseLeave={(e) => (e.currentTarget.style.background = "#fff")}
                        title="Edit"
                      >
                        <Pencil size={13} />
                      </button>
                      <button
                        onClick={() => handleDelete(item.id)}
                        disabled={deletingId === item.id}
                        style={{
                          width: 30,
                          height: 30,
                          borderRadius: 7,
                          border: "1px solid #fee2e2",
                          background: "#fff",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          cursor: deletingId === item.id ? "wait" : "pointer",
                          color: "#ef4444",
                          transition: "background 0.15s",
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = "#FEF2F2")}
                        onMouseLeave={(e) => (e.currentTarget.style.background = "#fff")}
                        title="Delete"
                      >
                        {deletingId === item.id
                          ? <Loader2 size={13} className="animate-spin" />
                          : <Trash2 size={13} />
                        }
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Live preview hint */}
          {updates.length > 0 && (
            <p style={{ fontSize: 12, color: "#a3b0be", textAlign: "center", marginTop: 16 }}>
              Changes take effect immediately for all logged-in students.
            </p>
          )}
        </>
      )}
    </div>
    </PageWrapper>
    </AdminLayout>
  );
}
