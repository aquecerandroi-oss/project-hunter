import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/logger", () => ({ logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() } }));

import RootRouteError from "@/app/error";

afterEach(cleanup);

/**
 * `app/error.tsx` (brief T3.28b): the boundary that now sits above
 * `app/page.tsx` (the `/` home redirect, which calls `me()` directly and
 * uncaught) -- before this file existed, that same 429/5xx incident would
 * have hit Next's bare "Application error" screen here too, with nothing
 * below `/` to catch it.
 */
describe("RootRouteError: honest failure for anything directly under app/, never a stack trace on screen", () => {
  it("shows the failure message and a retry, with no orgSlug-scoped link (none exists this early)", () => {
    render(<RootRouteError error={new Error("Rate limit exceeded.")} reset={vi.fn()} />);

    expect(screen.getByText(/Não foi possível continuar: Rate limit exceeded\./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voltar ao início" })).toHaveAttribute("href", "/");
  });

  it("calls reset() from 'Tentar novamente'", () => {
    const reset = vi.fn();
    render(<RootRouteError error={new Error("boom")} reset={reset} />);

    screen.getByRole("button", { name: "Tentar novamente" }).click();
    expect(reset).toHaveBeenCalledTimes(1);
  });
});
