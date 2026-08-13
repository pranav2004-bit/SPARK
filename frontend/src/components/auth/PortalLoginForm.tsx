"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { Eye, EyeOff, ArrowLeft } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import Image from "next/image";
import { useAuthStore } from "@/lib/auth-store";
import { setAuthCookies } from "@/lib/cookies";
import api, { getErrorMessage } from "@/lib/api";
import { ScrollingUpdates } from "@/components/ui/ScrollingUpdates";
import type { AuthUser, TokenPair } from "@/types";

// ── Types ──────────────────────────────────────────────────────────────────────

interface LoginFormFields {
  email: string;
  password: string;
}

interface LoginApiResponse {
  success: true;
  data: TokenPair & { user: AuthUser };
}

interface PortalFeature {
  icon: LucideIcon;
  title: string;
  desc: string;
}

export interface PortalLoginFormProps {
  /** Left panel */
  leftTitle: string;
  leftTagline: string;
  features: PortalFeature[];
  /** Right panel card */
  badgeLabel: string;
  badgeIcon: LucideIcon;
  cardTitle: string;
  cardSubtitle: string;
  footerHint?: string;
  /** Auth config */
  apiEndpoint: string;
  cookieRole: "admin" | "super_admin";
  redirectTo: string;
  /** Additional POST body fields (e.g. { role: "super_admin" }) */
  extraBody?: Record<string, string>;
}

// ── Spinner ────────────────────────────────────────────────────────────────────

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

// ── Component ──────────────────────────────────────────────────────────────────

export function PortalLoginForm({
  leftTitle,
  leftTagline,
  features,
  badgeLabel,
  badgeIcon: BadgeIcon,
  cardTitle,
  cardSubtitle,
  footerHint,
  apiEndpoint,
  cookieRole,
  redirectTo,
  extraBody,
}: PortalLoginFormProps) {
  const router = useRouter();
  const { setTokens } = useAuthStore();
  const [showPassword, setShowPassword] = useState(false);
  const [serverError, setServerError] = useState("");
  const [loading, setLoading] = useState(false);
  const [backLoading, setBackLoading] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormFields>({ mode: "onBlur" });

  async function onSubmit(data: LoginFormFields) {
    setLoading(true);
    setServerError("");
    try {
      const body = { ...data, ...extraBody };
      const response = await api.post<LoginApiResponse>(apiEndpoint, body);
      const { access_token, refresh_token, user } = response.data.data;
      setTokens(access_token, refresh_token, user);
      setAuthCookies(cookieRole, access_token);
      router.push(redirectTo);
    } catch (err) {
      setServerError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      <ScrollingUpdates context="public" stickyTop={0} />

      <div className="flex flex-1">

        {/* ── Left panel — desktop only ──────────────────────────────────── */}
        <div className="hidden lg:flex lg:w-[52%] flex-col bg-[var(--color-primary)] text-white p-10 xl:p-14">
          <div className="flex-1 flex flex-col justify-center py-12">

            {/* Logos */}
            <div className="inline-flex items-center gap-3 mb-8 self-start">
              <Image
                src="/institution-logo.svg"
                alt="Institution"
                width={44}
                height={44}
                className="h-11 w-auto object-contain"
                priority
              />
              <div className="w-px h-8" style={{ backgroundColor: "rgba(200,200,200,0.5)" }} />
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
              {leftTitle}
            </h1>
            <p className="text-white/70 text-lg mb-10 leading-relaxed max-w-sm">
              {leftTagline}
            </p>

            <div className="space-y-6">
              {features.map(({ icon: Icon, title, desc }) => (
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

        {/* ── Right panel ───────────────────────────────────────────────── */}
        <div className="login-panel-bg flex-1 flex flex-col px-5 py-8 sm:py-10">

          {/* Back to Home */}
          <div>
            <button
              onClick={() => { setBackLoading(true); router.push("/"); }}
              disabled={backLoading}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-[var(--color-border)] bg-white text-sm font-medium text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:border-[var(--color-border-strong)] transition-all duration-150 shadow-[var(--shadow-sm)] disabled:opacity-60"
            >
              {backLoading && (
                <span
                  className="animate-spin"
                  style={{
                    display: "inline-block",
                    width: 14,
                    height: 14,
                    borderRadius: "50%",
                    border: "2px solid rgba(0,0,0,0.15)",
                    borderTopColor: "#555",
                  }}
                />
              )}
              <ArrowLeft size={14} />
              Back to Home
            </button>
          </div>

          {/* Centered content */}
          <div className="flex-1 flex flex-col items-center justify-center">

            {/* Mobile logos */}
            <div className="lg:hidden flex items-center gap-3 mb-7">
              <Image
                src="/institution-logo.svg"
                alt="Institution"
                width={44}
                height={44}
                className="h-11 w-auto object-contain"
                priority
              />
              <div className="w-px h-8" style={{ backgroundColor: "var(--color-border)" }} />
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
                <BadgeIcon size={12} />
                {badgeLabel}
              </div>

              <h2 className="text-[26px] font-bold tracking-tight text-[var(--color-text)] mb-0.5 leading-tight">
                {cardTitle}
              </h2>
              <p className="text-sm text-[var(--color-text-muted)] mb-5 leading-relaxed">
                {cardSubtitle}
              </p>

              <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-3">

                {/* Email */}
                <div>
                  <label className="block text-sm font-semibold text-[var(--color-text)] mb-1">
                    Email
                  </label>
                  <input
                    type="email"
                    placeholder="Enter your email address"
                    autoComplete="email"
                    autoFocus
                    className={[
                      "w-full px-4 py-3 rounded-lg text-sm bg-[var(--color-surface-secondary)]",
                      "text-[var(--color-text)] placeholder:text-[var(--color-text-subtle)]",
                      "outline-none transition-all duration-150",
                      errors.email
                        ? "ring-2 ring-[var(--color-danger)]"
                        : "focus:ring-2 focus:ring-[var(--color-accent)]/30",
                    ].join(" ")}
                    {...register("email", {
                      required: "Email is required.",
                      pattern: {
                        value: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
                        message: "Enter a valid email address.",
                      },
                    })}
                  />
                  {errors.email && (
                    <p className="text-xs text-[var(--color-danger)] mt-1 pl-1">
                      {errors.email.message}
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
                      {...register("password", { required: "Password is required." })}
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
                    <p className="text-xs text-[var(--color-danger)] mt-1 pl-1">
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

              {footerHint && (
                <p className="text-center text-xs text-[var(--color-text-subtle)] mt-4">
                  {footerHint}
                </p>
              )}
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}
