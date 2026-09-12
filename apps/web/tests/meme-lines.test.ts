/**
 * T4.10b: the trend lines of a meme's curve as pure geometry
 * (`components/meme/meme-lines.ts`), built against the column names of brief
 * T4.10 §Contrato while the backend lands in parallel -- so every test here
 * also pins the tolerant reading: a payload without the columns yields
 * "linha: sem leitura", never a fabricated line.
 */
import { describe, expect, it } from "vitest";

import {
  LINE_WINDOW_MS,
  breakoutMark,
  hypeText,
  latestTwo,
  lineOverlay,
  lineReading,
  lineReadingText,
  previousHighLine,
  readHype,
  readLineFields,
  supportSegment,
} from "@/components/meme/meme-lines";
import type { MemeFeaturePoint } from "@/lib/api/meme-types";

const T = Date.parse("2026-09-12T13:30:00Z");
const MINUTE = 60_000;

function feature(overrides: Partial<MemeFeaturePoint> & Record<string, unknown> = {}): MemeFeaturePoint {
  return {
    end_time: "2026-09-12T13:30:00Z",
    age_minutes: 12,
    curve_progress_pct: "0.12",
    progress_reason: null,
    mcap_sol: "13",
    curve_reason: null,
    unique_buyers: 8,
    unique_buyers_reason: null,
    buy_sell_ratio: "1.5",
    buy_sell_ratio_reason: null,
    top10_share: null,
    top10_share_reason: "no_holders_reader",
    creator_sold: false,
    creator_sold_reason: null,
    coverage: "1",
    features_version: "meme_features_v3",
    ...overrides,
  };
}

const TRACED = {
  support_line_sol: "10",
  support_line_slope: "0.5",
  high_15m_sol: "12.5",
  low_15m_sol: "7",
  breakout_15m: true,
  higher_lows: true,
  distance_to_support_pct: "0.3",
  line_points: 11,
  line_reason: null,
  mcap_slope_5m: "0.01",
  mcap_slope_15m: "0.004",
};

describe("readLineFields: tolerant to the columns not existing yet", () => {
  it("a payload from meme_features_v2 (no line columns) reads as absent, every value null", () => {
    const fields = readLineFields(feature());
    expect(fields.present).toBe(false);
    expect(fields.supportLineSol).toBeNull();
    expect(fields.lineReason).toBeNull();
    expect(fields.breakout15m).toBeNull();
  });

  it("reads the contract's columns: decimals as strings, booleans, the smallint and the reason", () => {
    const fields = readLineFields(feature(TRACED));
    expect(fields.present).toBe(true);
    expect(fields.supportLineSol).toBe("10");
    expect(fields.supportLineSlope).toBe("0.5");
    expect(fields.high15mSol).toBe("12.5");
    expect(fields.breakout15m).toBe(true);
    expect(fields.higherLows).toBe(true);
    expect(fields.distanceToSupportPct).toBe("0.3");
    expect(fields.linePoints).toBe(11);
    expect(fields.lineReason).toBeNull();
  });

  it("a null support with line_reason is present-but-untraceable; a numeric decimal is tolerated as text", () => {
    const fields = readLineFields(feature({ support_line_sol: null, support_line_slope: null, line_reason: "flat", high_15m_sol: "12.5" }));
    expect(fields.present).toBe(true);
    expect(fields.supportLineSol).toBeNull();
    expect(fields.lineReason).toBe("flat");
    expect(fields.high15mSol).toBe("12.5");
  });
});

describe("lineReading: absent | untraceable | traced", () => {
  it("absent when no column exists -> 'linha: sem leitura'", () => {
    const reading = lineReading(readLineFields(feature()));
    expect(reading.kind).toBe("absent");
    expect(lineReadingText(reading)).toBe("linha: sem leitura");
  });

  it("untraceable carries the named reason -> 'linha ainda não traçável: <motivo>'", () => {
    const reading = lineReading(readLineFields(feature({ support_line_sol: null, line_reason: "too_few_points" })));
    expect(reading).toEqual({ kind: "untraceable", reason: "too_few_points" });
    expect(lineReadingText(reading)).toBe("linha ainda não traçável: menos de 5 fotografias na janela");
  });

  it("untraceable without a reason says so instead of inventing one", () => {
    const reading = lineReading(readLineFields(feature({ support_line_sol: null })));
    expect(reading).toEqual({ kind: "untraceable", reason: null });
    expect(lineReadingText(reading)).toBe("linha ainda não traçável: motivo não informado");
  });

  it("traced exposes the numbers the chart draws and a readable summary", () => {
    const reading = lineReading(readLineFields(feature(TRACED)));
    expect(reading.kind).toBe("traced");
    if (reading.kind !== "traced") throw new Error("unreachable");
    expect(reading.supportSol).toBe(10);
    expect(reading.slopePerMinute).toBe(0.5);
    expect(reading.higherLows).toBe(true);
    expect(reading.breakout).toBe(true);
    expect(lineReadingText(reading)).toBe("suporte 10.0000 SOL · distância ao suporte +30.00% · fundos ascendentes: sim · rompimento 15 min: sim");
  });

  it("traced with unknown higher_lows/breakout names the gap rather than printing 'não'", () => {
    const reading = lineReading(readLineFields(feature({ ...TRACED, higher_lows: null, breakout_15m: null, distance_to_support_pct: null })));
    expect(lineReadingText(reading)).toBe("suporte 10.0000 SOL · fundos ascendentes: sem leitura · rompimento 15 min: sem leitura");
  });
});

describe("supportSegment: the line through the last two lows, projected to now", () => {
  const span = { minX: T - 30 * MINUTE, maxX: T + 2 * MINUTE };

  it("starts at the 15-minute window's edge and ends at the chart's now, following the slope in SOL/min", () => {
    const segment = supportSegment(readLineFields(feature(TRACED)), T, span);
    expect(segment).toEqual({ x1: T - LINE_WINDOW_MS, y1: 10 - 0.5 * 15, x2: T + 2 * MINUTE, y2: 10 + 0.5 * 2, higherLows: true });
  });

  it("clamps to the chart's own start when the chart is shorter than the window", () => {
    const short = { minX: T - 5 * MINUTE, maxX: T };
    const segment = supportSegment(readLineFields(feature(TRACED)), T, short);
    expect(segment?.x1).toBe(T - 5 * MINUTE);
    expect(segment?.y1).toBe(10 - 0.5 * 5);
    expect(segment?.x2).toBe(T);
    expect(segment?.y2).toBe(10);
  });

  it("draws nothing when there is no support line or the chart ends before the window starts", () => {
    expect(supportSegment(readLineFields(feature()), T, span)).toBeNull();
    expect(supportSegment(readLineFields(feature({ ...TRACED, support_line_sol: null })), T, span)).toBeNull();
    expect(supportSegment(readLineFields(feature(TRACED)), T, { minX: T - 60 * MINUTE, maxX: T - 20 * MINUTE })).toBeNull();
  });

  it("a missing slope draws the level flat and says so through higherLows = null only when the field is null", () => {
    const segment = supportSegment(readLineFields(feature({ ...TRACED, support_line_slope: null, higher_lows: null })), T, span);
    expect(segment?.y1).toBe(10);
    expect(segment?.y2).toBe(10);
    expect(segment?.higherLows).toBeNull();
  });
});

describe("previousHighLine: the 15-minute high of the previous window, horizontal", () => {
  const span = { minX: T - 30 * MINUTE, maxX: T + MINUTE };

  it("uses the previous minute's high_15m_sol across its window and on to now", () => {
    const previous = readLineFields(feature({ ...TRACED, high_15m_sol: "12.5" }));
    expect(previousHighLine(previous, T - MINUTE, span)).toEqual({ x1: T - MINUTE - LINE_WINDOW_MS, x2: T + MINUTE, y: 12.5, yText: "12.5" });
  });

  it("is null without a previous row or without its high", () => {
    expect(previousHighLine(null, null, span)).toBeNull();
    expect(previousHighLine(readLineFields(feature({ ...TRACED, high_15m_sol: null })), T - MINUTE, span)).toBeNull();
  });
});

describe("breakoutMark: placed on the minute's mcap, else on the broken high, else declared unplaced", () => {
  it("marks the latest minute at its mcap when breakout_15m is true", () => {
    expect(breakoutMark(feature(TRACED), readLineFields(feature(TRACED)), T, null)).toEqual({ x: T, y: 13, unplaced: false });
  });

  it("falls back to the previous high when the minute has no mcap", () => {
    const row = feature({ ...TRACED, mcap_sol: null, curve_reason: "not_polled" });
    expect(breakoutMark(row, readLineFields(row), T, { x1: 0, x2: T, y: 12.5, yText: "12.5" })).toEqual({ x: T, y: 12.5, unplaced: false });
  });

  it("is unplaced (still reported) when nothing gives it a level, and null when there is no breakout", () => {
    const row = feature({ ...TRACED, mcap_sol: null, curve_reason: "not_polled" });
    expect(breakoutMark(row, readLineFields(row), T, null)).toEqual({ x: T, y: null, unplaced: true });
    expect(breakoutMark(feature({ ...TRACED, breakout_15m: false }), readLineFields(feature({ ...TRACED, breakout_15m: false })), T, null)).toBeNull();
    expect(breakoutMark(feature(), readLineFields(feature()), T, null)).toBeNull();
  });
});

describe("latestTwo / lineOverlay: order-tolerant over the API's newest-first series", () => {
  const older = feature({ ...TRACED, end_time: "2026-09-12T13:29:00Z", high_15m_sol: "12", breakout_15m: false });
  const latest = feature(TRACED);

  it("picks the latest and the previous minute whichever way the array is ordered", () => {
    expect(latestTwo([older, latest]).latest?.end_time).toBe("2026-09-12T13:30:00Z");
    expect(latestTwo([latest, older]).previous?.end_time).toBe("2026-09-12T13:29:00Z");
    expect(latestTwo([])).toEqual({ latest: null, previous: null });
  });

  it("assembles support, previous high and breakout in data space for the chart", () => {
    const span = { minX: T - 30 * MINUTE, maxX: T };
    const overlay = lineOverlay([latest, older], span);
    expect(overlay.reading.kind).toBe("traced");
    expect(overlay.support?.x2).toBe(T);
    expect(overlay.previousHigh).toEqual({ x1: T - MINUTE - LINE_WINDOW_MS, x2: T, y: 12, yText: "12" });
    expect(overlay.breakout).toEqual({ x: T, y: 13, unplaced: false });
    expect(overlay.higherLows).toBe(true);
  });

  it("without a drawable chart span it still reads the state and draws nothing", () => {
    const overlay = lineOverlay([latest, older], null);
    expect(overlay.reading.kind).toBe("traced");
    expect(overlay.support).toBeNull();
    expect(overlay.previousHigh).toBeNull();
    expect(overlay.breakout).toBeNull();
  });

  it("a series from before the columns existed is 'absent' end to end", () => {
    const overlay = lineOverlay([feature(), feature({ end_time: "2026-09-12T13:29:00Z" })], { minX: T - 30 * MINUTE, maxX: T });
    expect(overlay.reading).toEqual({ kind: "absent" });
    expect(overlay.support).toBeNull();
    expect(overlay.previousHigh).toBeNull();
    expect(overlay.breakout).toBeNull();
    expect(overlay.higherLows).toBeNull();
  });

  it("an empty series is absent too", () => {
    expect(lineOverlay([], null).reading).toEqual({ kind: "absent" });
  });
});

describe("readHype / hypeText: the documented 0..1 score with its reason", () => {
  it("absent columns -> 'hype: sem leitura'", () => {
    const hype = readHype(feature());
    expect(hype).toEqual({ present: false, score: null, reason: null });
    expect(hypeText(hype)).toBe("hype: sem leitura");
  });

  it("a score with no reason, and a score computed from one source only", () => {
    expect(hypeText(readHype(feature({ hype_score: "0.72", hype_reason: null })))).toBe("hype 0.72");
    expect(hypeText(readHype(feature({ hype_score: "0.6", hype_reason: "partial" })))).toBe("hype 0.60 · só uma das duas fontes (fita ou board)");
  });

  it("a null score names why", () => {
    expect(hypeText(readHype(feature({ hype_score: null, hype_reason: "no_tape_no_board" })))).toBe("sem hype: sem fita e sem board no minuto");
    expect(hypeText(readHype(feature({ hype_score: null, hype_reason: null })))).toBe("sem hype: motivo não informado");
  });
});
