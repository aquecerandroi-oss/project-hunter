import { describe, expect, it } from "vitest";

import { exitReasonLabel, memeDeskProblemMessage, proposalStatusLabel, quoteReasonLabel, refusalLabel } from "@/components/meme-desk/labels";
import { MEME_EXIT_REASONS, MEME_PROPOSAL_STATUSES } from "@/lib/api/meme-desk-types";

describe("meme-desk labels are exhaustive and never leak a raw enum", () => {
  it("every proposal status has a Portuguese label", () => {
    for (const status of MEME_PROPOSAL_STATUSES) {
      const label = proposalStatusLabel(status);
      expect(label).not.toBe(status);
      expect(label.length).toBeGreaterThan(3);
    }
    expect(proposalStatusLabel("something_new")).toBe("estado não previsto");
  });

  it("every exit reason has a label; null is honest", () => {
    for (const reason of MEME_EXIT_REASONS) {
      expect(exitReasonLabel(reason)).not.toBe(reason);
    }
    expect(exitReasonLabel(null)).toBe("saída sem motivo registrado");
  });

  it("refusals named by the loop are translated; unknown ones are still shown", () => {
    expect(refusalLabel("daily_loss_cap")).toBe("teto de perda diária do conjunto atingido");
    expect(refusalLabel("weird_new_reason")).toBe("recusa: weird_new_reason");
    expect(refusalLabel(null)).toBeNull();
  });

  it("quote reasons", () => {
    expect(quoteReasonLabel("no_snapshot_yet")).toContain("sem fotografia");
    expect(quoteReasonLabel(null)).toBe("sem cotação registrada");
  });
});

describe("memeDeskProblemMessage: one sentence per named refusal", () => {
  const base = { title: "x", status: 422 };

  it("maps a (reason: ...) in detail before anything else", () => {
    const message = memeDeskProblemMessage({ ...base, type: "https://hunter.dev/problems/meme-desk-refused", detail: "size_sol 0.6 exceeds ... (reason: exceeds_max_sol_per_bet)" });
    expect(message).toContain("teto por aposta");
  });

  it("maps the 409 state conflicts", () => {
    expect(memeDeskProblemMessage({ ...base, status: 409, type: "https://hunter.dev/problems/meme-proposal-state-conflict", detail: "proposal x is 'approved' (reason: not_proposed)" })).toContain("já foi decidida");
    expect(memeDeskProblemMessage({ ...base, status: 409, type: "https://hunter.dev/problems/meme-bet-state-conflict", detail: "bet x is 'open' (reason: sell_now_already_pending)" })).toContain("Vender agora pendente");
  });

  it("maps role and idempotency conflicts without the raw slug", () => {
    expect(memeDeskProblemMessage({ ...base, status: 403, type: "https://hunter.dev/problems/insufficient-role" })).toContain("Trader");
    expect(memeDeskProblemMessage({ ...base, status: 409, type: "https://hunter.dev/problems/idempotency-key-conflict" })).toContain("chave de envio");
  });

  it("falls back by status code, never echoing the type", () => {
    const message = memeDeskProblemMessage({ ...base, status: 500, type: "https://hunter.dev/problems/something-else" });
    expect(message).not.toContain("something-else");
    expect(message).toContain("indisponível");
  });
});
