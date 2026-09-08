"use client";

import { ServerCog, KeyRound, ShieldCheck } from "lucide-react";
import { PortalLoginForm } from "@/components/auth/PortalLoginForm";
import { IT_LOGIN_CONFIG } from "@/lib/constants";

const FEATURES = [
  {
    icon: ServerCog,
    title: "Platform Operations",
    desc: "Modules and interfaces for this role are configured by the platform team.",
  },
  {
    icon: KeyRound,
    title: "Provisioned Access",
    desc: "IT accounts are created by a Super Admin — there is no public sign-up.",
  },
];

export default function ITLoginPage() {
  return (
    <PortalLoginForm
      leftTitle="IT Portal"
      leftTagline="Platform operations and technical administration."
      features={FEATURES}
      badgeLabel="IT Portal"
      badgeIcon={ShieldCheck}
      cardTitle="Sign In"
      cardSubtitle="Sign in with your IT account"
      footerHint="For access issues, contact your Super Admin."
      {...IT_LOGIN_CONFIG}
    />
  );
}
