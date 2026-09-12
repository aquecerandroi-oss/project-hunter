import { describe, expect, it } from "vitest";

import {
  MEME_FEED_SOURCES,
  MEME_GAP_STREAMS,
  MEME_HYPE_NO_READING,
  MEME_HYPE_REASONS,
  MEME_LINE_NO_READING,
  MEME_LINE_REASONS,
  MEME_NULL_REASONS,
  MEME_RADAR_STATUSES,
  MEME_SOURCE_STATUSES,
  MEME_SOURCES,
  MEME_TOKEN_STATES,
  memeFeedSourceLabel,
  memeGapStreamLabel,
  memeHypeMissingText,
  memeHypeReasonLabel,
  memeLineReasonLabel,
  memeLineUntraceableText,
  memeNullReasonLabel,
  memeNullReasonText,
  memeRadarStatusLabel,
  memeSourceLabel,
  memeSourceStatusLabel,
  memeTokenStateLabel,
} from "@/components/meme/labels";

// DESIGN.md §2 "sem backstage na copy": every enum value the API can send
// must have a plain-language label, checked exhaustively here so a new enum
// member added upstream fails this test instead of rendering raw
// (`curve`/`no_trade_feed`) in production.
describe("Meme Radar labels: exhaustive over every enum value the API can send", () => {
  it("labels every token state", () => {
    for (const state of MEME_TOKEN_STATES) {
      expect(memeTokenStateLabel(state)).toMatch(/\S/);
    }
  });

  it("labels every source", () => {
    for (const source of MEME_SOURCES) {
      expect(memeSourceLabel(source)).toMatch(/\S/);
    }
  });

  it("labels every gap stream", () => {
    for (const stream of MEME_GAP_STREAMS) {
      expect(memeGapStreamLabel(stream)).toMatch(/\S/);
    }
  });

  it("labels every null reason", () => {
    // T4.2g: `no_sol_quote` (the batch tape spoke USD and there was no SOL/USD quote under 5 min) joined the contract's union.
    expect(MEME_NULL_REASONS).toEqual(["no_trade_feed", "no_holders_reader", "denominator_unknown", "not_polled", "rate_limited", "insufficient_coverage", "unsupported_quote", "no_sells", "out_of_range", "no_sol_quote"]);
    for (const reason of MEME_NULL_REASONS) {
      expect(memeNullReasonLabel(reason)).toMatch(/\S/);
    }
    expect(memeNullReasonLabel("no_sol_quote")).toBe("sem cotação SOL/USD no minuto");
    expect(memeNullReasonLabel("no_trade_feed")).toBe("sem fita");
  });

  it("never returns a raw enum value as its own label", () => {
    for (const reason of MEME_NULL_REASONS) {
      expect(memeNullReasonLabel(reason)).not.toBe(reason);
    }
  });

  // T4.3b: `GET /meme/sources` -- the radar's heartbeat state and each source's status.
  it("labels every radar status and every source status, never raw", () => {
    for (const status of MEME_RADAR_STATUSES) {
      expect(memeRadarStatusLabel(status)).toMatch(/\S/);
      expect(memeRadarStatusLabel(status)).not.toBe(status);
    }
    for (const status of MEME_SOURCE_STATUSES) {
      expect(memeSourceStatusLabel(status)).toMatch(/\S/);
      expect(memeSourceStatusLabel(status)).not.toBe(status);
    }
  });

  it("labels the seven feed sources the worker reports, and humanizes one it does not know yet instead of throwing", () => {
    // T4.2g: `swap_api_activity` is the batch tape (POST market-activity/batch) -- the same swap-api budget, its own source line.
    expect(MEME_FEED_SOURCES).toEqual(["pumpportal_ws", "pumpfun_rest", "solana_rpc", "trenches_ws", "swap_api", "indexer_risk", "swap_api_activity"]);
    for (const name of MEME_FEED_SOURCES) {
      expect(memeFeedSourceLabel(name)).toMatch(/\S/);
      expect(memeFeedSourceLabel(name)).not.toBe(name);
    }
    expect(memeFeedSourceLabel("swap_api")).toBe("fita por mint (swap-api)");
    expect(memeFeedSourceLabel("swap_api_activity")).toBe("fita por lote (swap-api)");
    expect(memeFeedSourceLabel("some_new_feed")).toBe("some new feed");
  });
});

// T4.10b: the trend-line and hype vocabularies of `meme_features_v3` (brief
// T4.10 §Contrato). Three deploys broke on 2026-09-12 for a missing label, so
// besides the exhaustive walk every label function also degrades to readable
// text on a value it does not know instead of throwing at render time.
describe("Meme lines/hype labels: exhaustive over the contract's vocabularies", () => {
  it("labels every line_reason of the contract, never raw", () => {
    expect(MEME_LINE_REASONS).toEqual(["too_few_points", "no_snapshot", "flat", "out_of_range"]);
    for (const reason of MEME_LINE_REASONS) {
      expect(memeLineReasonLabel(reason)).toMatch(/\S/);
      expect(memeLineReasonLabel(reason)).not.toBe(reason);
    }
  });

  it("labels every hype_reason of the contract, never raw", () => {
    expect(MEME_HYPE_REASONS).toEqual(["no_tape_no_board", "partial"]);
    for (const reason of MEME_HYPE_REASONS) {
      expect(memeHypeReasonLabel(reason)).toMatch(/\S/);
      expect(memeHypeReasonLabel(reason)).not.toBe(reason);
    }
  });

  it("humanizes a reason the vocabulary does not know yet instead of throwing", () => {
    expect(memeLineReasonLabel("brand_new_reason")).toBe("motivo não previsto (brand new reason)");
    expect(memeHypeReasonLabel("brand_new_reason")).toBe("motivo não previsto (brand new reason)");
  });

  it("composes the exact sentences the brief asks for", () => {
    expect(MEME_LINE_NO_READING).toBe("linha: sem leitura");
    expect(memeLineUntraceableText("too_few_points")).toBe("linha ainda não traçável: menos de 5 fotografias na janela");
    expect(memeLineUntraceableText(null)).toBe("linha ainda não traçável: motivo não informado");
    expect(memeLineUntraceableText(undefined)).toBe("linha ainda não traçável: motivo não informado");
    expect(MEME_HYPE_NO_READING).toBe("hype: sem leitura");
    expect(memeHypeMissingText("no_tape_no_board")).toBe("sem hype: sem fita e sem board no minuto");
    expect(memeHypeMissingText(null)).toBe("sem hype: motivo não informado");
  });
});

describe("memeNullReasonText", () => {
  it("prefixes 'sem medição:' before the reason label", () => {
    // T4.2c: the tape now exists (swap-api); "no_trade_feed" means this minute had none (T4.20 wording: "sem fita").
    expect(memeNullReasonText("no_trade_feed")).toBe("sem medição: sem fita");
    expect(memeNullReasonText("no_sol_quote")).toBe("sem medição: sem cotação SOL/USD no minuto");
  });

  it("degrades honestly when no reason is given at all (should not happen, but must not crash)", () => {
    expect(memeNullReasonText(null)).toBe("sem medição: motivo não informado");
    expect(memeNullReasonText(undefined)).toBe("sem medição: motivo não informado");
  });
});
