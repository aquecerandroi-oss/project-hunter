import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const listAnomaliesMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/anomalies", () => ({ listAnomalies: listAnomaliesMock }));
const listRadarMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/radar", () => ({ listRadar: listRadarMock }));
const getCurrentRegimeMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/regime", () => ({ getCurrentRegime: getCurrentRegimeMock }));

afterEach(() => {
  cleanup();
  listAnomaliesMock.mockReset();
  listRadarMock.mockReset();
  getCurrentRegimeMock.mockReset();
});

import { AnomaliesTile, loadAnomaliesTile } from "@/components/dashboard/anomalies-tile";
import { HotOpportunitiesTile, loadHotOpportunitiesTile } from "@/components/dashboard/hot-opportunities-tile";
import { RegimeTile, loadRegimeTile } from "@/components/dashboard/regime-tile";
import { makeRegime } from "@/tests/fixtures/radar";

describe("AnomaliesTile: 'sem verificação' (failed check) is never the same state as a verified zero", () => {
  it("shows 'sem verificação' when the read itself fails", async () => {
    listAnomaliesMock.mockRejectedValue(new Error("down"));
    const result = await loadAnomaliesTile();
    render(<AnomaliesTile result={result} />);
    expect(screen.getByText("sem verificação")).toBeInTheDocument();
  });

  it("shows a real, verified '0' with its as_of when the scanner has produced nothing yet", async () => {
    listAnomaliesMock.mockResolvedValue({ items: [], next_cursor: null, as_of: "2026-09-06T08:00:00Z", window_start: "2026-08-07T08:00:00Z" });
    const result = await loadAnomaliesTile();
    render(<AnomaliesTile result={result} />);
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.queryByText("sem verificação")).not.toBeInTheDocument();
  });

  it("shows the real count, never a locally-invented number", async () => {
    listAnomaliesMock.mockResolvedValue({
      items: [{ id: "a1" }, { id: "a2" }],
      next_cursor: null,
      as_of: "2026-09-06T08:00:00Z",
      window_start: "2026-08-07T08:00:00Z",
    });
    const result = await loadAnomaliesTile();
    render(<AnomaliesTile result={result} />);
    expect(screen.getByText("2")).toBeInTheDocument();
  });
});

describe("HotOpportunitiesTile", () => {
  it("shows 'sem verificação' when /radar fails", async () => {
    listRadarMock.mockRejectedValue(new Error("down"));
    const result = await loadHotOpportunitiesTile();
    render(<HotOpportunitiesTile orgSlug="acme" result={result} />);
    expect(screen.getByText("sem verificação")).toBeInTheDocument();
  });

  it("shows a '+' suffix when the page was truncated, never claiming a complete count", async () => {
    listRadarMock.mockResolvedValue({ items: [{ opportunity_id: "1" }], next_cursor: "more", as_of: "2026-09-06T08:00:00Z", org_scoped: true });
    const result = await loadHotOpportunitiesTile();
    render(<HotOpportunitiesTile orgSlug="acme" result={result} />);
    expect(screen.getByText("1+")).toBeInTheDocument();
  });

  it("links to /radar filtered by status=HOT", async () => {
    listRadarMock.mockResolvedValue({ items: [], next_cursor: null, as_of: "2026-09-06T08:00:00Z", org_scoped: true });
    const result = await loadHotOpportunitiesTile();
    render(<HotOpportunitiesTile orgSlug="acme" result={result} />);
    expect(screen.getByRole("link", { name: "Ver no radar" })).toHaveAttribute("href", "/acme/radar?status=HOT");
  });
});

describe("RegimeTile: UNKNOWN and stale are honest, never hidden", () => {
  it("shows 'sem verificação' when /regime fails", async () => {
    getCurrentRegimeMock.mockRejectedValue(new Error("down"));
    const result = await loadRegimeTile();
    render(<RegimeTile result={result} />);
    expect(screen.getByText("sem verificação")).toBeInTheDocument();
  });

  it("shows the stale badge when the classifier is not confirmed alive", async () => {
    getCurrentRegimeMock.mockResolvedValue({ items: [makeRegime({ is_stale: true })], as_of: "2026-09-06T08:00:00Z" });
    const result = await loadRegimeTile();
    render(<RegimeTile result={result} />);
    expect(screen.getByText("stale")).toBeInTheDocument();
  });

  it("shows UNKNOWN as a real classification, not hidden or replaced", async () => {
    getCurrentRegimeMock.mockResolvedValue({ items: [makeRegime({ regime: "UNKNOWN" })], as_of: "2026-09-06T08:00:00Z" });
    const result = await loadRegimeTile();
    render(<RegimeTile result={result} />);
    expect(screen.getByText("UNKNOWN")).toBeInTheDocument();
  });

  it("shows a verified '0 regimes classificados', distinct from 'sem verificação'", async () => {
    getCurrentRegimeMock.mockResolvedValue({ items: [], as_of: "2026-09-06T08:00:00Z" });
    const result = await loadRegimeTile();
    render(<RegimeTile result={result} />);
    expect(screen.getByText(/0 regimes classificados/)).toBeInTheDocument();
  });
});
