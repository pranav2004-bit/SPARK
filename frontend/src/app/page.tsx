export const dynamic = "force-static";

import Image from "next/image";
import Link from "next/link";
import {
  Briefcase,
  BookOpen,
  ClipboardList,
  Trophy,
  ArrowRight,
  Star,
  Zap,
} from "lucide-react";
import { LandingMobileMenu } from "@/components/layout/LandingMobileMenu";
import { ScrollingUpdates } from "@/components/ui/ScrollingUpdates";
import { SplashScreen } from "@/components/ui/SplashScreen";
import { LinkLabel } from "@/components/ui/LinkLabel";

// ── Module data ───────────────────────────────────────────────────────────────
const MODULES = [
  {
    icon: Briefcase,
    label: "Resources",
    heading: "Every resource. Every drive.",
    desc: "Aptitude, technical and HR materials - organised by company, updated before every recruitment drive.",
    accent: "#1A3150",
    accentBg: "#e8eef5",
  },
  {
    icon: BookOpen,
    label: "Practice",
    heading: "Master every topic, at your pace.",
    desc: "Topic-wise and difficulty-graded question banks across Aptitude, Reasoning, Verbal and Coding - with instant explanations and progress tracking.",
    accent: "#0D9488",
    accentBg: "#f0fdfa",
  },
  {
    icon: ClipboardList,
    label: "Proctored Assessments",
    heading: "Simulate the real thing.",
    desc: "Full-length, proctored timed mocks modelled on actual recruitment test patterns - with section-wise analytics and detailed post-test review.",
    accent: "#E8820C",
    accentBg: "#FFF4E6",
  },
  {
    icon: Trophy,
    label: "Contests",
    heading: "Compete. Rank. Win.",
    desc: "Live competitive rounds against your batchmates, real-time leaderboards, batch-vs-batch challenges and winner badges on your profile.",
    accent: "#7C3AED",
    accentBg: "#f5f3ff",
  },
];

// ── Steps ─────────────────────────────────────────────────────────────────────
const STEPS = [
  {
    step: "01",
    icon: Zap,
    title: "Log in with your credentials",
    desc: "Use your Student ID and password to log in - no separate sign-up required.",
  },
  {
    step: "02",
    icon: Briefcase,
    title: "Browse company resources",
    desc: "Find companies visiting your campus and access curated materials.",
  },
  {
    step: "03",
    icon: BookOpen,
    title: "Practice & get assessed",
    desc: "Work through topic-wise questions and take full mock assessments.",
  },
  {
    step: "04",
    icon: Trophy,
    title: "Compete and excel",
    desc: "Join live contests, track your rank and sharpen interview confidence.",
  },
];

export default function LandingPage() {
  return (
    <>
    <SplashScreen />
    <div className="min-h-screen bg-[var(--color-surface-secondary)]">

      {/* ── Sticky header group: announcement bar + navbar ───────────────────── */}
      {/* Both are wrapped in a single sticky container so they move together    */}
      {/* and the nav never slides over the scroll bar.                          */}
      <div className="sticky top-0 z-50">
        <ScrollingUpdates context="public" disableSticky />

      {/* ── Navbar ───────────────────────────────────────────────────────────── */}
      <nav className="bg-white border-b border-[var(--color-border)] flex items-center justify-between px-4 sm:px-10 xl:px-20 h-16 shadow-[var(--shadow-xs)]">
        {/* Left — Logos */}
        <div className="flex items-center">
          <Image
            src="/institution-logo.png"
            alt="ANITS"
            width={52}
            height={52}
            className="h-9 sm:h-11 w-auto object-contain mr-2.5 sm:mr-3.5"
            priority
          />
          <div className="w-px h-7 sm:h-8 bg-[var(--color-border-strong)]" />
          <Image
            src="/spark-logo.svg"
            alt="SPARK"
            width={0}
            height={0}
            className="h-8 sm:h-10 w-auto ml-2 sm:ml-3"
            priority
          />
        </div>

        {/* Center — Nav links (no active state on landing page) */}
        <div className="hidden md:flex items-center gap-10">
          <a
            href="#features"
            className="text-sm font-medium text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors duration-150"
          >
            Modules
          </a>
          <a
            href="#how-it-works"
            className="text-sm font-medium text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors duration-150"
          >
            Process
          </a>
          <Link
            href="/about"
            className="text-sm font-medium text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors duration-150"
          >
            About
          </Link>
        </div>

        {/* Right — CTA */}
        <div className="flex items-center gap-2 sm:gap-3">
          <Link
            href="/students/login"
            className="px-4 py-2 text-sm font-medium text-[var(--color-text)] hover:text-[var(--color-primary)] transition-colors duration-150 hidden sm:inline-flex"
          >
            Sign In
          </Link>
          <Link
            href="/students/login"
            className="inline-flex items-center gap-1.5 px-4 py-2 sm:px-6 sm:py-2.5 rounded-full text-[13px] sm:text-sm font-semibold bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white transition-all duration-150 shadow-[var(--shadow-sm)] hover:shadow-[var(--shadow-md)] hover:-translate-y-0.5 active:translate-y-0 shrink-0"
          >
            <LinkLabel>Get Started</LinkLabel>
          </Link>
          <LandingMobileMenu />
        </div>
      </nav>
      </div>{/* end sticky header group */}

      {/* ── Hero ─────────────────────────────────────────────────────────────── */}
      <section className="bg-[var(--color-surface-secondary)] px-5 pt-8 sm:pt-20 pb-8 sm:pb-10">
        <div className="max-w-5xl mx-auto text-center">

          {/* Institution identity */}
          <p className="text-[11px] sm:text-base lg:text-xl font-black tracking-[0.08em] sm:tracking-[0.12em] uppercase text-[var(--color-text)] leading-snug lg:whitespace-nowrap mb-1.5">
            Anil Neerukonda Institute of Technology & Sciences (Autonomous)
          </p>

          {/* Tagline */}
          <p className="text-[10px] sm:text-sm font-semibold tracking-[0.06em] sm:tracking-[0.1em] uppercase text-[var(--color-accent)] leading-tight mb-8">
            Structured Preparation And Readiness Kit
          </p>

          {/* Heading */}
          <h1
            className="font-extrabold leading-[1.1] mb-5 tracking-tight text-[var(--color-text)] whitespace-nowrap"
            style={{ fontSize: "clamp(1.15rem, 4.8vw, 3rem)" }}
          >
            Progress you can{" "}
            <span className="text-[var(--color-accent)]">measure.</span>
          </h1>

          {/* Subtitle */}
          <p className="text-[var(--color-text-muted)] text-base sm:text-lg leading-relaxed max-w-xl mx-auto mb-8">
            Company materials, practice questions, mock assessments and live
            contests - curated by your institution&apos;s training team.
          </p>

          {/* Badge */}
          <div className="inline-flex items-center gap-2 bg-[var(--color-accent)]/10 border border-[var(--color-accent)]/25 text-[var(--color-accent)] px-4 sm:px-6 py-1.5 sm:py-2 rounded-full text-xs sm:text-sm font-medium mb-8 tracking-normal uppercase text-center mx-auto">
            <Star size={10} fill="currentColor" className="shrink-0" />
            <span className="leading-tight">Proctored Assessments Platform</span>
          </div>

          {/* CTAs */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-center gap-4 max-w-sm sm:max-w-none mx-auto">
            <Link
              href="/students/login"
              className="inline-flex items-center justify-center gap-2 px-9 py-4 rounded-full bg-[var(--color-accent)] text-white font-semibold text-[15px] transition-all duration-150 shadow-[var(--shadow-md)] hover:shadow-[var(--shadow-lg)] hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.98]"
            >
              <LinkLabel>Start Practicing</LinkLabel>
              <ArrowRight size={16} />
            </Link>
            <a
              href="#how-it-works"
              className="inline-flex items-center justify-center gap-2 px-9 py-4 rounded-full bg-white border border-[var(--color-border)] hover:border-[var(--color-text-muted)] text-[var(--color-text)] font-semibold text-[15px] transition-all duration-150 shadow-[var(--shadow-sm)] hover:shadow-[var(--shadow-md)] hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.98]"
            >
              See How It Works
            </a>
          </div>
        </div>
      </section>

      {/* ── Module Showcase ───────────────────────────────────────────────────── */}
      <section id="features" className="bg-[var(--color-surface-secondary)] border-t border-[var(--color-border)] py-14 px-5 scroll-mt-16">
        <div className="max-w-6xl mx-auto">

          {/* Section header */}
          <div className="text-center mb-12">
            <p className="text-xs font-bold tracking-[0.18em] text-[var(--color-accent)] uppercase mb-3">
              What&apos;s Inside SPARK
            </p>
            <h2 className="text-3xl sm:text-4xl font-bold text-[var(--color-text)] leading-tight">
              Four modules. One goal - get ready.
            </h2>
          </div>

          {/* Module cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {MODULES.map(({ icon: Icon, label, heading, desc, accent, accentBg }) => (
              <div
                key={label}
                className="group bg-white rounded-[var(--radius-xl)] border border-[var(--color-border)] p-7 hover:shadow-[var(--shadow-md)] hover:-translate-y-0.5 transition-all duration-200"
              >
                {/* Icon */}
                <div className="mb-5">
                  <div
                    className="w-11 h-11 rounded-[var(--radius-lg)] flex items-center justify-center"
                    style={{ background: accentBg }}
                  >
                    <Icon size={20} style={{ color: accent }} />
                  </div>
                </div>

                {/* Label */}
                <p className="text-[11px] font-bold tracking-[0.15em] uppercase mb-1.5" style={{ color: accent }}>
                  {label}
                </p>

                {/* Heading */}
                <h3 className="text-[18px] font-bold text-[var(--color-text)] mb-2 leading-snug">
                  {heading}
                </h3>

                {/* Description */}
                <p className="text-sm text-[var(--color-text-muted)] leading-relaxed">
                  {desc}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── How it works ─────────────────────────────────────────────────────── */}
      <section id="how-it-works" className="bg-[var(--color-surface-secondary)] border-t border-[var(--color-border)] py-14 px-5 scroll-mt-16">
        <div className="max-w-5xl mx-auto">

          <div className="text-center mb-12">
            <p className="text-xs font-bold tracking-[0.18em] text-[var(--color-accent)] uppercase mb-3">
              How It Works
            </p>
            <h2 className="text-3xl sm:text-4xl font-bold text-[var(--color-text)] leading-tight">
              From login to confidence, in 4 steps.
            </h2>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {STEPS.map(({ step, icon: Icon, title, desc }) => (
              <div
                key={step}
                className="bg-white border border-[var(--color-border)] rounded-[var(--radius-xl)] p-6 hover:border-[var(--color-accent)] hover:shadow-[var(--shadow-sm)] hover:-translate-y-0.5 transition-all duration-200"
              >
                {/* Step icon + number */}
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-9 h-9 rounded-full bg-[var(--color-primary)] flex items-center justify-center shrink-0">
                    <Icon size={15} className="text-white" />
                  </div>
                  <span className="text-xs font-bold text-[var(--color-text-subtle)] tracking-widest">{step}</span>
                </div>
                <h3 className="font-bold text-[var(--color-text)] text-[14px] mb-1.5 leading-snug">{title}</h3>
                <p className="text-sm text-[var(--color-text-muted)] leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA Banner ────────────────────────────────────────────────────────── */}
      <section className="bg-[var(--color-primary)] py-14 sm:py-20 px-5">
        <div className="max-w-2xl mx-auto text-center">
          <p className="text-xs font-bold tracking-[0.18em] text-[var(--color-accent)] uppercase mb-4">
            Your preparation starts here
          </p>
          <h2 className="text-3xl sm:text-4xl font-bold text-white mb-4 leading-tight">
            Start preparing today.
          </h2>
          <p className="text-white/50 text-base mb-8 leading-relaxed">
            Log in with your Student ID and start immediately.
          </p>
          <Link
            href="/students/login"
            className="group relative overflow-hidden inline-flex items-center gap-2 px-10 py-4 rounded-full bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white font-semibold text-[15px] transition-all duration-150 shadow-[var(--shadow-md)] hover:shadow-[var(--shadow-lg)] hover:-translate-y-0.5 active:scale-[0.98] active:translate-y-0"
          >
            {/* Glass sheen — sweeps left-to-right on hover instead of a flat color swap */}
            <span
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 -translate-x-full skew-x-[-20deg] bg-gradient-to-r from-transparent via-white/40 to-transparent transition-transform duration-700 ease-out group-hover:translate-x-full"
            />
            <span className="relative z-10 inline-flex items-center gap-2">
              <LinkLabel>Get Started</LinkLabel>
              <ArrowRight size={16} />
            </span>
          </Link>
        </div>
      </section>

    </div>
    </>
  );
}
