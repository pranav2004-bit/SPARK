/**
 * @jest-environment jsdom
 *
 * Modal's two opt-in props added this session:
 *  - disableBackdropClose — the question editor modal needed a stray click
 *    outside it to NOT silently discard an in-progress new question.
 *  - headerAction — lets a caller (e.g. the Set-label modal's "Save
 *    changes" button) place an action in the header, before the X, instead
 *    of only in a footer.
 * Both default to off/undefined so Modal's many other call sites are
 * unaffected — covered here by the "default behavior" describe block.
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Modal } from "@/components/ui/Modal";

// The backdrop is the only element carrying this Tailwind class — stable
// enough to select without adding a test-only data-testid to the component.
function getBackdrop(): HTMLElement {
  const el = document.querySelector(".backdrop-blur-sm");
  if (!el) throw new Error("backdrop element not found");
  return el as HTMLElement;
}

describe("Modal — default behavior (no new props)", () => {
  it("clicking the backdrop calls onClose", async () => {
    const onClose = jest.fn();
    const user = userEvent.setup();
    render(
      <Modal isOpen={true} onClose={onClose} title="New Set">
        <p>content</p>
      </Modal>
    );
    await user.click(getBackdrop());
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("renders no extra header button when headerAction is not passed", () => {
    render(
      <Modal isOpen={true} onClose={jest.fn()} title="New Set">
        <p>content</p>
      </Modal>
    );
    // Only the X close button in the header.
    expect(screen.getByRole("button", { name: "Close modal" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
  });
});

describe("Modal — disableBackdropClose", () => {
  it("clicking the backdrop does nothing when true", async () => {
    const onClose = jest.fn();
    const user = userEvent.setup();
    render(
      <Modal isOpen={true} onClose={onClose} title="New Question" disableBackdropClose>
        <p>content</p>
      </Modal>
    );
    await user.click(getBackdrop());
    expect(onClose).not.toHaveBeenCalled();
  });

  it("the X button still calls onClose even when backdrop-close is disabled", async () => {
    const onClose = jest.fn();
    const user = userEvent.setup();
    render(
      <Modal isOpen={true} onClose={onClose} title="New Question" disableBackdropClose>
        <p>content</p>
      </Modal>
    );
    await user.click(screen.getByRole("button", { name: "Close modal" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("Modal — headerAction", () => {
  it("renders the header action before the X close button, and clicking it doesn't close the modal", async () => {
    const onClose = jest.fn();
    const onSave = jest.fn();
    const user = userEvent.setup();
    render(
      <Modal
        isOpen={true} onClose={onClose} title="Edit Set"
        headerAction={<button onClick={onSave}>Save changes</button>}
      >
        <p>content</p>
      </Modal>
    );

    const saveBtn = screen.getByRole("button", { name: "Save changes" });
    const closeBtn = screen.getByRole("button", { name: "Close modal" });
    expect(saveBtn.compareDocumentPosition(closeBtn) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    await user.click(saveBtn);
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
  });
});
