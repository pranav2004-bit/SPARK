"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { Eye, EyeOff, BookOpen, Building2, Zap, UserCircle, ArrowLeft } from "lucide-react";
import Image from "next/image";
import { useAuthStore } from "@/lib/auth-store";
import { setAuthCookies } from "@/lib/cookies";
import { useAuth } from "@/hooks/useAuth";
import { PORTAL_HOME } from "@/lib/portalRouting";
import api, { getErrorMessage } from "@/lib/api";
import { consumeScrollRedirect } from "@/lib/scrollRedirect";
import { ScrollingUpdates } from "@/components/ui/ScrollingUpdates";
import type { StudentLoginResponse } from "@/types";

interface LoginForm {
  student_id: string;
  password: string;
}

const FEATURES = [
  {
    icon: BookOpen,
    title: "Placement Materials",
    desc: "Access curated resources for every company visiting your campus.",
  },
  {
    icon: Building2,
    title: "Company-wise Sections",
    desc: "Aptitude, technical and HR prep — all organised in one place.",
  },
  {
    icon: Zap,
    title: "Always Up to Date",
    desc: "Your administrator keeps content fresh before each placement drive.",
  },
];

function Spinner() {
  return (
    <span
      className="animate-spin"
      style={{
        display: "inline-block",
        width: 16,
        height: 16,
        borderRadius: "50%",
        border: "2px solid rgba(255,255,255,0.3)",
        borderTopColor: "#fff",
      }}
    />
  );
}

export default function StudentLoginPage() {
  const router = useRouter();
  const { setTokens } = useAuthStore();
  const [showPassword, setShowPassword] = useState(false);
  const [serverError, setServerError] = useState("");
  const [loading, setLoading] = useState(false);
  const [backLoading, setBackLoading] = useState(false);

  // Already authenticated in THIS tab (added 2026-08-27) — see
  // PortalLoginForm.tsx's identical check for the full rationale (this
  // page doesn't use that shared component, so it needs its own copy).
  const { user, isAuthenticated, hasHydrated } = useAuth();
  useEffect(() => {
    if (hasHydrated && isAuthenticated && user) {
      router.replace(PORTAL_HOME[user.role] ?? "/");
    }
  }, [hasHydrated, isAuthenticated, user, router]);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginForm>({ mode: "onBlur" });

  async function onSubmit(data: LoginForm) {
    setLoading(true);
    setServerError("");
    try {
      const response = await api.post<StudentLoginResponse>("/auth/login/", {
        student_id: data.student_id.trim().toUpperCase(),
        password: data.password,
        role: "student",
      });
      const { access_token, refresh_token, user } = response.data.data;
      setTokens(access_token, refresh_token, user);
      setAuthCookies("student", access_token);

      // scrollRedirect: if the student arrived here via a scroll-bar link click,
      // consumeScrollRedirect() returns the saved path (validated /students/ only).
      // • Profile completed  → consume now and navigate there (or home if none saved).
      // • Profile incomplete → do NOT consume — leave it in sessionStorage so that
      //   my_profile will consume it after setup is done and redirect there.
      if (user.is_profile_completed) {
        const nextPath = consumeScrollRedirect();
        router.push(nextPath ?? "/students/home");
      } else {
        router.push("/students/my_profile");
      }
    } catch (err) {
      const raw = getErrorMessage(err);
      if (
        raw.toLowerCase().includes("disabled") ||
        raw.toLowerCase().includes("inactive") ||
        raw.toLowerCase().includes("contact")
      ) {
        setServerError("Your account is disabled. Contact your administrator.");
      } else if (
        raw.toLowerCase().includes("invalid") ||
        raw.toLowerCase().includes("credentials") ||
        raw.toLowerCase().includes("password") ||
        raw.toLowerCase().includes("not found")
      ) {
        setServerError("Invalid Student ID or password. Please try again.");
      } else {
        setServerError(raw || "Something went wrong. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col">

      {/* Announcement strip — top of login page, public context */}
      <ScrollingUpdates context="public" stickyTop={0} />

      <div className="flex flex-1">

      {/* ── Left panel — desktop only ─────────────────────────────────────── */}
      <div className="hidden lg:flex lg:w-[52%] flex-col bg-[var(--color-primary)] text-white p-10 xl:p-14">

        {/* Hero */}
        <div className="flex-1 flex flex-col justify-center py-12">

          {/* Logos — just above heading */}
          <div className="inline-flex items-center gap-3 mb-8 self-start">
            <Image
              src="/institution-logo.png"
              alt="Institution"
              width={44}
              height={44}
              className="h-11 w-auto object-contain"
              priority
            />
            <div className="w-px h-8" style={{ backgroundColor: 'rgba(200,200,200,0.5)' }} />
            <Image
              src="/spark-logo.svg"
              alt="SPARK"
              width={0}
              height={0}
              style={{ height: 30, width: "auto" }}
              priority
            />
          </div>

          <h1 className="text-4xl xl:text-5xl font-bold leading-tight tracking-tight mb-4">
            Welcome Back
          </h1>
          <p className="text-white/70 text-lg mb-10 leading-relaxed max-w-sm">
            Prepare smarter. Get placed faster.<br />
            Everything you need, in one place.
          </p>

          {/* Feature list */}
          <div className="space-y-6">
            {FEATURES.map(({ icon: Icon, title, desc }) => (
              <div key={title} className="flex items-start gap-4">
                <div className="w-10 h-10 rounded-full border border-white/20 bg-white/[0.07] flex items-center justify-center shrink-0 mt-0.5">
                  <Icon size={17} className="text-white/80" />
                </div>
                <div>
                  <p className="font-semibold text-[15px] text-white">{title}</p>
                  <p className="text-white/60 text-sm mt-0.5 leading-relaxed">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Right panel ───────────────────────────────────────────────────── */}
      <div className="login-panel-bg flex-1 flex flex-col px-5 py-8 sm:py-10">

        {/* Back to Home */}
        <div>
          <button
            onClick={() => { setBackLoading(true); router.push("/"); }}
            disabled={backLoading}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-[var(--color-border)] bg-white text-sm font-medium text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:border-[var(--color-border-strong)] transition-all duration-150 shadow-[var(--shadow-sm)] disabled:opacity-60 disabled:cursor-wait"
          >
            {backLoading
              ? <span className="animate-spin shrink-0" style={{ display:"inline-block", width:14, height:14, borderRadius:"50%", border:"2px solid rgba(0,0,0,0.15)", borderTopColor:"#555" }} />
              : <ArrowLeft size={14} />}
            Back to Home
          </button>
        </div>

        {/* Centered content */}
        <div className="flex-1 flex flex-col items-center justify-center">

        {/* Mobile logos — above card, desktop hidden */}
        <div className="lg:hidden flex items-center gap-3 mb-7">
          <Image
            src="/institution-logo.png"
            alt="Institution"
            width={44}
            height={44}
            className="h-11 w-auto object-contain"
            priority
          />
          <div className="w-px h-8" style={{ backgroundColor: 'var(--color-border)' }} />
          <Image
            src="/spark-logo.svg"
            alt="SPARK"
            width={0}
            height={0}
            style={{ height: 30, width: "auto" }}
            priority
          />
        </div>

        {/* Card */}
        <div className="w-full max-w-[400px] bg-white rounded-2xl shadow-[var(--shadow-lg)] px-6 py-6 sm:px-8 sm:py-7">

          {/* Badge */}
          <div className="inline-flex items-center gap-1.5 bg-[var(--color-accent-light)] text-[var(--color-accent)] border border-[var(--color-accent)]/25 px-3 py-1 rounded-full text-xs font-semibold mb-4 tracking-wide">
            <UserCircle size={12} />
            Student Portal
          </div>

          {/* Heading */}
          <h2 className="text-[26px] font-bold tracking-tight text-[var(--color-text)] mb-0.5 leading-tight">
            Sign In
          </h2>
          <p className="text-sm text-[var(--color-text-muted)] mb-5 leading-relaxed">
            Enter your credentials provided by your institution
          </p>

          {/* Form */}
          <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-3">

            {/* Student ID */}
            <div>
              <label className="block text-sm font-semibold text-[var(--color-text)] mb-1">
                Student ID
              </label>
              <input
                type="text"
                placeholder="Enter your Roll number"
                autoComplete="username"
                autoFocus
                className={[
                  "w-full px-4 py-3 rounded-lg text-sm bg-[var(--color-surface-secondary)]",
                  "text-[var(--color-text)] placeholder:text-[var(--color-text-subtle)]",
                  "outline-none transition-all duration-150",
                  errors.student_id
                    ? "ring-2 ring-[var(--color-danger)]"
                    : "focus:ring-2 focus:ring-[var(--color-accent)]/30",
                ].join(" ")}
                {...register("student_id", { required: "Student ID is required." })}
              />
              {errors.student_id && (
                <p className="text-xs text-[var(--color-danger)] mt-1 pl-1">
                  {errors.student_id.message}
                </p>
              )}
            </div>

            {/* Password */}
            <div>
              <label className="block text-sm font-semibold text-[var(--color-text)] mb-1">
                Password
              </label>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  placeholder="Enter your password"
                  autoComplete="current-password"
                  className={[
                    "w-full px-4 py-3 pr-11 rounded-lg text-sm bg-[var(--color-surface-secondary)]",
                    "text-[var(--color-text)] placeholder:text-[var(--color-text-subtle)]",
                    "outline-none transition-all duration-150",
                    errors.password
                      ? "ring-2 ring-[var(--color-danger)]"
                      : "focus:ring-2 focus:ring-[var(--color-accent)]/30",
                  ].join(" ")}
                  {...register("password", {
                    required: "Password is required.",
                    minLength: { value: 6, message: "Password must be at least 6 characters." },
                  })}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-[var(--color-text-subtle)] hover:text-[var(--color-text-muted)] transition-colors"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              {errors.password && (
                <p className="text-xs text-[var(--color-danger)] mt-1.5 pl-1">
                  {errors.password.message}
                </p>
              )}
            </div>

            {/* Server error */}
            <div
              className={[
                "rounded-xl text-sm text-[var(--color-danger)] bg-[var(--color-danger-bg)]",
                "transition-all duration-200",
                serverError
                  ? "p-3 opacity-100 max-h-20"
                  : "p-0 opacity-0 max-h-0 overflow-hidden",
              ].join(" ")}
              role="alert"
              aria-live="polite"
            >
              {serverError}
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 rounded-lg bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] active:scale-[0.99] text-white font-semibold text-[15px] transition-all duration-150 disabled:opacity-60 disabled:cursor-not-allowed shadow-[0_4px_14px_rgba(255,140,0,0.35)] hover:shadow-[0_4px_20px_rgba(255,140,0,0.45)] inline-flex items-center justify-center gap-2"
            >
              {loading && <Spinner />}
              Sign In
            </button>
          </form>

          {/* Hint inside card */}
          <p className="text-center text-xs text-[var(--color-text-subtle)] mt-4">
            Having trouble signing in? Contact your administrator.
          </p>
        </div>

        </div>{/* end centered content */}
      </div>
      </div>{/* end flex-1 */}
    </div>
  );
}
