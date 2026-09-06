import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const loadAnomalyTimelineActionMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/anomalies-actions", () => ({ loadAnomalyTimelineAction: loadAnomalyTimelineActionMock }));

afterEach(() => {
  cleanup();
  loadAnomalyTimelineActionMock.mockReset();
});

import { AnomalyTimeline } from "@/components/anomalies/anomaly-timeline";
import { makeAnomaly } from "@/tests/fixtures/radar";

describe("AnomalyTimeline: the market-detail 24h anomaly timeline", () => {
  it("shows type, severity, status and evaluation_state for each anomaly", async () => {
    loadAnomalyTimelineActionMock.mockResolvedValue({
      ok: true,
      page: { items: [makeAnomaly()], next_cursor: null, as_of: "2026-09-06T08:00:00Z", window_start: "2026-09-05T08:00:00Z" },
    });
    render(<AnomalyTimeline marketId="22222222-2222-2222-2222-222222222222" />);

    await waitFor(() => expect(screen.getByText("VOLUME_SPIKE")).toBeInTheDocument());
    expect(screen.getByText(/severidade 70.00/)).toBeInTheDocument();
    expect(screen.getByText("ativa")).toBeInTheDocument();
    expect(screen.getByText("avaliação ok")).toBeInTheDocument();
  });

  it("never reads an active + unknown anomaly as resolved", async () => {
    loadAnomalyTimelineActionMock.mockResolvedValue({
      ok: true,
      page: {
        items: [makeAnomaly({ status: "active", evaluation_state: "unknown" })],
        next_cursor: null,
        as_of: "2026-09-06T08:00:00Z",
        window_start: "2026-09-05T08:00:00Z",
      },
    });
    render(<AnomalyTimeline marketId="22222222-2222-2222-2222-222222222222" />);

    await waitFor(() => expect(screen.getByText("avaliação desconhecida")).toBeInTheDocument());
    expect(screen.getByText("ativa")).toBeInTheDocument();
    expect(screen.queryByText("resolvida")).not.toBeInTheDocument();
  });

  it("shows the honest empty state for a genuinely quiet 24h window", async () => {
    loadAnomalyTimelineActionMock.mockResolvedValue({
      ok: true,
      page: { items: [], next_cursor: null, as_of: "2026-09-06T08:00:00Z", window_start: "2026-09-05T08:00:00Z" },
    });
    render(<AnomalyTimeline marketId="22222222-2222-2222-2222-222222222222" />);
    await waitFor(() => expect(screen.getByText(/Nenhuma anomalia nas últimas 24h/)).toBeInTheDocument());
  });

  it("shows the real failure reason, never a stale-looking empty list", async () => {
    loadAnomalyTimelineActionMock.mockResolvedValue({ ok: false, reason: "timeout", page: { items: [], next_cursor: null, as_of: "", window_start: "" } });
    render(<AnomalyTimeline marketId="22222222-2222-2222-2222-222222222222" />);
    await waitFor(() => expect(screen.getByText(/Anomalias indisponíveis: timeout/)).toBeInTheDocument());
  });
});
