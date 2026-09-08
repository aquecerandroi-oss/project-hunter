import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { pushMock } = vi.hoisted(() => ({ pushMock: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => "/acme/lab",
}));

afterEach(cleanup);

import { LabFilters } from "@/components/lab/lab-filters";

/**
 * Brief T3.24b item [3] / Aceite: "Coorte é um `<select>` sem input livre."
 * `lab-filters.tsx` used to be a free-text `<input>` -- a reader could type
 * an unreachable cohort with no feedback.
 */
describe("LabFilters: Coorte is a <select>, never a free-text input (Aceite)", () => {
  it("renders a combobox for Coorte, offering 'prospective (padrão)' plus every distinct cohort passed in", () => {
    render(
      <LabFilters
        window="30d"
        cohort="prospective"
        versionId={null}
        versions={[]}
        cohorts={["prospective", "replay:11111111-1111-1111-1111-111111111111"]}
      />,
    );
    const select = screen.getByRole("combobox", { name: "Coorte" });
    expect(select.tagName).toBe("SELECT");
    expect(screen.getByRole("option", { name: "prospective (padrão)" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "replay:11111111-1111-1111-1111-111111111111" })).toBeInTheDocument();
    // never a free-text input for cohort
    expect(screen.queryByRole("textbox", { name: /coorte/i })).not.toBeInTheDocument();
  });

  it("navigates with the chosen cohort in the query string on change", () => {
    render(<LabFilters window="30d" cohort="prospective" versionId={null} versions={[]} cohorts={["prospective"]} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Coorte" }), { target: { value: "prospective" } });
    expect(pushMock).toHaveBeenCalledWith(expect.stringContaining("/acme/lab?window=30d"));
  });
});
