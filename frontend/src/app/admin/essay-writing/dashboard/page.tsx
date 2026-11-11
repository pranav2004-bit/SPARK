"use client";

import { LayoutDashboard } from "lucide-react";
import { EssayAssignmentPickerList } from "@/components/admin/EssayAssignmentPickerList";

export default function AdminEssayDashboardPickerPage() {
  return (
    <EssayAssignmentPickerList
      title="Dashboard"
      subtitle="Pick an assignment to watch its live evaluation status."
      basePath="/admin/essay-writing/dashboard"
      icon={LayoutDashboard}
      iconBg="#FFF4E6"
      iconColor="#E8820C"
      emptyTitle="No assignments yet"
      emptySubtitle="Create an essay assignment first to see its dashboard here."
    />
  );
}
