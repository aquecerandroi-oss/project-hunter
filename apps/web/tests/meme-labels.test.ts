import { describe, expect, it } from "vitest";

import {
  MEME_FEED_SOURCES,
  MEME_GAP_STREAMS,
  MEME_NULL_REASONS,
  MEME_RADAR_STATUSES,
  MEME_SOURCE_STATUSES,
  MEME_SOURCES,
  MEME_TOKEN_STATES,
  memeFeedSourceLabel,
  memeGapStreamLabel,
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
    for (const reason of MEME_NULL_REASONS) {
      expect(memeNullReasonLabel(reason)).toMatch(/\S/);
    }
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

  it("labels the six feed sources the worker reports, and humanizes one it does not know yet instead of throwing", () => {
    expect(MEME_FEED_SOURCES).toEqual(["pumpportal_ws", "pumpfun_rest", "solana_rpc", "trenches_ws", "swap_api", "indexer_risk"]);
    for (const name of MEME_FEED_SOURCES) {
      expect(memeFeedSourceLabel(name)).toMatch(/\S/);
      expect(memeFeedSourceLabel(name)).not.toBe(name);
    }
    expect(memeFeedSourceLabel("some_new_feed")).toBe("some new feed");
  });
});

describe("memeNullReasonText", () => {
  it("prefixes 'sem medição:' before the reason label", () => {
    // T4.2c: the tape now exists (swap-api); "no_trade_feed" means this minute had none.
    expect(memeNullReasonText("no_trade_feed")).toBe("sem medição: sem fita de negociações neste minuto");
  });

  it("degrades honestly when no reason is given at all (should not happen, but must not crash)", () => {
    expect(memeNullReasonText(null)).toBe("sem medição: motivo não informado");
    expect(memeNullReasonText(undefined)).toBe("sem medição: motivo não informado");
  });
});
