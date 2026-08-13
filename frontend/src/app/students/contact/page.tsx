"use client";

import { useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { Mail, Send, CheckCircle2, Building2, ArrowLeft, Loader2 } from "lucide-react";
import { StudentLayout } from "@/components/layout/StudentLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import api, { getErrorMessage } from "@/lib/api";
import type { ApiSuccess, Inquiry } from "@/types";

// ── Design token literals (avoid CSS variable cascade issues) ─────────────────
const T = {
  text:        "#1a2b3c",
  muted:       "#5c6e82",
  subtle:      "#8fa0b0",
  border:      "#e2e8f0",
  accent:      "#FF8C00",
  danger:      "#dc2626",
  dangerBg:    "#fef2f2",
  surface:     "#f8f9fa",
  white:       "#ffffff",
  accentLight: "#fff4e6",
};

// ── Builder data ──────────────────────────────────────────────────────────────
const BUILDERS = [
  {
    company: "SANJIVO",
    role: "Product Engineering & Strategy",
    contact: "Kosuru Pranavnath",
    logo: "/sanjivo-logo.svg",
    scaleStyle: { width: "100%", height: "100%", objectFit: "cover" as const, transform: "scale(1.55)", transformOrigin: "center" },
  },
  {
    company: "AuraTech-Vision",
    role: "Technology Partner & Experience Design",
    contact: "Mangala Sai Sri Abhinay",
    logo: "/auratech-logo.svg",
    scaleStyle: { width: "100%", height: "100%", objectFit: "cover" as const, transform: "scale(1.2) translateY(8%)", transformOrigin: "center" },
  },
];

const SUPPORT_EMAIL = "sanjivo0034@gmail.com";

// ── Main page ─────────────────────────────────────────────────────────────────
export default function ContactPage() {
  const router = useRouter();
  const toast = useToast();
  const [backLoading, setBackLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");

  const remaining = 2000 - message.length;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = message.trim();
    if (!trimmed) { setError("Please write your inquiry before submitting."); return; }
    if (trimmed.length < 10) { setError("Inquiry must be at least 10 characters."); return; }
    setSubmitting(true);
    setError("");
    try {
      await api.post<ApiSuccess<Inquiry>>("/users/inquiries/", { message: trimmed });
      setSubmitted(true);
      setMessage("");
      toast.success("Inquiry submitted. We'll get back to you shortly.");
    } catch (err) {
      setError(getErrorMessage(err) || "Failed to submit. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <StudentLayout>
      <PageWrapper className="max-w-4xl py-6 sm:py-8">

        {/* ── Back to Home ───────────────────────────────────────────────────── */}
        <button
          onClick={() => { setBackLoading(true); router.push("/students/home"); }}
          disabled={backLoading}
          className="inline-flex items-center gap-1.5 text-sm font-medium mb-5 transition-colors disabled:opacity-60"
          style={{ color: T.muted }}
          onMouseEnter={e => { if (!backLoading) e.currentTarget.style.color = T.text; }}
          onMouseLeave={e => (e.currentTarget.style.color = T.muted)}
        >
          {backLoading
            ? <Loader2 size={14} className="animate-spin" />
            : <ArrowLeft size={15} />
          }
          Back to Home
        </button>

        {/* ── Page header ────────────────────────────────────────────────────── */}
        <div className="mb-6 sm:mb-8">
          <h1
            className="text-2xl sm:text-3xl font-bold tracking-tight"
            style={{ color: T.text }}
          >
            Contact Us
          </h1>
          <p
            className="text-sm mt-1.5 leading-relaxed"
            style={{ color: T.muted }}
          >
            Have a question or facing an issue? Send us an inquiry and we&apos;ll respond promptly.
          </p>
        </div>

        {/* ── Two-column grid (stacked on mobile, side-by-side on lg) ───────── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-5 lg:items-stretch">

          {/* ── Left col ───────────────────────────────────────────────────── */}
          <div className="flex flex-col gap-4">

            {/* Built by card */}
            <div
              className="rounded-[var(--radius-xl)] overflow-hidden shadow-[var(--shadow-sm)]"
              style={{ background: T.white, border: `1px solid ${T.border}` }}
            >
              {/* Card header */}
              <div
                className="px-4 sm:px-5 py-3.5 flex items-center gap-2"
                style={{ borderBottom: `1px solid ${T.border}` }}
              >
                <Building2 size={14} style={{ color: T.muted }} className="shrink-0" />
                <p className="text-[13px] font-semibold" style={{ color: T.text }}>
                  Built by
                </p>
              </div>

              {/* Builder rows */}
              {BUILDERS.map((b, i) => (
                <div
                  key={b.company}
                  className="px-4 sm:px-5 py-4"
                  style={{ borderBottom: i < BUILDERS.length - 1 ? `1px solid ${T.border}` : "none" }}
                >
                  <div className="flex items-center gap-3">
                    <div
                      className="w-14 h-12 rounded-[var(--radius-md)] flex items-center justify-center shrink-0 overflow-hidden"
                    >
                      <Image
                        src={b.logo}
                        alt={b.company}
                        width={40}
                        height={40}
                        style={b.scaleStyle}
                      />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold leading-snug" style={{ color: T.text }}>
                        {b.company}
                      </p>
                      <p className="text-xs mt-0.5 leading-snug" style={{ color: T.muted }}>
                        {b.role}
                      </p>
                      <p className="text-xs mt-0.5 leading-snug" style={{ color: T.subtle }}>
                        {b.contact}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Support email card */}
            <div
              className="rounded-[var(--radius-xl)] px-4 sm:px-5 py-4 shadow-[var(--shadow-sm)]"
              style={{ background: T.white, border: `1px solid ${T.border}` }}
            >
              <div className="flex items-center gap-2 mb-2">
                <Mail size={14} style={{ color: T.muted }} className="shrink-0" />
                <p className="text-[13px] font-semibold" style={{ color: T.text }}>
                  Support email
                </p>
              </div>
              <a
                href={`mailto:${SUPPORT_EMAIL}`}
                className="text-sm font-medium break-all transition-opacity hover:opacity-80"
                style={{ color: T.accent }}
              >
                {SUPPORT_EMAIL}
              </a>
              <p className="text-xs mt-1.5 leading-relaxed" style={{ color: T.subtle }}>
                Or use the inquiry form — we monitor both channels.
              </p>
            </div>

          </div>

          {/* ── Right col: form card — stretches to match left col height ──── */}
          <div
            className="rounded-[var(--radius-xl)] overflow-hidden shadow-[var(--shadow-sm)] flex flex-col"
            style={{ background: T.white, border: `1px solid ${T.border}` }}
          >
            {/* Card header */}
            <div
              className="px-4 sm:px-6 py-4 sm:py-5 shrink-0"
              style={{ borderBottom: `1px solid ${T.border}` }}
            >
              <h2 className="text-[15px] font-semibold" style={{ color: T.text }}>
                Send an inquiry
              </h2>
              <p className="text-sm mt-0.5" style={{ color: T.muted }}>
                Describe your question or issue in detail.
              </p>
            </div>

            {/* Card body — grows to fill remaining height on desktop only */}
            <div className="px-4 sm:px-6 py-4 sm:py-6 flex flex-col lg:flex-1">
              {submitted ? (
                /* ── Success state ── */
                <div className="flex flex-col lg:flex-1 items-center justify-center text-center gap-3 py-6">
                  <div
                    className="w-14 h-14 rounded-full flex items-center justify-center"
                    style={{ background: "#f0fdf4" }}
                  >
                    <CheckCircle2 size={28} style={{ color: "#22c55e" }} />
                  </div>
                  <div>
                    <p className="text-[15px] font-semibold" style={{ color: T.text }}>
                      Inquiry submitted!
                    </p>
                    <p
                      className="text-sm mt-1 leading-relaxed max-w-[260px] mx-auto"
                      style={{ color: T.muted }}
                    >
                      We&apos;ve received your message and will respond as soon as possible.
                    </p>
                  </div>
                  <button
                    onClick={() => setSubmitted(false)}
                    className="text-sm font-medium mt-1 transition-opacity hover:opacity-75"
                    style={{ color: T.accent }}
                  >
                    Submit another inquiry
                  </button>
                </div>
              ) : (
                /* ── Form ── */
                <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4 lg:flex-1">
                  <div className="flex flex-col lg:flex-1">
                    <label
                      htmlFor="inquiry-message"
                      className="block text-xs font-medium mb-1.5"
                      style={{ color: T.muted }}
                    >
                      Your message
                    </label>
                    <textarea
                      id="inquiry-message"
                      value={message}
                      onChange={(e) => { setMessage(e.target.value); setError(""); }}
                      placeholder="Describe your question or issue clearly…"
                      maxLength={2000}
                      className="lg:flex-1 w-full px-3 py-2.5 text-sm rounded-[var(--radius-md)] resize-none outline-none transition-shadow"
                      style={{
                        border: `1px solid ${error ? T.danger : T.border}`,
                        color: T.text,
                        background: T.white,
                        lineHeight: "1.6",
                        minHeight: "140px",
                        boxShadow: "none",
                      }}
                      onFocus={e => (e.currentTarget.style.boxShadow = `0 0 0 3px ${T.accentLight}`)}
                      onBlur={e => (e.currentTarget.style.boxShadow = "none")}
                    />
                    {/* Error + counter row */}
                    <div className="flex items-start justify-between mt-1.5 gap-2 min-h-[18px]">
                      <p
                        className="text-xs leading-snug"
                        style={{ color: error ? T.danger : "transparent" }}
                      >
                        {error || "·"}
                      </p>
                      <p
                        className="text-xs shrink-0"
                        style={{ color: remaining < 100 ? T.danger : T.subtle }}
                      >
                        {remaining} left
                      </p>
                    </div>
                  </div>

                  <Button
                    type="submit"
                    variant="primary"
                    fullWidth
                    loading={submitting}
                    size="lg"
                  >
                    <Send size={15} className="mr-1.5" />
                    Submit inquiry
                  </Button>
                </form>
              )}
            </div>
          </div>

        </div>
      </PageWrapper>
    </StudentLayout>
  );
}
