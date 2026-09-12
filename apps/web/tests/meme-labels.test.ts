import { describe, expect, it } from "vitest";

import {
  MEME_GAP_STREAMS,
  MEME_NULL_REASONS,
  MEME_SOURCES,
  MEME_TOKEN_STATES,
  memeGapStreamLabel,
  memeNullReasonLabel,
  memeNullReasonText,
  memeSourceLabel,
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
});

describe("memeNullReasonText", () => {
  it("prefixes 'sem medição:' before the reason label", () => {
    expect(memeNullReasonText("no_trade_feed")).toBe("sem medição: sem feed de negociações (canal pago, não contratado)");
  });

  it("degrades honestly when no reason is given at all (should not happen, but must not crash)", () => {
    expect(memeNullReasonText(null)).toBe("sem medição: motivo não informado");
    expect(memeNullReasonText(undefined)).toBe("sem medição: motivo não informado");
  });
});
