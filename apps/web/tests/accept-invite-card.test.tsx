import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { pushMock, acceptInvitationMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  acceptInvitationMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

vi.mock("@/lib/api/invitations-actions", () => ({
  acceptInvitation: acceptInvitationMock,
}));

afterEach(() => {
  cleanup();
  pushMock.mockClear();
  acceptInvitationMock.mockReset();
});

import { AcceptInviteCard } from "@/components/invitations/accept-invite-card";

const TOKEN = "a".repeat(32);

describe("AcceptInviteCard (dead invitation link fix -- /accept-invite?token=...)", () => {
  it("renders a single primary 'Aceitar convite' button and is honest that the org name is unknown until accepted", () => {
    render(<AcceptInviteCard token={TOKEN} />);
    expect(screen.getByRole("button", { name: /aceitar convite/i })).toBeEnabled();
    expect(screen.getByText(/só é revelado depois que o convite é aceito/i)).toBeInTheDocument();
  });

  it("disables the button and shows an error when opened without a token", () => {
    render(<AcceptInviteCard token={null} />);
    expect(screen.getByRole("button", { name: /aceitar convite/i })).toBeDisabled();
    expect(screen.getByText(/link de convite inválido/i)).toBeInTheDocument();
  });

  it("accepts and redirects to the organization's dashboard on success", async () => {
    acceptInvitationMock.mockResolvedValue({ ok: true, data: { orgSlug: "acme" } });
    render(<AcceptInviteCard token={TOKEN} />);

    fireEvent.click(screen.getByRole("button", { name: /aceitar convite/i }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/acme/dashboard"));
    expect(acceptInvitationMock).toHaveBeenCalledWith(TOKEN);
  });

  it("shows the problem detail on failure (e.g. an expired/already-used token)", async () => {
    acceptInvitationMock.mockResolvedValue({
      ok: false,
      problem: {
        type: "https://hunter.dev/problems/invitation-not-found",
        title: "Not Found",
        status: 404,
        detail: "Convite inválido, expirado ou já usado.",
      },
    });
    render(<AcceptInviteCard token={TOKEN} />);

    fireEvent.click(screen.getByRole("button", { name: /aceitar convite/i }));

    expect(await screen.findByText(/convite inválido, expirado ou já usado/i)).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });
});
