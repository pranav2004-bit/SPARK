import { GlobalLoader } from "@/components/ui/GlobalLoader";

/**
 * Next.js App Router root loading boundary.
 * Automatically shown during any top-level route navigation until the
 * incoming page's data fetching resolves.
 */
export default function Loading() {
  return <GlobalLoader />;
}
