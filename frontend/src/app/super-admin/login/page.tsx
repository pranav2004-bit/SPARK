"use client";

import { BarChart2, Users, Shield, Activity } from "lucide-react";
import { PortalLoginForm } from "@/components/auth/PortalLoginForm";
import { SUPER_ADMIN_LOGIN_CONFIG } from "@/lib/constants";

const FEATURES = [
  {
    icon: Users,
    title: "Manage All Admins",
    desc: "Create, deactivate, and reset passwords for institution admins.",
  },
  {
    icon: BarChart2,
    title: "Platform-wide Analytics",
    desc: "Engagement, performance, and utilisation across all departments.",
  },
  {
    icon: Activity,
    title: "Full Visibility",
    desc: "Read-only access to all batches, students, and resources.",
  },
];

export default function SuperAdminLoginPage() {
  return (
    <PortalLoginForm
      leftTitle="Super Admin Portal"
      leftTagline="Platform-wide oversight — manage admins, monitor engagement, and drive outcomes."
      features={FEATURES}
      badgeLabel="Super Admin"
      badgeIcon={Shield}
      cardTitle="Sign In"
      cardSubtitle="Sign in to manage your institution platform"
      footerHint="For super admin access, contact your platform administrator."
      {...SUPER_ADMIN_LOGIN_CONFIG}
    />
  );
}
