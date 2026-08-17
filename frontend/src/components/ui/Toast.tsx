"use client";

import { useEffect, useCallback, createContext, useContext, useState, useMemo } from "react";
import { createPortal } from "react-dom";
import { CheckCircle2, XCircle, AlertTriangle, X } from "lucide-react";

type ToastType = "success" | "error" | "warning";

interface Toast {
  id: string;
  type: ToastType;
  message: string;
}

interface ToastContextValue {
  showToast: (type: ToastType, message: string) => void;
  success: (message: string) => void;
  error: (message: string) => void;
  /** Amber, non-fatal — a graduated caution (e.g. "2 of 5 warnings used")
   * that isn't a failure but shouldn't read as a green success either. */
  warning: (message: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback((type: ToastType, message: string) => {
    const id = crypto.randomUUID();
    setToasts((prev) => [...prev, { id, type, message }]);
    setTimeout(() => removeToast(id), 4000);
  }, [removeToast]);

  const success = useCallback(
    (message: string) => showToast("success", message),
    [showToast]
  );
  const error = useCallback(
    (message: string) => showToast("error", message),
    [showToast]
  );
  const warning = useCallback(
    (message: string) => showToast("warning", message),
    [showToast]
  );

  const contextValue = useMemo(
    () => ({ showToast, success, error, warning }),
    [showToast, success, error, warning]
  );

  return (
    <ToastContext.Provider value={contextValue}>
      {children}
      {mounted &&
        createPortal(
          <div
            aria-live="polite"
            className="fixed top-5 right-5 z-[100] flex flex-col gap-2 max-w-sm w-full pointer-events-none"
          >
            {toasts.map((toast) => (
              <ToastItem
                key={toast.id}
                toast={toast}
                onClose={() => removeToast(toast.id)}
              />
            ))}
          </div>,
          document.body
        )}
    </ToastContext.Provider>
  );
}

function ToastItem({
  toast,
  onClose,
}: {
  toast: Toast;
  onClose: () => void;
}) {
  useEffect(() => {
    // Accessible: auto-dismiss after 4s, but keep visible 300ms for animation
  }, []);

  const borderColor = {
    success: "border-[var(--color-success)]",
    error: "border-[var(--color-danger)]",
    warning: "border-[#E8820C]",
  }[toast.type];

  return (
    <div
      role="alert"
      className={[
        "flex items-start gap-3 p-4 rounded-[var(--radius-md)] shadow-[var(--shadow-lg)]",
        "pointer-events-auto bg-white border text-[var(--color-text)]",
        borderColor,
      ].join(" ")}
    >
      {toast.type === "success" ? (
        <CheckCircle2 size={16} className="text-[var(--color-success)] shrink-0 mt-0.5" />
      ) : toast.type === "warning" ? (
        <AlertTriangle size={16} className="text-[#E8820C] shrink-0 mt-0.5" />
      ) : (
        <XCircle size={16} className="text-[var(--color-danger)] shrink-0 mt-0.5" />
      )}
      <p className="text-sm flex-1 leading-relaxed">{toast.message}</p>
      <button
        onClick={onClose}
        className="text-[var(--color-text-muted)] hover:text-[var(--color-text)] shrink-0"
        aria-label="Dismiss notification"
      >
        <X size={14} />
      </button>
    </div>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx;
}
