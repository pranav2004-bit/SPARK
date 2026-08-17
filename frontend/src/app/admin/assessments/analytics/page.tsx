"use client";

import { TrendingUp } from "lucide-react";
import { AssignmentPickerList } from "@/components/admin/AssignmentPickerList";

export default function AdminAssessmentAnalyticsListPage() {
  return (
    <AssignmentPickerList
      title="Analytics"
      subtitle="Pick an assignment to see score distribution, pass/fail rate, and question difficulty."
      basePath="/admin/assessments/analytics"
      icon={TrendingUp}
      emptyTitle="No assignments yet"
      emptySubtitle="Assign a question paper to a batch from the paper's own page to see it here."
    />
  );
}
