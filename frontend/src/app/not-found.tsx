"use client";

import { useRouter } from "next/navigation";
import { SearchX } from "lucide-react";
import { ErrorScreen } from "@/components/ui/ErrorScreen";

// Next.js App Router convention — automatically rendered for any route that
// doesn't match a real page, anywhere in the app. Before this file existed,
// that case fell through to Next's own bare default ("404 / This page
// could not be found", no branding at all).
export default function NotFound() {
  const router = useRouter();
  return (
    <ErrorScreen
      icon={SearchX}
      title="Page not found"
      message="The page you're looking for doesn't exist or may have moved."
      primaryLabel="Go to Homepage"
      onPrimary={() => router.push("/")}
    />
  );
}
