"use client";

import { forwardRef } from "react";

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
  rightElement?: React.ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, helperText, rightElement, className = "", id, ...props }, ref) => {
    const inputId = id ?? label?.toLowerCase().replace(/\s+/g, "-");

    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label
            htmlFor={inputId}
            className="text-sm font-medium text-[var(--color-text)]"
          >
            {label}
          </label>
        )}
        <div className="relative">
          <input
            ref={ref}
            id={inputId}
            className={[
              "w-full h-9 px-3 text-sm rounded-[var(--radius-md)]",
              "border bg-white text-[var(--color-text)]",
              "placeholder:text-[var(--color-text-subtle)]",
              "focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] focus:ring-offset-0",
              error
                ? "border-[var(--color-danger)] focus:ring-[var(--color-danger)]"
                : "border-[var(--color-border)] hover:border-[var(--color-border-strong)]",
              rightElement ? "pr-10" : "",
              className,
            ]
              .filter(Boolean)
              .join(" ")}
            {...props}
          />
          {rightElement && (
            <div className="absolute right-0 top-0 h-full flex items-center pr-2">
              {rightElement}
            </div>
          )}
        </div>
        {/* Always render error/helper container to prevent layout shift */}
        <p
          className={[
            "text-xs min-h-[16px]",
            error
              ? "text-[var(--color-danger)]"
              : "text-[var(--color-text-muted)]",
          ].join(" ")}
        >
          {error ?? helperText ?? ""}
        </p>
      </div>
    );
  }
);

Input.displayName = "Input";
