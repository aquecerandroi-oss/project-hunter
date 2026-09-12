/**
 * "Vender agora (REAL)" (T4.17 deliverable 3): the same double confirmation
 * as approving REAL, here typing the word "VENDER" instead of the size.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { sellNowLiveActionMock, refreshMock } = vi.hoisted(() => ({ sellNowLiveActionMock: vi.fn(), refreshMock: vi.fn() }));

vi.mock("@/lib/api/meme-live-actions", () => ({ sellNowLiveAction: sellNowLiveActionMock }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: refreshMock }) }));

afterEach(() => {
  cleanup();
  sellNowLiveActionMock.mockReset();
  refreshMock.mockReset();
});

import { LivePositionsSection } from "@/components/meme-live/live-positions-section";
import type { LivePosition } from "@/lib/api/meme-live-types";

function position(overrides: Partial<LivePosition> = {}): LivePosition {
  return {
    id: "position-1",
    proposal_id: "proposal-1",
    mint: "Fh42kAfy27CGoUA8CgFwpTGMubzndaAyTy2gghu5pump",
    status: "open",
    entry_at: "2026-09-12T18:00:00Z",
    tokens: 1_000_000,
    sol_spent: "0.02",
    initial_risk_sol: "0.02",
    params: {},
    mark_sol: "0.025",
    mark_at: "2026-09-12T18:05:00Z",
    mark_source: "solana_rpc",
    mark_reason: null,
    high_water_sol: "0.03",
    exit_intent: null,
    sell_requested_at: null,
    sell_requested_by: null,
    exit_at: null,
    exit: null,
    sol_received: null,
    pnl_sol: null,
    r_multiple: null,
    migrated: false,
    can_sell_now: true,
    ...overrides,
  };
}

const NOW_MS = new Date("2026-09-12T18:06:00Z").getTime();

describe("LivePositionsSection: an honest empty state when there is nothing open", () => {
  it("says so, never an empty table", () => {
    render(<LivePositionsSection orgSlug="ever" orgId="org-1" positions={[]} canOperate={true} nowMs={NOW_MS} />);
    expect(screen.getByText("Nenhuma posição real aberta agora.")).toBeInTheDocument();
  });
});

describe("LivePositionsSection: 'Vender agora (REAL)' gated and two-step", () => {
  it("is disabled without the Trader role", () => {
    render(<LivePositionsSection orgSlug="ever" orgId="org-1" positions={[position()]} canOperate={false} nowMs={NOW_MS} />);
    const button = screen.getByRole("button", { name: "Vender agora (REAL)" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("title", "Requer o papel Trader ou superior nesta organização.");
  });

  it("is disabled when the position itself is not sellable now (a request is already pending)", () => {
    render(<LivePositionsSection orgSlug="ever" orgId="org-1" positions={[position({ can_sell_now: false, sell_requested_at: "2026-09-12T18:05:30Z", sell_requested_by: "operador" })]} canOperate={true} nowMs={NOW_MS} />);
    const button = screen.getByRole("button", { name: "Vender agora (REAL)" });
    expect(button).toBeDisabled();
    expect(screen.getByText(/venda solicitada em/)).toBeInTheDocument();
  });

  it("step (a) shows the mainnet warning; step (b) requires typing VENDER before the red button unlocks", () => {
    render(<LivePositionsSection orgSlug="ever" orgId="org-1" positions={[position()]} canOperate={true} nowMs={NOW_MS} />);
    fireEvent.click(screen.getByRole("button", { name: "Vender agora (REAL)" }));
    expect(screen.getByText(/Isto assina uma transação real na mainnet\./)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Continuar" }));
    const confirm = screen.getByRole("button", { name: "Confirmar venda (REAL)" });
    expect(confirm).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Digite VENDER/), { target: { value: "vender" } });
    expect(confirm).toBeEnabled();
  });

  it("Voltar/Cancelar return to the plain button without submitting", () => {
    render(<LivePositionsSection orgSlug="ever" orgId="org-1" positions={[position()]} canOperate={true} nowMs={NOW_MS} />);
    fireEvent.click(screen.getByRole("button", { name: "Vender agora (REAL)" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(screen.getByRole("button", { name: "Vender agora (REAL)" })).toBeInTheDocument();
    expect(sellNowLiveActionMock).not.toHaveBeenCalled();
  });

  it("confirms with a fresh Idempotency-Key and refreshes on success", async () => {
    sellNowLiveActionMock.mockResolvedValueOnce({ ok: true, data: { position_id: "position-1", status: "open", sell_requested_at: "2026-09-12T18:06:00Z", sell_requested_by: "u1", already_requested: false } });
    render(<LivePositionsSection orgSlug="ever" orgId="org-1" positions={[position()]} canOperate={true} nowMs={NOW_MS} />);
    fireEvent.click(screen.getByRole("button", { name: "Vender agora (REAL)" }));
    fireEvent.click(screen.getByRole("button", { name: "Continuar" }));
    fireEvent.change(screen.getByLabelText(/Digite VENDER/), { target: { value: "VENDER" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirmar venda (REAL)" }));

    await waitFor(() => expect(sellNowLiveActionMock).toHaveBeenCalledTimes(1));
    const [orgId, positionId] = sellNowLiveActionMock.mock.calls[0] as [string, string, string];
    expect(orgId).toBe("org-1");
    expect(positionId).toBe("position-1");
    await waitFor(() => expect(refreshMock).toHaveBeenCalledTimes(1));
  });

  it("shows a named refusal in Portuguese, never a raw type/status", async () => {
    sellNowLiveActionMock.mockResolvedValueOnce({
      ok: false,
      problem: { type: "https://hunter.dev/problems/meme-live-position-not-found", title: "Not Found", status: 404 },
    });
    render(<LivePositionsSection orgSlug="ever" orgId="org-1" positions={[position()]} canOperate={true} nowMs={NOW_MS} />);
    fireEvent.click(screen.getByRole("button", { name: "Vender agora (REAL)" }));
    fireEvent.click(screen.getByRole("button", { name: "Continuar" }));
    fireEvent.change(screen.getByLabelText(/Digite VENDER/), { target: { value: "VENDER" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirmar venda (REAL)" }));
    expect(await screen.findByText("Posição real não encontrada — a lista será atualizada.")).toBeInTheDocument();
  });

  it("a blocked exit intent (e.g. migrated to PumpSwap) is shown, labeled, never a raw code", () => {
    render(<LivePositionsSection orgSlug="ever" orgId="org-1" positions={[position({ exit_intent: { blocked: "pumpswap_sell_not_implemented", reason: "migrated" } })]} canOperate={true} nowMs={NOW_MS} />);
    expect(screen.getByText(/venda no PumpSwap ainda não existe/)).toBeInTheDocument();
  });
});
