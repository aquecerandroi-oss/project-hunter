/**
 * "Comprar manual" (T4.7) and its REAL sibling "Registrar (REAL)" (T4.17):
 * off by default, only ever enabled when `liveAvailable` (the executor is
 * `ligado`), with the same two-step confirmation as the proposal card.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { fileManualProposalActionMock } = vi.hoisted(() => ({ fileManualProposalActionMock: vi.fn() }));
vi.mock("@/lib/api/meme-desk-actions", () => ({ fileManualProposalAction: fileManualProposalActionMock }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

afterEach(() => {
  cleanup();
  fileManualProposalActionMock.mockReset();
});

import { ManualBuyDialog } from "@/components/meme-desk/manual-buy-dialog";

function openDialog() {
  fireEvent.click(screen.getByRole("button", { name: "Comprar manual" }));
}

function fillParams() {
  fireEvent.change(screen.getByLabelText("Mint (pump.fun)"), { target: { value: "Fh42kAfy27CGoUA8CgFwpTGMubzndaAyTy2gghu5pump" } });
  fireEvent.change(screen.getByLabelText("Tamanho (SOL)"), { target: { value: "0.02" } });
  fireEvent.change(screen.getByLabelText("Alvo (×)"), { target: { value: "2" } });
  fireEvent.change(screen.getByLabelText("Trailing (%)"), { target: { value: "30" } });
  fireEvent.change(screen.getByLabelText("Espera máx (s)"), { target: { value: "900" } });
}

describe("ManualBuyDialog: 'Registrar (REAL)' gated by the executor's own state", () => {
  it("is disabled with a named reason when the executor is not ligado", () => {
    render(<ManualBuyDialog orgId="org-1" canOperate={true} liveAvailable={false} />);
    openDialog();
    const button = screen.getByRole("button", { name: "Registrar (REAL)" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("title", "O executor real não está ligado — veja o painel Executor real.");
  });

  it("is enabled once liveAvailable is true, and opens the two-step REAL confirmation", () => {
    render(<ManualBuyDialog orgId="org-1" canOperate={true} liveAvailable={true} />);
    openDialog();
    fillParams();
    expect(screen.getByRole("button", { name: "Registrar (REAL)" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Registrar (REAL)" }));
    expect(screen.getByText(/Isto assina uma transação real na mainnet\./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Assinar e enviar (REAL)" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Digite o tamanho em SOL/), { target: { value: "0.02" } });
    expect(screen.getByRole("button", { name: "Assinar e enviar (REAL)" })).toBeEnabled();
  });

  it("submits mode: 'live' only after the size is confirmed", async () => {
    fileManualProposalActionMock.mockResolvedValueOnce({ ok: true, data: { row: { id: "p1", status: "approved" } } });
    render(<ManualBuyDialog orgId="org-1" canOperate={true} liveAvailable={true} />);
    openDialog();
    fillParams();
    fireEvent.click(screen.getByRole("button", { name: "Registrar (REAL)" }));
    fireEvent.change(screen.getByLabelText(/Digite o tamanho em SOL/), { target: { value: "0.02" } });
    fireEvent.click(screen.getByRole("button", { name: "Assinar e enviar (REAL)" }));

    await waitFor(() => expect(fileManualProposalActionMock).toHaveBeenCalledTimes(1));
    const [orgId, , body] = fileManualProposalActionMock.mock.calls[0] as [string, string, { mode: string; mint: string }];
    expect(orgId).toBe("org-1");
    expect(body.mode).toBe("live");
    expect(body.mint).toBe("Fh42kAfy27CGoUA8CgFwpTGMubzndaAyTy2gghu5pump");
  });

  it("the ordinary paper 'Registrar compra (papel)' is unaffected by liveAvailable", () => {
    render(<ManualBuyDialog orgId="org-1" canOperate={true} liveAvailable={false} />);
    openDialog();
    expect(screen.getByRole("button", { name: "Registrar compra (papel)" })).toBeEnabled();
  });
});
