"use client";

import { useEffect, useCallback, createContext, useContext, useState, useMemo } from "react";
import { createPortal } from "react-dom";
import { CheckCircle2, XCircle, X } from "lucide-react";

type ToastType = "success" | "error";

interface Toast {
  id: string;
  type: ToastType;
  message: string;
}

interface ToastContextValue {
  showToast: (type: ToastType, message: string) => void;
  success: (message: string) => void;
  error: (message: string) => void;
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

  const contextValue = useMemo(
    () => ({ showToast, success, error }),
    [showToast, success, error]
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

  const isSuccess = toast.type === "success";

  return (
    <div
      role="alert"
      className={[
        "flex items-start gap-3 p-4 rounded-[var(--radius-md)] shadow-[var(--shadow-lg)]",
        "pointer-events-auto bg-white border",
        isSuccess
          ? "border-[var(--color-success)] text-[var(--color-text)]"
          : "border-[var(--color-danger)] text-[var(--color-text)]",
      ].join(" ")}
    >
      {isSuccess ? (
        <CheckCircle2
          size={16}
          className="text-[var(--color-success)] shrink-0 mt-0.5"
        />
      ) : (
        <XCircle
          size={16}
          className="text-[var(--color-danger)] shrink-0 mt-0.5"
        />
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
