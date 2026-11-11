"use client";

import { BarChart3 } from "lucide-react";
import { EssayAssignmentPickerList } from "@/components/admin/EssayAssignmentPickerList";

// Refactored in Phase 9 to use the shared picker once Analytics became a
// second real consumer of this exact shape — see
// EssayAssignmentPickerList's own docstring for the full reasoning.
export default function AdminEssayResultsPickerPage() {
  return (
    <EssayAssignmentPickerList
      title="Results"
      subtitle="Pick an assignment to see per-student scores and LLM feedback."
      basePath="/admin/essay-writing/results"
      icon={BarChart3}
      iconBg="#F0FDF4"
      iconColor="#16A34A"
      emptyTitle="No assignments yet"
      emptySubtitle="Create an essay assignment first to see results here."
    />
  );
}
