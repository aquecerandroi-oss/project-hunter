import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(cleanup);

import { QualityBadge } from "@/components/markets/quality-badge";
import type { MarketComponents } from "@/lib/api/types";

const STALE_AFTER_MS = 10_000;

function componentsAt(iso: string): MarketComponents {
  return {
    ticker: { ts: iso, age_ms: 0, quality: "ok" },
    book: { ts: iso, age_ms: 0, quality: "ok" },
    mark: { ts: iso, age_ms: 0, quality: "ok" },
    open_interest: { ts: iso, age_ms: 0 },
    funding: { ts: iso, age_ms: 0, kind: "realized" },
  };
}

const ABSENT: MarketComponents = {
  ticker: { ts: null, age_ms: null, quality: "absent" },
  book: { ts: null, age_ms: null, quality: "absent" },
  mark: { ts: null, age_ms: null, quality: "absent" },
  open_interest: { ts: null, age_ms: null },
  funding: { ts: null, age_ms: null, kind: null },
};

describe("QualityBadge: quality vocabulary (docs/plans/M1.md T1.5)", () => {
  it("ok (fresh components) renders a green OK badge", () => {
    render(
      <QualityBadge
        quality="ok"
        components={componentsAt(new Date().toISOString())}
        staleAfterMs={STALE_AFTER_MS}
        hasOpenGap={false}
      />,
    );
    expect(screen.getByText("OK")).toBeInTheDocument();
  });

  it("degraded with an absent required component and no open gap renders 'sem dado', not a misleading 'gap'", () => {
    render(<QualityBadge quality="degraded" components={ABSENT} staleAfterMs={STALE_AFTER_MS} hasOpenGap={false} />);
    expect(screen.getByText("sem dado")).toBeInTheDocument();
  });

  it("degraded with every required component present renders 'gap' (a real ingestion gap)", () => {
    render(
      <QualityBadge
        quality="degraded"
        components={componentsAt(new Date().toISOString())}
        staleAfterMs={STALE_AFTER_MS}
        hasOpenGap={false}
      />,
    );
    expect(screen.getByText("gap")).toBeInTheDocument();
  });

  it("unavailable renders 'sem dado', never a stale number", () => {
    render(<QualityBadge quality="unavailable" components={ABSENT} staleAfterMs={STALE_AFTER_MS} hasOpenGap={false} />);
    expect(screen.getByText("sem dado")).toBeInTheDocument();
  });

  it("an 'ok' row goes visibly stale on its own once a required component crosses the API's stale_after_ms with no new data (fake timers)", () => {
    vi.useFakeTimers();
    const now = new Date("2026-09-05T12:00:00.000Z");
    vi.setSystemTime(now);

    render(
      <QualityBadge quality="ok" components={componentsAt(now.toISOString())} staleAfterMs={STALE_AFTER_MS} hasOpenGap={false} />,
    );
    expect(screen.getByText("OK")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(11_000);
    });
    expect(screen.getByText("atrasado 11s")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(screen.getByText("atrasado 1min")).toBeInTheDocument();

    vi.useRealTimers();
  });

  it("recovers from stale back to OK once fresh component timestamps arrive (a realtime tick), without waiting for a refetch", () => {
    const stale = componentsAt(new Date(Date.now() - 20_000).toISOString());
    const { rerender } = render(
      <QualityBadge quality="ok" components={stale} staleAfterMs={STALE_AFTER_MS} hasOpenGap={false} />,
    );
    expect(screen.getByText(/^atrasado/)).toBeInTheDocument();

    rerender(
      <QualityBadge
        quality="ok"
        components={componentsAt(new Date().toISOString())}
        staleAfterMs={STALE_AFTER_MS}
        hasOpenGap={false}
      />,
    );
    expect(screen.getByText("OK")).toBeInTheDocument();
  });
});

describe("QualityBadge: staleness threshold comes from the API, not a hardcoded client constant (H2)", () => {
  it("reads a component older than the API's stale_after_ms as stale even well under the old 10s default", () => {
    const eightSecondsAgo = new Date(Date.now() - 8_000).toISOString();
    render(
      <QualityBadge quality="ok" components={componentsAt(eightSecondsAgo)} staleAfterMs={5_000} hasOpenGap={false} />,
    );
    expect(screen.queryByText("OK")).not.toBeInTheDocument();
    expect(screen.getByText(/^atrasado/)).toBeInTheDocument();
  });

  it("still reads a component as OK under a stale_after_ms larger than the old 10s default", () => {
    const twelveSecondsAgo = new Date(Date.now() - 12_000).toISOString();
    render(
      <QualityBadge quality="ok" components={componentsAt(twelveSecondsAgo)} staleAfterMs={30_000} hasOpenGap={false} />,
    );
    expect(screen.getByText("OK")).toBeInTheDocument();
  });
});

describe("QualityBadge: an open gap must still read as 'gap' even when a component is also absent (H2)", () => {
  it("renders 'gap', not 'sem dado', when has_open_gap is true and a required component is absent", () => {
    render(<QualityBadge quality="degraded" components={ABSENT} staleAfterMs={STALE_AFTER_MS} hasOpenGap />);
    expect(screen.getByText("gap")).toBeInTheDocument();
    expect(screen.queryByText("sem dado")).not.toBeInTheDocument();
  });
});
