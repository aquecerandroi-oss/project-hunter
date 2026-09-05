import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({ getToken: async () => null }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }),
}));

afterEach(cleanup);

import { MarketsTable } from "@/components/markets/markets-table";
import { MARKETS_TABLE_HEADERS } from "@/components/markets/markets-table-head";
import { makeRow, summary } from "@/tests/fixtures/markets-row";

/**
 * M2 (both reviewers, T1.5b fix pass 2): `role="presentation"` on the
 * `<table>` used to cascade down and strip the implicit `row`/
 * `columnheader`/`cell` roles off every plain descendant, since none of them
 * had an explicit role of their own -- the grid announced zero rows and zero
 * cells to assistive tech. The old test here only asserted the ABSENCE of a
 * competing `role="table"`, which is exactly what let that regression slip
 * through; these assert the POSITIVE, complete role tree instead. Split out
 * of `markets-table.test.tsx` to keep that file under the lint config's
 * 350-line budget.
 */
describe("MarketsTable: exposes a complete, explicit ARIA grid role tree, not two competing ones (M2, T1.5b fix pass 2)", () => {
  it("suppresses the native <table>'s own implicit role so only the container's role=grid is exposed", () => {
    render(<MarketsTable orgSlug="acme" items={[makeRow()]} summary={summary} staleAfterMs={10_000} />);

    expect(screen.getByRole("grid", { name: "Mercados monitorados" })).toBeInTheDocument();
    // A real `<table>` with no role override is implicitly `role="table"` --
    // NVDA/JAWS then announce two different row/column counts for the same
    // markup (the div's grid vs. the table's own table semantics).
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("exposes a real row for the header and each rendered data row, not zero rows and zero cells", () => {
    const rows = [makeRow(), makeRow({ symbol: "ETHUSDT", base_asset: "ETH" })];
    render(<MarketsTable orgSlug="acme" items={rows} summary={summary} staleAfterMs={10_000} />);

    // Positive assertion (this is what the old test's negative-only
    // `queryByRole("table")` check let slip through): the old
    // `role="presentation"` on the `<table>` alone stripped the implicit
    // row role off every plain `<tr>` beneath it -- 1 header row + 2 data
    // rows here, never zero.
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("exposes every column header with its real label, matching MARKETS_TABLE_HEADERS", () => {
    render(<MarketsTable orgSlug="acme" items={[makeRow()]} summary={summary} staleAfterMs={10_000} />);

    const headers = screen.getAllByRole("columnheader");
    expect(headers).toHaveLength(MARKETS_TABLE_HEADERS.length);
    for (const header of MARKETS_TABLE_HEADERS) {
      expect(screen.getByRole("columnheader", { name: new RegExp(header.label) })).toBeInTheDocument();
    }
  });

  it("exposes gridcell cells inside a data row, one per column", () => {
    render(<MarketsTable orgSlug="acme" items={[makeRow()]} summary={summary} staleAfterMs={10_000} />);

    const dataRow = screen.getByText("BTCUSDT").closest('[role="row"]');
    expect(dataRow).not.toBeNull();
    expect(within(dataRow as HTMLElement).getAllByRole("gridcell")).toHaveLength(MARKETS_TABLE_HEADERS.length);
  });

  it("reports aria-rowcount for the FULL row count while the DOM only holds the virtualized window", () => {
    const rows = Array.from({ length: 60 }, (_, i) => makeRow({ symbol: `SYM${i}USDT` }));
    render(<MarketsTable orgSlug="acme" items={rows} summary={summary} staleAfterMs={10_000} />);
    const grid = screen.getByRole("grid", { name: "Mercados monitorados" });

    // 60 data rows + 1 header row -- never just the ~28-row rendered window.
    expect(grid).toHaveAttribute("aria-rowcount", "61");
    expect(screen.getAllByRole("row").length).toBeLessThan(61);
  });
});
