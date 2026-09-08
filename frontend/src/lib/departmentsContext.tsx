"use client";

import { createContext, useContext, useCallback, useRef, useState, useMemo, useEffect } from "react";
import api, { getErrorMessage } from "@/lib/api";
import { listenAdminChannel } from "@/lib/adminChannel";
import type { DepartmentRecord } from "@/types";

interface DepartmentsContextValue {
  /** All departments for the caller's institution — active and inactive.
   * Use this for FILTER dropdowns, so a since-deactivated code still
   * filters historical records correctly. */
  departments: DepartmentRecord[];
  /** Active departments only — use this for CREATE/ASSIGN forms, so a
   * deactivated department can't be freshly assigned to a new record. */
  activeDepartments: DepartmentRecord[];
  loading: boolean;
  error: string;
  refetch: () => Promise<void>;
  /** Internal — triggers the lazy first-load. Called by useDepartments(). */
  _ensureLoaded: () => void;
}

const DepartmentsContext = createContext<DepartmentsContextValue | null>(null);

/**
 * Shared, app-wide department list (2026-08-20, IT's Departments module).
 * The root layout persists across every route including the pre-auth login
 * page, so this deliberately does NOT fetch on mount (that would 401 there).
 * Instead the fetch is triggered lazily by whichever consumer calls
 * useDepartments() first; the result is cached in this Context for the rest
 * of the app session and shared by every later consumer without refetching.
 */
export function DepartmentsProvider({ children }: { children: React.ReactNode }) {
  const [departments, setDepartments] = useState<DepartmentRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const fetchStarted = useRef(false);

  const fetchDepartments = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.get<{ data: DepartmentRecord[] }>("/auth/departments/");
      setDepartments(res.data.data ?? []);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  const _ensureLoaded = useCallback(() => {
    if (fetchStarted.current) return;
    fetchStarted.current = true;
    fetchDepartments();
  }, [fetchDepartments]);

  const refetch = useCallback(async () => {
    fetchStarted.current = true;
    await fetchDepartments();
  }, [fetchDepartments]);

  // Cross-tab: another tab's IT user changed departments — refetch here too.
  // Only if this tab has actually loaded departments before (no point
  // waking up a tab that never needed them).
  useEffect(() => {
    const cleanup = listenAdminChannel((event) => {
      if (event.type === "DEPARTMENTS_UPDATED" && fetchStarted.current) {
        fetchDepartments();
      }
    });
    return cleanup;
  }, [fetchDepartments]);

  const activeDepartments = useMemo(() => departments.filter((d) => d.is_active), [departments]);

  const value = useMemo<DepartmentsContextValue>(
    () => ({ departments, activeDepartments, loading, error, refetch, _ensureLoaded }),
    [departments, activeDepartments, loading, error, refetch, _ensureLoaded]
  );

  return <DepartmentsContext.Provider value={value}>{children}</DepartmentsContext.Provider>;
}

export function useDepartments(): Omit<DepartmentsContextValue, "_ensureLoaded"> {
  const ctx = useContext(DepartmentsContext);
  if (!ctx) throw new Error("useDepartments must be used inside DepartmentsProvider");

  useEffect(() => {
    ctx._ensureLoaded();
  }, [ctx]);

  return ctx;
}
