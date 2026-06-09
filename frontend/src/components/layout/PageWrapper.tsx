"use client";

interface PageWrapperProps {
  children: React.ReactNode;
  className?: string;
}

export function PageWrapper({ children, className = "" }: PageWrapperProps) {
  return (
    <main
      className={[
        "flex-1 p-6 max-w-[1400px] w-full mx-auto",
        className,
      ].join(" ")}
    >
      {children}
    </main>
  );
}
