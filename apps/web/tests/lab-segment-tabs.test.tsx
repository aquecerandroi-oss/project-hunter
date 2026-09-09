import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

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

  // T3.51 (Everton on the VPS: "eu clico e não resolve nada"): each tab is a
  // real `<a href>` now (`<Link>`), not a `<button onClick={() =>
  // router.push(...)}>` with no fallback -- so the assertion is the anchor's
  // own `href`, never a `router.push` call that could silently never run.
  it("renders every tab as a real anchor pointing at that segment's own href (state=open|pending|all|closed)", () => {
    render(<LabSegmentTabs state="closed" totals={exampleSignalsTotals()} hrefs={hrefs} />);
    expect(screen.getByRole("tab", { name: /Concluídas/ })).toHaveAttribute("href", "/acme/lab?state=closed");
    expect(screen.getByRole("tab", { name: /Abertas/ })).toHaveAttribute("href", "/acme/lab?state=open");
    expect(screen.getByRole("tab", { name: /Pendentes\/sem entrada/ })).toHaveAttribute("href", "/acme/lab?state=pending");
    expect(screen.getByRole("tab", { name: /Todas/ })).toHaveAttribute("href", "/acme/lab?state=all");
  });

  it("exposes an aria-live region announcing the active tab's real total", () => {
    render(<LabSegmentTabs state="pending" totals={exampleSignalsTotals()} hrefs={hrefs} />);
    const live = document.querySelector('[aria-live="polite"]');
    expect(live?.textContent).toMatch(/Pendentes\/sem entrada — 866 sinais no total/);
  });
});

/** Brief T3.38 item 4: each tab keeps counting signals visibly, but gains a `title` stating the real unique-operations count from `totals.distinct_operations`. */
describe("LabSegmentTabs: tab title states 'N sinais · K operações únicas' (brief T3.38 item 4)", () => {
  it("uses totals.distinct_operations when the contract field is present", () => {
    render(
      <LabSegmentTabs
        state="closed"
        totals={exampleSignalsTotals({ distinct_operations: { closed: 900, open: 340, pending: 866, all: 2100 } })}
        hrefs={hrefs}
      />,
    );
    expect(screen.getByRole("tab", { name: "Concluídas (929)" })).toHaveAttribute("title", "929 sinais · 900 operações únicas");
  });

  it("falls back to the same signals count until the API provides distinct_operations", () => {
    // A fixture traz distinct_operations (T3.38a); este caso é a resposta de uma API mais velha.
    const withoutDistinct = { ...exampleSignalsTotals() };
    delete withoutDistinct.distinct_operations;
    render(<LabSegmentTabs state="closed" totals={withoutDistinct} hrefs={hrefs} />);
    expect(screen.getByRole("tab", { name: "Concluídas (929)" })).toHaveAttribute("title", "929 sinais · 929 operações únicas");
  });
});
