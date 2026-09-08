"use client";

import Link from "next/link";
import { Inbox, MessageSquare, ArrowRight, LayoutDashboard, Users, ShieldCheck, Crown, Building2 } from "lucide-react";
import { ITLayout } from "@/components/layout/ITLayout";
import { PageWrapper } from "@/components/layout/PageWrapper";
import { useAuth } from "@/hooks/useAuth";
import type { ITUser } from "@/types";

// Post-login landing page for this role. Add a card here for each new
// module as it's added to NAV_ITEMS in ITLayout.
const MODULES = [
  {
    href: "/it/super-admins",
    icon: Crown,
    title: "Super Admins",
    desc: "Create and manage super admin accounts. They have no access to this roster.",
  },
  {
    href: "/it/admins",
    icon: ShieldCheck,
    title: "Admins",
    desc: "Create and manage faculty admin accounts. Super Admin has read-only access.",
  },
  {
    href: "/it/departments",
    icon: Building2,
    title: "Departments",
    desc: "Manage the department list used across every create/assign form and filter in the app.",
  },
  {
    href: "/it/batch",
    icon: LayoutDashboard,
    title: "Batches",
    desc: "Create and manage student batches. Admin has read-only access.",
  },
  {
    href: "/it/students",
    icon: Users,
    title: "Students",
    desc: "Add, import, and manage student accounts. Admin has read-only access.",
  },
  {
    href: "/it/dlq",
    icon: Inbox,
    title: "Dead Letter Queue",
    desc: "Outbox events that exhausted all delivery retries — manual intervention required.",
  },
  {
    href: "/it/inquiries",
    icon: MessageSquare,
    title: "Inquiries",
    desc: "Student inquiries submitted from the student portal.",
  },
];

export default function ITWelcomePage() {
  const { user } = useAuth();
  const itUser = user?.role === "it" ? (user as ITUser) : null;
  const displayName = itUser?.name || itUser?.email || "there";

  return (
    <ITLayout>
      <PageWrapper>
        <div className="py-12">
          <h1 className="text-2xl font-bold mb-1" style={{ color: "var(--color-text)" }}>
            Welcome, {displayName}
          </h1>
          <p className="text-sm mb-8" style={{ color: "var(--color-text-muted)" }}>
            Pick a module below, or use the nav bar above.
          </p>

          <div className="space-y-3">
            {MODULES.map(({ href, icon: Icon, title, desc }) => (
              <Link
                key={href}
                href={href}
                className="group flex items-center gap-4 bg-white rounded-[var(--radius-xl)] px-5 py-4 transition-all duration-150 hover:shadow-[var(--shadow-md)]"
                style={{ border: "1px solid var(--color-border)" }}
              >
                <div
                  className="w-10 h-10 rounded-full flex items-center justify-center shrink-0"
                  style={{ background: "var(--color-primary-light)" }}
                >
                  <Icon size={18} style={{ color: "var(--color-primary)" }} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold" style={{ color: "var(--color-text)" }}>{title}</p>
                  <p className="text-xs mt-0.5" style={{ color: "var(--color-text-muted)" }}>{desc}</p>
                </div>
                <ArrowRight
                  size={16}
                  className="shrink-0 transition-transform duration-150 group-hover:translate-x-0.5"
                  style={{ color: "var(--color-text-subtle)" }}
                />
              </Link>
            ))}
          </div>
        </div>
      </PageWrapper>
    </ITLayout>
  );
}
