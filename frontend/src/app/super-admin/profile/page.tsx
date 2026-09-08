"use client";

import { useEffect, useState, forwardRef } from "react";
import { useForm } from "react-hook-form";
import {
  Pencil, X, Check, KeyRound, User, Mail, ShieldCheck, Loader2,
  Eye, EyeOff, Camera, CalendarDays,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useAuthStore } from "@/lib/auth-store";
import { broadcastAdminEvent } from "@/lib/adminChannel";
import axios from "axios";
import api, { getErrorMessage } from "@/lib/api";
import type { SuperAdminUser } from "@/types";

// Mirrors admin/profile/page.tsx (2026-08-20) — Super Admin's self-service
// profile got the same /auth/me/ + /auth/me/change-password/ endpoints
// Admin already had (opened on the backend the same day). No layout wrapper
// here — super-admin/* uses the file-based layout.tsx (Pattern B), unlike
// admin/* (Pattern A).

// ── Password field with show/hide toggle ──────────────────────────────────────

interface PasswordFieldProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
}

const PasswordField = forwardRef<HTMLInputElement, PasswordFieldProps>(
  ({ label, error, ...props }, ref) => {
    const [show, setShow] = useState(false);
    return (
      <Input
        ref={ref}
        label={label}
        type={show ? "text" : "password"}
        error={error}
        rightElement={
          <button
            type="button"
            tabIndex={-1}
            onClick={() => setShow((v) => !v)}
            className="flex items-center justify-center transition-colors"
            style={{
              color: "var(--color-text-muted)",
              background: "none",
              border: "none",
              padding: 4,
              cursor: "pointer",
            }}
            onMouseEnter={(e) =>
              ((e.currentTarget as HTMLElement).style.color = "var(--color-text)")
            }
            onMouseLeave={(e) =>
              ((e.currentTarget as HTMLElement).style.color = "var(--color-text-muted)")
            }
            aria-label={show ? "Hide password" : "Show password"}
          >
            {show ? <EyeOff size={15} /> : <Eye size={15} />}
          </button>
        }
        {...props}
      />
    );
  }
);
PasswordField.displayName = "PasswordField";

// ── Types ──────────────────────────────────────────────────────────────────────

interface ProfileData {
  id: string;
  email: string;
  name: string;
  is_active: boolean;
  /** ISO-8601 — returned by backend; used for "Member since" display. */
  date_joined?: string;
}

interface NameForm {
  name: string;
}
interface PasswordForm {
  current_password: string;
  new_password: string;
  confirm_password: string;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

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

function formatDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat("en-IN", {
      day: "numeric",
      month: "long",
      year: "numeric",
    }).format(new Date(iso));
  } catch {
    return "—";
  }
}

// ── Shared action-button style (Edit / Change Password) ───────────────────────

const actionBtnBase: React.CSSProperties = {
  background: "#fff",
  color: "var(--color-text-muted)",
  border: "1px solid var(--color-border)",
};
const actionBtnHover = (el: HTMLElement) => {
  el.style.borderColor = "var(--color-accent)";
  el.style.color = "var(--color-accent)";
};
const actionBtnLeave = (el: HTMLElement) => {
  el.style.borderColor = "var(--color-border)";
  el.style.color = "var(--color-text-muted)";
};
const closeBtnHover = (el: HTMLElement) => {
  el.style.borderColor = "var(--color-danger)";
  el.style.color = "var(--color-danger)";
};

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <p
      className="text-[11px] font-semibold mb-1.5"
      style={{ color: "var(--color-text-muted)", letterSpacing: "0.02em" }}
    >
      {children}
    </p>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function SuperAdminProfilePage() {
  const { user, logout } = useAuth();
  const setUser = useAuthStore((s) => s.setUser);
  const { success: toastSuccess, error: toastError } = useToast();

  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [loadError, setLoadError] = useState("");
  const [loadingProfile, setLoadingProfile] = useState(true);

  // Name editing
  const [editingName, setEditingName] = useState(false);
  const [savingName, setSavingName] = useState(false);
  const [nameSavedFlash, setNameSavedFlash] = useState(false);

  // Password section
  const [showPasswordForm, setShowPasswordForm] = useState(false);
  const [savingPassword, setSavingPassword] = useState(false);

  // Avatar hover
  const [avatarHovered, setAvatarHovered] = useState(false);

  const nameForm = useForm<NameForm>();
  const pwForm = useForm<PasswordForm>();

  // ── Load profile ──────────────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoadingProfile(true);
      setLoadError("");
      try {
        const res = await api.get<{ data: ProfileData }>("/auth/me/");
        if (!cancelled) setProfile(res.data.data);
      } catch (err) {
        if (!cancelled) setLoadError(extractError(err));
      } finally {
        if (!cancelled) setLoadingProfile(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // ── Save name ─────────────────────────────────────────────────────────────────
  async function onSaveName(data: NameForm) {
    setSavingName(true);
    try {
      const res = await api.patch<{ data: ProfileData }>("/auth/me/", {
        name: data.name.trim(),
      });
      const updated = res.data.data;
      setProfile(updated);
      if (user?.role === "super_admin") {
        setUser({ ...(user as SuperAdminUser), name: updated.name });
      }
      broadcastAdminEvent({ type: "PROFILE_UPDATED", id: updated.id, name: updated.name });
      toastSuccess("Name updated successfully.");
      setEditingName(false);
      setNameSavedFlash(true);
      setTimeout(() => setNameSavedFlash(false), 2500);
    } catch (err) {
      nameForm.setError("name", { message: extractError(err, "name") });
    } finally {
      setSavingName(false);
    }
  }

  function startEditName() {
    if (showPasswordForm) {
      setShowPasswordForm(false);
      pwForm.reset();
    }
    nameForm.reset({ name: profile?.name ?? "" });
    setEditingName(true);
  }

  function cancelEditName() {
    nameForm.reset();
    setEditingName(false);
  }

  function openPasswordForm() {
    if (editingName) {
      cancelEditName();
    }
    setShowPasswordForm(true);
    pwForm.reset();
  }

  // ── Change password ───────────────────────────────────────────────────────────
  async function onChangePassword(data: PasswordForm) {
    if (data.new_password !== data.confirm_password) {
      pwForm.setError("confirm_password", { message: "Passwords do not match." });
      return;
    }
    setSavingPassword(true);
    try {
      await api.post("/auth/me/change-password/", {
        current_password: data.current_password,
        new_password: data.new_password,
        confirm_password: data.confirm_password,
      });
      toastSuccess("Password changed. Logging you out in a moment…");
      pwForm.reset();
      setShowPasswordForm(false);
      setTimeout(() => logout(), 1500);
    } catch (err) {
      const msg = extractError(err, "current_password");
      if (msg.toLowerCase().includes("current") || msg.toLowerCase().includes("incorrect")) {
        pwForm.setError("current_password", { message: msg });
      } else if (
        msg.toLowerCase().includes("different") ||
        msg.toLowerCase().includes("same")
      ) {
        pwForm.setError("new_password", { message: msg });
      } else {
        pwForm.setError("current_password", { message: msg });
      }
    } finally {
      setSavingPassword(false);
    }
  }

  function handleAvatarClick() {
    toastError("Profile photo upload is not yet available.");
  }

  // ── Loading state ─────────────────────────────────────────────────────────────
  if (loadingProfile) {
    return (
      <div
        className="flex items-center justify-center"
        style={{ minHeight: "60vh" }}
      >
        <Loader2
          className="animate-spin"
          size={28}
          style={{ color: "var(--color-accent)" }}
        />
      </div>
    );
  }

  // ── Error state ───────────────────────────────────────────────────────────────
  if (loadError || !profile) {
    return (
      <div className="p-6 max-w-2xl mx-auto mt-10">
        <div
          className="rounded-2xl p-5 flex items-center justify-between gap-4"
          style={{
            background: "var(--color-danger-bg)",
            border: "1px solid rgba(220,38,38,0.15)",
          }}
        >
          <p className="text-sm" style={{ color: "var(--color-danger)" }}>
            {loadError || "Unable to load profile."}
          </p>
          <button
            onClick={() => window.location.reload()}
            className="shrink-0 text-sm font-semibold px-4 py-2 rounded-lg"
            style={{ background: "var(--color-danger)", color: "#fff" }}
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const avatarLetter = (profile.name || profile.email).charAt(0).toUpperCase();

  return (
    <div
      className="px-4 sm:px-6 py-8 max-w-3xl mx-auto space-y-5"
      style={{ minHeight: "calc(100vh - 56px)" }}
    >

      {/* ── Header card — sticky so name/email stay visible while scrolling ─── */}
      <div
        className="rounded-2xl p-5 sm:p-6 flex items-center gap-4 sm:gap-5"
        style={{
          background: "var(--color-primary)",
          boxShadow: "var(--shadow-md)",
          position: "sticky",
          top: 56,
          zIndex: 20,
        }}
      >
        {/* Avatar — interactive overlay for future photo upload */}
        <button
          type="button"
          onClick={handleAvatarClick}
          onMouseEnter={() => setAvatarHovered(true)}
          onMouseLeave={() => setAvatarHovered(false)}
          aria-label="Change profile photo"
          className="relative shrink-0 rounded-full"
          style={{
            width: 68,
            height: 68,
            background: "var(--color-accent)",
            border: "none",
            padding: 0,
            overflow: "hidden",
          }}
        >
          <span
            className="flex items-center justify-center w-full h-full text-2xl font-bold select-none"
            style={{ color: "#fff" }}
          >
            {avatarLetter}
          </span>
          {/* Camera overlay on hover */}
          <div
            aria-hidden="true"
            style={{
              position: "absolute",
              inset: 0,
              background: "rgba(0,0,0,0.45)",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 3,
              opacity: avatarHovered ? 1 : 0,
              transition: "opacity 0.18s ease",
            }}
          >
            <Camera size={16} style={{ color: "#fff" }} />
            <span
              style={{
                fontSize: 8,
                color: "#fff",
                fontWeight: 700,
                letterSpacing: "0.06em",
                lineHeight: 1,
              }}
            >
              PHOTO
            </span>
          </div>
        </button>

        {/* Name + email + status */}
        <div className="min-w-0 flex-1">
          <p
            className="text-lg sm:text-xl font-bold truncate"
            style={{ color: "#fff" }}
          >
            {profile.name || (
              <span style={{ opacity: 0.5, fontStyle: "italic", fontSize: 16 }}>
                No name set
              </span>
            )}
          </p>
          <p
            className="text-sm mt-0.5 truncate"
            style={{ color: "rgba(255,255,255,0.60)" }}
          >
            {profile.email}
          </p>
          <span
            className="inline-flex items-center mt-2 px-2.5 py-0.5 rounded-full text-xs font-semibold"
            style={{
              background: profile.is_active
                ? "rgba(34,197,94,0.20)"
                : "rgba(239,68,68,0.20)",
              color: profile.is_active ? "#86efac" : "#fca5a5",
            }}
          >
            {profile.is_active ? "Active" : "Inactive"}
          </span>
        </div>
      </div>

      {/* ── Profile Details card ──────────────────────────────────────────────── */}
      <div
        className="rounded-2xl overflow-hidden"
        style={{
          background: "#fff",
          border: "1px solid var(--color-border)",
          boxShadow: "var(--shadow-md)",
        }}
      >
        {/* Card header */}
        <div
          className="px-5 sm:px-6 py-4"
          style={{
            borderBottom: "1px solid var(--color-border)",
            background: "var(--color-surface-hover)",
          }}
        >
          <p className="text-sm font-semibold" style={{ color: "var(--color-text)" }}>
            Profile Details
          </p>
          <p className="text-xs mt-0.5" style={{ color: "var(--color-text-muted)" }}>
            Email cannot be changed. Contact IT for email updates.
          </p>
        </div>

        <div className="divide-y" style={{ borderColor: "var(--color-border)" }}>

          {/* Full Name row */}
          <div className="px-5 sm:px-6 py-5">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-3 min-w-0 flex-1">
                <User
                  size={16}
                  style={{
                    color: "var(--color-text-muted)",
                    flexShrink: 0,
                    marginTop: 2,
                  }}
                />
                <div className="min-w-0 flex-1">
                  <FieldLabel>Full Name</FieldLabel>

                  {editingName ? (
                    <form
                      onSubmit={nameForm.handleSubmit(onSaveName)}
                      className="flex flex-col sm:flex-row sm:items-start gap-2"
                    >
                      <div className="w-full sm:max-w-xs">
                        <Input
                          placeholder="Your full name"
                          autoFocus
                          error={nameForm.formState.errors.name?.message}
                          {...nameForm.register("name", {
                            maxLength: {
                              value: 150,
                              message: "Name is too long (max 150 chars).",
                            },
                          })}
                        />
                      </div>
                      <div className="flex items-center gap-2 sm:mt-1">
                        <Button
                          type="submit"
                          size="sm"
                          loading={savingName}
                          leftIcon={<Check size={13} />}
                        >
                          Save
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          onClick={cancelEditName}
                          disabled={savingName}
                        >
                          Cancel
                        </Button>
                      </div>
                    </form>
                  ) : (
                    <div className="flex items-center gap-2 flex-wrap">
                      <p
                        className="text-sm font-medium"
                        style={{
                          color: profile.name
                            ? "var(--color-text)"
                            : "var(--color-text-muted)",
                        }}
                      >
                        {profile.name || (
                          <span style={{ fontStyle: "italic" }}>Not set</span>
                        )}
                      </p>
                      {nameSavedFlash && (
                        <span
                          className="inline-flex items-center gap-1 text-xs font-medium"
                          style={{ color: "var(--color-success)" }}
                        >
                          <Check size={12} /> Saved
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Edit button — hidden while editing */}
              {!editingName && (
                <button
                  onClick={startEditName}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold shrink-0 transition-all"
                  style={actionBtnBase}
                  onMouseEnter={(e) => actionBtnHover(e.currentTarget as HTMLElement)}
                  onMouseLeave={(e) => actionBtnLeave(e.currentTarget as HTMLElement)}
                >
                  <Pencil size={12} /> Edit
                </button>
              )}
            </div>
          </div>

          {/* Email row */}
          <div className="px-5 sm:px-6 py-5">
            <div className="flex items-center gap-3">
              <Mail
                size={16}
                style={{ color: "var(--color-text-muted)", flexShrink: 0 }}
              />
              <div className="min-w-0">
                <FieldLabel>Email Address</FieldLabel>
                <div className="flex items-center gap-2 flex-wrap">
                  <p
                    className="text-sm font-medium"
                    style={{ color: "var(--color-text)" }}
                  >
                    {profile.email}
                  </p>
                  <span
                    className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium"
                    style={{
                      background: "var(--color-surface-hover)",
                      color: "var(--color-text-muted)",
                      border: "1px solid var(--color-border)",
                    }}
                  >
                    Read-only
                  </span>
                </div>
              </div>
            </div>
          </div>

        </div>
      </div>

      {/* ── Security card ─────────────────────────────────────────────────────── */}
      <div
        className="rounded-2xl overflow-hidden"
        style={{
          background: "#fff",
          border: "1px solid var(--color-border)",
          boxShadow: "var(--shadow-md)",
        }}
      >
        <div
          className="px-5 sm:px-6 py-4 flex items-center justify-between gap-4"
          style={{
            borderBottom: showPasswordForm ? "1px solid var(--color-border)" : "none",
            background: "var(--color-surface-hover)",
          }}
        >
          <div className="min-w-0">
            <p className="text-sm font-semibold" style={{ color: "var(--color-text)" }}>
              Security
            </p>
            <p className="text-xs mt-0.5" style={{ color: "var(--color-text-muted)" }}>
              {showPasswordForm
                ? "Fill in all fields below to set a new password."
                : "Change your login password"}
            </p>
          </div>

          {showPasswordForm ? (
            <button
              onClick={() => {
                setShowPasswordForm(false);
                pwForm.reset();
              }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold shrink-0 transition-all"
              style={actionBtnBase}
              onMouseEnter={(e) => closeBtnHover(e.currentTarget as HTMLElement)}
              onMouseLeave={(e) => actionBtnLeave(e.currentTarget as HTMLElement)}
              aria-label="Close password form"
            >
              <X size={12} /> Close
            </button>
          ) : (
            <button
              onClick={openPasswordForm}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold shrink-0 transition-all"
              style={actionBtnBase}
              onMouseEnter={(e) => actionBtnHover(e.currentTarget as HTMLElement)}
              onMouseLeave={(e) => actionBtnLeave(e.currentTarget as HTMLElement)}
            >
              <KeyRound size={12} /> Change Password
            </button>
          )}
        </div>

        {showPasswordForm && (
          <form
            onSubmit={pwForm.handleSubmit(onChangePassword)}
            className="px-5 sm:px-6 py-5 space-y-4"
          >
            <PasswordField
              label="Current Password"
              placeholder="Enter your current password"
              error={pwForm.formState.errors.current_password?.message}
              {...pwForm.register("current_password", {
                required: "Current password is required.",
              })}
            />
            <PasswordField
              label="New Password"
              placeholder="Min. 8 characters"
              error={pwForm.formState.errors.new_password?.message}
              {...pwForm.register("new_password", {
                required: "New password is required.",
                minLength: {
                  value: 8,
                  message: "Password must be at least 8 characters.",
                },
              })}
            />
            <PasswordField
              label="Confirm New Password"
              placeholder="Re-enter new password"
              error={pwForm.formState.errors.confirm_password?.message}
              {...pwForm.register("confirm_password", {
                required: "Please confirm your new password.",
              })}
            />

            <div className="flex items-start gap-1.5 pt-1">
              <ShieldCheck
                size={13}
                style={{
                  color: "var(--color-text-muted)",
                  marginTop: 1,
                  flexShrink: 0,
                }}
              />
              <p className="text-xs" style={{ color: "var(--color-text-muted)" }}>
                You will be logged out after changing your password.
              </p>
            </div>

            <div className="flex justify-end gap-3 pt-1">
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  setShowPasswordForm(false);
                  pwForm.reset();
                }}
                disabled={savingPassword}
              >
                Cancel
              </Button>
              <Button type="submit" loading={savingPassword}>
                Update Password
              </Button>
            </div>
          </form>
        )}
      </div>

      {/* ── Account Information card ─────────────────────────────────────────── */}
      {profile.date_joined && (
        <div
          className="rounded-2xl overflow-hidden"
          style={{
            background: "#fff",
            border: "1px solid var(--color-border)",
            boxShadow: "var(--shadow-md)",
          }}
        >
          <div
            className="px-5 sm:px-6 py-4"
            style={{
              borderBottom: "1px solid var(--color-border)",
              background: "var(--color-surface-hover)",
            }}
          >
            <p className="text-sm font-semibold" style={{ color: "var(--color-text)" }}>
              Account Information
            </p>
            <p className="text-xs mt-0.5" style={{ color: "var(--color-text-muted)" }}>
              Read-only details about your account.
            </p>
          </div>

          <div className="px-5 sm:px-6 py-5">
            <div className="flex items-center gap-3">
              <CalendarDays
                size={16}
                style={{ color: "var(--color-text-muted)", flexShrink: 0 }}
              />
              <div>
                <FieldLabel>Member Since</FieldLabel>
                <p
                  className="text-sm font-medium"
                  style={{ color: "var(--color-text)" }}
                >
                  {formatDate(profile.date_joined)}
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
