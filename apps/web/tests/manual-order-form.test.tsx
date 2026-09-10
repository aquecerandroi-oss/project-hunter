/**
 * T3.72b HIGH finding #1: `resetForRetry` ("Enviar outra ordem") must
 * generate a fresh `Idempotency-Key` and clear the market/stop/notional
 * fields -- reusing the key for a genuinely different order body would 409
 * `order_replay_conflict` (the API remembers the key's original body,
 * `manual-orders-actions.ts`'s own docstring). A network retry of the SAME
 * submission (the trader clicks "Enviar ordem" again while the form still
 * shows the same fields, before any `filedOrder` ever landed) is the one
 * case that must reuse the key -- that is the header's entire purpose.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { SpotMarketOption } from "@/lib/api/markets-actions";

const { fileManualOrderActionMock } = vi.hoisted(() => ({
  fileManualOrderActionMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

// Real polling (setInterval + a second Server Action) is orthogonal to the
// idempotency-key question this file tests -- stubbed out so tests do not
// need fake timers.
vi.mock("@/hooks/useManualOrderPoll", () => ({
  useManualOrderPoll: () => null,
}));

vi.mock("@/lib/api/manual-orders-actions", () => ({
  fileManualOrderAction: fileManualOrderActionMock,
}));

const MARKET: SpotMarketOption = {
  id: "3f6b3b9a-6b1a-4e6a-9c1a-000000000001",
  exchange: "binance",
  symbol: "BTCUSDT",
  status: "active",
  is_monitored: true,
  quote_asset: "USDT",
  last_price: "65000",
  volume_24h: "100000000",
};

// The market picker's own search (`useSpotMarketSearch`) is a different
// concern (covered by its own tests) -- stubbed here to a single button so
// this file can select/clear a market deterministically.
vi.mock("@/components/portfolio/manual-order-market-field", () => ({
  ManualOrderMarketField: ({
    value,
    onChange,
    disabled,
  }: {
    value: SpotMarketOption | null;
    onChange: (market: SpotMarketOption) => void;
    disabled?: boolean;
  }) =>
    value ? (
      <span>{value.symbol}</span>
    ) : (
      <button type="button" disabled={disabled} onClick={() => onChange(MARKET)}>
        Selecionar mercado
      </button>
    ),
}));

afterEach(() => {
  cleanup();
  fileManualOrderActionMock.mockReset();
});

import { Dialog } from "@/components/ui/dialog";
import { ManualOrderForm } from "@/components/portfolio/manual-order-form";

/** `ManualOrderFiledStatus`'s "Fechar" button is a `DialogClose`, which needs a `Dialog` ancestor -- matches how `manual-order-section.tsx` actually mounts this form. */
function renderForm() {
  return render(
    <Dialog open>
      <ManualOrderForm orgId="org-1" portfolioId="wallet-1" maxStopDistancePct="0.03" onSettled={vi.fn()} />
    </Dialog>,
  );
}

function selectMarketAndStop(stop: string): void {
  fireEvent.click(screen.getByRole("button", { name: "Selecionar mercado" }));
  fireEvent.change(screen.getByLabelText("Stop"), { target: { value: stop } });
}

function decidedResponse() {
  return {
    ok: true as const,
    data: {
      request_id: `req-${Math.random()}`,
      market_id: MARKET.id,
      direction: "long" as const,
      status: "decided" as const,
      filed_at: new Date().toISOString(),
      decision: null,
    },
  };
}

describe("ManualOrderForm: Idempotency-Key per submission", () => {
  it("generates a new Idempotency-Key for a genuinely new order after 'Enviar outra ordem'", async () => {
    fileManualOrderActionMock.mockResolvedValueOnce(decidedResponse());

    renderForm();

    selectMarketAndStop("60000");
    fireEvent.click(screen.getByRole("button", { name: "Enviar ordem" }));

    await waitFor(() => expect(fileManualOrderActionMock).toHaveBeenCalledTimes(1));
    const [, , firstKey, firstBody] = fileManualOrderActionMock.mock.calls[0] as [string, string, string, { stop: string }];
    expect(firstBody.stop).toBe("60000");

    fireEvent.click(await screen.findByRole("button", { name: "Enviar outra ordem" }));

    // Back on a blank form -- selecting the market again is required, proof the field was cleared.
    expect(screen.getByRole("button", { name: "Selecionar mercado" })).toBeInTheDocument();

    fileManualOrderActionMock.mockResolvedValueOnce(decidedResponse());
    selectMarketAndStop("61000");
    fireEvent.click(screen.getByRole("button", { name: "Enviar ordem" }));

    await waitFor(() => expect(fileManualOrderActionMock).toHaveBeenCalledTimes(2));
    const [, , secondKey, secondBody] = fileManualOrderActionMock.mock.calls[1] as [string, string, string, { stop: string }];

    expect(secondKey).not.toBe(firstKey);
    expect(secondBody.stop).toBe("61000");
  });

  it("reuses the same Idempotency-Key when retrying the SAME submission after a failed attempt", async () => {
    fileManualOrderActionMock.mockResolvedValueOnce({
      ok: false,
      problem: {
        type: "https://hunter.dev/problems/unexpected-response",
        title: "Erro",
        status: 502,
        detail: "Falha de rede.",
      },
    });

    renderForm();

    selectMarketAndStop("60000");
    fireEvent.click(screen.getByRole("button", { name: "Enviar ordem" }));

    await waitFor(() => expect(fileManualOrderActionMock).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/tente novamente em instantes/i)).toBeInTheDocument();

    fileManualOrderActionMock.mockResolvedValueOnce(decidedResponse());
    // Same button, same untouched fields -- a retry of the SAME submission, not a new one.
    fireEvent.click(screen.getByRole("button", { name: "Enviar ordem" }));

    await waitFor(() => expect(fileManualOrderActionMock).toHaveBeenCalledTimes(2));
    const firstKey = fileManualOrderActionMock.mock.calls[0]?.[2] as string;
    const secondKey = fileManualOrderActionMock.mock.calls[1]?.[2] as string;

    expect(secondKey).toBe(firstKey);
  });
});
