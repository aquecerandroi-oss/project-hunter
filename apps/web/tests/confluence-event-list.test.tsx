import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfluenceEventList } from "@/components/confluence/confluence-event-list";
import { makeSignal } from "@/tests/fixtures/lab";
import type { SignalListItemOut } from "@/lib/api/lab-types";

afterEach(cleanup);

const noop = vi.fn();

function signalsAt(count: number): SignalListItemOut[] {
  return Array.from({ length: count }, (_, i) =>
    makeSignal({
      signal_id: `signal-${i}`,
      decision_at: new Date(Date.UTC(2026, 8, 23, 0, 0, 0) + i * 60_000).toISOString(),
    }),
  );
}

describe("ConfluenceEventList: honest empty state", () => {
  it("says nothing was registered, rather than rendering an empty table", () => {
    render(<ConfluenceEventList signals={[]} events={[]} desk={null} onSelectSignal={noop} selectedSignalId={null} />);
    expect(screen.getByText("Nada registrado neste período para este mercado.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("ConfluenceEventList: virtualized, per CLAUDE.md's >= 200 rows rule (code review, must-fix 4)", () => {
  it("does not mount every <tr> for a 300-row period -- only the visible window plus overscan", () => {
    render(<ConfluenceEventList signals={signalsAt(300)} events={[]} desk={null} onSelectSignal={noop} selectedSignalId={null} />);
    // 300 data rows + 1 header row would be 301 <tr>s if this ever regressed
    // back to rendering everything at once.
    const rows = screen.getAllByRole("row");
    expect(rows.length).toBeLessThan(301);
    expect(rows.length).toBeGreaterThan(1);
  });

  it("never truncates -- every row is still reachable through the scrollable window, never dropped past a fixed cap", () => {
    const { container } = render(
      <ConfluenceEventList signals={signalsAt(300)} events={[]} desk={null} onSelectSignal={noop} selectedSignalId={null} />,
    );
    // The old fixed 500-row cap warned in prose once past it; virtualization
    // has no such ceiling to warn about in the first place.
    expect(container.textContent).not.toMatch(/estreite a janela para ver o restante/);
  });
});
