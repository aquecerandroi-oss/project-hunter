import { describe, expect, it } from "vitest";

import {
  countdownLabel,
  emptyProposalsLabel,
  formatDuration,
  formatMultiple,
  formatR,
  formatSolSigned,
  loopStateLabel,
  minutesSinceNewestProposal,
  multiplyDecimalStrings,
  partitionDesk,
  remainingHoldLabel,
  signClass,
  solToUsd,
} from "@/components/meme-desk/meme-desk-format";
import type { MemeDeskBet, MemeDeskRow } from "@/lib/api/meme-desk-types";

const NOW_ISO = "2026-09-12T12:00:00Z"; // 09:00 Brasília
const NOW_MS = new Date(NOW_ISO).getTime();

function bet(overrides: Partial<MemeDeskBet> = {}): MemeDeskBet {
  return {
    id: "bet-1",
    status: "open",
    mode: "paper",
    entry_at: "2026-09-12T11:51:00Z",
    sol_spent: "0.2",
    fee_sol: "0.0035",
    tokens: "21000000",
    initial_risk_sol: "0.2",
    params: { size_sol: "0.2", target_x: "2", trailing_pct: "30", max_hold_s: 900, note: null },
    hold_deadline_at: "2026-09-12T12:06:00Z",
    mark_sol: "0.25",
    mark_at: "2026-09-12T11:59:00Z",
    high_water_x: "1.3",
    pnl_sol: null,
    r_multiple: null,
    unrealized_pnl_sol: "0.05",
    unrealized_r: "0.25",
    exit_at: null,
    exit_reason: null,
    sol_received: null,
    sol_usd_at_entry: "180",
    sol_usd_at_exit: null,
    // T4.10a: `leg` and `parent_bet_id` are required in the generated type.
    leg: "single",
    parent_bet_id: null,
    ...overrides,
  };
}

function row(overrides: Partial<MemeDeskRow> = {}): MemeDeskRow {
  return {
    id: `p-${Math.random()}`,
    mint: "Fh42kAfy27CGoUA8CgFwpTGMubzndaAyTy2gghu5pump",
    origin: "rules",
    status: "proposed",
    proposed_at: "2026-09-12T11:59:30Z",
    expires_at: "2026-09-12T12:01:30Z",
    features_end_time: null,
    quote: { observed_at: null, source: null, mcap_sol: null, curve_progress_pct: null, price_sol_per_token: null, size_sol: null, fee_pct: null, fee_sol: null, cost_sol: null, tokens: null, reason: "no_snapshot_yet" },
    reasons: [],
    suggested: { size_sol: "0.2", target_x: "2", trailing_pct: "30", max_hold_s: 900, note: null },
    decision: null,
    decided_by: null,
    decided_at: null,
    refusal: null,
    token: null,
    rule_set: null,
    bet: null,
    ...overrides,
  };
}

describe("partitionDesk: five honest sections, Brasília day for 'fechadas hoje'", () => {
  it("routes each row by proposal status and bet state", () => {
    const rows = [
      row({ id: "proposed", status: "proposed" }),
      row({ id: "awaiting", status: "approved" }),
      row({ id: "open", status: "filled", bet: bet() }),
      row({ id: "closed-today", status: "filled", bet: bet({ status: "closed", exit_at: "2026-09-12T11:00:00Z", pnl_sol: "0.18" }) }),
      // 23:30 Brasília the day before (02:30 UTC same calendar day in UTC!) -- must NOT count as today
      row({ id: "closed-yesterday", status: "filled", bet: bet({ status: "closed", exit_at: "2026-09-12T02:30:00Z", pnl_sol: "-0.02" }) }),
      row({ id: "rejected", status: "rejected" }),
      row({ id: "unfilled", status: "unfilled", refusal: "daily_loss_cap" }),
    ];
    const sections = partitionDesk(rows, NOW_ISO);
    expect(sections.proposals.map((r) => r.id)).toEqual(["proposed"]);
    expect(sections.awaitingFill.map((r) => r.id)).toEqual(["awaiting"]);
    expect(sections.open.map((r) => r.id)).toEqual(["open"]);
    expect(sections.closedToday.map((r) => r.id)).toEqual(["closed-today"]);
    expect(sections.recent.map((r) => r.id)).toEqual(["closed-yesterday", "rejected", "unfilled"]);
  });
});

describe("countdownLabel / formatDuration", () => {
  it("counts down to expires_at with a space before the unit", () => {
    expect(countdownLabel("2026-09-12T12:01:30Z", NOW_MS)).toBe("expira em 1 min 30 s");
    expect(countdownLabel("2026-09-12T12:00:45Z", NOW_MS)).toBe("expira em 45 s");
  });

  it("says it expired instead of counting negative", () => {
    expect(countdownLabel("2026-09-12T11:59:55Z", NOW_MS)).toBe("expirou há 5 s");
  });

  it("never invents a deadline for an unparseable timestamp", () => {
    expect(countdownLabel("not-a-date", NOW_MS)).toBe("prazo desconhecido");
  });

  it("formats hours with zero-padded minutes", () => {
    expect(formatDuration(2 * 3_600_000 + 5 * 60_000)).toBe("2 h 05 min");
  });
});

describe("remainingHoldLabel", () => {
  it("shows the remaining hold and, past it, says the loop closes on the next snapshot", () => {
    expect(remainingHoldLabel("2026-09-12T12:06:00Z", NOW_MS)).toBe("espera restante 6 min 0 s");
    expect(remainingHoldLabel("2026-09-12T11:59:30Z", NOW_MS)).toBe("espera vencida há 30 s — fecha na próxima fotografia");
  });

  it("says when max_hold_s was never written instead of guessing one", () => {
    expect(remainingHoldLabel(null, NOW_MS)).toBe("espera máxima não informada");
  });
});

describe("money helpers are decimal-safe", () => {
  it("multiplies two decimal strings exactly (BigInt, no float)", () => {
    expect(multiplyDecimalStrings("4.98", "181")).toBe("901.38");
    expect(multiplyDecimalStrings("0.1", "0.2")).toBe("0.02");
    expect(multiplyDecimalStrings("-0.02", "180")).toBe("-3.60");
    expect(multiplyDecimalStrings("9007199254740993", "1.1")).toBe("9907919180215092.3");
  });

  it("converts SOL to US$ at the observed rate", () => {
    expect(solToUsd("4.98", "181")).toBe("US$ 901.38");
  });

  it("signs SOL amounts explicitly and colors them semantically", () => {
    expect(formatSolSigned("0.18")).toBe("+0.1800 SOL");
    expect(formatSolSigned("-0.02")).toBe("-0.0200 SOL");
    expect(formatSolSigned("0")).toBe("0.0000 SOL");
    expect(signClass("0.18")).toBe("text-green");
    expect(signClass("-0.02")).toBe("text-red");
    expect(signClass("0")).toBe("text-fg-muted");
    expect(signClass(null)).toBe("text-fg-muted");
  });

  it("formats multiples and R", () => {
    expect(formatMultiple("2")).toBe("2.00×");
    expect(formatR("0.9")).toBe("0.90 R");
  });
});

describe("loopStateLabel: vivo ≠ parado ≠ sem leitura (contract §Semântica 5)", () => {
  it("is alive within three ticks", () => {
    const state = loopStateLabel({ lastTickAt: "2026-09-12T11:59:20Z", reason: null }, NOW_MS);
    expect(state.tone).toBe("alive");
    expect(state.label).toBe("laço vivo · último tick há 40 s");
  });

  it("is stopped after three missed ticks, naming when it last ran (Brasília)", () => {
    const state = loopStateLabel({ lastTickAt: "2026-09-12T11:30:00Z", reason: null }, NOW_MS);
    expect(state.tone).toBe("stopped");
    expect(state.label).toBe("laço parado desde 12/09 08:30");
  });

  it("is 'sem leitura' with the reason when there is no tick to read", () => {
    expect(loopStateLabel({ lastTickAt: null, reason: "endpoint_missing" }, NOW_MS)).toEqual({
      tone: "unknown",
      label: "laço: sem leitura (o placar do laço ainda não responde)",
    });
    expect(loopStateLabel({ lastTickAt: null, reason: "shape_unknown" }, NOW_MS).label).toContain("carimbo");
    expect(loopStateLabel({ lastTickAt: null, reason: "read_failed" }, NOW_MS).label).toContain("falha");
  });
});

describe("emptyProposalsLabel: the empty state names the loop's state, never a generic 'nothing'", () => {
  it("alive: 'nenhuma proposta nos últimos N min (laço vivo)'", () => {
    const rows = [row({ proposed_at: "2026-09-12T11:47:00Z" })];
    const minutes = minutesSinceNewestProposal(rows, NOW_MS);
    expect(minutes).toBe(13);
    expect(emptyProposalsLabel({ tone: "alive", label: "" }, minutes)).toBe("nenhuma proposta nos últimos 13 min (laço vivo)");
  });

  it("alive with no proposal ever: says so", () => {
    expect(minutesSinceNewestProposal([], NOW_MS)).toBeNull();
    expect(emptyProposalsLabel({ tone: "alive", label: "" }, null)).toBe("nenhuma proposta registrada ainda (laço vivo)");
  });

  it("stopped: repeats 'laço parado desde …'", () => {
    expect(emptyProposalsLabel({ tone: "stopped", label: "laço parado desde 12/09 08:30" }, 13)).toBe(
      "laço parado desde 12/09 08:30 — nenhuma proposta nova chega enquanto o laço não roda",
    );
  });

  it("unknown: admits it cannot tell", () => {
    expect(emptyProposalsLabel({ tone: "unknown", label: "" }, 13)).toContain("sem leitura do laço");
  });
});
