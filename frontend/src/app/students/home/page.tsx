"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, User, GraduationCap, BookOpen, Building2, ClipboardList, Trophy, Lock, Briefcase } from "lucide-react";
import { StudentLayout } from "@/components/layout/StudentLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { Skeleton, LoadingSpinner } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { useAuthStore } from "@/lib/auth-store";
import api from "@/lib/api";
import type { StudentProfile, PaginatedResponse, Company, ApiSuccess, StudentUser } from "@/types";


// ── Stat card ─────────────────────────────────────────────────────────────────
function StatCard({
  icon: Icon,
  label,
  value,
  loading,
  color = "blue",
}: {
  icon: React.ElementType;
  label: string;
  value?: string | number;
  loading: boolean;
  color?: "blue" | "indigo" | "teal";
}) {
  const colorMap = {
    blue: {
      bg: "bg-[var(--color-accent-light)]",
      icon: "text-[var(--color-accent)]",
      border: "border-[var(--color-accent)]/20",
    },
    indigo: {
      bg: "bg-[var(--color-primary-light)]",
      icon: "text-[var(--color-primary)]",
      border: "border-[var(--color-primary)]/15",
    },
    teal: {
      bg: "bg-emerald-50",
      icon: "text-emerald-600",
      border: "border-emerald-100",
    },
  };
  const c = colorMap[color];

  return (
    <div
      className={[
        "bg-white border rounded-[var(--radius-xl)] p-5 flex items-center gap-4",
        "shadow-[var(--shadow-sm)]",
        c.border,
      ].join(" ")}
    >
      <div className={["w-11 h-11 rounded-[var(--radius-lg)] flex items-center justify-center shrink-0", c.bg].join(" ")}>
        <Icon size={20} className={c.icon} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-0.5">
          {label}
        </p>
        {loading ? (
          <Skeleton className="h-5 w-20 mt-1" />
        ) : (
          <p
            className="text-[17px] font-bold text-[var(--color-text)] truncate"
            title={typeof value === "string" ? value : undefined}
          >
            {value ?? "—"}
          </p>
        )}
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function StudentHomePage() {
  const router = useRouter();
  const toast = useToast();
  const { user } = useAuthStore();
  const studentUser = user as StudentUser | null;

  const [profile, setProfile] = useState<StudentProfile | null>(null);
  const [companiesCount, setCompaniesCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [navigatingTo, setNavigatingTo] = useState<"companies" | "practice" | null>(null);

  const goTo = (path: string, dest: "companies" | "practice") => {
    setNavigatingTo(dest);
    router.push(path);
  };

  const fetchData = useCallback(async () => {
    try {
      const [profileRes, companiesRes] = await Promise.all([
        api.get<ApiSuccess<StudentProfile>>("/students/profile/"),
        api.get<PaginatedResponse<Company>>("/students/companies/"),
      ]);
      setProfile(profileRes.data.data);
      setCompaniesCount(companiesRes.data.count);
    } catch {
      // Silently fail — partial data is acceptable on home page
      // toast.error is reserved for critical failures only
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);


  return (
    <StudentLayout>
      <PageWrapper className="max-w-4xl pt-8 sm:pt-12 pb-4">

        {/* ── Hero ──────────────────────────────────────────────────────────── */}
        <div className="mb-8">
          {loading ? (
            <>
              <Skeleton className="h-8 w-72 mb-3" />
              <Skeleton className="h-5 w-56" />
            </>
          ) : (
            <>
              <h1 className="text-3xl sm:text-4xl font-bold text-[var(--color-text)] tracking-tight leading-tight">
                Welcome to{" "}
                <span className="text-[var(--color-accent)]">SPARK</span> 🎓
              </h1>
              <p className="text-base text-[var(--color-text-muted)] mt-2">
Prepare smart. Show up confident. Get placed.
              </p>
            </>
          )}
        </div>

        {/* ── Stats row ─────────────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
          <StatCard
            icon={User}
            label="Name"
            value={profile?.fullname}
            loading={loading}
            color="blue"
          />
          <StatCard
            icon={GraduationCap}
            label="Batch"
            value={profile?.batch_name}
            loading={loading}
            color="indigo"
          />
          <StatCard
            icon={Building2}
            label="Department"
            value={profile?.department}
            loading={loading}
            color="teal"
          />
        </div>

        {/* ── CTA cards ─────────────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">

          {/* Company materials card */}
          <button
            onClick={() => goTo("/students/companies", "companies")}
            disabled={!!navigatingTo}
            className="group cursor-pointer bg-white border border-[var(--color-border)] rounded-[var(--radius-xl)] shadow-[var(--shadow-sm)] hover:shadow-[var(--shadow-md)] hover:border-[var(--color-accent)]/40 transition-all duration-200 text-left overflow-hidden disabled:cursor-wait"
            style={{ opacity: navigatingTo && navigatingTo !== "companies" ? 0.5 : 1 }}
          >
            <div className="h-0.5 w-full bg-[var(--color-accent)] opacity-0 group-hover:opacity-100 transition-opacity duration-200" />
            <div className="px-5 py-5 flex items-center gap-4">
              <div className="w-10 h-10 rounded-[var(--radius-lg)] bg-[var(--color-accent-light)] flex items-center justify-center shrink-0">
                <Briefcase size={18} className="text-[var(--color-accent)]" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[15px] font-semibold text-[var(--color-text)] group-hover:text-[var(--color-accent)] transition-colors leading-snug">
                  Browse company materials
                </p>
                <p className="text-sm text-[var(--color-text-muted)] mt-0.5 leading-snug select-none">
                  Aptitude, technical &amp; HR resources, organised by company.
                </p>
              </div>
              <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 transition-colors duration-200 ${navigatingTo === "companies" ? "bg-[var(--color-accent)]" : "bg-[var(--color-surface-hover)] group-hover:bg-[var(--color-accent)]"}`}>
                {navigatingTo === "companies"
                  ? <LoadingSpinner size={14} color="#fff" />
                  : <ArrowRight size={15} className="text-[var(--color-text-muted)] group-hover:text-white transition-colors duration-200" />}
              </div>
            </div>
          </button>

          {/* Practice card */}
          <button
            onClick={() => goTo("/students/practice", "practice")}
            disabled={!!navigatingTo}
            className="group cursor-pointer bg-white border border-[var(--color-border)] rounded-[var(--radius-xl)] shadow-[var(--shadow-sm)] hover:shadow-[var(--shadow-md)] hover:border-[var(--color-accent)]/40 transition-all duration-200 text-left overflow-hidden disabled:cursor-wait"
            style={{ opacity: navigatingTo && navigatingTo !== "practice" ? 0.5 : 1 }}
          >
            <div className="h-0.5 w-full bg-[var(--color-accent)] opacity-0 group-hover:opacity-100 transition-opacity duration-200" />
            <div className="px-5 py-5 flex items-center gap-4">
              <div className="w-10 h-10 rounded-[var(--radius-lg)] bg-[var(--color-primary-light)] flex items-center justify-center shrink-0">
                <BookOpen size={18} className="text-[var(--color-primary)]" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[15px] font-semibold text-[var(--color-text)] group-hover:text-[var(--color-accent)] transition-colors leading-snug">
                  Start practicing
                </p>
                <p className="text-sm text-[var(--color-text-muted)] mt-0.5 leading-snug select-none">
                  Topic-wise &amp; difficulty-graded aptitude and technical questions.
                </p>
              </div>
              <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 transition-colors duration-200 ${navigatingTo === "practice" ? "bg-[var(--color-accent)]" : "bg-[var(--color-surface-hover)] group-hover:bg-[var(--color-accent)]"}`}>
                {navigatingTo === "practice"
                  ? <LoadingSpinner size={14} color="#fff" />
                  : <ArrowRight size={15} className="text-[var(--color-text-muted)] group-hover:text-white transition-colors duration-200" />}
              </div>
            </div>
          </button>

        </div>

        {/* ── Quick tip ─────────────────────────────────────────────────────── */}
        {!loading && companiesCount === 0 && (
          <div className="mt-6 flex items-start gap-3 p-4 bg-[var(--color-warning-bg)] border border-amber-200 rounded-[var(--radius-lg)]">
            <span className="text-amber-500 mt-0.5 shrink-0 text-base">⏳</span>
            <p className="text-sm text-amber-700">
              No companies have been published yet. Check back soon — your
              administrator will publish materials before your placement drive.
            </p>
          </div>
        )}

        {/* ── Preparation path — journey map ────────────────────────────────── */}
        <div className="mt-8">
          <style>{`
            @keyframes spark-travel {
              0%   { transform: translateX(-150%); }
              100% { transform: translateX(600%);  }
            }
            @keyframes pulse-ring {
              0%   { transform: scale(1);   opacity: 0.65; }
              100% { transform: scale(2.1); opacity: 0;    }
            }
          `}</style>

          <div className="flex items-center gap-3 mb-5">
            <p className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider whitespace-nowrap">
              Your preparation path
            </p>
            <div className="flex-1 h-px bg-[var(--color-border)]" />
          </div>

          {/* ── Desktop (lg+): dark premium horizontal journey map ─────────── */}
          <div
            className="hidden lg:block rounded-[var(--radius-xl)] px-12 py-9 relative overflow-hidden"
            style={{
              background: "linear-gradient(135deg, #1a3150 0%, #0d1e31 100%)",
              boxShadow: "0 8px 40px rgba(13, 30, 49, 0.28), inset 0 1px 0 rgba(255,255,255,0.07)",
            }}
          >
            {/* Ambient radial glow behind active nodes */}
            <div style={{
              position: "absolute", inset: 0, pointerEvents: "none",
              background: [
                "radial-gradient(ellipse 46% 85% at 17% 58%, rgba(255,140,0,0.10) 0%, transparent 100%)",
                "radial-gradient(ellipse 36% 85% at 42% 58%, rgba(255,140,0,0.07) 0%, transparent 100%)",
              ].join(", "),
            }} />

            <div className="grid grid-cols-4 gap-0 relative z-10">

              {/* ① Browse resources */}
              <button
                onClick={() => goTo("/students/companies", "companies")}
                disabled={!!navigatingTo}
                className="group cursor-pointer relative flex flex-col items-center focus-visible:outline-none disabled:cursor-wait transition-opacity duration-200"
                style={{ opacity: navigatingTo && navigatingTo !== "companies" ? 0.4 : 1 }}
              >
                {/* Step number */}
                <p className="text-[10px] font-black tracking-[0.18em] mb-3 select-none" style={{ color: "rgba(255,140,0,0.6)" }}>01</p>

                {/* Fixed-height row so connectors align on the circle center */}
                <div className="relative w-full flex justify-center" style={{ height: 52 }}>
                  {/* Right connector — orange with travelling shimmer */}
                  <div className="absolute left-1/2 right-0 overflow-hidden" style={{ top: 25, height: 1 }}>
                    <div style={{ position: "absolute", inset: 0, background: "var(--color-accent)" }} />
                    <div style={{
                      position: "absolute", inset: 0, width: "38%",
                      background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.85), transparent)",
                      animation: "spark-travel 2.1s ease-in-out infinite",
                    }} />
                  </div>

                  {/* Pulse ring — marks the start of the journey */}
                  <div className="absolute z-10 rounded-full pointer-events-none" style={{
                    width: 52, height: 52, top: 0,
                    border: "1.5px solid rgba(255,140,0,0.5)",
                    animation: "pulse-ring 2.4s ease-out infinite",
                  }} />

                  {/* Circle */}
                  <div
                    className="relative z-20 w-[52px] h-[52px] rounded-full flex items-center justify-center transition-transform duration-300 group-hover:scale-110"
                    style={{
                      background: "linear-gradient(135deg, #FFAA2C 0%, #FF8C00 100%)",
                      boxShadow: "0 0 0 3px rgba(255,140,0,0.2), 0 0 30px rgba(255,140,0,0.52)",
                    }}
                  >
                    {navigatingTo === "companies"
                      ? <LoadingSpinner size={20} color="#fff" />
                      : <Briefcase size={20} color="white" strokeWidth={2} />}
                  </div>
                </div>

                <div className="text-center px-2 mt-3.5">
                  <p className="text-[13px] font-semibold leading-tight mb-1.5 select-none group-hover:text-[var(--color-accent)] transition-colors duration-200" style={{ color: "rgba(255,255,255,0.92)" }}>
                    Browse resources
                  </p>
                  <p className="text-[11px] leading-relaxed select-none" style={{ color: "rgba(255,255,255,0.38)" }}>
                    Company-wise aptitude, technical &amp; HR materials
                  </p>
                </div>
              </button>

              {/* ② Practice questions */}
              <button
                onClick={() => goTo("/students/practice", "practice")}
                disabled={!!navigatingTo}
                className="group cursor-pointer relative flex flex-col items-center focus-visible:outline-none disabled:cursor-wait transition-opacity duration-200"
                style={{ opacity: navigatingTo && navigatingTo !== "practice" ? 0.4 : 1 }}
              >
                <p className="text-[10px] font-black tracking-[0.18em] mb-3 select-none" style={{ color: "rgba(255,140,0,0.6)" }}>02</p>

                <div className="relative w-full flex justify-center" style={{ height: 52 }}>
                  {/* Left connector — solid orange */}
                  <div className="absolute left-0 right-1/2" style={{ top: 25, height: 1, background: "var(--color-accent)" }} />
                  {/* Right connector — orange fading to glass (active → locked boundary) */}
                  <div className="absolute left-1/2 right-0" style={{
                    top: 25, height: 1,
                    background: "linear-gradient(90deg, #FF8C00 0%, rgba(255,255,255,0.10) 100%)",
                  }} />

                  <div
                    className="relative z-10 w-[52px] h-[52px] rounded-full flex items-center justify-center transition-transform duration-300 group-hover:scale-110"
                    style={{
                      background: "linear-gradient(135deg, #FFAA2C 0%, #FF8C00 100%)",
                      boxShadow: "0 0 0 3px rgba(255,140,0,0.2), 0 0 30px rgba(255,140,0,0.52)",
                    }}
                  >
                    {navigatingTo === "practice"
                      ? <LoadingSpinner size={20} color="#fff" />
                      : <BookOpen size={20} color="white" strokeWidth={2} />}
                  </div>
                </div>

                <div className="text-center px-2 mt-3.5">
                  <p className="text-[13px] font-semibold leading-tight mb-1.5 select-none group-hover:text-[var(--color-accent)] transition-colors duration-200" style={{ color: "rgba(255,255,255,0.92)" }}>
                    Practice questions
                  </p>
                  <p className="text-[11px] leading-relaxed select-none" style={{ color: "rgba(255,255,255,0.38)" }}>
                    Aptitude &amp; technical practice, by topic and difficulty
                  </p>
                </div>
              </button>

              {/* ③ Assessments — locked, v2 */}
              <div className="relative flex flex-col items-center cursor-default" aria-disabled="true">
                <p className="text-[10px] font-black tracking-[0.18em] mb-3 select-none" style={{ color: "rgba(255,255,255,0.2)" }}>03</p>

                <div className="relative w-full flex justify-center" style={{ height: 52 }}>
                  {/* Left connector — glass */}
                  <div className="absolute left-0 right-1/2" style={{ top: 25, height: 1, background: "rgba(255,255,255,0.10)" }} />
                  {/* Right connector — dashed glass */}
                  <div className="absolute left-1/2 right-0" style={{
                    top: 25, height: 1,
                    backgroundImage: "repeating-linear-gradient(90deg, rgba(255,255,255,0.16) 0, rgba(255,255,255,0.16) 5px, transparent 5px, transparent 11px)",
                    backgroundSize: "11px 1px",
                  }} />

                  <div
                    className="relative z-10 w-[52px] h-[52px] rounded-full flex items-center justify-center"
                    style={{
                      border: "1.5px dashed rgba(255,255,255,0.2)",
                      background: "rgba(255,255,255,0.05)",
                    }}
                  >
                    <ClipboardList size={20} color="rgba(255,255,255,0.25)" strokeWidth={1.75} />
                  </div>
                </div>

                <div className="text-center px-2 mt-3.5">
                  <div className="flex items-center justify-center gap-1.5 mb-1.5">
                    <p className="text-[13px] font-semibold select-none leading-tight" style={{ color: "rgba(255,255,255,0.28)" }}>
                      Assessments
                    </p>
                    <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded-full" style={{ background: "rgba(255,255,255,0.07)" }}>
                      <Lock size={7} color="rgba(255,255,255,0.3)" />
                      <span className="text-[8px] font-bold uppercase tracking-wide select-none" style={{ color: "rgba(255,255,255,0.3)" }}>v2</span>
                    </span>
                  </div>
                  <p className="text-[11px] leading-relaxed select-none" style={{ color: "rgba(255,255,255,0.26)" }}>
                    Timed mock tests &amp; performance analytics
                  </p>
                </div>
              </div>

              {/* ④ Compete & rank — locked, v2 */}
              <div className="relative flex flex-col items-center cursor-default" aria-disabled="true">
                <p className="text-[10px] font-black tracking-[0.18em] mb-3 select-none" style={{ color: "rgba(255,255,255,0.2)" }}>04</p>

                <div className="relative w-full flex justify-center" style={{ height: 52 }}>
                  {/* Left connector — dashed glass */}
                  <div className="absolute left-0 right-1/2" style={{
                    top: 25, height: 1,
                    backgroundImage: "repeating-linear-gradient(90deg, rgba(255,255,255,0.16) 0, rgba(255,255,255,0.16) 5px, transparent 5px, transparent 11px)",
                    backgroundSize: "11px 1px",
                  }} />

                  <div
                    className="relative z-10 w-[52px] h-[52px] rounded-full flex items-center justify-center"
                    style={{
                      border: "1.5px dashed rgba(255,255,255,0.2)",
                      background: "rgba(255,255,255,0.05)",
                    }}
                  >
                    <Trophy size={20} color="rgba(255,255,255,0.25)" strokeWidth={1.75} />
                  </div>
                </div>

                <div className="text-center px-2 mt-3.5">
                  <div className="flex items-center justify-center gap-1.5 mb-1.5">
                    <p className="text-[13px] font-semibold select-none leading-tight" style={{ color: "rgba(255,255,255,0.28)" }}>
                      Compete &amp; rank
                    </p>
                    <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded-full" style={{ background: "rgba(255,255,255,0.07)" }}>
                      <Lock size={7} color="rgba(255,255,255,0.3)" />
                      <span className="text-[8px] font-bold uppercase tracking-wide select-none" style={{ color: "rgba(255,255,255,0.3)" }}>v2</span>
                    </span>
                  </div>
                  <p className="text-[11px] leading-relaxed select-none" style={{ color: "rgba(255,255,255,0.26)" }}>
                    Live competitive rounds &amp; leaderboards
                  </p>
                </div>
              </div>

            </div>
          </div>

          {/* ── Mobile (<lg): step list inside dark card ──────────────────── */}
          <div
            className="lg:hidden rounded-[var(--radius-xl)] overflow-hidden"
            style={{ background: "linear-gradient(135deg, #1a3150 0%, #0d1e31 100%)" }}
          >

            {/* Step 01 */}
            <button
              onClick={() => goTo("/students/companies", "companies")}
              disabled={!!navigatingTo}
              className="group cursor-pointer w-full px-5 py-4 flex items-center gap-4 text-left border-b transition-all active:brightness-110 disabled:cursor-wait"
              style={{
                borderColor: "rgba(255,255,255,0.07)",
                opacity: navigatingTo && navigatingTo !== "companies" ? 0.4 : 1,
              }}
            >
              <div
                className="w-10 h-10 rounded-full shrink-0 flex items-center justify-center"
                style={{
                  background: "linear-gradient(135deg, #FFAA2C, #FF8C00)",
                  boxShadow: "0 0 0 3px rgba(255,140,0,0.15), 0 3px 14px rgba(255,140,0,0.35)",
                }}
              >
                {navigatingTo === "companies"
                  ? <LoadingSpinner size={16} color="#fff" />
                  : <Briefcase size={16} color="white" strokeWidth={2} />}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[10px] font-black uppercase tracking-[0.14em] select-none mb-0.5" style={{ color: "rgba(255,140,0,0.7)" }}>Step 01</p>
                <p className="text-[13px] font-semibold select-none group-hover:text-[var(--color-accent)] transition-colors duration-200" style={{ color: "rgba(255,255,255,0.88)" }}>Browse resources</p>
                <p className="text-[11px] mt-0.5 select-none line-clamp-1" style={{ color: "rgba(255,255,255,0.38)" }}>Company-wise aptitude, technical &amp; HR materials</p>
              </div>
              {navigatingTo === "companies"
                ? <LoadingSpinner size={14} color="rgba(255,255,255,0.7)" />
                : <ArrowRight size={14} className="shrink-0 transition-colors duration-200 group-hover:text-[var(--color-accent)]" style={{ color: "rgba(255,255,255,0.28)" }} />}
            </button>

            {/* Step 02 */}
            <button
              onClick={() => goTo("/students/practice", "practice")}
              disabled={!!navigatingTo}
              className="group cursor-pointer w-full px-5 py-4 flex items-center gap-4 text-left border-b transition-all active:brightness-110 disabled:cursor-wait"
              style={{
                borderColor: "rgba(255,255,255,0.07)",
                opacity: navigatingTo && navigatingTo !== "practice" ? 0.4 : 1,
              }}
            >
              <div
                className="w-10 h-10 rounded-full shrink-0 flex items-center justify-center"
                style={{
                  background: "linear-gradient(135deg, #FFAA2C, #FF8C00)",
                  boxShadow: "0 0 0 3px rgba(255,140,0,0.15), 0 3px 14px rgba(255,140,0,0.35)",
                }}
              >
                {navigatingTo === "practice"
                  ? <LoadingSpinner size={16} color="#fff" />
                  : <BookOpen size={16} color="white" strokeWidth={2} />}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[10px] font-black uppercase tracking-[0.14em] select-none mb-0.5" style={{ color: "rgba(255,140,0,0.7)" }}>Step 02</p>
                <p className="text-[13px] font-semibold select-none group-hover:text-[var(--color-accent)] transition-colors duration-200" style={{ color: "rgba(255,255,255,0.88)" }}>Practice questions</p>
                <p className="text-[11px] mt-0.5 select-none line-clamp-1" style={{ color: "rgba(255,255,255,0.38)" }}>Aptitude &amp; technical practice, by topic and difficulty</p>
              </div>
              {navigatingTo === "practice"
                ? <LoadingSpinner size={14} color="rgba(255,255,255,0.7)" />
                : <ArrowRight size={14} className="shrink-0 transition-colors duration-200 group-hover:text-[var(--color-accent)]" style={{ color: "rgba(255,255,255,0.28)" }} />}
            </button>

            {/* Step 03 — locked */}
            <div
              className="px-5 py-4 flex items-center gap-4 border-b cursor-default"
              style={{ borderColor: "rgba(255,255,255,0.07)" }}
              aria-disabled="true"
            >
              <div
                className="w-10 h-10 rounded-full shrink-0 flex items-center justify-center"
                style={{ border: "1.5px dashed rgba(255,255,255,0.2)", background: "rgba(255,255,255,0.05)" }}
              >
                <ClipboardList size={16} color="rgba(255,255,255,0.25)" strokeWidth={1.75} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[10px] font-black uppercase tracking-[0.14em] select-none mb-0.5" style={{ color: "rgba(255,255,255,0.2)" }}>Step 03</p>
                <p className="text-[13px] font-semibold select-none" style={{ color: "rgba(255,255,255,0.28)" }}>Assessments</p>
                <p className="text-[11px] mt-0.5 select-none line-clamp-1" style={{ color: "rgba(255,255,255,0.26)" }}>Timed mock tests &amp; performance analytics</p>
              </div>
              <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded-full shrink-0" style={{ background: "rgba(255,255,255,0.07)" }}>
                <Lock size={7} color="rgba(255,255,255,0.3)" />
                <span className="text-[8px] font-bold uppercase tracking-wide select-none" style={{ color: "rgba(255,255,255,0.3)" }}>v2</span>
              </span>
            </div>

            {/* Step 04 — locked */}
            <div className="px-5 py-4 flex items-center gap-4 cursor-default" aria-disabled="true">
              <div
                className="w-10 h-10 rounded-full shrink-0 flex items-center justify-center"
                style={{ border: "1.5px dashed rgba(255,255,255,0.2)", background: "rgba(255,255,255,0.05)" }}
              >
                <Trophy size={16} color="rgba(255,255,255,0.25)" strokeWidth={1.75} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[10px] font-black uppercase tracking-[0.14em] select-none mb-0.5" style={{ color: "rgba(255,255,255,0.2)" }}>Step 04</p>
                <p className="text-[13px] font-semibold select-none" style={{ color: "rgba(255,255,255,0.28)" }}>Compete &amp; rank</p>
                <p className="text-[11px] mt-0.5 select-none line-clamp-1" style={{ color: "rgba(255,255,255,0.26)" }}>Live competitive rounds &amp; leaderboards</p>
              </div>
              <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded-full shrink-0" style={{ background: "rgba(255,255,255,0.07)" }}>
                <Lock size={7} color="rgba(255,255,255,0.3)" />
                <span className="text-[8px] font-bold uppercase tracking-wide select-none" style={{ color: "rgba(255,255,255,0.3)" }}>v2</span>
              </span>
            </div>

          </div>
        </div>

      </PageWrapper>
    </StudentLayout>
  );
}
