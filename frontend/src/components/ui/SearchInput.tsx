"use client";

import { useState, useEffect, useRef } from "react";
import { Search, X } from "lucide-react";

/**
 * Controlled search input with built-in debounce.
 *
 * IMPORTANT — two rules every caller must follow:
 *
 * 1. Always pass a controlled `value` prop (string state from the parent).
 *    The component syncs its internal display value when `value` changes
 *    externally (e.g. when the parent resets filters). Without this the
 *    input will appear stale after a "Clear filters" action.
 *
 * 2. Do NOT add a separate debounce (useRef/setTimeout) in the parent.
 *    This component already debounces `onChange` by `debounceMs` (default
 *    300 ms). Adding a second debounce doubles the delay and creates
 *    stale-closure bugs. Just call `setValue` + `setPage(1)` directly
 *    inside the `onChange` handler.
 *
 * @example
 *   const [search, setSearch] = useState("");
 *
 *   <SearchInput
 *     value={search}
 *     onChange={(val) => { setSearch(val); setPage(1); }}
 *     placeholder="Search by name..."
 *   />
 */
interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  debounceMs?: number;
  className?: string;
}

export function SearchInput({
  value,
  onChange,
  placeholder = "Search...",
  debounceMs = 300,
  className = "",
}: SearchInputProps) {
  const [localValue, setLocalValue] = useState(value);
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  // Sync if parent resets value
  useEffect(() => {
    setLocalValue(value);
  }, [value]);

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const val = e.target.value;
    setLocalValue(val);
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => onChange(val), debounceMs);
  }

  function handleClear() {
    setLocalValue("");
    clearTimeout(timerRef.current);
    onChange("");
  }

  return (
    <div className={["relative", className].join(" ")}>
      <Search
        size={14}
        className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-subtle)] pointer-events-none"
      />
      <input
        type="text"
        value={localValue}
        onChange={handleChange}
        placeholder={placeholder}
        className={[
          "h-9 pl-9 pr-8 text-sm rounded-[var(--radius-md)] w-full",
          "border border-[var(--color-border)] bg-white",
          "placeholder:text-[var(--color-text-subtle)]",
          "focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]",
          "hover:border-[var(--color-border-strong)]",
        ].join(" ")}
      />
      {localValue && (
        <button
          onClick={handleClear}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[var(--color-text-subtle)] hover:text-[var(--color-text)]"
          aria-label="Clear search"
        >
          <X size={14} />
        </button>
      )}
    </div>
  );
}
