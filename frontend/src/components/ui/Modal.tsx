"use client";

import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  maxWidth?: "sm" | "md" | "lg";
  /** Opt-in — when true, clicking the backdrop does nothing (only the X
   * button / Escape can close). Off by default: most of this component's
   * many call sites are fine losing an accidental-click's worth of state,
   * but a form with real in-progress, not-yet-saved data (e.g. the
   * question editor) shouldn't let a stray click outside it silently
   * discard everything typed. Escape and the X button are deliberately
   * NOT covered by this — they still call onClose normally, so a caller
   * that wants a "you have unsaved changes" confirmation on those too
   * implements that inside its own onClose, not here. */
  disableBackdropClose?: boolean;
  /** Opt-in — rendered in the header between the title and the X button,
   * e.g. a "Save changes" action a caller wants reachable from the top of
   * the modal instead of (or in addition to) a footer button. */
  headerAction?: React.ReactNode;
}

const maxWidthClass = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-lg",
};

export function Modal({
  isOpen,
  onClose,
  title,
  children,
  maxWidth = "md",
  disableBackdropClose = false,
  headerAction,
}: ModalProps) {
  const overlayRef    = useRef<HTMLDivElement>(null);
  const firstFocusRef = useRef<HTMLButtonElement>(null);
  // Keep a stable ref to onClose so the effect below never needs it as a dep.
  // This prevents the effect from re-running (and stealing focus) on every
  // keystroke when the parent re-renders and produces a new closeModal reference.
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);

  // Only re-run when isOpen changes — not when onClose changes.
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCloseRef.current();
    };

    document.addEventListener("keydown", handleKeyDown);
    document.body.style.overflow = "hidden";
    // Focus the close button only on initial open, not on every render —
    // but only as a fallback. If something inside the modal already
    // grabbed focus (e.g. an <Input autoFocus> like ConfirmDialog's
    // type-to-confirm field), don't steal it away 50ms later; that
    // silently yanked keyboard focus out from under anyone who started
    // typing right as the modal opened.
    setTimeout(() => {
      if (overlayRef.current?.contains(document.activeElement)) return;
      firstFocusRef.current?.focus();
    }, 50);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "";
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  if (!isOpen) return null;

  const content = (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={disableBackdropClose ? undefined : onClose}
        aria-hidden="true"
      />

      {/* Panel */}
      <div
        className={[
          "relative w-full bg-white rounded-[var(--radius-lg)] shadow-[var(--shadow-xl)]",
          "flex flex-col max-h-[90vh]",
          maxWidthClass[maxWidth],
        ].join(" ")}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b border-[var(--color-border)] shrink-0">
          <h2
            id="modal-title"
            className="text-base font-semibold text-[var(--color-text)]"
          >
            {title}
          </h2>
          <div className="flex items-center gap-2 shrink-0">
            {headerAction}
            <button
              ref={firstFocusRef}
              onClick={onClose}
              className="p-1 rounded-[var(--radius-sm)] text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-hover)] transition-colors"
              aria-label="Close modal"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="px-6 py-5 overflow-y-auto">{children}</div>
      </div>
    </div>
  );

  return createPortal(content, document.body);
}
