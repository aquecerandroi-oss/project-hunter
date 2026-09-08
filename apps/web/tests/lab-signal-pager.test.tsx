import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { pushMock } = vi.hoisted(() => ({ pushMock: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

afterEach(cleanup);

import { LabSignalPager } from "@/components/lab/lab-signal-pager";

const pageSizeHrefs = { 50: "/acme/lab?page_size=50", 100: "/acme/lab?page_size=100", 200: "/acme/lab?page_size=200", 500: "/acme/lab?page_size=500" };

describe("LabSignalPager: 'X–Y de Z · página N' pager math (brief T3.37)", () => {
  it("prints the 1-based range, the real total and the page number derived from page.from/pageSize", () => {
    render(
      <LabSignalPager
        page={{ from: 1, to: 200 }}
        total={2135}
        pageSize={200}
        prevHref={null}
        nextHref="/acme/lab?c=cursor-1"
        pageSizeHrefs={pageSizeHrefs}
      />,
    );
    expect(screen.getByText("1–200 de 2.135 · página 1")).toBeInTheDocument();
  });

  it("computes the page number for a later page from page.from/pageSize (never a separately tracked counter)", () => {
    render(
      <LabSignalPager
        page={{ from: 401, to: 600 }}
        total={2135}
        pageSize={200}
        prevHref="/acme/lab?c=cursor-1"
        nextHref="/acme/lab?c=cursor-1&c=cursor-2&c=cursor-3"
        pageSizeHrefs={pageSizeHrefs}
      />,
    );
    expect(screen.getByText("401–600 de 2.135 · página 3")).toBeInTheDocument();
  });

  it("shows the honest '0 sinais nesta seleção' when the total is 0", () => {
    render(<LabSignalPager page={{ from: 0, to: 0 }} total={0} pageSize={200} prevHref={null} nextHref={null} pageSizeHrefs={pageSizeHrefs} />);
    expect(screen.getByText("0 sinais nesta seleção")).toBeInTheDocument();
  });

  it("disables 'Anterior' with no prevHref and 'Próxima' with no nextHref", () => {
    render(<LabSignalPager page={{ from: 1, to: 200 }} total={200} pageSize={200} prevHref={null} nextHref={null} pageSizeHrefs={pageSizeHrefs} />);
    expect(screen.getByRole("button", { name: "Anterior" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Próxima" })).toBeDisabled();
  });

  it("navigates to nextHref/prevHref on click", () => {
    render(
      <LabSignalPager
        page={{ from: 201, to: 400 }}
        total={2135}
        pageSize={200}
        prevHref="/acme/lab?prev=1"
        nextHref="/acme/lab?next=1"
        pageSizeHrefs={pageSizeHrefs}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Próxima" }));
    expect(pushMock).toHaveBeenCalledWith("/acme/lab?next=1");
    fireEvent.click(screen.getByRole("button", { name: "Anterior" }));
    expect(pushMock).toHaveBeenCalledWith("/acme/lab?prev=1");
  });

  it("navigates to the matching page-size href when the select changes", () => {
    render(
      <LabSignalPager page={{ from: 1, to: 200 }} total={2135} pageSize={200} prevHref={null} nextHref="/acme/lab?c=x" pageSizeHrefs={pageSizeHrefs} />,
    );
    fireEvent.change(screen.getByRole("combobox", { name: "Sinais por página" }), { target: { value: "500" } });
    expect(pushMock).toHaveBeenCalledWith("/acme/lab?page_size=500");
  });
});
