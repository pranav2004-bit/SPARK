"use client";

import { TrendingUp } from "lucide-react";
import { EssayAssignmentPickerList } from "@/components/admin/EssayAssignmentPickerList";

export default function AdminEssayAnalyticsPickerPage() {
  return (
    <EssayAssignmentPickerList
      title="Analytics"
      subtitle="Pick an assignment to see its score distribution and LLM evaluation metrics."
      basePath="/admin/essay-writing/analytics"
      icon={TrendingUp}
      iconBg="#FDF4FF"
      iconColor="#9333EA"
      emptyTitle="No assignments yet"
      emptySubtitle="Create an essay assignment first to see analytics here."
    />
  );
}
