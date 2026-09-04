import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(cleanup);

import { InvitationCreatedBox } from "@/components/settings/invitation-created";

const LINK = "https://app.hunter.dev/accept-invite?token=abc123";

describe("InvitationCreatedBox (apps/api/hunter_api/schemas/invitations.py: token shown once, never recoverable)", () => {
  it("shows the link and an explicit 'cannot be recovered' warning", () => {
    render(<InvitationCreatedBox link={LINK} email="someone@example.com" />);
    expect(screen.getByText(LINK)).toBeInTheDocument();
    expect(screen.getByText(/não pode ser recuperado/i)).toBeInTheDocument();
    expect(screen.getByText(/someone@example.com/)).toBeInTheDocument();
  });

  it("has a copy button that writes the link to the clipboard", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    render(<InvitationCreatedBox link={LINK} email="someone@example.com" />);
    fireEvent.click(screen.getByRole("button", { name: /copiar/i }));

    expect(writeText).toHaveBeenCalledWith(LINK);
    expect(await screen.findByRole("button", { name: /copiado/i })).toBeInTheDocument();
  });
});
