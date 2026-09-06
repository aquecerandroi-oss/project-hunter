import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const routerPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPush }),
  usePathname: () => "/acme/radar",
}));

afterEach(() => {
  cleanup();
  routerPush.mockClear();
});

import { RadarFilters, type RadarFiltersState } from "@/components/radar/radar-filters";

const emptyState: RadarFiltersState = {
  q: "",
  scoreMin: "",
  status: [],
  stage: [],
  exchange: "",
  anomalyType: "",
  regime: "",
  volatilityMin: "",
  volatilityMax: "",
};

describe("RadarFilters: state is the URL query string", () => {
  it("navigates with score_min when the field loses focus", () => {
    render(<RadarFilters state={emptyState} hasOrg />);
    fireEvent.blur(screen.getByLabelText("Score mínimo"), { target: { value: "80" } });
    expect(routerPush).toHaveBeenCalledWith("/acme/radar?score_min=80");
  });

  it("appends every checked status as its own status= entry", () => {
    render(<RadarFilters state={emptyState} hasOrg />);
    fireEvent.click(screen.getByLabelText("HOT"));
    const [url] = routerPush.mock.calls[0] as [string];
    expect(url).toContain("status=HOT");
  });

  it("includes IN_POSITION/RISK_BLOCKED only when hasOrg is true", () => {
    render(<RadarFilters state={emptyState} hasOrg={false} />);
    expect(screen.queryByLabelText("IN_POSITION")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("RISK_BLOCKED")).not.toBeInTheDocument();
  });

  it("drops the field entirely from the query string when it is blank", () => {
    render(<RadarFilters state={emptyState} hasOrg />);
    fireEvent.blur(screen.getByLabelText("Buscar símbolo no radar"), { target: { value: "" } });
    expect(routerPush).toHaveBeenCalledWith("/acme/radar?");
  });
});
