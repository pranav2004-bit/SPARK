"use client";

import { FileOutput } from "lucide-react";
import { EssayAssignmentPickerList } from "@/components/admin/EssayAssignmentPickerList";

export default function AdminEssayReportsPickerPage() {
  return (
    <EssayAssignmentPickerList
      title="Reports"
      subtitle="Pick an assignment to generate and deliver per-student reports."
      basePath="/admin/essay-writing/reports"
      icon={FileOutput}
      iconBg="#F0F9FF"
      iconColor="#0284C7"
      emptyTitle="No assignments yet"
      emptySubtitle="Create an essay assignment first to see its reports here."
    />
  );
}
