import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }),
}));

vi.mock("@/lib/api/members-actions", () => ({
  updateMemberRole: vi.fn(),
  removeMember: vi.fn(),
}));

afterEach(cleanup);

import { MembersTable } from "@/components/settings/members-table";
import type { MemberOut } from "@/lib/api/types";

const members: MemberOut[] = [
  {
    user_id: "u1",
    email: "owner@acme.com",
    display_name: "Owner Person",
    avatar_url: null,
    role: "OWNER",
    status: "active",
    joined_at: "2026-01-01T00:00:00Z",
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    user_id: "u2",
    email: "viewer@acme.com",
    display_name: "Viewer Person",
    avatar_url: null,
    role: "VIEWER",
    status: "active",
    joined_at: "2026-01-02T00:00:00Z",
    created_at: "2026-01-02T00:00:00Z",
  },
];

describe("MembersTable role gating (apps/api/hunter_api/routers/members.py is OWNER-only)", () => {
  it("hides the role select and remove button for a VIEWER", () => {
    render(<MembersTable orgId="org-1" members={members} currentRole="VIEWER" />);
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /remover/i })).not.toBeInTheDocument();
    // The role still renders, just as plain text.
    expect(screen.getAllByText("OWNER").length).toBeGreaterThan(0);
  });

  it("hides management controls for ADMIN too (the API keeps both mutations OWNER-only)", () => {
    render(<MembersTable orgId="org-1" members={members} currentRole="ADMIN" />);
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /remover/i })).not.toBeInTheDocument();
  });

  it("shows the role select and remove button for an OWNER", () => {
    render(<MembersTable orgId="org-1" members={members} currentRole="OWNER" />);
    expect(screen.getAllByRole("combobox")).toHaveLength(members.length);
    expect(screen.getAllByRole("button", { name: /remover/i })).toHaveLength(members.length);
  });

  it("opens a confirm dialog before removing (never removes on a single click)", () => {
    render(<MembersTable orgId="org-1" members={members} currentRole="OWNER" />);
    const [removeButton] = screen.getAllByRole("button", { name: /remover/i });
    fireEvent.click(removeButton as HTMLElement);
    expect(screen.getByText(/perderá acesso a esta organização/i)).toBeInTheDocument();
  });
});
