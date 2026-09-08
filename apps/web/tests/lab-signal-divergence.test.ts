import { describe, expect, it } from "vitest";

import { countDivergentGroups, formatMoneyRange, notionalRangeUsdt, pnlRangeUsdt } from "@/components/lab/lab-signal-divergence";
import { groupSignalsByIdentity } from "@/components/lab/lab-signal-grouping";
import { exampleRuler, makeSignal } from "@/tests/fixtures/lab";
import { exampleSiblingSignals } from "@/tests/fixtures/lab-pagination";
import { formatUsdtSigned } from "@/lib/format";

const ruler = exampleRuler();

/**
 * Finding 2 of the T3.38 review (closed by T3.38c): once `identity_key`
 * includes `stop` (T3.38c-api), sibling versions in one group should always
 * agree on `r_multiple`/money -- this module is the display-time safeguard
 * for the case where they still do not, so the screen never silently shows
 * the first member's money as if it spoke for the whole group.
 */
describe("pnlRangeUsdt: the money-divergence safeguard (finding 2)", () => {
  it("is null when the group's members all agree (the healthy case, exampleSiblingSignals' own r_multiple: '1.0000' on every member)", () => {
    expect(pnlRangeUsdt(exampleSiblingSignals(), ruler)).toBeNull();
  });

  it("is null with fewer than two members (nothing to compare)", () => {
    expect(pnlRangeUsdt([makeSignal({ r_multiple: "1.0" })], ruler)).toBeNull();
  });

  it("returns the real [min, max] when members disagree on r_multiple", () => {
    const members = [makeSignal({ signal_id: "a", r_multiple: "1.0" }), makeSignal({ signal_id: "b", r_multiple: "1.5" })];
    const range = pnlRangeUsdt(members, ruler);
    expect(range).not.toBeNull();
    expect(range?.min).toBeCloseTo(1.0 * ruler.riskUsdt, 6);
    expect(range?.max).toBeCloseTo(1.5 * ruler.riskUsdt, 6);
  });

  it("never flags a difference the reader could not see on screen (sub-cent Decimal noise rounds to the same figure)", () => {
    const members = [makeSignal({ signal_id: "a", r_multiple: "1.00000001" }), makeSignal({ signal_id: "b", r_multiple: "1.00000002" })];
    expect(pnlRangeUsdt(members, ruler)).toBeNull();
  });

  it("ignores members with an unknown r_multiple instead of treating null as a divergent 0", () => {
    const members = [makeSignal({ signal_id: "a", r_multiple: "1.0" }), makeSignal({ signal_id: "b", r_multiple: null, r_multiple_reason: "no_sample" })];
    expect(pnlRangeUsdt(members, ruler)).toBeNull();
  });
});

describe("notionalRangeUsdt: same safeguard for 'quantia simulada', driven by stop", () => {
  it("is null when every member shares the same stop distance", () => {
    expect(notionalRangeUsdt(exampleSiblingSignals(), ruler)).toBeNull();
  });

  it("returns a real range when members disagree on stop (the exact gap T3.38c-api's identity_key fix closes)", () => {
    const members = [
      makeSignal({ signal_id: "a", virtual_entry: "100", stop: "90" }),
      makeSignal({ signal_id: "b", virtual_entry: "100", stop: "95" }),
    ];
    const range = notionalRangeUsdt(members, ruler);
    expect(range).not.toBeNull();
    expect(range?.min).toBeLessThan(range?.max as number);
  });
});

describe("formatMoneyRange: both ends through the same signed formatter every other money figure uses", () => {
  it("joins min and max with ' a '", () => {
    expect(formatMoneyRange({ min: 10, max: 20 })).toBe(`${formatUsdtSigned(10)} a ${formatUsdtSigned(20)}`);
  });
});

describe("countDivergentGroups: the totals card's own honesty gate", () => {
  it("is 0 for a healthy, agreeing sibling group (the expected case once T3.38c-api's fix is live)", () => {
    const groups = groupSignalsByIdentity(exampleSiblingSignals());
    expect(countDivergentGroups(groups, ruler)).toBe(0);
  });

  it("counts a group whose members disagree on r_multiple, and never counts a singleton group", () => {
    const divergent = exampleSiblingSignals().map((row, i) => (i === 0 ? { ...row, r_multiple: "9.0000" } : row));
    const singleton = [makeSignal({ signal_id: "solo", identity_key: "solo-key" })];
    const groups = groupSignalsByIdentity([...divergent, ...singleton]);
    expect(countDivergentGroups(groups, ruler)).toBe(1);
  });
});
