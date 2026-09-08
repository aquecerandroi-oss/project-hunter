import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { useParamsMock } = vi.hoisted(() => ({
  useParamsMock: vi.fn(() => ({ orgSlug: "ever" })),
}));

vi.mock("next/navigation", () => ({
  useParams: useParamsMock,
}));

afterEach(() => {
  cleanup();
  useParamsMock.mockClear();
});

import OrgSegmentError from "@/app/(app)/[orgSlug]/error";
import Loading from "@/app/(app)/[orgSlug]/loading";

describe("loading.tsx: decorative skeleton, no text (T3.24a's brief §3, fixes X1)", () => {
  it("renders with no visible text content", () => {
    const { container } = render(<Loading />);
    expect(container.textContent).toBe("");
  });

  it("is marked decorative for assistive tech", () => {
    const { container } = render(<Loading />);
    expect(container.firstElementChild).toHaveAttribute("aria-hidden", "true");
  });
});

describe("error.tsx: honest failure state, no stack trace, calls reset (fixes X1)", () => {
  it("shows the error message in Portuguese", () => {
    const error = Object.assign(new Error("fetch failed"), { digest: "abc123" });
    render(<OrgSegmentError error={error} reset={vi.fn()} />);
    expect(screen.getByText(/Esta tela falhou ao renderizar: fetch failed/)).toBeInTheDocument();
  });

  it("never renders the error's stack trace", () => {
    const error = Object.assign(new Error("fetch failed"), { stack: "at someInternalFunction (secret/path.ts:42)" });
    render(<OrgSegmentError error={error} reset={vi.fn()} />);
    expect(screen.queryByText(/secret\/path\.ts/)).not.toBeInTheDocument();
  });

  it("calls reset() when 'Tentar novamente' is clicked", () => {
    const reset = vi.fn();
    render(<OrgSegmentError error={new Error("boom")} reset={reset} />);
    fireEvent.click(screen.getByRole("button", { name: /tentar novamente/i }));
    expect(reset).toHaveBeenCalledTimes(1);
  });

  it("links to the current org's System page", () => {
    render(<OrgSegmentError error={new Error("boom")} reset={vi.fn()} />);
    expect(screen.getByRole("link", { name: /ver system/i })).toHaveAttribute("href", "/ever/system");
  });
});
