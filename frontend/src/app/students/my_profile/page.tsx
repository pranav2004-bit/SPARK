"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { Eye, EyeOff, User, Mail, Building2, GraduationCap, Info, KeyRound, ArrowLeft, Pencil, Check, X as XIcon, Loader2 } from "lucide-react";
import { StudentLayout } from "@/components/layout/StudentLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { useAuthStore } from "@/lib/auth-store";
import { setAuthCookies } from "@/lib/cookies";
import { consumeScrollRedirect } from "@/lib/scrollRedirect";
import api, { getErrorMessage } from "@/lib/api";
import type {
  StudentProfile,
  StudentUser,
  ApiSuccess,
} from "@/types";

// ── Profile info field ────────────────────────────────────────────────────────
function InfoField({
  icon: Icon,
  label,
  value,
  loading,
}: {
  icon: React.ElementType;
  label: string;
  value?: string | null;
  loading: boolean;
}) {
  return (
    <div className="flex items-start gap-3 py-3 border-b border-[var(--color-border)] last:border-0">
      <div className="w-8 h-8 rounded-[var(--radius-md)] bg-[var(--color-surface-hover)] flex items-center justify-center shrink-0 mt-0.5">
        <Icon size={17} className="text-[var(--color-text-muted)]" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs text-[var(--color-text-muted)] mb-0.5">{label}</p>
        {loading ? (
          <Skeleton className="h-4 w-36 mt-1" />
        ) : (
          <p
            className="text-sm font-medium text-[var(--color-text)] break-all"
            title={value ?? undefined}
          >
            {value || "—"}
          </p>
        )}
      </div>
    </div>
  );
}

// ── First-login setup form ────────────────────────────────────────────────────
interface SetupForm {
  fullname: string;
  college_email_id: string;
  current_password: string;
  new_password: string;
  confirm_password: string;
  change_password: boolean;
}

// ── Change-password-only form (returning users) ───────────────────────────────
interface ChangePasswordForm {
  current_password: string;
  new_password: string;
  confirm_password: string;
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function MyProfilePage() {
  const router = useRouter();
  const toast = useToast();
  const { user, setTokens, accessToken: currentAccessToken, refreshToken: currentRefreshToken } = useAuthStore();
  const studentUser = user as StudentUser | null;

  const isFirstLogin = studentUser?.is_profile_completed === false;

  const [profile, setProfile] = useState<StudentProfile | null>(null);
  const [profileLoading, setProfileLoading] = useState(true);

  // ── Setup form (first login) ────────────────────────────────────────────────
  const [setupSaving, setSetupSaving] = useState(false);
  const [setupError, setSetupError] = useState("");
  const [showSetupNew, setShowSetupNew] = useState(false);
  const [showSetupConfirm, setShowSetupConfirm] = useState(false);
  const [showSetupCurrent, setShowSetupCurrent] = useState(false);
  const [wantsPasswordChange, setWantsPasswordChange] = useState(false);

  const {
    register: regSetup,
    handleSubmit: handleSetup,
    watch: watchSetup,
    formState: { errors: setupErrors },
  } = useForm<SetupForm>({ mode: "onBlur" });

  const setupNewPass = watchSetup("new_password");
  const setupCurrentPass = watchSetup("current_password");

  // ── Profile edit (returning users) ────────────────────────────────────────
  const [backLoading, setBackLoading] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editFullname, setEditFullname] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState("");

  function startEdit() {
    setEditFullname(profile?.fullname ?? "");
    setEditEmail(profile?.college_email_id ?? "");
    setEditError("");
    setIsEditing(true);
  }

  function cancelEdit() {
    setIsEditing(false);
    setEditError("");
  }

  async function handleEditSave() {
    const name = editFullname.trim();
    const email = editEmail.trim().toLowerCase();
    if (!name) { setEditError("Full name cannot be empty."); return; }
    if (!email) { setEditError("College email cannot be empty."); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { setEditError("Enter a valid email address."); return; }

    setEditSaving(true);
    setEditError("");
    try {
      const res = await api.patch<ApiSuccess<StudentProfile>>(
        "/users/me/",
        { fullname: name, college_email_id: email }
      );
      const updated = res.data.data;
      setProfile(updated);
      // Update auth store so avatar initial + dropdown name refresh immediately
      const updatedUser: StudentUser = {
        ...(studentUser as StudentUser),
        fullname: updated.fullname ?? "",
      };
      setTokens(currentAccessToken!, currentRefreshToken!, updatedUser);
      setIsEditing(false);
      toast.success("Profile updated successfully.");
    } catch (err) {
      setEditError(getErrorMessage(err) || "Failed to update profile.");
    } finally {
      setEditSaving(false);
    }
  }

  // ── Password-only form (returning users) ───────────────────────────────────
  const [pwSaving, setPwSaving] = useState(false);
  const [pwError, setPwError] = useState("");
  const [pwErrorKey, setPwErrorKey] = useState(0);
  const [showPwCurrent, setShowPwCurrent] = useState(false);
  const [showPwNew, setShowPwNew] = useState(false);
  const [showPwConfirm, setShowPwConfirm] = useState(false);

  const {
    register: regPw,
    handleSubmit: handlePw,
    watch: watchPw,
    reset: resetPw,
    formState: { errors: pwErrors },
  } = useForm<ChangePasswordForm>({ mode: "onBlur" });

  const pwNewPass = watchPw("new_password");
  const pwCurrentPass = watchPw("current_password");

  // ── Fetch profile ──────────────────────────────────────────────────────────
  const fetchProfile = useCallback(async () => {
    try {
      const res = await api.get<ApiSuccess<StudentProfile>>("/users/me/");
      setProfile(res.data.data);
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setProfileLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    fetchProfile();
  }, [fetchProfile]);

  // ── First-login submit ─────────────────────────────────────────────────────
  async function onSetupSubmit(data: SetupForm) {
    setSetupSaving(true);
    setSetupError("");

    try {
      // Step 1: change password if requested (optional but encouraged)
      if (wantsPasswordChange && data.new_password) {
        await api.post("/auth/student/change-password/", {
          current_password: data.current_password,
          new_password: data.new_password,
          repeat_new_password: data.confirm_password,
        });
      }

      // Step 2: update profile (mandatory — this is what marks is_profile_completed=true)
      const res = await api.put<ApiSuccess<StudentProfile>>(
        "/users/me/",
        {
          fullname: data.fullname.trim(),
          college_email_id: data.college_email_id.trim().toLowerCase(),
        }
      );

      const updatedProfile = res.data.data;
      setProfile(updatedProfile);

      const updatedUser: StudentUser = {
        student_id: updatedProfile.student_id,
        role: "student",
        is_profile_completed: updatedProfile.is_profile_completed,
        fullname: updatedProfile.fullname ?? "",
      };

      // Step 3: Sync auth-service — marks is_profile_completed=True in auth_db
      // and returns fresh tokens with the correct JWT claim baked in.
      // Without this every subsequent login re-issues tokens with is_profile_completed=False.
      const syncRes = await api.patch<ApiSuccess<{ access_token: string; refresh_token: string }>>(
        "/auth/profile/complete/",
        { fullname: data.fullname.trim() }
      );
      const { access_token, refresh_token } = syncRes.data.data;
      setTokens(access_token, refresh_token, updatedUser);
      setAuthCookies("student", access_token);

      toast.success("Profile setup complete. Welcome!");
      // If the student arrived via a scroll-bar deep link, send them there now.
      // consumeScrollRedirect() validates the path is /students/ before returning it.
      const nextPath = consumeScrollRedirect();
      window.location.href = nextPath ?? "/students/home";
    } catch (err) {
      const raw = getErrorMessage(err);
      if (
        raw.toLowerCase().includes("current") ||
        raw.toLowerCase().includes("incorrect") ||
        raw.toLowerCase().includes("wrong")
      ) {
        setSetupError("Current password is incorrect. Please try again.");
      } else {
        setSetupError(raw || "Setup failed. Please try again.");
      }
    } finally {
      setSetupSaving(false);
    }
  }

  // ── Change password submit (returning users) ───────────────────────────────
  async function onPasswordSubmit(data: ChangePasswordForm) {
    setPwErrorKey((k) => k + 1);
    setPwSaving(true);
    setPwError("");

    try {
      const res = await api.post<ApiSuccess<{ access_token: string; refresh_token: string }>>(
        "/auth/student/change-password/",
        {
          current_password: data.current_password,
          new_password: data.new_password,
          repeat_new_password: data.confirm_password,
        }
      );

      const { access_token, refresh_token } = res.data.data;

      // Update auth store with new tokens
      if (studentUser) {
        setTokens(access_token, refresh_token, studentUser);
        setAuthCookies("student", access_token);
      }

      resetPw();
      toast.success("Password changed successfully.");
    } catch (err) {
      const raw = getErrorMessage(err);
      if (
        raw.toLowerCase().includes("current") ||
        raw.toLowerCase().includes("incorrect") ||
        raw.toLowerCase().includes("wrong")
      ) {
        setPwError("Current password is incorrect.");
      } else {
        setPwError(raw || "Failed to update password. Please try again.");
      }
    } finally {
      setPwSaving(false);
    }
  }

  // ── Inline error helper ────────────────────────────────────────────────────
  function ErrorBanner({ message }: { message: string }) {
    return (
      <div
        className={[
          "rounded-[var(--radius-md)] text-sm text-[var(--color-danger)]",
          "bg-[var(--color-danger-bg)] border border-red-100 transition-all duration-200",
          message
            ? "mt-4 p-3 opacity-100 max-h-20"
            : "!mt-0 p-0 opacity-0 max-h-0 overflow-hidden border-transparent",
        ].join(" ")}
        role="alert"
        aria-live="polite"
      >
        {message}
      </div>
    );
  }

  // ── Password eye toggle helper ─────────────────────────────────────────────
  function EyeToggle({
    show,
    onToggle,
  }: {
    show: boolean;
    onToggle: () => void;
  }) {
    return (
      <button
        type="button"
        onClick={onToggle}
        tabIndex={-1}
        className="text-[var(--color-text-muted)] hover:text-[var(--color-text)] p-1 transition-colors"
        aria-label={show ? "Hide password" : "Show password"}
      >
        {show ? <EyeOff size={14} /> : <Eye size={14} />}
      </button>
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // FIRST-LOGIN VIEW
  // ═══════════════════════════════════════════════════════════════════════════
  if (isFirstLogin) {
    return (
      <StudentLayout hideNav>
        <PageWrapper className="max-w-xl pt-8 pb-0">
          {/* Welcome banner */}
          <div className="flex items-start gap-3 mb-6 p-4 bg-[var(--color-info-bg)] border border-[var(--color-accent)]/30 rounded-[var(--radius-lg)]">
            <Info size={17} className="text-[var(--color-accent)] shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-semibold text-[var(--color-accent)]">
                Welcome to SPARK! Let&apos;s set up your profile.
              </p>
              <p className="text-sm text-[var(--color-primary)] mt-0.5">
                Complete the form below to unlock access to all features.
              </p>
            </div>
          </div>

          {/* Setup card */}
          <div className="bg-white border border-[var(--color-border)] rounded-[var(--radius-xl)] shadow-[var(--shadow-sm)] overflow-hidden">
            <div className="h-0.5 bg-gradient-to-r from-[var(--color-accent)] to-[var(--color-primary)]" />

            <div className="px-7 py-7">
              <h2 className="text-[16px] font-semibold text-[var(--color-text)] mb-5">
                Complete your profile
              </h2>

              <form onSubmit={handleSetup(onSetupSubmit)} noValidate className="space-y-4">
                {/* Full name */}
                <Input
                  label="Full name"
                  type="text"
                  placeholder="Your full name"
                  autoComplete="name"
                  autoFocus
                  error={setupErrors.fullname?.message}
                  {...regSetup("fullname", {
                    required: "Full name is required.",
                    minLength: { value: 2, message: "Name must be at least 2 characters." },
                  })}
                />

                {/* College email */}
                <Input
                  label="College email"
                  type="email"
                  placeholder="yourname@college.edu"
                  autoComplete="email"
                  error={setupErrors.college_email_id?.message}
                  {...regSetup("college_email_id", {
                    required: "College email is required.",
                    pattern: {
                      value: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
                      message: "Enter a valid email address.",
                    },
                  })}
                />

                {/* Password change (optional toggle) */}
                <div className="pt-2 border-t border-[var(--color-border)]">
                  <label className="flex items-center gap-2.5 cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={wantsPasswordChange}
                      onChange={(e) => setWantsPasswordChange(e.target.checked)}
                      className="w-4 h-4 rounded accent-[var(--color-accent)] cursor-pointer"
                    />
                    <span className="text-sm font-medium text-[var(--color-text)] flex items-center gap-1.5">
                      <KeyRound size={14} className="text-[var(--color-text-muted)]" />
                      Change default password
                    </span>
                  </label>
                  <p className="text-xs text-[var(--color-text-muted)] mt-1 ml-6.5">
                    Strongly recommended — the default password is shared.
                  </p>
                </div>

                {wantsPasswordChange && (
                  <div className="space-y-3 pl-0">
                    <Input
                      label="Current password"
                      type={showSetupCurrent ? "text" : "password"}
                      placeholder="Enter your current password"
                      autoComplete="current-password"
                      error={setupErrors.current_password?.message}
                      rightElement={
                        <EyeToggle
                          show={showSetupCurrent}
                          onToggle={() => setShowSetupCurrent((v) => !v)}
                        />
                      }
                      {...regSetup("current_password", {
                        required: wantsPasswordChange
                          ? "Current password is required."
                          : false,
                      })}
                    />

                    <Input
                      label="New password"
                      type={showSetupNew ? "text" : "password"}
                      placeholder="Min. 8 characters"
                      autoComplete="new-password"
                      error={setupErrors.new_password?.message}
                      rightElement={
                        <EyeToggle
                          show={showSetupNew}
                          onToggle={() => setShowSetupNew((v) => !v)}
                        />
                      }
                      {...regSetup("new_password", {
                        required: wantsPasswordChange
                          ? "New password is required."
                          : false,
                        minLength: wantsPasswordChange
                          ? { value: 8, message: "Minimum 8 characters." }
                          : undefined,
                        validate: wantsPasswordChange
                          ? (val) =>
                              val !== setupCurrentPass ||
                              "New password must be different from your current password."
                          : undefined,
                      })}
                    />

                    <Input
                      label="Confirm new password"
                      type={showSetupConfirm ? "text" : "password"}
                      placeholder="Repeat new password"
                      autoComplete="new-password"
                      error={setupErrors.confirm_password?.message}
                      rightElement={
                        <EyeToggle
                          show={showSetupConfirm}
                          onToggle={() => setShowSetupConfirm((v) => !v)}
                        />
                      }
                      {...regSetup("confirm_password", {
                        required: wantsPasswordChange
                          ? "Please confirm your password."
                          : false,
                        validate: wantsPasswordChange
                          ? (val) =>
                              val === setupNewPass || "Passwords do not match."
                          : undefined,
                      })}
                    />
                  </div>
                )}

                <ErrorBanner message={setupError} />

                <Button
                  type="submit"
                  variant="primary"
                  fullWidth
                  loading={setupSaving}
                  size="lg"
                >
                  Complete setup & continue
                </Button>
              </form>
            </div>
          </div>
        </PageWrapper>
      </StudentLayout>
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // RETURNING USER VIEW
  // ═══════════════════════════════════════════════════════════════════════════
  return (
    <StudentLayout>
      <PageWrapper className="max-w-4xl pt-8 pb-0">

        {/* Back to Home */}
        <button
          onClick={() => { setBackLoading(true); router.push("/students/home"); }}
          disabled={backLoading}
          className="inline-flex items-center gap-1.5 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors mb-5 disabled:opacity-60 disabled:cursor-wait"
        >
          {backLoading
            ? <Loader2 size={14} className="animate-spin" />
            : <ArrowLeft size={15} />
          }
          Back to Home
        </button>

        <PageHeader
          title="My Profile"
          subtitle="View your details and manage account security."
        />

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* ── Profile Info Card ──────────────────────────────────────────── */}
          <div className="bg-white border border-[var(--color-border)] rounded-[var(--radius-xl)] overflow-hidden shadow-[var(--shadow-sm)]">
            {/* Header with avatar + edit button */}
            <div className="px-6 py-5 border-b border-[var(--color-border)] flex items-center gap-3">
              <div className="w-11 h-11 rounded-full bg-[var(--color-accent)] flex items-center justify-center shrink-0">
                <span className="text-white text-base font-bold">
                  {(profile?.fullname ?? studentUser?.student_id ?? "S")[0].toUpperCase()}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                {profileLoading ? (
                  <Skeleton className="h-4 w-32" />
                ) : (
                  <h2
                    className="text-[15px] font-semibold text-[var(--color-text)] truncate"
                    title={profile?.fullname ?? undefined}
                  >
                    {profile?.fullname ?? "—"}
                  </h2>
                )}
                <p className="text-xs text-[var(--color-text-muted)] mt-0.5">Student</p>
              </div>
              {!profileLoading && !isEditing && (
                <button
                  onClick={startEdit}
                  className="p-2 rounded-[var(--radius-md)] transition-colors shrink-0"
                  style={{ color: "var(--color-text-subtle)" }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.background = "var(--color-surface-hover)";
                    (e.currentTarget as HTMLButtonElement).style.color = "var(--color-text)";
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.background = "transparent";
                    (e.currentTarget as HTMLButtonElement).style.color = "var(--color-text-subtle)";
                  }}
                  aria-label="Edit profile"
                >
                  <Pencil size={15} />
                </button>
              )}
            </div>

            {/* Fields */}
            <div className="px-6">
              <InfoField icon={User} label="Student ID" value={profile?.student_id} loading={profileLoading} />

              {/* Full Name — editable */}
              {isEditing ? (
                <div className="flex items-start gap-3 py-3.5 border-b border-[var(--color-border)]">
                  <div className="w-8 h-8 rounded-[var(--radius-md)] bg-[var(--color-surface-hover)] flex items-center justify-center shrink-0 mt-0.5">
                    <User size={15} className="text-[var(--color-text-muted)]" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-[var(--color-text-muted)] mb-1">Full Name</p>
                    <input
                      autoFocus
                      type="text"
                      value={editFullname}
                      onChange={(e) => { setEditFullname(e.target.value); setEditError(""); }}
                      placeholder="Your full name"
                      className="w-full h-8 px-2.5 text-sm rounded-[var(--radius-sm)] outline-none focus:ring-2 focus:ring-[var(--color-accent)]/30"
                      style={{ border: "1px solid var(--color-border)", color: "var(--color-text)", background: "#fff" }}
                    />
                  </div>
                </div>
              ) : (
                <InfoField icon={User} label="Full Name" value={profile?.fullname} loading={profileLoading} />
              )}

              {/* College Email — editable */}
              {isEditing ? (
                <div className="flex items-start gap-3 py-3.5 border-b border-[var(--color-border)]">
                  <div className="w-8 h-8 rounded-[var(--radius-md)] bg-[var(--color-surface-hover)] flex items-center justify-center shrink-0 mt-0.5">
                    <Mail size={15} className="text-[var(--color-text-muted)]" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-[var(--color-text-muted)] mb-1">College Email</p>
                    <input
                      type="email"
                      value={editEmail}
                      onChange={(e) => { setEditEmail(e.target.value); setEditError(""); }}
                      placeholder="yourname@college.edu"
                      className="w-full h-8 px-2.5 text-sm rounded-[var(--radius-sm)] outline-none focus:ring-2 focus:ring-[var(--color-accent)]/30"
                      style={{ border: "1px solid var(--color-border)", color: "var(--color-text)", background: "#fff" }}
                    />
                  </div>
                </div>
              ) : (
                <InfoField icon={Mail} label="College Email" value={profile?.college_email_id} loading={profileLoading} />
              )}

              <InfoField icon={Building2} label="Department" value={profile?.department} loading={profileLoading} />
              <InfoField icon={GraduationCap} label="Batch" value={profile?.batch_name} loading={profileLoading} />
            </div>

            {/* Edit footer */}
            {isEditing ? (
              <div className="px-6 pb-5 pt-3">
                {editError && (
                  <p className="text-xs mb-3" style={{ color: "var(--color-danger)" }}>{editError}</p>
                )}
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleEditSave}
                    disabled={editSaving}
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-[var(--radius-md)] text-sm font-semibold text-white transition-colors disabled:opacity-60 disabled:cursor-wait"
                    style={{ background: "var(--color-accent)" }}
                  >
                    {editSaving
                      ? <><Loader2 size={14} className="animate-spin" /> Saving…</>
                      : <><Check size={14} /> Save</>
                    }
                  </button>
                  <button
                    onClick={cancelEdit}
                    disabled={editSaving}
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-[var(--radius-md)] text-sm font-medium transition-colors disabled:opacity-60 disabled:cursor-wait"
                    style={{ color: "var(--color-text-muted)", background: "var(--color-surface-hover)" }}
                  >
                    <XIcon size={14} /> Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="px-6 pb-5 pt-2 flex items-start gap-2">
                <Info size={13} className="text-[var(--color-text-muted)] shrink-0 mt-0.5" />
                <p className="text-[13px] text-[var(--color-text-muted)]">
                  Name and email are editable. Contact your administrator for other changes.
                </p>
              </div>
            )}
          </div>

          {/* ── Change Password Card ───────────────────────────────────────── */}
          <div className="bg-white border border-[var(--color-border)] rounded-[var(--radius-xl)] overflow-hidden shadow-[var(--shadow-sm)] self-start">
            <div className="px-6 py-5 border-b border-[var(--color-border)]">
              <h2 className="text-[15px] font-semibold text-[var(--color-text)]">
                Change Password
              </h2>
              <p className="text-sm text-neutral-500 mt-0.5">
                Keep your account secure with a strong password.
              </p>
            </div>

            <div className="px-6 pt-5 pb-4">
              <form onSubmit={handlePw(onPasswordSubmit)} noValidate className="space-y-4">
                <Input
                  label="Current password"
                  type={showPwCurrent ? "text" : "password"}
                  placeholder="Your current password"
                  autoComplete="current-password"
                  error={pwErrors.current_password?.message}
                  rightElement={
                    <button type="button" onClick={() => setShowPwCurrent((v) => !v)} tabIndex={-1}
                      className="text-[var(--color-text-muted)] hover:text-[var(--color-text)] p-1 transition-colors">
                      {showPwCurrent ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                  }
                  {...regPw("current_password", { required: "Current password is required." })}
                />

                <Input
                  label="New password"
                  type={showPwNew ? "text" : "password"}
                  placeholder="Min. 8 characters"
                  autoComplete="new-password"
                  error={pwErrors.new_password?.message}
                  rightElement={
                    <button type="button" onClick={() => setShowPwNew((v) => !v)} tabIndex={-1}
                      className="text-[var(--color-text-muted)] hover:text-[var(--color-text)] p-1 transition-colors">
                      {showPwNew ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                  }
                  {...regPw("new_password", {
                    required: "New password is required.",
                    minLength: { value: 8, message: "Minimum 8 characters." },
                    validate: (val) =>
                      val !== pwCurrentPass ||
                      "New password must be different from your current password.",
                  })}
                />

                <Input
                  label="Confirm new password"
                  type={showPwConfirm ? "text" : "password"}
                  placeholder="Repeat new password"
                  autoComplete="new-password"
                  error={pwErrors.confirm_password?.message}
                  rightElement={
                    <button type="button" onClick={() => setShowPwConfirm((v) => !v)} tabIndex={-1}
                      className="text-[var(--color-text-muted)] hover:text-[var(--color-text)] p-1 transition-colors">
                      {showPwConfirm ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                  }
                  {...regPw("confirm_password", {
                    required: "Please confirm your new password.",
                    validate: (val) => val === pwNewPass || "Passwords do not match.",
                  })}
                />

                <div
                  key={pwErrorKey}
                  className={[
                    "rounded-[var(--radius-md)] text-sm text-[var(--color-danger)]",
                    "bg-[var(--color-danger-bg)] border border-red-100 transition-all duration-200",
                    pwError
                      ? "p-3 opacity-100 max-h-20"
                      : "p-0 opacity-0 max-h-0 overflow-hidden border-transparent !mt-0",
                  ].join(" ")}
                  role="alert"
                  aria-live="polite"
                >
                  {pwError}
                </div>

                <Button type="submit" variant="primary" fullWidth loading={pwSaving} size="lg">
                  Update password
                </Button>
              </form>
            </div>
          </div>
        </div>
      </PageWrapper>
    </StudentLayout>
  );
}
