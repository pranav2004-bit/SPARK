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

// ── Module data ───────────────────────────────────────────────────────────────
const MODULES = [
  {
    icon: Briefcase,
    label: "Resources",
    heading: "Every resource. Every drive.",
    desc: "Aptitude, technical, and HR materials — organised by company, updated before every placement drive.",
    accent: "#1A3150",
    accentBg: "#e8eef5",
  },
  {
    icon: BookOpen,
    label: "Practice",
    heading: "Master every topic, at your pace.",
    desc: "Topic-wise and difficulty-graded question banks across Aptitude, Reasoning, Verbal, and Coding — with instant explanations and progress tracking.",
    accent: "#0D9488",
    accentBg: "#f0fdfa",
  },
  {
    icon: ClipboardList,
    label: "Assessments",
    heading: "Simulate the real thing.",
    desc: "Full-length timed mocks modelled on actual placement test patterns — with section-wise analytics and detailed post-test review.",
    accent: "#E8820C",
    accentBg: "#FFF4E6",
  },
  {
    icon: Trophy,
    label: "Contests",
    heading: "Compete. Rank. Win.",
    desc: "Live competitive rounds against your batchmates, real-time leaderboards, batch-vs-batch challenges, and winner badges on your profile.",
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
    desc: "Use your Student ID and password. No sign-up required.",
  },
  {
    step: "02",
    icon: Briefcase,
    title: "Browse placement resources",
    desc: "Find companies visiting your campus and access section-wise materials curated for each drive.",
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
    title: "Compete and get placed",
    desc: "Join live contests, track your rank, and walk into every interview with confidence.",
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
      <nav className="bg-white border-b border-[var(--color-border)] flex items-center justify-between px-4 sm:px-10 xl:px-20 py-2 shadow-[var(--shadow-xs)]">
        {/* Left — Logos */}
        <div className="flex items-center gap-2 sm:gap-3">
          <Image
            src="/institution-logo.svg"
            alt="ANITS"
            width={52}
            height={52}
            className="h-[40px] sm:h-[52px] w-auto object-contain"
            priority
          />
          <div className="w-px h-7 sm:h-9 bg-[var(--color-border-strong)]" />
          <Image
            src="/spark-logo.svg"
            alt="SPARK"
            width={0}
            height={0}
            className="h-[26px] sm:h-[34px] w-auto"
            priority
          />
        </div>

        {/* Center — Nav links (no active state on landing page) */}
        <div className="hidden md:flex items-center gap-8">
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
            className="inline-flex items-center gap-1.5 px-4 py-2 sm:px-6 sm:py-2.5 rounded-full text-[13px] sm:text-sm font-semibold bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white transition-all duration-150 shadow-[var(--shadow-sm)] hover:shadow-[var(--shadow-md)] shrink-0"
          >
            Get Started
          </Link>
          <LandingMobileMenu />
        </div>
      </nav>
      </div>{/* end sticky header group */}

      {/* ── Hero ─────────────────────────────────────────────────────────────── */}
      <section className="bg-[var(--color-surface-secondary)] px-5 pt-8 sm:pt-24 pb-8 sm:pb-14">
        <div className="max-w-3xl mx-auto text-center">

          {/* Institution identity */}
          <p className="text-[10px] sm:text-xs font-medium tracking-[0.14em] text-[var(--color-text-muted)] uppercase mb-3">
            Anil Neerukonda Institute of Technology & Sciences (Autonomous)
          </p>

          {/* SPARK badge */}
          <div className="inline-flex items-center gap-2 bg-[var(--color-accent)]/10 border border-[var(--color-accent)]/25 text-[var(--color-accent)] px-3 sm:px-4 py-1.5 rounded-full text-[10px] font-bold mb-10 tracking-widest uppercase text-center mx-auto">
            <Star size={10} fill="currentColor" className="shrink-0" />
            <span className="leading-tight">Structured Preparation And Readiness Kit</span>
          </div>

          {/* Heading */}
          <h1 className="text-5xl sm:text-6xl xl:text-[68px] font-bold leading-[1.1] mb-5 tracking-tight text-[var(--color-text)]">
            Everything you need to
            <span className="block text-[var(--color-accent)] mt-1">get placed.</span>
          </h1>

          {/* Subtitle */}
          <p className="text-[var(--color-text-muted)] text-lg sm:text-xl leading-relaxed max-w-xl mx-auto mb-10">
            Company materials, practice questions, mock assessments, and live
            contests — curated by your institution&apos;s placement team.
          </p>

          {/* Primary CTA */}
          <Link
            href="/students/login"
            className="inline-flex items-center gap-2 px-9 py-4 rounded-full bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white font-semibold text-[15px] transition-all duration-150 shadow-[var(--shadow-md)] hover:shadow-[var(--shadow-lg)] active:scale-[0.98]"
          >
            Get Started
            <ArrowRight size={16} />
          </Link>

          {/* Institutional note — subtle, below CTA */}
          <p className="text-[var(--color-text-muted)] text-sm mt-4 font-medium">
            Exclusively for ANITS students
          </p>
        </div>
      </section>

      {/* ── Module Showcase ───────────────────────────────────────────────────── */}
      <section id="features" className="bg-[var(--color-surface-secondary)] border-t border-[var(--color-border)] py-14 px-5">
        <div className="max-w-6xl mx-auto">

          {/* Section header */}
          <div className="text-center mb-12">
            <p className="text-xs font-bold tracking-[0.18em] text-[var(--color-accent)] uppercase mb-3">
              What&apos;s Inside SPARK
            </p>
            <h2 className="text-3xl sm:text-4xl font-bold text-[var(--color-text)] leading-tight">
              Four modules. One goal – get placed.
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
      <section id="how-it-works" className="bg-[var(--color-surface-secondary)] border-t border-[var(--color-border)] py-14 px-5">
        <div className="max-w-5xl mx-auto">

          <div className="text-center mb-12">
            <p className="text-xs font-bold tracking-[0.18em] text-[var(--color-accent)] uppercase mb-3">
              How It Works
            </p>
            <h2 className="text-3xl sm:text-4xl font-bold text-[var(--color-text)] leading-tight">
              From login to placement, in 4 steps.
            </h2>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {STEPS.map(({ step, icon: Icon, title, desc }) => (
              <div
                key={step}
                className="bg-white border border-[var(--color-border)] rounded-[var(--radius-xl)] p-6 hover:shadow-[var(--shadow-sm)] transition-all duration-200"
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
            className="inline-flex items-center gap-2 px-10 py-4 rounded-full bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white font-semibold text-[15px] transition-all duration-150 shadow-[var(--shadow-md)] hover:shadow-[var(--shadow-lg)] active:scale-[0.98]"
          >
            Get Started
            <ArrowRight size={16} />
          </Link>
        </div>
      </section>

    </div>
    </>
  );
}
