/**
 * T4.28c -- the "Modo sozinho — estágio 1" block's pure helpers: the hourly
 * approved/refused line, the written scope's usage, the skip vocabulary and
 * the gates-reload/kill-switch-latch sentences. No React here (`auto-stage1-panel.test.tsx`
 * covers rendering) -- only the arithmetic and the vocabulary, CLAUDE.md's
 * "unavailable never becomes zero" proved for every missing field.
 */
import { describe, expect, it } from "vitest";

import { autoApprovedLine, autoScopeLine } from "@/components/meme-live/live-format";
import { autoSkipLabel, gatesReloadErrorLabel, killSwitchLatchReasonLabel, scopeExhaustedLabel } from "@/components/meme-live/refusal-labels";

describe("autoApprovedLine: 'aprovadas na hora N / M', never a fabricated total", () => {
  it("both numbers present", () => {
    expect(autoApprovedLine(2, 5)).toBe("aprovadas na hora: 2 de 5");
  });

  it("both missing says so plainly", () => {
    expect(autoApprovedLine(null, null)).toBe("aprovadas na hora: sem leitura");
  });

  it("only one missing keeps the other, never invents the gap", () => {
    expect(autoApprovedLine(null, 5)).toContain("sem leitura");
    expect(autoApprovedLine(null, 5)).toContain("teto 5");
    expect(autoApprovedLine(2, null)).toContain("2");
    expect(autoApprovedLine(2, null)).toContain("sem leitura");
  });

  it("zero approved is shown as zero, not as 'sem leitura'", () => {
    expect(autoApprovedLine(0, 5)).toBe("aprovadas na hora: 0 de 5");
  });
});

describe("autoScopeLine: the written small-test scope's usage, from gates + the executor's counters", () => {
  const GATES = {
    live: true,
    small_test: { authorized_by: "Everton", max_sol_per_trade: "0.05", max_total_sol: "0.25", max_trades: 5, expires_at: "2026-09-20T00:00:00Z", decision_note: "x" },
  };

  it("a partly spent scope names ceilings and usage together", () => {
    const line = autoScopeLine(GATES, { usedSol: "0.18", remainingSol: "0.07", tradesDone: 3, exhausted: null });
    expect(line.tradesLine).toBe("compras: 3 de 5");
    expect(line.solLine).toContain("usado");
    expect(line.solLine).toContain("restante");
    expect(line.solLine).toContain("teto");
    expect(line.exhaustedLabel).toBeNull();
  });

  it("no gates at all (portões vermelhos) says 'sem leitura', never a bare zero", () => {
    const line = autoScopeLine(null, { usedSol: null, remainingSol: null, tradesDone: null, exhausted: null });
    expect(line.tradesLine).toBe("compras: sem leitura");
    expect(line.solLine).toBe("SOL do escopo: sem leitura");
  });

  it("an exhausted scope carries the badge label, by counter name", () => {
    const byTrades = autoScopeLine(GATES, { usedSol: "0.10", remainingSol: "0.15", tradesDone: 5, exhausted: "max_trades" });
    expect(byTrades.exhaustedLabel).toBe(scopeExhaustedLabel("max_trades"));
    const bySol = autoScopeLine(GATES, { usedSol: "0.25", remainingSol: "0", tradesDone: 2, exhausted: "max_total_sol" });
    expect(bySol.exhaustedLabel).toBe(scopeExhaustedLabel("max_total_sol"));
  });

  it("counters present without gates (small_test absent) still shows what is known", () => {
    const line = autoScopeLine({ live: true, signed_by: "Everton", valid_until: "2026-12-01T00:00:00Z" }, { usedSol: "0.02", remainingSol: null, tradesDone: 1, exhausted: null });
    expect(line.tradesLine).toBe("compras: 1");
    expect(line.solLine).toContain("usado");
  });
});

describe("autoSkipLabel: the stage-1 pre-filter vocabulary, exhaustive with a named fallback", () => {
  it("every named skip reason from auto_approve.py has a sentence", () => {
    for (const code of ["expired", "too_old", "mint_busy", "recently_refused", "suggested_incomplete", "exceeds_max_sol_per_bet", "hourly_cap", "tick_cap", "mint_repeated", "decided_concurrently", "kill_switch", "program_upgraded"]) {
      expect(autoSkipLabel(code)).not.toBe(code);
    }
  });

  it("the dynamic scope_exhausted:<reason> prefix keeps the reason", () => {
    expect(autoSkipLabel("scope_exhausted:max_trades")).toContain("nº de compras");
    expect(autoSkipLabel("scope_exhausted:max_total_sol")).toContain("SOL do escopo");
    expect(autoSkipLabel("scope_exhausted:something_new")).toContain("something_new");
  });

  it("never returns the bare code -- an unrecognized one is still prefixed", () => {
    expect(autoSkipLabel("never_seen_before")).toBe("pulo: never_seen_before");
  });
});

describe("gatesReloadErrorLabel: the reload's own failure vocabulary, distinct from the admission's", () => {
  it("no error at all is null, not an empty sentence", () => {
    expect(gatesReloadErrorLabel(null)).toBeNull();
    expect(gatesReloadErrorLabel(undefined)).toBeNull();
    expect(gatesReloadErrorLabel("")).toBeNull();
  });

  it("a latched semantic failure names the gate", () => {
    expect(gatesReloadErrorLabel("gates_expired")).toContain("trava dos portões");
    expect(gatesReloadErrorLabel("gates_expired")).toContain("expirada");
    expect(gatesReloadErrorLabel("auto_approve_needs_small_test")).toContain("modo sozinho");
  });

  it("a deferred parse failure (T4.28f grace) says the previous policy still holds", () => {
    const label = gatesReloadErrorLabel("deferred:gates_file_invalid");
    expect(label).toContain("leitura anterior mantida");
    expect(label).toContain("ilegível");
  });

  it("an unrecognized reason is still shown, never a bare slug", () => {
    expect(gatesReloadErrorLabel("something_new")).toContain("something_new");
  });
});

describe("killSwitchLatchReasonLabel: the wallet's daily-loss latch or a gates_invalid: reason from T4.28d", () => {
  it("not latched is null", () => {
    expect(killSwitchLatchReasonLabel(null)).toBeNull();
  });

  it("the daily-loss latch reuses the admission's own sentence", () => {
    expect(killSwitchLatchReasonLabel("daily_loss_cap_reached")).toContain("perda diária");
  });

  it("a gates_invalid: reason names the gate, not the raw code", () => {
    const label = killSwitchLatchReasonLabel("gates_invalid:gates_file_invalid");
    expect(label).toContain("portões inválidos");
    expect(label).toContain("ilegível");
    expect(label).not.toContain("gates_invalid:");
  });

  it("an unrecognized reason is still shown, never silently dropped", () => {
    expect(killSwitchLatchReasonLabel("something_new")).toContain("something_new");
  });
});
