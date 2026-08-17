"use client";

import { BarChart3 } from "lucide-react";
import { AssignmentPickerList } from "@/components/admin/AssignmentPickerList";

export default function AdminAssessmentResultsListPage() {
  return (
    <AssignmentPickerList
      title="Results"
      subtitle="Pick an assignment to review submitted responses and activity logs."
      basePath="/admin/assessments/results"
      icon={BarChart3}
      emptyTitle="No assignments yet"
      emptySubtitle="Assign a question paper to a batch from the paper's own page to see it here."
    />
  );
}
