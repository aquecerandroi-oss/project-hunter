import { describe, expect, it } from "vitest";

import { betLegLabel, exitReasonLabel, memeDeskProblemMessage, proposalStatusLabel, quoteReasonLabel, refusalLabel } from "@/components/meme-desk/labels";
import { MEME_BET_LEGS, MEME_EXIT_REASONS, MEME_PROPOSAL_STATUSES, isMemeBetLeg, readBetLeg } from "@/lib/api/meme-desk-types";

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
    // T4.13: the API's `ExitReason` has nine members since T4.10a (`max_loss`, `line_broken`).
    expect(MEME_EXIT_REASONS).toEqual(["target", "trailing", "time_stop", "migrated", "creator_dump", "sell_now", "rug_no_snapshot", "max_loss", "line_broken", "dead"]);
    for (const reason of MEME_EXIT_REASONS) {
      expect(exitReasonLabel(reason)).not.toBe(reason);
    }
    expect(exitReasonLabel(null)).toBe("saída sem motivo registrado");
    expect(exitReasonLabel("something_new")).toBe("motivo não previsto");
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

  // T4.10b: `meme_paper_bets.leg` (brief T4.10 §Conjuntos de regras) -- the
  // hype probe and its second leg get the exact words the brief asks for.
  it("every bet leg has a label; the probe and the scale say what the brief says", () => {
    expect(MEME_BET_LEGS).toEqual(["probe", "scale", "single"]);
    for (const leg of MEME_BET_LEGS) {
      expect(betLegLabel(leg)).not.toBe(leg);
      expect(betLegLabel(leg).length).toBeGreaterThan(3);
    }
    expect(betLegLabel("probe")).toBe("semi-comprado (sonda)");
    expect(betLegLabel("scale")).toBe("escalado (perna 2)");
    expect(betLegLabel("something_new")).toBe("perna não prevista");
    expect(isMemeBetLeg("probe")).toBe(true);
    expect(isMemeBetLeg("nope")).toBe(false);
  });

  it("readBetLeg tolerates a payload from before the column existed", () => {
    expect(readBetLeg({ id: "bet-1" })).toEqual({ leg: null, parentBetId: null });
    expect(readBetLeg({ id: "bet-2", leg: "scale", parent_bet_id: "bet-1" })).toEqual({ leg: "scale", parentBetId: "bet-1" });
    // A leg the screen does not know is reported as null, never rendered raw.
    expect(readBetLeg({ id: "bet-3", leg: "weird", parent_bet_id: null })).toEqual({ leg: null, parentBetId: null });
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
