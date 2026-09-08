import { describe, expect, it } from "vitest";

import {
  buildReferenceRuler,
  buildWalletRuler,
  moneyForRow,
  priceAndTime,
  REFERENCE_EQUITY_USDT,
  resultBadgeKind,
  saidaText,
  summarizeRows,
  totalsHeading,
  usdtToBrl,
} from "@/components/lab/lab-money";
import type { OutcomeResult, ShadowTrackingState } from "@/lib/api/lab-types";
import { makeSignal } from "@/tests/fixtures/lab";

describe("buildReferenceRuler: the labelled 10.000 USDT fallback (brief T3.17)", () => {
  it("is flagged as a reference, has no BRL, and its risk is 0,25% of 10.000", () => {
    const ruler = buildReferenceRuler();
    expect(ruler.isReference).toBe(true);
    expect(ruler.equityUsdt).toBe(REFERENCE_EQUITY_USDT);
    expect(ruler.equityBrl).toBeNull();
    expect(ruler.riskUsdt).toBeCloseTo(25, 6);
  });
});

describe("buildWalletRuler: the real principal paper wallet (the 'ever' example, 19.333,01 USDT)", () => {
  it("computes 48,33 USDT of risk from 19.333,01 USDT of equity (docs/RISK_ENGINE.md §3's 0,25%)", () => {
    const ruler = buildWalletRuler("19333.01", "115998.06");
    expect(ruler.isReference).toBe(false);
    expect(ruler.riskUsdt).toBeCloseTo(48.332525, 6);
    expect(Number(ruler.riskUsdt.toFixed(2))).toBe(48.33);
  });

  it("keeps equityBrl null when the wallet has no BRL decomposition, without inventing a rate", () => {
    const ruler = buildWalletRuler("19333.01", null);
    expect(ruler.equityBrl).toBeNull();
  });
});

describe("usdtToBrl: through the wallet's own equity_brl/equity ratio, never a fabricated rate", () => {
  it("converts an arbitrary USDT amount by the wallet's real ratio", () => {
    const ruler = buildWalletRuler("19333.01", "115998.06"); // ratio = 6 exactly
    expect(usdtToBrl(48.332525, ruler)).toBeCloseTo(289.99515, 4);
  });

  it("returns null when the ruler has no BRL (reference wallet, or a wallet without BRL yet)", () => {
    expect(usdtToBrl(100, buildReferenceRuler())).toBeNull();
  });
});

describe("moneyForRow: pnl, notional and pct move (brief T3.17 item 2's declared formulas)", () => {
  const ruler = buildWalletRuler("19333.01", "115998.06");

  it("pnl = r_multiple * risk, with the real sign kept", () => {
    const row = makeSignal({ r_multiple: "-1.0421" });
    const { pnlUsdt } = moneyForRow(row, ruler);
    expect(pnlUsdt.value).toBeCloseTo(-1.0421 * ruler.riskUsdt, 6);
    expect(pnlUsdt.reason).toBeNull();
  });

  it("pnl is null with r_multiple's own reason -- never a 0 standing in for 'unknown'", () => {
    const row = makeSignal({ r_multiple: null, r_multiple_reason: "no_sample" });
    const { pnlUsdt } = moneyForRow(row, ruler);
    expect(pnlUsdt.value).toBeNull();
    expect(pnlUsdt.reason).toBe("no_sample");
  });

  it("notional = risk / |entry - stop| * entry when both entry and stop exist", () => {
    const row = makeSignal({ virtual_entry: "27460.0000000000", stop: "27100.0000000000" });
    const { notionalUsdt } = moneyForRow(row, ruler);
    const expected = (ruler.riskUsdt / Math.abs(27460 - 27100)) * 27460;
    expect(notionalUsdt.value).toBeCloseTo(expected, 4);
  });

  it("notional is null with the tracking's own no_entry_reason when there was no entry", () => {
    const row = makeSignal({ virtual_entry: null, entry_ts: null, tracking_state: "no_entry", no_entry_reason: "late:delay" });
    const { notionalUsdt } = moneyForRow(row, ruler);
    expect(notionalUsdt.value).toBeNull();
    expect(notionalUsdt.reason).toBe("late:delay");
  });

  it("notional is null with 'no_stop' when the entry exists but the stop is missing", () => {
    const row = makeSignal({ stop: null });
    const { notionalUsdt } = moneyForRow(row, ruler);
    expect(notionalUsdt.value).toBeNull();
    expect(notionalUsdt.reason).toBe("no_stop");
  });

  it("pctMove = exit/entry - 1", () => {
    const row = makeSignal({ virtual_entry: "27460.0000000000", exit_price: "27100.0000000000" });
    const { pctMove } = moneyForRow(row, ruler);
    expect(pctMove).toBeCloseTo(27100 / 27460 - 1, 8);
  });

  it("pctMove is null when either price is missing", () => {
    const row = makeSignal({ exit_price: null });
    expect(moneyForRow(row, ruler).pctMove).toBeNull();
  });
});

describe("priceAndTime / saidaText: the plain-language 'Entrou'/'Saiu' text", () => {
  it("joins price and the short one-line date/time (brief T3.17b item 3)", () => {
    expect(priceAndTime("27460.0000000000", "2026-09-06T00:26:00Z")).toBe("27460.0000000000 · 06/09 00:26");
  });

  it("returns '--' when the price is absent", () => {
    expect(priceAndTime(null, null)).toBe("--");
  });

  it("saidaText shows the real exit AND its own motivo when one exists (brief T3.17b item 5)", () => {
    const row = makeSignal({ exit_price: "27100.0000000000", exit_ts: "2026-09-06T03:41:00Z", result: "stop" });
    expect(saidaText(row)).toBe("27100.0000000000 · 06/09 03:41 · motivo: stop");
  });

  it("saidaText says 'não entrou: <motivo>' for a no_entry row", () => {
    const row = makeSignal({ exit_price: null, tracking_state: "no_entry", no_entry_reason: "late:delay" });
    expect(saidaText(row)).toMatch(/^não entrou:/);
  });

  it("saidaText says 'censurada: <motivo>' for a censored row", () => {
    const row = makeSignal({ exit_price: null, tracking_state: "censored", censored_reason: "gap:failed" });
    expect(saidaText(row)).toMatch(/^censurada:/);
  });

  it("saidaText says 'aberta' for a still-active row", () => {
    const row = makeSignal({ exit_price: null, tracking_state: "active" });
    expect(saidaText(row)).toBe("aberta");
  });

  it("saidaText says 'aberta' for a still pending_entry row", () => {
    const row = makeSignal({ exit_price: null, tracking_state: "pending_entry" });
    expect(saidaText(row)).toBe("aberta");
  });

  it("saidaText falls back to '--' for a tracking_state with no exit and no honest reason to give (terminal but no exit_price)", () => {
    const row = makeSignal({ exit_price: null, tracking_state: "terminal" });
    expect(saidaText(row)).toBe("--");
  });

  const EXIT_RESULTS: OutcomeResult[] = ["target", "stop", "expired", "invalidated"];
  it.each(EXIT_RESULTS)("saidaText's motivo covers OutcomeResult %s when the row actually exited", (result) => {
    const row = makeSignal({ exit_price: "1.0", exit_ts: "2026-09-06T00:00:00Z", result });
    expect(saidaText(row)).toMatch(new RegExp(`motivo: `));
    expect(saidaText(row).endsWith("--")).toBe(false);
  });

  const NON_EXIT_STATES: ShadowTrackingState[] = ["pending_entry", "active", "no_entry", "censored"];
  it.each(NON_EXIT_STATES)("saidaText never claims a price/motivo for a %s row with no exit_price", (tracking_state) => {
    const row = makeSignal({ exit_price: null, tracking_state, no_entry_reason: "late:delay", censored_reason: "gap:failed" });
    expect(saidaText(row)).not.toMatch(/motivo: (alvo|stop|expirou|invalidada)$/);
  });
});

describe("resultBadgeKind: lucro/prejuízo/pendente (brief T3.17 item 3)", () => {
  it("is 'pendente' when pnl is unknown", () => {
    expect(resultBadgeKind(null)).toBe("pendente");
  });
  it("is 'lucro' for a positive pnl and 'prejuizo' for a negative one", () => {
    expect(resultBadgeKind(10)).toBe("lucro");
    expect(resultBadgeKind(-10)).toBe("prejuizo");
  });
});

describe("summarizeRows: the totals card math (brief T3.17 item 2)", () => {
  const ruler = buildWalletRuler("19333.01", "115998.06");

  it("counts pending/no_entry/censored separately, never folded into 'concluídas'", () => {
    const rows = [
      makeSignal({ signal_id: "1", tracking_state: "terminal", r_multiple: "1.0" }),
      makeSignal({ signal_id: "2", tracking_state: "pending_entry", r_multiple: null, r_multiple_reason: null }),
      makeSignal({ signal_id: "3", tracking_state: "no_entry", r_multiple: null, r_multiple_reason: null }),
      makeSignal({ signal_id: "4", tracking_state: "censored", r_multiple: null, r_multiple_reason: null }),
    ];
    const summary = summarizeRows(rows, ruler);
    expect(summary.total).toBe(4);
    expect(summary.completed).toBe(1);
    expect(summary.pending).toBe(1);
    expect(summary.noEntry).toBe(1);
    expect(summary.censored).toBe(1);
  });

  it("sums pnl only across rows with a known r_multiple, signed correctly", () => {
    const rows = [
      makeSignal({ signal_id: "1", tracking_state: "terminal", r_multiple: "1.0" }),
      makeSignal({ signal_id: "2", tracking_state: "terminal", r_multiple: "-0.5" }),
    ];
    const summary = summarizeRows(rows, ruler);
    expect(summary.withProfit).toBe(1);
    expect(summary.withLoss).toBe(1);
    expect(summary.resultUsdt.value).toBeCloseTo(0.5 * ruler.riskUsdt, 6);
    expect(summary.resultBrl.value).not.toBeNull();
    expect(summary.winRate.value).toBeCloseTo(0.5, 8);
  });

  it("resultUsdt/resultBrl/winRate are null with 'no_completed_operations' when nothing has a known pnl", () => {
    const rows = [makeSignal({ tracking_state: "pending_entry", r_multiple: null, r_multiple_reason: null })];
    const summary = summarizeRows(rows, ruler);
    expect(summary.resultUsdt).toEqual({ value: null, reason: "no_completed_operations" });
    expect(summary.resultBrl).toEqual({ value: null, reason: "no_completed_operations" });
    expect(summary.winRate).toEqual({ value: null, reason: "no_completed_operations" });
  });

  it("resultBrl is null with 'no_brl_wallet' when pnl is known but the ruler has no BRL", () => {
    const rows = [makeSignal({ tracking_state: "terminal", r_multiple: "1.0" })];
    const summary = summarizeRows(rows, buildReferenceRuler());
    expect(summary.resultUsdt.value).not.toBeNull();
    expect(summary.resultBrl).toEqual({ value: null, reason: "no_brl_wallet" });
  });

  it("averages profit and loss separately (brief T3.17b item 1)", () => {
    const rows = [
      makeSignal({ signal_id: "1", tracking_state: "terminal", r_multiple: "1.0" }),
      makeSignal({ signal_id: "2", tracking_state: "terminal", r_multiple: "2.0" }),
      makeSignal({ signal_id: "3", tracking_state: "terminal", r_multiple: "-0.5" }),
    ];
    const summary = summarizeRows(rows, ruler);
    expect(summary.avgProfitUsdt.value).toBeCloseTo(((1.0 + 2.0) / 2) * ruler.riskUsdt, 6);
    expect(summary.avgLossUsdt.value).toBeCloseTo(-0.5 * ruler.riskUsdt, 6);
  });

  it("avgProfitUsdt/avgLossUsdt carry an honest reason instead of a fabricated 0 when a side is empty", () => {
    const rows = [makeSignal({ tracking_state: "terminal", r_multiple: "1.0" })];
    const summary = summarizeRows(rows, ruler);
    expect(summary.avgProfitUsdt.value).not.toBeNull();
    expect(summary.avgLossUsdt).toEqual({ value: null, reason: "no_loss_operations" });
  });

  it("names the best and worst operation (market + result) among known-pnl rows", () => {
    const rows = [
      makeSignal({ signal_id: "1", market: "AAAAUSDT", tracking_state: "terminal", r_multiple: "1.0", result: "target" }),
      makeSignal({ signal_id: "2", market: "BBBBUSDT", tracking_state: "terminal", r_multiple: "-2.0", result: "stop" }),
      makeSignal({ signal_id: "3", market: "CCCCUSDT", tracking_state: "terminal", r_multiple: "0.3", result: "target" }),
    ];
    const summary = summarizeRows(rows, ruler);
    expect(summary.best).toEqual({ market: "AAAAUSDT", pnlUsdt: 1.0 * ruler.riskUsdt, result: "target" });
    expect(summary.worst).toEqual({ market: "BBBBUSDT", pnlUsdt: -2.0 * ruler.riskUsdt, result: "stop" });
  });

  it("best/worst are null (never a fabricated row) when nothing has a known pnl", () => {
    const rows = [makeSignal({ tracking_state: "pending_entry", r_multiple: null, r_multiple_reason: null })];
    const summary = summarizeRows(rows, ruler);
    expect(summary.best).toBeNull();
    expect(summary.worst).toBeNull();
  });
});

describe("totalsHeading: the card's own page-scope wording (brief T3.17b item 1)", () => {
  it("says 'desta página' with the count when the list is truncated (a next_cursor exists)", () => {
    expect(totalsHeading(200, true)).toBe("Resultado das operações desta página (200)");
  });

  it("never says 'há mais sinais além desta página' (Everton's screenshot, item 1: that read as if it were the Lab's whole total)", () => {
    expect(totalsHeading(200, true)).not.toMatch(/há mais sinais/);
  });

  it("says 'todas as operações do período' with the count when nothing is truncated", () => {
    expect(totalsHeading(37, false)).toBe("Resultado de todas as operações do período (37)");
  });
});
