"use client";

import { Users, Building2, ToggleRight, ShieldCheck } from "lucide-react";
import { PortalLoginForm } from "@/components/auth/PortalLoginForm";
import { ADMIN_LOGIN_CONFIG } from "@/lib/constants";

const FEATURES = [
  {
    icon: Users,
    title: "Manage Batches & Students",
    desc: "Create student cohorts and manage batch details with ease.",
  },
  {
    icon: Building2,
    title: "Upload Company Materials",
    desc: "Publish placement resources organised by company and section.",
  },
  {
    icon: ToggleRight,
    title: "Control Publishing",
    desc: "Publish or unpublish content on your schedule — full control.",
  },
];

export default function AdminLoginPage() {
  return (
    <PortalLoginForm
      leftTitle="Admin Portal"
      leftTagline="Manage students, batches and placement materials — all from one dashboard."
      features={FEATURES}
      badgeLabel="Admin Portal"
      badgeIcon={ShieldCheck}
      cardTitle="Sign In"
      cardSubtitle="Sign in to manage batches, students and companies"
      footerHint="For admin access issues, contact your system administrator."
      {...ADMIN_LOGIN_CONFIG}
    />
  );
}
