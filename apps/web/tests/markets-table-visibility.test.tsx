import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({ getToken: async () => null }),
}));

const routerPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: routerPush }),
}));

afterEach(() => {
  cleanup();
  routerPush.mockClear();
});

import { MarketsTable } from "@/components/markets/markets-table";
import { makeRow, summary } from "@/tests/fixtures/markets-row";

/**
 * M3 (Astra, T1.5b fix pass 2 -- pass 1 only PARTIALLY fixed this): a row
 * can be MEMBER of the virtualized window's rendered rows (inside
 * `useVirtualizedRows`'s `OVERSCAN` of 8 rows above/below the viewport)
 * while still being fully off-screen. The old guard in `markets-table.tsx`
 * only checked window membership; this file locks in the real geometry-based
 * visibility check instead. Split out of `markets-table.test.tsx` to keep
 * that file under the lint config's 350-line budget.
 */
describe("MarketsTable: a keyboard selection that is off-screen is not silently opened (M3, closed in T1.5b fix pass 2)", () => {
  it("resets the selection instead of navigating when Enter fires after selectedIndex has scrolled out of the virtualized window entirely", () => {
    const rows = Array.from({ length: 60 }, (_, i) => makeRow({ symbol: `SYM${i}USDT`, exchange: "binance" }));
    render(<MarketsTable orgSlug="acme" items={rows} summary={summary} staleAfterMs={10_000} />);
    const grid = screen.getByRole("grid", { name: "Mercados monitorados" });

    // Select row 0 with the arrow keys.
    fireEvent.keyDown(grid, { key: "ArrowDown" });
    expect(screen.getByText("SYM0USDT").closest("tr")).toHaveAttribute("aria-selected", "true");

    // Now scroll the container far down MANUALLY (not via the arrow keys) --
    // row 0 falls out of the virtualized window's rendered rows, and
    // `aria-activedescendant` is correctly dropped, but the hook's own
    // `selectedIndex` state still says "0".
    Object.defineProperty(grid, "scrollTop", { value: 4000, writable: true });
    fireEvent.scroll(grid);
    expect(grid).not.toHaveAttribute("aria-activedescendant");

    fireEvent.keyDown(grid, { key: "Enter" });

    expect(routerPush).not.toHaveBeenCalled();
  });

  it("resets the selection instead of navigating when the row is still RENDERED (inside the overscan window) but off-screen (M3, was only PARTIALLY fixed in pass 1)", () => {
    // Comfortable density row height is 40px (hooks/useDensity.ts); the
    // sticky header is 32px (markets-table.tsx's HEADER_HEIGHT). Row 0's real
    // span in the scrollable content is [32, 72). Scrolling 160px leaves it
    // between -128px and -88px relative to the viewport -- fully off-screen
    // -- yet still comfortably inside the 8-row overscan the old (membership-
    // only) guard checked, so the old guard let Enter navigate anyway.
    const rows = Array.from({ length: 60 }, (_, i) => makeRow({ symbol: `SYM${i}USDT`, exchange: "binance" }));
    render(<MarketsTable orgSlug="acme" items={rows} summary={summary} staleAfterMs={10_000} />);
    const grid = screen.getByRole("grid", { name: "Mercados monitorados" });

    fireEvent.keyDown(grid, { key: "ArrowDown" });
    expect(screen.getByText("SYM0USDT").closest("tr")).toHaveAttribute("aria-selected", "true");

    Object.defineProperty(grid, "scrollTop", { value: 160, writable: true });
    fireEvent.scroll(grid);
    // Row 0 is still rendered (well within the overscan window) -- this is
    // exactly the "rendered but invisible" gap the membership-only guard
    // missed, so unlike the 4000px case above, aria-activedescendant is
    // NOT dropped here.
    expect(screen.getByText("SYM0USDT")).toBeInTheDocument();

    fireEvent.keyDown(grid, { key: "Enter" });

    expect(routerPush).not.toHaveBeenCalled();
  });

  it("still opens a row that IS visible after a small scroll (visibility check isn't overly strict)", () => {
    const rows = Array.from({ length: 60 }, (_, i) => makeRow({ symbol: `SYM${i}USDT`, exchange: "binance" }));
    render(<MarketsTable orgSlug="acme" items={rows} summary={summary} staleAfterMs={10_000} />);
    const grid = screen.getByRole("grid", { name: "Mercados monitorados" });

    fireEvent.keyDown(grid, { key: "ArrowDown" });

    // A 20px nudge still leaves row 0's [32, 72) span overlapping the
    // viewport [20, 500) -- genuinely visible, so Enter must still open it.
    Object.defineProperty(grid, "scrollTop", { value: 20, writable: true });
    fireEvent.scroll(grid);

    fireEvent.keyDown(grid, { key: "Enter" });

    expect(routerPush).toHaveBeenCalledWith("/acme/markets/binance/SYM0USDT");
  });
});
