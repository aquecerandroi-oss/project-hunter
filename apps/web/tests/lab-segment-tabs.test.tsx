import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { pushMock } = vi.hoisted(() => ({ pushMock: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

afterEach(cleanup);

import { LabSegmentTabs } from "@/components/lab/lab-segment-tabs";
import { exampleSignalsTotals } from "@/tests/fixtures/lab-pagination";

const hrefs = {
  concluded: "/acme/lab?state=closed",
  open: "/acme/lab?state=open",
  pending: "/acme/lab?state=pending",
  all: "/acme/lab?state=all",
};

/**
 * Brief T3.37: "the tabs render totals from a fixture; clicking a tab
 * changes the query, not the array" -- replacing the old client-filtered
 * `LabSegmentTabs` (which counted among whatever `rows` were loaded) with
 * one driven entirely by the API's own real `totals`.
 */
describe("LabSegmentTabs: real, whole-dataset totals (brief T3.37)", () => {
  it("shows the API's own totals.* next to each tab, never a count derived from loaded rows", () => {
    render(<LabSegmentTabs state="closed" totals={exampleSignalsTotals()} hrefs={hrefs} />);
    expect(screen.getByRole("tab", { name: "Concluídas (929)" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Abertas (340)" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Pendentes/sem entrada (866)" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Todas (2.135)" })).toBeInTheDocument();
  });

  it("marks the tab matching the current `state` prop as selected -- not a locally tracked segment", () => {
    render(<LabSegmentTabs state="open" totals={exampleSignalsTotals()} hrefs={hrefs} />);
    expect(screen.getByRole("tab", { name: /Abertas/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: /Concluídas/ })).toHaveAttribute("aria-selected", "false");
  });

  it("clicking a tab navigates to that tab's own href (a query change), never mutates an in-memory array", () => {
    render(<LabSegmentTabs state="closed" totals={exampleSignalsTotals()} hrefs={hrefs} />);
    fireEvent.click(screen.getByRole("tab", { name: /Abertas/ }));
    expect(pushMock).toHaveBeenCalledWith("/acme/lab?state=open");
  });

  it("does nothing when clicking the already-active tab", () => {
    render(<LabSegmentTabs state="closed" totals={exampleSignalsTotals()} hrefs={hrefs} />);
    fireEvent.click(screen.getByRole("tab", { name: /Concluídas/ }));
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("exposes an aria-live region announcing the active tab's real total", () => {
    render(<LabSegmentTabs state="pending" totals={exampleSignalsTotals()} hrefs={hrefs} />);
    const live = document.querySelector('[aria-live="polite"]');
    expect(live?.textContent).toMatch(/Pendentes\/sem entrada — 866 sinais no total/);
  });
});
