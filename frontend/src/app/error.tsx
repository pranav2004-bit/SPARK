"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle } from "lucide-react";
import { ErrorScreen } from "@/components/ui/ErrorScreen";

// Next.js App Router convention — the nearest error boundary above
// wherever an unhandled exception is thrown while rendering. Placed at the
// app root, so it catches a crash from ANY page/layout below the root
// layout, while the root layout itself (and its providers) keeps running —
// only global-error.tsx (a separate, fully self-contained file) covers the
// root layout crashing too. Before this file existed, any such crash fell
// through to Next's own bare default error page in production.
//
// Deliberately never shows `error.message`/`error.stack` to the user —
// same reasoning as getErrorMessage() (frontend/src/lib/api.ts) elsewhere
// in this app: a raw exception message can leak internal details, and
// isn't actionable for a student/admin anyway. Logged to the console only,
// so it's still visible while developing/debugging.
export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const router = useRouter();

  useEffect(() => {
    if (process.env.NODE_ENV === "development") {
      console.error("[error.tsx] Unhandled render error:", error);
    }
  }, [error]);

  return (
    <ErrorScreen
      icon={AlertTriangle}
      title="Something went wrong"
      message="An unexpected error occurred. You can try again, or head back to the homepage."
      primaryLabel="Try Again"
      onPrimary={reset}
      secondaryLabel="Go to Homepage"
      onSecondary={() => router.push("/")}
    />
  );
}
