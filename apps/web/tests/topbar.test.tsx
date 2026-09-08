import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const { getMarketStatusMock } = vi.hoisted(() => ({ getMarketStatusMock: vi.fn() }));
vi.mock("@/lib/api/system", () => ({ getMarketStatus: getMarketStatusMock }));
vi.mock("@/hooks/useMarketChannels", () => ({ useMarketChannels: () => ({ status: "closed", messages: {} }) }));
vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({ getToken: async () => null }),
  UserButton: () => null,
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));

import { Topbar } from "@/components/layout/topbar";
import { ApiError } from "@/lib/api-error";

beforeEach(() => {
  getMarketStatusMock.mockReset().mockRejectedValue(new Error("market-status down"));
});

afterEach(cleanup);

describe("Topbar: 'sem verificação' is distinct from a real outage (T1.5b joint decision #5, H11)", () => {
  it("shows 'Sistema: sem verificação' (not 'Sistema indisponível') when the /ready check itself never ran (status is null)", async () => {
    const jsx = await Topbar({ orgSlug: "acme", systemStatus: null });
    render(jsx);

    expect(screen.getByText("Sistema: sem verificação")).toBeInTheDocument();
    expect(screen.queryByText("Sistema indisponível")).not.toBeInTheDocument();
  });

  it("shows the real 'Sistema indisponível' when the check ran and both dependencies failed", async () => {
    const jsx = await Topbar({ orgSlug: "acme", systemStatus: { database: false, redis: false } });
    render(jsx);

    expect(screen.getByText("Sistema indisponível")).toBeInTheDocument();
    expect(screen.queryByText("Sistema: sem verificação")).not.toBeInTheDocument();
  });

  it("shows 'Sistema operacional' when both dependencies are healthy", async () => {
    const jsx = await Topbar({ orgSlug: "acme", systemStatus: { database: true, redis: true } });
    render(jsx);

    expect(screen.getByText("Sistema operacional")).toBeInTheDocument();
  });
});

describe("Topbar: a failed market-status widget FETCH is not the same fact as the markets being down (LOW, T1.5b fix pass)", () => {
  it("says 'Status dos mercados indisponível', with a real reason and a retry, when /system/market-status fails to load (T3.28b)", async () => {
    const jsx = await Topbar({ orgSlug: "acme", systemStatus: { database: true, redis: true } });
    render(jsx);

    expect(screen.getByText(/Status dos mercados indisponível: erro desconhecido/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tentar de novo" })).toBeInTheDocument();
    expect(screen.queryByText(/^mercados indisponível/)).not.toBeInTheDocument();
  });

  it("surfaces the API's own detail instead of a generic message when it is a typed ApiError (T3.28b)", async () => {
    getMarketStatusMock.mockReset().mockRejectedValue(new ApiError({ type: "about:blank", title: "Too Many Requests", status: 429, detail: "Rate limit exceeded." }));

    const jsx = await Topbar({ orgSlug: "acme", systemStatus: { database: true, redis: true } });
    render(jsx);

    expect(screen.getByText(/Status dos mercados indisponível: Rate limit exceeded\./)).toBeInTheDocument();
  });
});
