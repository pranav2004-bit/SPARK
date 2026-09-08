"use client";

interface PageWrapperProps {
  children: React.ReactNode;
  className?: string;
}

export function PageWrapper({ children, className = "" }: PageWrapperProps) {
  // The default max-w-[1400px] only applies when the caller doesn't supply
  // its own max-w-* (added 2026-08-27) — previously both were always
  // concatenated into one class string, and which one actually won was
  // decided by Tailwind's internal stylesheet order, not by which appeared
  // later in the string. That silently broke every page passing a
  // narrower max-w (e.g. "max-w-3xl") whenever the default's arbitrary
  // value happened to be compiled after it, rendering far wider than the
  // page intended with no visual indication anything was wrong.
  const hasCustomMaxWidth = /(^|\s)max-w-/.test(className);
  return (
    <main
      className={[
        "flex-1 p-6 w-full mx-auto",
        hasCustomMaxWidth ? "" : "max-w-[1400px]",
        className,
      ].filter(Boolean).join(" ")}
    >
      {children}
    </main>
  );
}
