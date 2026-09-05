import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { searchMarketsActionMock, routerPushMock } = vi.hoisted(() => ({
  searchMarketsActionMock: vi.fn(),
  routerPushMock: vi.fn(),
}));

vi.mock("@/lib/api/markets-actions", () => ({ searchMarketsAction: searchMarketsActionMock }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: routerPushMock }) }));

afterEach(cleanup);

import { CommandPalette } from "@/components/layout/command-palette";

beforeEach(() => {
  searchMarketsActionMock.mockReset();
  routerPushMock.mockReset();
});

describe("CommandPalette: visible button + Ctrl/⌘K both open it", () => {
  it("opens on clicking the visible 'Buscar mercados' button", () => {
    render(<CommandPalette orgSlug="acme" />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Buscar mercados/ }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByLabelText("Buscar por símbolo")).toBeInTheDocument();
  });

  it("opens on Ctrl+K from anywhere", () => {
    render(<CommandPalette orgSlug="acme" />);
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

describe("CommandPalette: searches the real API (debounced), not a client-side filter", () => {
  it("calls searchMarketsAction with the typed query and renders exchange + symbol results", async () => {
    searchMarketsActionMock.mockResolvedValue({
      ok: true,
      results: [
        { exchange: "binance", symbol: "BTCUSDT" },
        { exchange: "bybit", symbol: "BTCUSDT" },
      ],
    });

    render(<CommandPalette orgSlug="acme" />);
    fireEvent.click(screen.getByRole("button", { name: /Buscar mercados/ }));
    fireEvent.change(screen.getByLabelText("Buscar por símbolo"), { target: { value: "BTC" } });

    await waitFor(() => expect(searchMarketsActionMock).toHaveBeenCalledWith("BTC"));
    expect(await screen.findAllByText("BTCUSDT")).toHaveLength(2);
    expect(screen.getByText("binance")).toBeInTheDocument();
    expect(screen.getByText("bybit")).toBeInTheDocument();
  });

  it("shows an honest error state distinct from 'no results' when the search itself fails", async () => {
    searchMarketsActionMock.mockResolvedValue({ ok: false, results: [], reason: "timeout" });

    render(<CommandPalette orgSlug="acme" />);
    fireEvent.click(screen.getByRole("button", { name: /Buscar mercados/ }));
    fireEvent.change(screen.getByLabelText("Buscar por símbolo"), { target: { value: "BTC" } });

    await screen.findByText(/Busca indisponível/);
    expect(screen.queryByText(/Nenhum mercado encontrado/)).not.toBeInTheDocument();
  });

  it("shows 'Nenhum mercado encontrado' only for a real empty result, not while still loading", async () => {
    searchMarketsActionMock.mockResolvedValue({ ok: true, results: [] });

    render(<CommandPalette orgSlug="acme" />);
    fireEvent.click(screen.getByRole("button", { name: /Buscar mercados/ }));
    fireEvent.change(screen.getByLabelText("Buscar por símbolo"), { target: { value: "zzz" } });

    await screen.findByText(/Nenhum mercado encontrado para "zzz"/);
  });
});

describe("CommandPalette: exchange/symbol segments are URL-encoded before router.push (LOW, one-liner)", () => {
  it("encodes a symbol containing a slash before navigating", async () => {
    searchMarketsActionMock.mockResolvedValue({ ok: true, results: [{ exchange: "binance", symbol: "WEIRD/SYM" }] });

    render(<CommandPalette orgSlug="acme" />);
    fireEvent.click(screen.getByRole("button", { name: /Buscar mercados/ }));
    fireEvent.change(screen.getByLabelText("Buscar por símbolo"), { target: { value: "WEIRD" } });

    await screen.findByText("WEIRD/SYM");
    fireEvent.click(screen.getByText("WEIRD/SYM"));

    expect(routerPushMock).toHaveBeenCalledWith("/acme/markets/binance/WEIRD%2FSYM");
  });
});

describe("CommandPalette: never searches below the minimum query length (M8, security)", () => {
  it("does not call searchMarketsAction for a single-character query", async () => {
    render(<CommandPalette orgSlug="acme" />);
    fireEvent.click(screen.getByRole("button", { name: /Buscar mercados/ }));
    fireEvent.change(screen.getByLabelText("Buscar por símbolo"), { target: { value: "b" } });

    // Give the (raised) debounce window plenty of time to have fired if the
    // guard were missing.
    await new Promise((resolve) => setTimeout(resolve, 300));

    expect(searchMarketsActionMock).not.toHaveBeenCalled();
    expect(screen.queryByText(/Nenhum mercado encontrado/)).not.toBeInTheDocument();
  });

  it("calls searchMarketsAction once the query reaches the minimum length", async () => {
    searchMarketsActionMock.mockResolvedValue({ ok: true, results: [] });
    render(<CommandPalette orgSlug="acme" />);
    fireEvent.click(screen.getByRole("button", { name: /Buscar mercados/ }));
    fireEvent.change(screen.getByLabelText("Buscar por símbolo"), { target: { value: "bt" } });

    await waitFor(() => expect(searchMarketsActionMock).toHaveBeenCalledWith("bt"));
  });
});

describe("CommandPalette: keyboard navigation (arrow keys move, Enter opens)", () => {
  it("moves the highlighted result with arrow keys and navigates on Enter", async () => {
    searchMarketsActionMock.mockResolvedValue({
      ok: true,
      results: [
        { exchange: "binance", symbol: "AAAUSDT" },
        { exchange: "binance", symbol: "BBBUSDT" },
      ],
    });

    render(<CommandPalette orgSlug="acme" />);
    fireEvent.click(screen.getByRole("button", { name: /Buscar mercados/ }));
    const input = screen.getByLabelText("Buscar por símbolo");
    fireEvent.change(input, { target: { value: "USDT" } });

    await screen.findByText("AAAUSDT");

    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(routerPushMock).toHaveBeenCalledWith("/acme/markets/binance/BBBUSDT");
  });
});

describe("CommandPalette: a slower, older response must not clobber a faster, newer one", () => {
  it("keeps the results for the latest query even if an earlier query's promise resolves later", async () => {
    let resolveFirst: (value: { ok: true; results: { exchange: string; symbol: string }[] }) => void = () => {};
    const firstPromise = new Promise((resolve) => {
      resolveFirst = resolve;
    });
    searchMarketsActionMock.mockImplementationOnce(() => firstPromise);
    searchMarketsActionMock.mockResolvedValueOnce({ ok: true, results: [{ exchange: "binance", symbol: "SECONDUSDT" }] });

    render(<CommandPalette orgSlug="acme" />);
    fireEvent.click(screen.getByRole("button", { name: /Buscar mercados/ }));
    const input = screen.getByLabelText("Buscar por símbolo");

    fireEvent.change(input, { target: { value: "FIR" } });
    await waitFor(() => expect(searchMarketsActionMock).toHaveBeenCalledWith("FIR"));

    fireEvent.change(input, { target: { value: "SEC" } });
    await waitFor(() => expect(searchMarketsActionMock).toHaveBeenCalledWith("SEC"));
    await screen.findByText("SECONDUSDT");

    await act(async () => {
      resolveFirst({ ok: true, results: [{ exchange: "binance", symbol: "FIRSTUSDT" }] });
      await Promise.resolve();
    });

    expect(screen.queryByText("FIRSTUSDT")).not.toBeInTheDocument();
    expect(screen.getByText("SECONDUSDT")).toBeInTheDocument();
  });
});
