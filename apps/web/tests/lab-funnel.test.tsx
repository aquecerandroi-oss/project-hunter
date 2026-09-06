import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { LabFunnel } from "@/components/lab/lab-funnel";
import type { VersionCounts } from "@/lib/api/lab-types";

afterEach(cleanup);

const baseCounts: VersionCounts = {
  decisions: null,
  decisions_reason: "evaluation_state_not_persisted",
  signals_emitted: 18,
  pending_entry: 4,
  entered: 11,
  no_entry: { total: 0, by_reason: {} },
  active: 2,
  terminal: { total: 0, by_result: {} },
  censored: { total: 0, by_reason: {} },
  funding_not_settleable: 0,
};

/**
 * `Evaluation.state` is never durable (SHADOW-LAB.md §9) -- `counts.decisions`
 * is therefore always `null`, and the only honest thing to render for it is
 * `reasonLabel(counts.decisions_reason)`. The mutation this kills: swapping
 * that render for `String(counts.decisions ?? 0)` (a fabricated "0") or for
 * `counts.signals_emitted` (a different, real count standing in for a value
 * that was never computed) -- both would look like real numbers to a reader.
 */
describe("LabFunnel: decisions is null with a reason, never a fabricated count", () => {
  it("renders the readable reason, never '0' nor signals_emitted's value, for the decisions row", () => {
    render(<LabFunnel counts={baseCounts} />);

    const decisionsRow = screen.getByText("Avaliações (decisões)").closest("div");
    expect(decisionsRow).not.toBeNull();
    const dd = within(decisionsRow as HTMLElement).getByText(/avaliação não é persistida/);
    expect(dd).toBeInTheDocument();

    // The mutation to kill: `String(counts.decisions ?? 0)` renders a bare "0".
    expect(within(decisionsRow as HTMLElement).queryByText("0")).not.toBeInTheDocument();
    // The other mutation to kill: falling back to `counts.signals_emitted` (18).
    expect(within(decisionsRow as HTMLElement).queryByText("18")).not.toBeInTheDocument();

    // `signals_emitted` still renders its own real number in its own row.
    const emittedRow = screen.getByText("Sinais emitidos").closest("div");
    expect(within(emittedRow as HTMLElement).getByText("18")).toBeInTheDocument();
  });

  it("still shows a readable reason for an unrecognized decisions_reason code (never disappears, never '0')", () => {
    render(<LabFunnel counts={{ ...baseCounts, decisions_reason: "some_future_reason" }} />);

    const decisionsRow = screen.getByText("Avaliações (decisões)").closest("div");
    expect(within(decisionsRow as HTMLElement).getByText(/some_future_reason/)).toBeInTheDocument();
    expect(within(decisionsRow as HTMLElement).queryByText("0")).not.toBeInTheDocument();
  });
});
