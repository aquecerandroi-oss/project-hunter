import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { refreshReadinessMock } = vi.hoisted(() => ({ refreshReadinessMock: vi.fn() }));
vi.mock("@/lib/api/system-actions", () => ({ refreshReadiness: refreshReadinessMock }));

afterEach(cleanup);

import { ReadinessPanel } from "@/components/system/readiness-panel";
import type { ReadyStatus } from "@/lib/api/types";

const ready: ReadyStatus = { database: true, redis: true };
const redisDown: ReadyStatus = { database: true, redis: false, redis_detail: "unreachable" };

beforeEach(() => {
  refreshReadinessMock.mockReset();
});

describe("ReadinessPanel: reconciles a fresh server snapshot, not just the value read at mount (H6)", () => {
  it("shows Redis going down once a newer `initial` prop arrives (AutoRefresh re-rendering the page)", () => {
    const { rerender } = render(<ReadinessPanel initial={ready} />);
    expect(screen.getByText("Ready")).toBeInTheDocument();

    // Simulates `AutoRefresh`'s `router.refresh()` producing a fresh
    // server-fetched `initial` prop on the next render of this same
    // component instance -- a plain `useState(initial)` ignores this.
    rerender(<ReadinessPanel initial={redisDown} />);

    expect(screen.getByText("Not Ready")).toBeInTheDocument();
    expect(screen.getByText(/Indisponível \(unreachable\)/)).toBeInTheDocument();
  });

  it("still reflects a manual refresh result even though a newer initial prop had not landed yet", async () => {
    refreshReadinessMock.mockResolvedValue(redisDown);
    render(<ReadinessPanel initial={ready} />);

    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(screen.getByRole("button", { name: /Atualizar/ }));

    await screen.findByText("Not Ready");
  });
});
