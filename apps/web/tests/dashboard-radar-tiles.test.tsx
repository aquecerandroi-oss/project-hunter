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

  it("shows UNKNOWN as a real classification, not hidden or replaced (D19: pt-BR label, never the raw enum)", async () => {
    getCurrentRegimeMock.mockResolvedValue({ items: [makeRegime({ regime: "UNKNOWN" })], as_of: "2026-09-06T08:00:00Z" });
    const result = await loadRegimeTile();
    render(<RegimeTile result={result} />);
    expect(screen.getByText("Sem classificação")).toBeInTheDocument();
    expect(screen.queryByText("UNKNOWN")).not.toBeInTheDocument();
  });

  it("shows a verified '0 regimes classificados', distinct from 'sem verificação'", async () => {
    getCurrentRegimeMock.mockResolvedValue({ items: [], as_of: "2026-09-06T08:00:00Z" });
    const result = await loadRegimeTile();
    render(<RegimeTile result={result} />);
    expect(screen.getByText(/0 regimes classificados/)).toBeInTheDocument();
  });
});

describe("RegimeTile: T3.43b hourly (regime_hourly_v1) decomposition", () => {
  const HOURLY_COMPONENTS = [
    { name: "trend", normalized: "100", weight: "0.35", contribution: "35.0" },
    { name: "breadth", normalized: "54.32", weight: "0.25", contribution: "13.6" },
    { name: "volatility", normalized: "60", weight: "0.20", contribution: "12.0" },
    { name: "drawdown", normalized: "84.50", weight: "0.10", contribution: "8.5" },
    { name: "funding", normalized: null, weight: "0.10", contribution: null },
  ];

  function makeHourlyRegime(overrides: Parameters<typeof makeRegime>[0] = {}) {
    return makeRegime({
      scope: "btc",
      regime: "BTC_BULL",
      confidence: "0.8000",
      classifier_version: "regime_hourly_v1",
      identity: "regime_hourly_v1",
      as_of: "2026-09-08T15:00:00Z",
      score: "62.00",
      components: HOURLY_COMPONENTS,
      is_stale: false,
      ...overrides,
    });
  }

  it("shows the score, pt-BR confidence and the hour for a fresh hourly row (D17: comma decimal)", async () => {
    getCurrentRegimeMock.mockResolvedValue({ items: [makeHourlyRegime()], as_of: "2026-09-08T15:12:00Z" });
    const result = await loadRegimeTile();
    render(<RegimeTile result={result} />);
    expect(screen.getByText(/score 62\/100/)).toBeInTheDocument();
    expect(screen.getByText(/confiança 0,8/)).toBeInTheDocument();
    expect(screen.getByText(/hora/)).toBeInTheDocument();
    expect(screen.queryByText("stale")).not.toBeInTheDocument();
  });

  it("translates the regime label to pt-BR, never the raw enum (D19)", async () => {
    getCurrentRegimeMock.mockResolvedValue({ items: [makeHourlyRegime()], as_of: "2026-09-08T15:12:00Z" });
    const result = await loadRegimeTile();
    render(<RegimeTile result={result} />);
    expect(screen.getByText("Alta de BTC")).toBeInTheDocument();
    expect(screen.queryByText("BTC_BULL")).not.toBeInTheDocument();
  });

  it("shows the stale badge for an hourly row the API marked stale (old hour or dead producer)", async () => {
    getCurrentRegimeMock.mockResolvedValue({
      items: [makeHourlyRegime({ is_stale: true })],
      as_of: "2026-09-08T18:12:00Z",
    });
    const result = await loadRegimeTile();
    render(<RegimeTile result={result} />);
    expect(screen.getByText("stale")).toBeInTheDocument();
  });

  it("lists the five components (pt-BR labels) inside a collapsed <details>, funding's missing reading shown honestly", async () => {
    getCurrentRegimeMock.mockResolvedValue({ items: [makeHourlyRegime()], as_of: "2026-09-08T15:12:00Z" });
    const result = await loadRegimeTile();
    render(<RegimeTile result={result} />);
    const disclosure = screen.getByText("5 componentes do score").closest("details");
    expect(disclosure).not.toHaveAttribute("open");
    for (const label of ["Tendência", "Amplitude", "Volatilidade", "Drawdown", "Funding"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText("sem leitura")).toBeInTheDocument();
    expect(screen.queryByText("funding")).not.toBeInTheDocument();
  });

  it("a regime_v0 row (no identity) never shows a score, confidence or hour line, and no components disclosure", async () => {
    getCurrentRegimeMock.mockResolvedValue({ items: [makeRegime()], as_of: "2026-09-06T08:00:00Z" });
    const result = await loadRegimeTile();
    render(<RegimeTile result={result} />);
    expect(screen.queryByText(/score/)).not.toBeInTheDocument();
    expect(screen.queryByText(/confiança/)).not.toBeInTheDocument();
    expect(screen.queryByText(/hora/)).not.toBeInTheDocument();
    expect(screen.queryByText(/componentes do score/)).not.toBeInTheDocument();
  });
});
