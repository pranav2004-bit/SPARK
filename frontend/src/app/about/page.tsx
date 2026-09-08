"use client";

import Image from "next/image";
import Link from "next/link";
import {
  Users,
  ShieldCheck,
  BarChart3,
  BookOpen,
  Trophy,
  ArrowRight,
  CheckCircle,
  Code2,
  GraduationCap,
  ClipboardCheck,
  Building2,
  Star,
} from "lucide-react";
import { LandingMobileMenu } from "@/components/layout/LandingMobileMenu";
import { ScrollingUpdates } from "@/components/ui/ScrollingUpdates";
import { LinkLabel } from "@/components/ui/LinkLabel";

// ── Features ─────────────────────────────────────────────────────────────────
const features = [
  {
    icon: ShieldCheck,
    title: "Proctored Assessments",
    description: "Built-in proctoring keeps every assessment fair, so results reflect real performance.",
  },
  {
    icon: BarChart3,
    title: "Detailed Analytics",
    description: "Score distributions, per-question difficulty and pass-rate breakdowns for every assessment.",
  },
  {
    icon: BookOpen,
    title: "Curated Resources",
    description: "Company materials organised by department, curated and refreshed before every recruitment drive.",
  },
  {
    icon: Trophy,
    title: "Live Contests",
    description: "Real-time leaderboards and batch-vs-batch challenges that make practice genuinely competitive.",
  },
];

// ── Team data ────────────────────────────────────────────────────────────────
interface ProfileMember {
  id: string;
  name: string;
  initials: string;
  role: string;
  photo?: string;
  title?: string;
  department?: string;
}

const row1: ProfileMember[] = [
  {
    id: "r1-1",
    name: "Dr. V. Rajya Lakshmi",
    initials: "VR",
    photo: "/images/profile_r1_1.jpg",
    role: "Principal",
    department: "ANIL NEERUKONDA INSTITUTE OF TECHNOLOGY & SCIENCES (Autonomous)",
  },
];

const row2: ProfileMember[] = [
  {
    id: "r2-1",
    name: "Prof. Poosapati. Padmaja",
    initials: "PP",
    photo: "/images/profile_r2_1.jpg",
    role: "Dean - Training",
  },
  {
    id: "r2-2",
    name: "Prof. Adinarayana Salina",
    initials: "AS",
    photo: "/images/profile_r2_2.jpg",
    role: "HOD - CSE (Data Science)",
  },
];

const row3: ProfileMember[] = [
  {
    id: "r3-1",
    name: "Mr. K Rajkiran",
    initials: "KR",
    photo: "/images/rajkiran.jpeg",
    role: "Coordinator - SPARK",
    title: "Aptitude Trainer",
    department: "Department of Training",
  },
  {
    id: "r3-4",
    name: "Mr. M.V. Kishore",
    initials: "MK",
    photo: "/images/profile_r3_4.jpg",
    role: "Technical Support",
    title: "Asst. Professor",
    department: "Department of IT",
  },
];

interface TechTeamMember {
  id: number;
  name: string;
  batch: string;
  department: string;
  founder?: string;
  founderRole?: string;
  role?: string;
  photo: string;
  photoPosition?: string;
}

const techTeam: TechTeamMember[] = [
  { id: 1, name: "Padala Lohit Reddy", batch: "2023-2027", department: "CSE (Data Science)", founder: "SANJIVO", founderRole: "PRO", photo: "/images/tech_team_1.jpg" },
  { id: 2, name: "Managala Gyana Saisri Abhinay", batch: "2023-2027", department: "CSE (Data Science)", founder: "AURATECH-VISION", photo: "/images/tech_team_3.jpg" },
  { id: 3, name: "Pranavnath Kosuru", batch: "2023-2027", department: "CSE (Data Science)", founder: "SANJIVO", photo: "/images/tech_team_4.jpg" },
  { id: 4, name: "Thumu Anoop", batch: "2023-2027", department: "CSE (Data Science)", founder: "SANJIVO", founderRole: "CTO", photo: "/images/tech_team_2.jpg" },
  { id: 5, name: "Adari Yaswanth", batch: "2023-2027", department: "CSE (Data Science)", role: "Quality Assurance", photo: "/images/yaswanth.jpeg" },
  { id: 6, name: "Majji Mohan Pradeep", batch: "2023-2027", department: "CSE (Data Science)", role: "Designer", photo: "/images/pradeep.jpeg", photoPosition: "center 25%" },
];

const techAvatarGradients = [
  "from-blue-500 to-indigo-600",
  "from-violet-500 to-purple-600",
  "from-emerald-500 to-teal-600",
  "from-orange-500 to-rose-600",
];

function getInitials(name: string) {
  return name.split(" ").filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join("");
}

// ── Sub-components ───────────────────────────────────────────────────────────

function ProfileCard({ member, large = false }: { member: ProfileMember; large?: boolean }) {
  return (
    <div className="bg-white rounded-2xl border border-[var(--color-border)] shadow-[var(--shadow-xs)] hover:shadow-[var(--shadow-sm)] hover:-translate-y-0.5 transition-all duration-200 p-6 flex flex-col items-center text-center">
      {member.photo ? (
        <div className="w-24 h-24 sm:w-32 sm:h-32 rounded-full overflow-hidden mx-auto mb-4 sm:mb-5 ring-2 ring-[var(--color-border)] relative">
          <Image src={member.photo} alt={member.name} fill sizes="(max-width: 640px) 96px, 128px" className="object-cover object-center" />
        </div>
      ) : (
        <div className="w-24 h-24 sm:w-32 sm:h-32 rounded-full bg-[var(--color-accent)]/10 flex items-center justify-center mx-auto mb-4 sm:mb-5 ring-2 ring-[var(--color-border)]">
          <span className="text-2xl font-bold text-[var(--color-accent)] select-none tracking-wide">{member.initials}</span>
        </div>
      )}
      <h3 className="font-semibold text-[var(--color-text)] text-base leading-snug mb-1">{member.name}</h3>
      <p className={`${large ? "text-sm" : "text-xs"} font-semibold text-[var(--color-accent)] mb-3 leading-snug`}>{member.role}</p>
      <div className="space-y-0.5">
        {member.title && <p className="text-xs text-[var(--color-text-muted)] font-medium leading-snug">{member.title}</p>}
        {member.department && <p className="text-xs text-[var(--color-text-muted)] leading-snug">{member.department}</p>}
      </div>
    </div>
  );
}

interface PyramidRowProps {
  members: ProfileMember[];
  large?: boolean;
  maxCols: 1 | 2 | 4;
}

function PyramidRow({ members, large, maxCols }: PyramidRowProps) {
  const gridClass =
    maxCols === 1 ? "grid-cols-1" :
    maxCols === 2 ? "grid-cols-1 sm:grid-cols-2" :
    "grid-cols-2 lg:grid-cols-4";
  const maxWClass = maxCols === 1 ? "max-w-xs" : maxCols === 2 ? "max-w-xl" : "max-w-5xl";

  return (
    <div className={`grid ${gridClass} gap-4 sm:gap-5 mx-auto ${maxWClass} w-full`}>
      {members.map(member => <ProfileCard key={member.id} member={member} large={large} />)}
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function AboutPage() {
  return (
    <>
    <div className="min-h-screen bg-[var(--color-surface-secondary)]">

      {/* ── Sticky header group ─────────────────────────────────────────────── */}
      <div className="sticky top-0 z-50">
        <ScrollingUpdates context="public" disableSticky />

        <nav className="bg-white border-b border-[var(--color-border)] flex items-center justify-between px-4 sm:px-10 xl:px-20 h-16 shadow-[var(--shadow-xs)]">
          <Link href="/" className="flex items-center">
            <Image src="/institution-logo.png" alt="ANITS" width={52} height={52} className="h-9 sm:h-11 w-auto object-contain mr-2.5 sm:mr-3.5" priority />
            <div className="w-px h-7 sm:h-8 bg-[var(--color-border-strong)]" />
            <Image src="/spark-logo.svg" alt="SPARK" width={0} height={0} className="h-8 sm:h-10 w-auto ml-2 sm:ml-3" priority />
          </Link>

          <div className="hidden md:flex items-center gap-10">
            <Link href="/#features" className="text-sm font-medium text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors duration-150">Modules</Link>
            <Link href="/#how-it-works" className="text-sm font-medium text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors duration-150">Process</Link>
            <span className="text-sm font-semibold text-[var(--color-text)]">About</span>
          </div>

          <div className="flex items-center gap-2 sm:gap-3">
            <Link href="/students/login" className="px-4 py-2 text-sm font-medium text-[var(--color-text)] hover:text-[var(--color-primary)] transition-colors duration-150 hidden sm:inline-flex">
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
      </div>

      {/* ── Hero ─────────────────────────────────────────────────────────────── */}
      <section className="pt-8 pb-4 sm:pb-6 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto text-center">
          <span className="inline-block mb-4 sm:mb-5 px-3 sm:px-4 py-1 sm:py-1.5 rounded-lg bg-[var(--color-accent)]/15 text-[var(--color-accent)] text-xs sm:text-sm font-semibold border border-[var(--color-accent)]/25">
            About SPARK
          </span>
          <h1
            className="mb-3 sm:mb-4 font-bold tracking-tight text-[var(--color-text)] leading-tight whitespace-nowrap"
            style={{ fontSize: "clamp(1rem, 3.8vw, 2.25rem)" }}
          >
            Exclusively for{" "}
            <span className="text-[var(--color-accent)]">ANITS Students</span>
          </h1>
          <p className="text-sm sm:text-base text-[var(--color-text-muted)] max-w-2xl mx-auto leading-relaxed">
            Here's the story behind SPARK and the team at ANITS that builds and maintains it for you.
          </p>
        </div>
      </section>

      {/* ── Mission ──────────────────────────────────────────────────────────── */}
      <section className="pt-6 pb-10 px-4 sm:px-6 lg:px-8">
        <div className="max-w-3xl mx-auto bg-white border border-[var(--color-border)] rounded-2xl shadow-[var(--shadow-xs)] hover:shadow-[var(--shadow-sm)] hover:-translate-y-0.5 transition-all duration-200 overflow-hidden">
          <div className="p-2 sm:p-3">
            <div className="bg-[var(--color-surface-secondary)] px-4 sm:px-8 py-4 sm:py-5 rounded-xl relative overflow-hidden">
              <div className="absolute left-0 top-0 bottom-0 w-1.5 bg-[var(--color-accent)]" />
              <h2 className="text-xl sm:text-2xl lg:text-4xl text-center font-bold tracking-tight text-[var(--color-text)]">Our Mission</h2>
            </div>
          </div>
          <div className="px-4 sm:px-8 py-4 sm:py-6 space-y-4">
            <p className="text-base text-[var(--color-text-muted)] leading-relaxed">
              We believe every student deserves structured, institution-verified preparation -
              not scattered PDFs and guesswork before a recruitment drive.
            </p>
            <p className="text-base text-[var(--color-text-muted)] leading-relaxed">
              SPARK brings resources, practice, proctored assessments and live contests into a
              single platform, curated directly by ANITS's own training team.
            </p>
            <div className="bg-[var(--color-surface-secondary)] rounded-xl p-5 border border-[var(--color-border)]">
              <ul className="space-y-3">
                {[
                  "Give every student the same structured preparation, regardless of background",
                  "Provide immediate, measurable feedback through real analytics",
                  "Keep results trustworthy with proctored, malpractice-monitored assessments",
                ].map(item => (
                  <li key={item} className="flex items-start gap-3">
                    <CheckCircle className="w-5 h-5 text-[var(--color-accent)] mt-0.5 shrink-0" />
                    <span className="text-sm text-[var(--color-text)] font-medium">{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* ── Features ─────────────────────────────────────────────────────────── */}
      <section className="pt-6 pb-12 px-4 sm:px-6 lg:px-8">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-8 sm:mb-10">
            <h2 className="text-2xl sm:text-3xl lg:text-4xl mb-3 sm:mb-4 font-bold tracking-tight text-[var(--color-text)]">What Makes SPARK Different</h2>
            <p className="text-sm sm:text-base lg:text-lg text-[var(--color-text-muted)] max-w-2xl mx-auto">
              Built by the training team that actually runs your placement drives
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6">
            {features.map(feature => (
              <div key={feature.title} className="bg-white rounded-2xl border border-[var(--color-border)] shadow-[var(--shadow-xs)] hover:shadow-[var(--shadow-sm)] hover:-translate-y-0.5 transition-all duration-200 p-6">
                <div className="w-12 h-12 rounded-xl bg-[var(--color-accent)]/10 flex items-center justify-center mb-4">
                  <feature.icon className="w-6 h-6 text-[var(--color-accent)]" />
                </div>
                <h3 className="text-lg font-semibold text-[var(--color-text)] mb-2">{feature.title}</h3>
                <p className="text-[var(--color-text-muted)] text-sm leading-relaxed">{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Our People ───────────────────────────────────────────────────────── */}
      <section className="pt-12 pb-10 px-4 sm:px-6 lg:px-8 border-t border-[var(--color-border)]">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-8 sm:mb-10">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-[var(--color-text)] text-xs font-semibold text-[var(--color-text)] mb-3 sm:mb-4">
              <Star size={11} className="text-[var(--color-accent)]" fill="currentColor" /> Our People
            </span>
            <h2 className="text-2xl sm:text-3xl lg:text-4xl mb-3 sm:mb-4 font-bold tracking-tight text-[var(--color-text)]">The Team Behind SPARK</h2>
            <p className="text-sm sm:text-base lg:text-lg text-[var(--color-text-muted)] max-w-2xl mx-auto">
              The educators and coordinators who curate and run SPARK for ANITS students
            </p>
          </div>

          <div className="flex flex-col items-center gap-10 sm:gap-12">
            <div className="w-full flex flex-col items-center gap-5">
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-[var(--color-text)] text-xs font-semibold text-[var(--color-text)]">
                <Building2 className="w-3.5 h-3.5" /> Head of Institution
              </span>
              <PyramidRow members={row1} large maxCols={1} />
            </div>

            <div className="w-px h-5 bg-[var(--color-border)] -my-3" aria-hidden="true" />

            <div className="w-full flex flex-col items-center gap-5">
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-[var(--color-text)] text-xs font-semibold text-[var(--color-text)]">
                <GraduationCap className="w-3.5 h-3.5" /> Academic Leadership
              </span>
              <PyramidRow members={row2} maxCols={2} />
            </div>

            <div className="w-px h-5 bg-[var(--color-border)] -my-3" aria-hidden="true" />

            <div className="w-full flex flex-col items-center gap-5">
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-[var(--color-text)] text-xs font-semibold text-[var(--color-text)]">
                <ClipboardCheck className="w-3.5 h-3.5" /> SPARK Panel
              </span>
              <PyramidRow members={row3} maxCols={2} />
            </div>
          </div>
        </div>
      </section>

      {/* ── Development Team ─────────────────────────────────────────────────── */}
      <section className="pt-6 pb-12 px-4 sm:px-6 lg:px-8">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-8">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-[var(--color-text)] text-xs font-semibold text-[var(--color-text)]">
              <Code2 className="w-3.5 h-3.5" /> Development Team
            </span>
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6 max-w-4xl mx-auto">
            {techTeam.map((member, index) => (
              <div key={member.id} className="bg-white rounded-2xl border border-[var(--color-border)] shadow-[var(--shadow-xs)] hover:shadow-[var(--shadow-sm)] hover:-translate-y-0.5 transition-all duration-200 p-6 text-center">
                <div className="mx-auto mb-3 relative w-28 h-28">
                  {member.photo ? (
                    <div className="w-28 h-28 rounded-full overflow-hidden mx-auto ring-2 ring-[var(--color-accent)]/30 relative">
                      <Image
                        src={member.photo}
                        alt={member.name}
                        fill
                        sizes="112px"
                        className="object-cover"
                        style={{ objectPosition: member.photoPosition ?? "center" }}
                      />
                    </div>
                  ) : (
                    <div className={`w-28 h-28 rounded-full bg-gradient-to-br ${techAvatarGradients[index % techAvatarGradients.length]} mx-auto flex items-center justify-center ring-2 ring-[var(--color-accent)]/30`}>
                      <span className="text-xl font-bold text-white select-none">{getInitials(member.name)}</span>
                    </div>
                  )}
                </div>
                <h3 className="text-sm font-semibold text-[var(--color-text)] leading-tight">{member.name}</h3>
                {(member.founder || member.role) && (
                  <div className="mt-2">
                    <span className="inline-block px-2.5 py-1 text-[10px] font-semibold rounded-md bg-[var(--color-accent)]/10 text-[var(--color-accent)] border border-[var(--color-accent)]/20">
                      {member.role ?? `${member.founderRole ?? (member.founder === "SANJIVO" ? "Co-Founder" : "Founder")} / ${member.founder}`}
                    </span>
                  </div>
                )}
                <p className="text-xs font-medium text-[var(--color-text-muted)] mt-2">{member.batch}</p>
                <p className="text-xs text-[var(--color-text-subtle)] mt-0.5">{member.department}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ──────────────────────────────────────────────────────────────── */}
      <section className="py-12 px-4 sm:px-6 lg:px-8 bg-[var(--color-surface-secondary)] border-t border-[var(--color-border)]">
        <div className="max-w-3xl mx-auto text-center">
          <h2 className="text-2xl sm:text-3xl lg:text-4xl mb-4 sm:mb-6 font-bold tracking-tight text-[var(--color-text)]">Ready to Start Preparing?</h2>
          <p className="text-sm sm:text-base lg:text-lg text-[var(--color-text-muted)] mb-8 sm:mb-10">
            Because preparation should feel like confidence, not chaos.
          </p>
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-center gap-4 max-w-sm sm:max-w-none mx-auto">
            <Link
              href="/students/login"
              className="inline-flex items-center justify-center gap-2 px-9 py-4 rounded-full bg-[var(--color-accent)] text-white font-semibold text-[15px] transition-all duration-150 shadow-[var(--shadow-md)] hover:shadow-[var(--shadow-lg)] hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.98]"
            >
              <Users className="w-5 h-5" />
              <LinkLabel>Start Practicing</LinkLabel>
              <ArrowRight className="w-5 h-5" />
            </Link>
            <Link
              href="/#features"
              className="inline-flex items-center justify-center gap-2 px-9 py-4 rounded-full bg-white border border-[var(--color-border)] hover:border-[var(--color-text-muted)] text-[var(--color-text)] font-semibold text-[15px] transition-all duration-150 shadow-[var(--shadow-sm)] hover:shadow-[var(--shadow-md)] hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.98]"
            >
              <LinkLabel>Learn More</LinkLabel>
            </Link>
          </div>
        </div>
      </section>

      {/* ── Footer ───────────────────────────────────────────────────────────── */}
      <footer className="py-8 px-4 sm:px-6 lg:px-8 border-t border-[var(--color-border)]">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-3 text-center md:text-left">
          <div className="flex flex-col gap-0.5">
            <span className="text-xs sm:text-sm font-bold tracking-wide text-[var(--color-text)] uppercase leading-snug">
              Anil Neerukonda Institute of Technology & Sciences (Autonomous)
            </span>
            <span className="text-[10px] sm:text-xs text-[var(--color-text-muted)]">Structured Preparation And Readiness Kit</span>
          </div>
          <p className="text-xs sm:text-sm text-[var(--color-text-muted)]">© 2026 SPARK. All rights reserved.</p>
        </div>
      </footer>
    </div>
    </>
  );
}
