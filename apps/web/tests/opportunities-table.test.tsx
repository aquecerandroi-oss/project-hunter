import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const routerPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPush }),
}));
vi.mock("@/lib/api/opportunities-actions", () => ({ loadOpportunitiesAction: vi.fn() }));

afterEach(() => {
  cleanup();
  routerPush.mockClear();
});

import { OpportunitiesTable } from "@/components/opportunities/opportunities-table";
import { makeOpportunitySummary } from "@/tests/fixtures/radar";

const baseParams = { org_id: "org-1", limit: 200 };

describe("OpportunitiesTable: the compact index shares chips with /radar", () => {
  it("shows symbol, score and status/stage chips", () => {
    render(<OpportunitiesTable orgSlug="acme" initialItems={[makeOpportunitySummary()]} initialCursor={null} hasFilters={false} baseParams={baseParams} />);
    expect(screen.getByText("BTCUSDT")).toBeInTheDocument();
    expect(screen.getByText("WATCHING")).toBeInTheDocument();
  });

  it("links each row straight to /opportunities/[id]", () => {
    render(<OpportunitiesTable orgSlug="acme" initialItems={[makeOpportunitySummary()]} initialCursor={null} hasFilters={false} baseParams={baseParams} />);
    expect(screen.getByRole("link", { name: "BTCUSDT" })).toHaveAttribute("href", "/acme/opportunities/11111111-1111-1111-1111-111111111111");
  });

  it("says no episode scored yet when empty and unfiltered, points to the full /radar", () => {
    render(<OpportunitiesTable orgSlug="acme" initialItems={[]} initialCursor={null} hasFilters={false} baseParams={baseParams} />);
    expect(screen.getByText(/Nenhuma oportunidade pontuada ainda/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "/radar" })).toHaveAttribute("href", "/acme/radar");
  });

  it("says nothing matched the filters when filtered and empty", () => {
    render(<OpportunitiesTable orgSlug="acme" initialItems={[]} initialCursor={null} hasFilters baseParams={baseParams} />);
    expect(screen.getByText(/Nenhuma oportunidade encontrada para estes filtros/)).toBeInTheDocument();
  });
});
