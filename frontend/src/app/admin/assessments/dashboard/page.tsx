"use client";

import { LayoutDashboard } from "lucide-react";
import { AssignmentPickerList } from "@/components/admin/AssignmentPickerList";

export default function AdminAssessmentDashboardListPage() {
  return (
    <AssignmentPickerList
      title="Dashboard"
      subtitle="Pick an assignment to see its live KPI rollup."
      basePath="/admin/assessments/dashboard"
      icon={LayoutDashboard}
      emptyTitle="No assignments yet"
      emptySubtitle="Assign a question paper to a batch from the paper's own page to see it here."
    />
  );
}
