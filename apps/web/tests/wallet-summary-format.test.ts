import { describe, expect, it } from "vitest";

import { formatBrasiliaShort } from "@/lib/time";

import {
  ageSince,
  formatBrlSigned,
  formatSolSigned,
  fxNote,
  pnlColorClass,
  stalenessNote,
  startingEquitySourceLabel,
  walletExecutorStatusNote,
  walletReasonLabel,
} from "@/components/meme-live/wallet-summary-format";

describe("formatSolSigned", () => {
  it("signs a positive amount with a leading +", () => {
    expect(formatSolSigned("0.05")).toBe("+0.0500 SOL");
  });

  it("never double-signs a negative amount", () => {
    expect(formatSolSigned("-0.05")).toBe("-0.0500 SOL");
  });

  it("never signs zero", () => {
    expect(formatSolSigned("0")).toBe("0.0000 SOL");
  });
});

describe("formatBrlSigned", () => {
  it("signs a positive amount and never double-signs a negative one", () => {
    expect(formatBrlSigned("10")).toBe("+R$ 10,00");
    expect(formatBrlSigned("-10")).toBe("−R$ 10,00");
    expect(formatBrlSigned("0")).toBe("R$ 0,00");
  });
});

describe("pnlColorClass", () => {
  it("colors positive green, negative red, zero neutral, and absent muted", () => {
    expect(pnlColorClass("0.01")).toBe("text-green");
    expect(pnlColorClass("-0.01")).toBe("text-red");
    expect(pnlColorClass("0")).toBe("text-fg");
    expect(pnlColorClass(null)).toBe("text-fg-muted");
    expect(pnlColorClass(undefined)).toBe("text-fg-muted");
  });
});

describe("walletReasonLabel", () => {
  it("labels every reason services/meme_live_wallet.py names", () => {
    expect(walletReasonLabel("no_wallet_balance")).toBe("sem leitura da carteira");
    expect(walletReasonLabel("no_sol_usd_quote")).toBe("sem cotação SOL/USD do radar");
    expect(walletReasonLabel("no_fx_quote")).toBe("sem câmbio USD/BRL");
    expect(walletReasonLabel("no_open_positions")).toBe("nenhuma posição aberta agora");
    expect(walletReasonLabel("positions_without_mark")).toBe("há posições abertas ainda sem marca");
    expect(walletReasonLabel("no_closed_positions")).toBe("nenhuma posição fechada ainda");
    expect(walletReasonLabel("no_starting_equity_reading")).toBe("sem leitura inicial da carteira");
  });

  it("never hides an unrecognized code behind a generic message", () => {
    expect(walletReasonLabel("something_new")).toBe("motivo não previsto: something_new");
  });

  it("names the absence of a reason too", () => {
    expect(walletReasonLabel(null)).toBe("sem motivo registrado");
    expect(walletReasonLabel(undefined)).toBe("sem motivo registrado");
  });
});

describe("walletExecutorStatusNote", () => {
  it("reuses the executor's own status vocabulary", () => {
    expect(walletExecutorStatusNote("alive")).toBe("no ar");
    expect(walletExecutorStatusNote("heartbeat_missing")).toBe("heartbeat ausente");
  });
});

describe("fxNote", () => {
  const OBSERVED = "2026-09-18T18:32:00Z";

  it("names a fresh quote with its time", () => {
    const expected = `câmbio de ${formatBrasiliaShort(OBSERVED)}`;
    expect(fxNote({ usd_brl: "5.4", observed_at: OBSERVED, stale: false, reason: null })).toBe(expected);
  });

  it("names a stale quote apart from a fresh one", () => {
    const note = fxNote({ usd_brl: "5.4", observed_at: OBSERVED, stale: true, reason: "stale" });
    expect(note).toContain("última leitura disponível");
  });

  it("never invents a rate when none was ever read", () => {
    expect(fxNote({ usd_brl: null, observed_at: null, stale: false, reason: "no_fx_quote" })).toBe("sem câmbio USD/BRL");
  });
});

describe("startingEquitySourceLabel", () => {
  it("labels the two known sources and passes an unknown one through", () => {
    expect(startingEquitySourceLabel("kill_switch_anchor")).toBe("início do dia registrado hoje");
    expect(startingEquitySourceLabel("first_treasury_swap")).toBe("primeira leitura de carteira registrada (troca da tesouraria)");
    expect(startingEquitySourceLabel(null)).toBeNull();
  });
});

describe("stalenessNote", () => {
  it("rounds the executor's own age in seconds", () => {
    expect(stalenessNote("2.3")).toBe("atualizado há 2 s");
    expect(stalenessNote(null)).toBe("sem leitura");
    expect(stalenessNote("not-a-number")).toBe("sem leitura");
  });
});

describe("ageSince", () => {
  it("renders seconds, minutes and hours at their own scale", () => {
    const now = new Date("2026-09-18T18:00:00Z").getTime();
    expect(ageSince("2026-09-18T17:59:50Z", now)).toBe("10 s");
    expect(ageSince("2026-09-18T17:50:00Z", now)).toBe("10 min");
    expect(ageSince("2026-09-18T15:00:00Z", now)).toBe("3 h");
  });

  it("never reads negative on a clock skew", () => {
    const now = new Date("2026-09-18T18:00:00Z").getTime();
    expect(ageSince("2026-09-18T18:00:05Z", now)).toBe("0 s");
  });
});
