import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const warnSpy = vi.fn();
vi.mock("@/lib/logger", () => ({ logger: { warn: warnSpy, info: vi.fn(), debug: vi.fn(), error: vi.fn() } }));

afterEach(cleanup);

import { exampleSignalsTotals } from "@/tests/fixtures/lab-pagination";

const hrefs = {
  concluded: "/acme/lab?state=closed",
  open: "/acme/lab?state=open",
  pending: "/acme/lab?state=pending",
  all: "/acme/lab?state=all",
};

/**
 * Finding 6 of the T3.38 review: `LabSegmentTabs` warns (via `@/lib/logger`,
 * never a bare `console.*`) exactly once when an older API response omits
 * `totals.distinct_operations` -- never per render, never per tab. This
 * file gets its own fresh module instance per test (`vi.resetModules` + a
 * dynamic import) so the "only once" assertion is never polluted by
 * `lab-segment-tabs.test.tsx` exercising the same fallback path first (both
 * files would otherwise share the same module-level flag).
 */
describe("LabSegmentTabs: warns once when totals.distinct_operations is missing (finding 6)", () => {
  beforeEach(() => {
    vi.resetModules();
    warnSpy.mockClear();
  });

  it("logs exactly one logger.warn even across multiple renders/tab changes missing the field", async () => {
    const { LabSegmentTabs } = await import("@/components/lab/lab-segment-tabs");
    const withoutDistinct = { ...exampleSignalsTotals() };
    delete withoutDistinct.distinct_operations;

    const { rerender } = render(<LabSegmentTabs state="closed" totals={withoutDistinct} hrefs={hrefs} />);
    rerender(<LabSegmentTabs state="open" totals={withoutDistinct} hrefs={hrefs} />);
    rerender(<LabSegmentTabs state="pending" totals={withoutDistinct} hrefs={hrefs} />);

    expect(warnSpy).toHaveBeenCalledTimes(1);
    expect(warnSpy).toHaveBeenCalledWith("lab_signals_totals_missing_distinct_operations", expect.objectContaining({ all: withoutDistinct.all }));
  });

  it("never warns when totals.distinct_operations is present", async () => {
    const { LabSegmentTabs } = await import("@/components/lab/lab-segment-tabs");
    render(<LabSegmentTabs state="closed" totals={exampleSignalsTotals()} hrefs={hrefs} />);
    expect(warnSpy).not.toHaveBeenCalled();
  });
});
