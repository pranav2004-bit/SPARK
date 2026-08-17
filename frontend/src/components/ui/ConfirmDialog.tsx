"use client";

import { useEffect, useState } from "react";
import { Modal } from "./Modal";
import { Button } from "./Button";
import { Input } from "./Input";

interface ConfirmDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  message: string;
  confirmLabel?: string;
  confirmVariant?: "danger" | "primary" | "warning";
  loading?: boolean;
  /** Opt-in — when set, the confirm button stays disabled until the user
   * types this exact word (case-insensitive), e.g. "delete". Off by
   * default: most of this dialog's 17 call sites (submit exam, remove a
   * batch, etc.) are either not destructive or already behind their own
   * safeguards, and shouldn't gain a typing requirement just because this
   * component gained the capability. */
  requireTypedConfirmation?: string;
  /** Opt-in — an extra caller-computed condition that must be true for the
   * confirm button to enable, on top of requireTypedConfirmation (if any).
   * For a caller whose "confirm" action needs the same validation as a
   * main form's own submit button (e.g. the question editor's exit-confirm
   * offering "Create Question" — it shouldn't succeed with a still-invalid
   * form just because the admin tried to leave). Defaults to true (no
   * extra restriction) for every other call site. */
  confirmDisabled?: boolean;
  /** Opt-in — renders a third button between Cancel and Confirm for a
   * distinct third outcome (neither "stay" nor "confirm"). Built for the
   * question editor's exit-confirm: closing with an unsaved new question
   * only offered "Cancel" (keep editing) or "Create Question" (forced
   * save) — an admin who typed details but decided not to save them had
   * no way to just leave, since Cancel re-opens the form instead of
   * actually closing it. Off by default for every other call site. */
  secondaryActionLabel?: string;
  onSecondaryAction?: () => void;
}

export function ConfirmDialog({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel = "Confirm",
  confirmVariant = "danger",
  loading = false,
  requireTypedConfirmation,
  confirmDisabled = false,
  secondaryActionLabel,
  onSecondaryAction,
}: ConfirmDialogProps) {
  const [typedValue, setTypedValue] = useState("");

  // Reset on every open (not just once) — otherwise a previous "delete"
  // typed for one item would silently pre-satisfy the check for a
  // different item this same dialog instance later opens for.
  useEffect(() => {
    if (isOpen) setTypedValue("");
  }, [isOpen]);

  const confirmationSatisfied =
    !confirmDisabled &&
    (!requireTypedConfirmation ||
      typedValue.trim().toLowerCase() === requireTypedConfirmation.trim().toLowerCase());

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} maxWidth="sm">
      <p className="text-sm text-[var(--color-text-muted)] leading-relaxed">
        {message}
      </p>
      {requireTypedConfirmation && (
        <div className="mt-4">
          <Input
            label={`Type "${requireTypedConfirmation}" to confirm`}
            value={typedValue}
            onChange={e => setTypedValue(e.target.value)}
            placeholder={requireTypedConfirmation}
            autoFocus
          />
        </div>
      )}
      <div className="flex items-center justify-end gap-3 mt-6">
        <Button variant="secondary" onClick={onClose} disabled={loading}>
          Cancel
        </Button>
        {secondaryActionLabel && onSecondaryAction && (
          <Button variant="secondary" onClick={onSecondaryAction} disabled={loading}>
            {secondaryActionLabel}
          </Button>
        )}
        <Button
          variant={confirmVariant}
          onClick={onConfirm}
          loading={loading}
          disabled={!confirmationSatisfied}
        >
          {confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}
