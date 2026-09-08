import { describe, expect, it } from "vitest";

import {
  LAB_SEGMENTS,
  matchesSegment,
  SEGMENT_TO_STATE,
  segmentCounts,
  sortSignalsConcludedFirst,
  stateToSegment,
  visibleSignalsForSegment,
} from "@/components/lab/lab-signal-segments";
import { makeSignal } from "@/tests/fixtures/lab";

describe("matchesSegment: the four buckets brief T3.17b item 4 names", () => {
  it("'concluded' is exactly tracking_state === terminal", () => {
    expect(matchesSegment(makeSignal({ tracking_state: "terminal" }), "concluded")).toBe(true);
    expect(matchesSegment(makeSignal({ tracking_state: "active" }), "concluded")).toBe(false);
  });

  it("'open' is exactly tracking_state === active", () => {
    expect(matchesSegment(makeSignal({ tracking_state: "active" }), "open")).toBe(true);
    expect(matchesSegment(makeSignal({ tracking_state: "terminal" }), "open")).toBe(false);
  });

  it("'pending' folds pending_entry, no_entry and censored together -- none of them a win/loss/still-tracked in the active sense", () => {
    expect(matchesSegment(makeSignal({ tracking_state: "pending_entry" }), "pending")).toBe(true);
    expect(matchesSegment(makeSignal({ tracking_state: "no_entry" }), "pending")).toBe(true);
    expect(matchesSegment(makeSignal({ tracking_state: "censored" }), "pending")).toBe(true);
    expect(matchesSegment(makeSignal({ tracking_state: "terminal" }), "pending")).toBe(false);
    expect(matchesSegment(makeSignal({ tracking_state: "active" }), "pending")).toBe(false);
  });

  it("'all' matches every tracking_state", () => {
    for (const tracking_state of ["pending_entry", "active", "terminal", "no_entry", "censored"] as const) {
      expect(matchesSegment(makeSignal({ tracking_state }), "all")).toBe(true);
    }
  });
});

describe("segmentCounts", () => {
  it("counts each row into exactly one of concluded/open/pending, plus the running total in 'all'", () => {
    const rows = [
      makeSignal({ signal_id: "1", tracking_state: "terminal" }),
      makeSignal({ signal_id: "2", tracking_state: "active" }),
      makeSignal({ signal_id: "3", tracking_state: "pending_entry" }),
      makeSignal({ signal_id: "4", tracking_state: "no_entry" }),
      makeSignal({ signal_id: "5", tracking_state: "censored" }),
    ];
    expect(segmentCounts(rows)).toEqual({ concluded: 1, open: 1, pending: 3, all: 5 });
  });
});

describe("sortSignalsConcludedFirst: default order (brief T3.17b item 4)", () => {
  it("puts every terminal row before every non-terminal row, each block sorted by decision_at desc", () => {
    const rows = [
      makeSignal({ signal_id: "old-pending", tracking_state: "pending_entry", decision_at: "2026-09-08T05:05:00Z" }),
      makeSignal({ signal_id: "old-terminal", tracking_state: "terminal", decision_at: "2026-09-07T00:00:00Z" }),
      makeSignal({ signal_id: "new-pending", tracking_state: "pending_entry", decision_at: "2026-09-08T06:00:00Z" }),
      makeSignal({ signal_id: "new-terminal", tracking_state: "terminal", decision_at: "2026-09-08T00:00:00Z" }),
    ];
    const ordered = sortSignalsConcludedFirst(rows).map((row) => row.signal_id);
    // A fresh page of mostly-pending rows (Everton's screenshot, item 4) must
    // never bury a concluded operation, even one from an earlier decision_at.
    expect(ordered).toEqual(["new-terminal", "old-terminal", "new-pending", "old-pending"]);
  });
});

describe("visibleSignalsForSegment: filters the ordered list", () => {
  it("returns only the segment's own rows, preserving the concluded-first/decision_at-desc order", () => {
    const rows = [
      makeSignal({ signal_id: "1", tracking_state: "pending_entry", decision_at: "2026-09-08T00:00:00Z" }),
      makeSignal({ signal_id: "2", tracking_state: "terminal", decision_at: "2026-09-07T00:00:00Z" }),
      makeSignal({ signal_id: "3", tracking_state: "no_entry", decision_at: "2026-09-08T06:00:00Z" }),
    ];
    expect(visibleSignalsForSegment(rows, "pending").map((r) => r.signal_id)).toEqual(["3", "1"]);
    expect(visibleSignalsForSegment(rows, "concluded").map((r) => r.signal_id)).toEqual(["2"]);
  });
});

describe("SEGMENT_TO_STATE / stateToSegment: T3.37's web<->API vocabulary mapping", () => {
  it("maps every LabSegment to its own API state 1:1, and back", () => {
    expect(SEGMENT_TO_STATE).toEqual({ concluded: "closed", open: "open", pending: "pending", all: "all" });
    for (const segment of LAB_SEGMENTS) {
      expect(stateToSegment(SEGMENT_TO_STATE[segment])).toBe(segment);
    }
  });
});
