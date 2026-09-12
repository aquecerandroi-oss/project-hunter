import { describe, expect, it } from "vitest";

import {
  betDetailHref,
  csvExportHref,
  formatBrasiliaClock,
  formatDurationSeconds,
  formatUsdSigned,
  isDayString,
  mergeTestRows,
  ruleSetLabel,
  shiftDay,
  testsHref,
} from "@/components/meme-tests/meme-tests-format";

import { realRow, testRow } from "./meme-tests-fixtures";

describe("Brasília clock with seconds", () => {
  it("prints hh:mm:ss in Brasília (UTC-3), never the browser's zone", () => {
    expect(formatBrasiliaClock("2026-09-12T14:00:05Z")).toBe("11:00:05");
    expect(formatBrasiliaClock("2026-09-13T02:59:59Z")).toBe("23:59:59");
  });

  it("is honest about an absent or unreadable instant", () => {
    expect(formatBrasiliaClock(null)).toBe("--");
    expect(formatBrasiliaClock("not-a-date")).toBe("--");
  });
});

describe("durations and money", () => {
  it("formats whole seconds with a space before the unit", () => {
    expect(formatDurationSeconds(445)).toBe("7 min 25 s");
    expect(formatDurationSeconds(45)).toBe("45 s");
    expect(formatDurationSeconds(null)).toBe("sem duração");
  });

  it("US$ with an explicit sign, decimal-safe", () => {
    expect(formatUsdSigned("32.58")).toBe("+US$ 32.58");
    expect(formatUsdSigned("-5")).toBe("-US$ 5.00");
    expect(formatUsdSigned("0")).toBe("US$ 0.00");
    expect(formatUsdSigned("1234.5")).toBe("+US$ 1,234.50");
  });
});

describe("mergeTestRows", () => {
  it("interleaves REAL rows with paper rows, newest entry first", () => {
    const older = testRow({ id: "old", entry: { ...testRow().entry, at: "2026-09-12T13:00:00Z" } });
    const newer = testRow({ id: "new", entry: { ...testRow().entry, at: "2026-09-12T14:30:00Z" } });
    const real = realRow(); // 14:03
    expect(mergeTestRows([older, newer], [real]).map((r) => r.id)).toEqual(["new", real.id, "old"]);
  });

  it("breaks a tie by id so the order is stable", () => {
    const a = testRow({ id: "a" });
    const b = testRow({ id: "b" });
    expect(mergeTestRows([b, a], []).map((r) => r.id)).toEqual(["a", "b"]);
  });
});

describe("day strings", () => {
  it("shifts calendar days without a timezone", () => {
    expect(shiftDay("2026-09-12", -1)).toBe("2026-09-11");
    expect(shiftDay("2026-09-30", 1)).toBe("2026-10-01");
    expect(shiftDay("2026-01-01", -1)).toBe("2025-12-31");
  });

  it("accepts only YYYY-MM-DD", () => {
    expect(isDayString("2026-09-12")).toBe(true);
    expect(isDayString("12/09/2026")).toBe(false);
    expect(isDayString("2026-13-45")).toBe(false);
    expect(isDayString(undefined)).toBe(false);
  });
});

describe("hrefs", () => {
  it("builds the standalone route and the desk tab with only the params that are set", () => {
    expect(testsHref({ orgSlug: "ever", host: "testes" })).toBe("/ever/meme/testes");
    expect(testsHref({ orgSlug: "ever", host: "testes", day: "2026-09-12", ruleSet: "operator" })).toBe("/ever/meme/testes?day=2026-09-12&set=operator");
    expect(testsHref({ orgSlug: "ever", host: "mesa", day: "2026-09-12", cursor: "abc" })).toBe("/ever/meme/mesa?tab=testes&day=2026-09-12&cursor=abc");
  });

  it("points the CSV button at the route handler that carries the session token, never at the API", () => {
    expect(csvExportHref("ever", "2026-09-12", null)).toBe("/ever/meme/testes/export?day=2026-09-12");
    expect(csvExportHref("ever", "2026-09-12", "operator")).toBe("/ever/meme/testes/export?day=2026-09-12&rule_set=operator");
    expect(csvExportHref("ever", "2026-09-12", null)).not.toMatch(/\.csv(\?|$)/);
  });

  it("bet detail lives under the desk", () => {
    expect(betDetailHref("ever", "bet-1")).toBe("/ever/meme/mesa/aposta/bet-1");
  });
});

describe("rule set labels", () => {
  it("reads a wallet set as REAL and leaves an experiment's name alone", () => {
    expect(ruleSetLabel("wallet:6nAh8drz")).toBe("REAL · carteira 6nAh8drz");
    expect(ruleSetLabel("meme_paper_v0/1")).toBe("meme_paper_v0/1");
  });
});
