import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useVirtualizedRows } from "@/hooks/useVirtualizedRows";

/**
 * M9 (T1.5b fix pass): the windowing math extracted out of
 * `components/markets/markets-table.tsx` to keep that component under the
 * lint config's per-function statement budget. No behaviour change is
 * intended -- these assertions lock in the exact arithmetic that used to
 * live inline in that component.
 */
describe("useVirtualizedRows", () => {
  it("slices the visible window with overscan on both edges", () => {
    const rows = Array.from({ length: 100 }, (_, i) => i);
    const { result } = renderHook(() =>
      useVirtualizedRows({ rows, rowHeight: 40, scrollTop: 400, viewportHeight: 480, overscan: 8 }),
    );

    // floor(400/40) - 8 = 10 - 8 = 2
    expect(result.current.startIndex).toBe(2);
    // ceil(480/40) + 8*2 = 12 + 16 = 28
    expect(result.current.endIndex).toBe(2 + 28);
    expect(result.current.visibleRows).toEqual(rows.slice(2, 30));
    expect(result.current.topPad).toBe(2 * 40);
    expect(result.current.bottomPad).toBe((100 - 30) * 40);
  });

  it("clamps startIndex to the end of a shorter list instead of slicing out an empty window", () => {
    const rows = [0, 1, 2];
    const { result } = renderHook(() =>
      useVirtualizedRows({ rows, rowHeight: 40, scrollTop: 4000, viewportHeight: 480, overscan: 8 }),
    );

    expect(result.current.startIndex).toBe(2);
    expect(result.current.visibleRows).toEqual([2]);
  });

  it("defaults overscan to 0", () => {
    const rows = [0, 1, 2, 3, 4];
    const { result } = renderHook(() => useVirtualizedRows({ rows, rowHeight: 40, scrollTop: 0, viewportHeight: 80 }));

    expect(result.current.startIndex).toBe(0);
    expect(result.current.endIndex).toBe(2);
  });
});
