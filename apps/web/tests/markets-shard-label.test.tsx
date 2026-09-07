import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

afterEach(cleanup);

import { SummaryChips } from "@/components/markets/summary-chips";
import { summary } from "@/tests/fixtures/markets-row";

/**
 * T2.5g: the collector runs as N sharded processes and `/markets`'s summary
 * carries how many of them are reporting. The label is real data or nothing --
 * never a guessed "1 shard".
 */
describe("SummaryChips: the collector's shard label", () => {
  it("names the topology when every shard is reporting", () => {
    render(
      <SummaryChips
        summary={{ ...summary, collector_shards_expected: 4, collector_shards_reporting: 4 }}
      />,
    );
    expect(screen.getByText("4 shards, 2 mercados")).toBeInTheDocument();
  });

  it("says how many are missing instead of pretending the collector is whole", () => {
    render(
      <SummaryChips
        summary={{ ...summary, collector_shards_expected: 4, collector_shards_reporting: 3 }}
      />,
    );
    expect(screen.getByText("3 de 4 shards, 2 mercados")).toBeInTheDocument();
  });

  it("prints no label at all when no collector declared a topology", () => {
    render(<SummaryChips summary={summary} />);
    expect(screen.queryByText(/shards/)).not.toBeInTheDocument();
  });
});
