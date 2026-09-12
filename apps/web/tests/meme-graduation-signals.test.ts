import { describe, expect, it } from "vitest";

import {
  COMPLETION_SIGNAL_KEYS,
  MEME_DENOMINATOR_SOURCES,
  MEME_POOL_SOURCES,
  memeCompletionSignalLabel,
  memeDenominatorSourceLabel,
  memePoolSourceLabel,
} from "@/components/meme/labels";
import { markX } from "@/components/meme/meme-curve-chart";
import { completionSignals, matrixDisagreements, signalMarks, signalsDisagree } from "@/components/meme/meme-graduation-signals";
import type { MemeToken } from "@/lib/api/meme-types";

// T4.2d: the four completion signals of `meme_tokens` (0024) travel separately;
// the screen names them in Portuguese and turns amber when they disagree.
const BASE: Pick<
  MemeToken,
  "rest_complete_seen_at" | "curve_filled_seen_at" | "graduated_board_seen_at" | "pool_created_at" | "pool_created_source"
> = {
  rest_complete_seen_at: null,
  curve_filled_seen_at: null,
  graduated_board_seen_at: null,
  pool_created_at: null,
  pool_created_source: null,
};

describe("labels: every signal, pool source and denominator source has Portuguese copy", () => {
  it("names the four signals as the brief wrote them", () => {
    expect(COMPLETION_SIGNAL_KEYS).toEqual(["rest_complete", "curve_filled", "graduated_board", "pool_created"]);
    expect(memeCompletionSignalLabel("rest_complete")).toBe("REST diz completa");
    expect(memeCompletionSignalLabel("curve_filled")).toBe("curva cheia (≥ 85 SOL)");
    expect(memeCompletionSignalLabel("graduated_board")).toBe("no board graduated");
    expect(memeCompletionSignalLabel("pool_created")).toBe("pool criada");
  });

  it("labels every pool source and every denominator source without leaking the enum", () => {
    for (const source of MEME_POOL_SOURCES) {
      expect(memePoolSourceLabel(source)).toMatch(/\S/);
      expect(memePoolSourceLabel(source)).not.toBe(source);
    }
    for (const source of MEME_DENOMINATOR_SOURCES) {
      expect(memeDenominatorSourceLabel(source)).toMatch(/\S/);
      expect(memeDenominatorSourceLabel(source)).not.toBe(source);
    }
  });
});

describe("completionSignals: the four, in order, with their instants", () => {
  it("keeps the order and reports an absent signal as null, never as a date", () => {
    const signals = completionSignals({ ...BASE, rest_complete_seen_at: "2026-09-12T08:47:00Z" });
    expect(signals.map((s) => s.key)).toEqual(COMPLETION_SIGNAL_KEYS);
    expect(signals[0]?.at).toBe("2026-09-12T08:47:00Z");
    expect(signals.slice(1).every((s) => s.at === null)).toBe(true);
  });

  it("carries the pool source beside the pool signal only", () => {
    const signals = completionSignals({
      ...BASE,
      pool_created_at: "2026-09-12T08:46:00Z",
      pool_created_source: "trenches_ws",
    });
    expect(signals[3]?.source).toBe("trenches_ws");
    expect(signals[0]?.source).toBeUndefined();
  });

  it("treats a field the API left out (older payload) as absent", () => {
    const signals = completionSignals({ pool_created_at: undefined, pool_created_source: undefined } as never);
    expect(signals.every((s) => s.at === null)).toBe(true);
  });
});

describe("signalsDisagree: amber when some signals speak and others do not", () => {
  it("is false with no signal (nothing to disagree about) and false with all four", () => {
    expect(signalsDisagree(completionSignals(BASE))).toBe(false);
    expect(
      signalsDisagree(
        completionSignals({
          ...BASE,
          rest_complete_seen_at: "2026-09-12T08:47:00Z",
          curve_filled_seen_at: "2026-09-12T08:47:00Z",
          graduated_board_seen_at: "2026-09-12T08:47:10Z",
          pool_created_at: "2026-09-12T08:46:50Z",
          pool_created_source: "pumpportal_ws",
        }),
      ),
    ).toBe(false);
  });

  it("is true for the plantão's case: REST says complete and nothing else does", () => {
    expect(signalsDisagree(completionSignals({ ...BASE, rest_complete_seen_at: "2026-09-12T08:47:00Z" }))).toBe(true);
  });
});

describe("matrixDisagreements: the six pairs summed, what the strip turns amber on", () => {
  it("sums the six pair columns of the matrix row", () => {
    expect(
      matrixDisagreements({
        disagree_rest_filled: 81,
        disagree_rest_board: 72,
        disagree_rest_pool: 72,
        disagree_filled_board: 37,
        disagree_filled_pool: 37,
        disagree_board_pool: 0,
      }),
    ).toBe(299);
  });
});

describe("signalMarks + markX: event marks on the mcap chart", () => {
  it("turns present signals into timestamped marks and drops absent ones", () => {
    const marks = signalMarks(completionSignals({ ...BASE, pool_created_at: "2026-09-12T08:46:00Z", pool_created_source: "pumpportal_ws" }));
    expect(marks).toEqual([{ x: Date.parse("2026-09-12T08:46:00Z"), label: "pool criada" }]);
  });

  it("places a mark by real elapsed time inside the drawn span and refuses one outside it", () => {
    const geometry = { linePoints: "", min: 0, max: 1, minX: 0, maxX: 1000 };
    expect(markX(geometry, 500)).toBe(160); // WIDTH / 2
    expect(markX(geometry, 1000)).toBe(320);
    expect(markX(geometry, -1)).toBeNull();
    expect(markX(geometry, 1001)).toBeNull();
  });
});
