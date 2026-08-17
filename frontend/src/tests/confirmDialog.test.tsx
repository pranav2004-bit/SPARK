/**
 * @jest-environment jsdom
 *
 * ConfirmDialog's opt-in "type to confirm" guard (requireTypedConfirmation)
 * — added for the papers-list delete-paper flow, which now requires typing
 * "delete" before the Delete button enables. Off by default: this prop
 * must never change behavior for ConfirmDialog's other 16 call sites
 * (submit exam, remove a batch, etc.) that don't pass it.
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

describe("ConfirmDialog — default behavior (no requireTypedConfirmation)", () => {
  it("confirm button is enabled immediately and calls onConfirm on click", async () => {
    const onConfirm = jest.fn();
    const user = userEvent.setup();
    render(
      <ConfirmDialog
        isOpen={true} onClose={jest.fn()} onConfirm={onConfirm}
        title="Submit exam?" message="Are you sure?" confirmLabel="Submit"
      />
    );
    const confirmBtn = screen.getByRole("button", { name: "Submit" });
    expect(confirmBtn).not.toBeDisabled();
    await user.click(confirmBtn);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});

describe("ConfirmDialog — requireTypedConfirmation", () => {
  it("confirm button starts disabled", () => {
    render(
      <ConfirmDialog
        isOpen={true} onClose={jest.fn()} onConfirm={jest.fn()}
        title="Delete question paper?" message="This cannot be undone."
        confirmLabel="Delete" requireTypedConfirmation="delete"
      />
    );
    expect(screen.getByRole("button", { name: "Delete" })).toBeDisabled();
  });

  it("stays disabled while the typed text doesn't match", async () => {
    const user = userEvent.setup();
    render(
      <ConfirmDialog
        isOpen={true} onClose={jest.fn()} onConfirm={jest.fn()}
        title="Delete question paper?" message="This cannot be undone."
        confirmLabel="Delete" requireTypedConfirmation="delete"
      />
    );
    await user.type(screen.getByLabelText('Type "delete" to confirm'), "delet");
    expect(screen.getByRole("button", { name: "Delete" })).toBeDisabled();
  });

  it("enables once the exact word is typed, case-insensitively", async () => {
    const onConfirm = jest.fn();
    const user = userEvent.setup();
    render(
      <ConfirmDialog
        isOpen={true} onClose={jest.fn()} onConfirm={onConfirm}
        title="Delete question paper?" message="This cannot be undone."
        confirmLabel="Delete" requireTypedConfirmation="delete"
      />
    );
    await user.type(screen.getByLabelText('Type "delete" to confirm'), "DELETE");
    const confirmBtn = screen.getByRole("button", { name: "Delete" });
    expect(confirmBtn).not.toBeDisabled();
    await user.click(confirmBtn);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("resets the typed text each time the dialog re-opens", async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <ConfirmDialog
        isOpen={true} onClose={jest.fn()} onConfirm={jest.fn()}
        title="Delete question paper?" message="This cannot be undone."
        confirmLabel="Delete" requireTypedConfirmation="delete"
      />
    );
    await user.type(screen.getByLabelText('Type "delete" to confirm'), "delete");
    expect(screen.getByRole("button", { name: "Delete" })).not.toBeDisabled();

    // Close, then re-open for a different item — must not carry over the
    // previous confirmation.
    rerender(
      <ConfirmDialog
        isOpen={false} onClose={jest.fn()} onConfirm={jest.fn()}
        title="Delete question paper?" message="This cannot be undone."
        confirmLabel="Delete" requireTypedConfirmation="delete"
      />
    );
    rerender(
      <ConfirmDialog
        isOpen={true} onClose={jest.fn()} onConfirm={jest.fn()}
        title="Delete question paper?" message="This cannot be undone."
        confirmLabel="Delete" requireTypedConfirmation="delete"
      />
    );
    expect(screen.getByRole("button", { name: "Delete" })).toBeDisabled();
    expect(screen.getByLabelText('Type "delete" to confirm')).toHaveValue("");
  });
});

// confirmDisabled — added for the question editor's exit-confirm, whose
// "Create Question"/"Save Question" option shouldn't enable just because
// the admin tried to leave while the underlying form is still invalid.
describe("ConfirmDialog — confirmDisabled", () => {
  it("disables the confirm button when confirmDisabled is true, even with no typed-confirmation requirement", () => {
    render(
      <ConfirmDialog
        isOpen={true} onClose={jest.fn()} onConfirm={jest.fn()}
        title="Unsaved changes" message="Leaving now will discard your changes."
        confirmLabel="Create Question" confirmDisabled={true}
      />
    );
    expect(screen.getByRole("button", { name: "Create Question" })).toBeDisabled();
  });

  it("stays enabled when confirmDisabled is false (the default)", () => {
    render(
      <ConfirmDialog
        isOpen={true} onClose={jest.fn()} onConfirm={jest.fn()}
        title="Unsaved changes" message="Leaving now will discard your changes."
        confirmLabel="Create Question" confirmDisabled={false}
      />
    );
    expect(screen.getByRole("button", { name: "Create Question" })).not.toBeDisabled();
  });
});

// secondaryActionLabel/onSecondaryAction — the "Discard" option on the
// question editor's exit-confirm, letting an admin actually leave without
// saving instead of only choosing between "keep editing" and "save".
describe("ConfirmDialog — secondaryActionLabel / onSecondaryAction", () => {
  it("does not render a third button when neither prop is passed", () => {
    render(
      <ConfirmDialog
        isOpen={true} onClose={jest.fn()} onConfirm={jest.fn()}
        title="Delete question paper?" message="This cannot be undone." confirmLabel="Delete"
      />
    );
    expect(screen.queryByRole("button", { name: "Discard" })).not.toBeInTheDocument();
  });

  it("renders the secondary action and calls its handler on click, independent of onConfirm/onClose", async () => {
    const onConfirm = jest.fn();
    const onClose = jest.fn();
    const onSecondaryAction = jest.fn();
    const user = userEvent.setup();
    render(
      <ConfirmDialog
        isOpen={true} onClose={onClose} onConfirm={onConfirm}
        title="Unsaved question" message="Leaving now will discard everything you've typed."
        confirmLabel="Create Question" confirmDisabled={true}
        secondaryActionLabel="Discard" onSecondaryAction={onSecondaryAction}
      />
    );
    const discardBtn = screen.getByRole("button", { name: "Discard" });
    await user.click(discardBtn);
    expect(onSecondaryAction).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("the secondary action stays clickable even while confirmDisabled is true", () => {
    render(
      <ConfirmDialog
        isOpen={true} onClose={jest.fn()} onConfirm={jest.fn()}
        title="Unsaved question" message="Leaving now will discard everything you've typed."
        confirmLabel="Create Question" confirmDisabled={true}
        secondaryActionLabel="Discard" onSecondaryAction={jest.fn()}
      />
    );
    expect(screen.getByRole("button", { name: "Create Question" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Discard" })).not.toBeDisabled();
  });
});
