import { describe, expect, it } from "vitest";

import {
  classifyEventTiming,
  eventInWindow,
  eventKnownInWindow,
  latestOrderStateForSignal,
  orderFinalAsOfCursor,
  orderSettledAsOfCursor,
  positionVigenteAtCursor,
  regimeAtCursor,
  signalVigenteAtCursor,
  windowBounds,
} from "@/components/confluence/confluence-window";
import type { DeskOrderOut, DeskPositionOut } from "@/lib/api/market-desk-types";
import type { MarketEventOut } from "@/lib/api/market-events-types";
import type { SignalListItemOut } from "@/lib/api/lab-types";
import type { RegimeOut } from "@/lib/api/regime-types";

const CURSOR = "2026-09-23T11:45:00Z";

describe("windowBounds", () => {
  it("is symmetric around the cursor", () => {
    expect(windowBounds(CURSOR, 15)).toEqual({
      since: "2026-09-23T11:30:00.000Z",
      until: "2026-09-23T12:00:00.000Z",
    });
  });
});

function position(overrides: Partial<DeskPositionOut> = {}): Pick<DeskPositionOut, "entry_at" | "exit_at"> {
  return { entry_at: "2026-09-23T10:00:00Z", exit_at: null, ...overrides };
}

describe("positionVigenteAtCursor", () => {
  it("a position opened at 10:00 and still open at 11:45 is vigente", () => {
    expect(positionVigenteAtCursor(position(), CURSOR)).toBe(true);
  });

  it("the same position, once it has exit_at after the cursor, still counts", () => {
    expect(positionVigenteAtCursor(position({ exit_at: "2026-09-23T12:00:00Z" }), CURSOR)).toBe(true);
  });

  it("the same position, after its own exit_at, no longer counts", () => {
    expect(positionVigenteAtCursor(position({ exit_at: "2026-09-23T11:00:00Z" }), CURSOR)).toBe(false);
  });

  it("a position that only opens after the cursor is not vigente", () => {
    expect(positionVigenteAtCursor(position({ entry_at: "2026-09-23T12:00:00Z" }), CURSOR)).toBe(false);
  });
});

function signal(
  overrides: Partial<Pick<SignalListItemOut, "decision_at" | "expires_at" | "tracking_state">> = {},
): Pick<SignalListItemOut, "decision_at" | "expires_at" | "tracking_state"> {
  return {
    decision_at: "2026-09-23T11:40:00Z",
    expires_at: "2026-09-23T11:50:00Z",
    tracking_state: "active",
    ...overrides,
  };
}

describe("signalVigenteAtCursor", () => {
  it("emitted before the cursor, expiring after it, still active: vigente", () => {
    expect(signalVigenteAtCursor(signal(), CURSOR)).toBe(true);
  });

  it("already expired at the cursor: not vigente", () => {
    expect(signalVigenteAtCursor(signal({ expires_at: "2026-09-23T11:44:00Z" }), CURSOR)).toBe(false);
  });

  it("emitted after the cursor: not vigente yet", () => {
    expect(signalVigenteAtCursor(signal({ decision_at: "2026-09-23T11:46:00Z" }), CURSOR)).toBe(false);
  });

  it("a terminal/no_entry/censored signal never counts, however the timestamps line up", () => {
    expect(signalVigenteAtCursor(signal({ tracking_state: "terminal" }), CURSOR)).toBe(false);
  });

  it("no expires_at recorded is not read as already expired", () => {
    expect(signalVigenteAtCursor(signal({ expires_at: null }), CURSOR)).toBe(true);
  });
});

function order(overrides: Partial<DeskOrderOut> = {}): DeskOrderOut {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    signal_id: "22222222-2222-2222-2222-222222222222",
    side: "buy",
    status: "refused",
    reason: "parity_above_cap",
    attempt: 1,
    admission: {},
    quote: null,
    tx_signature: null,
    received_at: "2026-09-23T11:41:00Z",
    // Real shape of a row REFUSED AT CREATION (`spot_entries.py`'s
    // `status="admitted" if approved else "refused"` / `spot_entry_writes.py`'s
    // `refuse_row`): `_INSERT_ORDER` never sets `settled_at` on this path, and
    // `admitted_at` only when `status = 'admitted'` -- so both stay `null`
    // forever for a row that was never admitted. This is the MAJORITY real
    // shape (Astra's round-4 review, must-fix 1), not an edge case.
    admitted_at: null,
    settled_at: null,
    ...overrides,
  };
}

describe("orderSettledAsOfCursor", () => {
  it("a settled_at at or before the cursor counts as settled", () => {
    expect(orderSettledAsOfCursor(order({ settled_at: "2026-09-23T11:42:00Z" }), CURSOR)).toBe(true);
    expect(orderSettledAsOfCursor(order({ settled_at: CURSOR }), CURSOR)).toBe(true);
  });

  it("a settled_at strictly after the cursor does not count yet", () => {
    expect(orderSettledAsOfCursor(order({ settled_at: "2026-09-23T11:47:00Z" }), CURSOR)).toBe(false);
  });

  it("no settled_at at all is never treated as settled", () => {
    expect(orderSettledAsOfCursor(order({ settled_at: null }), CURSOR)).toBe(false);
  });
});

describe("orderFinalAsOfCursor (Astra's round-4 review, must-fix 1)", () => {
  it("a row refused at creation (admitted_at null) is final at its own received_at, even with no settled_at at all", () => {
    expect(orderFinalAsOfCursor(order({ admitted_at: null, settled_at: null, received_at: "2026-09-23T11:41:00Z" }), CURSOR)).toBe(true);
  });

  it("a row refused at creation but received AFTER the cursor is not yet final", () => {
    expect(orderFinalAsOfCursor(order({ admitted_at: null, settled_at: null, received_at: "2026-09-23T11:46:00Z" }), CURSOR)).toBe(false);
  });

  it("an admitted row (admitted_at set) with no settled_at at all is never final, regardless of received_at", () => {
    expect(orderFinalAsOfCursor(order({ admitted_at: "2026-09-23T11:41:00Z", settled_at: null }), CURSOR)).toBe(false);
  });

  it("an admitted row that settles at or before the cursor is final", () => {
    expect(orderFinalAsOfCursor(order({ admitted_at: "2026-09-23T11:41:00Z", settled_at: "2026-09-23T11:42:00Z" }), CURSOR)).toBe(true);
  });

  it("an admitted row that only settles strictly after the cursor is not final yet", () => {
    expect(orderFinalAsOfCursor(order({ admitted_at: "2026-09-23T11:41:00Z", settled_at: "2026-09-23T11:47:00Z" }), CURSOR)).toBe(false);
  });
});

describe("latestOrderStateForSignal", () => {
  const signalId = "22222222-2222-2222-2222-222222222222";

  it("a signal refused AT CREATION (admitted_at/settled_at both null) still renders the refusal -- Astra's round-4 review, must-fix 1", () => {
    const state = latestOrderStateForSignal([order()], signalId, CURSOR);
    expect(state.kind).toBe("refused");
  });

  it("a signal with no matching order at all is 'none' -- never inferred as 'not looked at'", () => {
    const state = latestOrderStateForSignal([order({ signal_id: "other" })], signalId, CURSOR);
    expect(state.kind).toBe("none");
  });

  it("an executed retry after a refused attempt wins -- the outcome that happened, not the first try", () => {
    const state = latestOrderStateForSignal(
      [
        order({ attempt: 1, status: "refused" }),
        order({ attempt: 2, status: "confirmed", reason: null, admitted_at: "2026-09-23T11:41:30Z", settled_at: "2026-09-23T11:42:00Z" }),
      ],
      signalId,
      CURSOR,
    );
    expect(state.kind).toBe("executed");
  });

  it("code review round 3/4: received before the cursor, ADMITTED, but only CONFIRMED after it stays 'pending' at the cursor -- never the future status", () => {
    // received 11:44, admitted 11:44, cursor 11:45, confirmed 11:47 -- the
    // exact scenario in the review: `status` already reads 'confirmed'
    // (mutated in place), but `settled_at` (11:47) is strictly after CURSOR.
    const state = latestOrderStateForSignal(
      [
        order({
          received_at: "2026-09-23T11:44:00Z",
          status: "confirmed",
          reason: null,
          admitted_at: "2026-09-23T11:44:00Z",
          settled_at: "2026-09-23T11:47:00Z",
        }),
      ],
      signalId,
      CURSOR,
    );
    expect(state.kind).toBe("pending");
  });

  it("an admitted order received by the cursor but never yet settled (settled_at null) is 'pending', not 'none'", () => {
    const state = latestOrderStateForSignal(
      [order({ status: "admitted", reason: null, admitted_at: "2026-09-23T11:41:00Z", settled_at: null })],
      signalId,
      CURSOR,
    );
    expect(state.kind).toBe("pending");
  });

  it("a FAILED order settled by the cursor renders as 'failed', not 'pending' or 'none' -- Astra's round-4 review, must-fix 2", () => {
    const state = latestOrderStateForSignal(
      [order({ status: "failed", reason: "signer_failed:timeout", admitted_at: "2026-09-23T11:41:00Z", settled_at: "2026-09-23T11:42:00Z" })],
      signalId,
      CURSOR,
    );
    expect(state.kind).toBe("failed");
  });
});

function event(overrides: Partial<MarketEventOut> = {}): Pick<MarketEventOut, "published_at" | "ingested_at" | "observed_at"> {
  return {
    published_at: "2026-09-23T11:40:00Z",
    observed_at: "2026-09-23T11:40:00Z",
    ingested_at: "2026-09-23T11:41:00Z",
    ...overrides,
  };
}

describe("classifyEventTiming", () => {
  it("published before the cursor, ingested before it too: known", () => {
    expect(classifyEventTiming(event(), CURSOR)).toBe("known");
  });

  it("published before the cursor but ingested after it: later -- never folded into block A", () => {
    expect(classifyEventTiming(event({ ingested_at: "2026-09-23T13:00:00Z" }), CURSOR)).toBe("later");
  });
});

describe("eventInWindow", () => {
  it("uses published_at when present", () => {
    const bounds = windowBounds(CURSOR, 15);
    expect(eventInWindow(event(), bounds)).toBe(true);
  });

  it("falls back to observed_at when published_at is unknown", () => {
    const bounds = windowBounds(CURSOR, 15);
    expect(eventInWindow(event({ published_at: null, observed_at: "2026-09-23T11:35:00Z" }), bounds)).toBe(true);
  });
});

describe("eventKnownInWindow (code review round 2, must-fix 3)", () => {
  const bounds = windowBounds(CURSOR, 15);

  it("an event inside the window and known (ingested by the cursor) is included", () => {
    expect(eventKnownInWindow(event(), bounds, CURSOR)).toBe(true);
  });

  it("an event inside the window by published_at, but ingested AFTER the cursor, is excluded -- block B must never absorb it, even though block C will", () => {
    expect(eventKnownInWindow(event({ ingested_at: "2026-09-23T13:00:00Z" }), bounds, CURSOR)).toBe(false);
  });

  it("an event outside the window is excluded regardless of ingestion timing", () => {
    expect(
      eventKnownInWindow(
        event({ published_at: "2026-09-23T09:00:00Z", observed_at: "2026-09-23T09:00:00Z", ingested_at: "2026-09-23T09:01:00Z" }),
        bounds,
        CURSOR,
      ),
    ).toBe(false);
  });
});

function regimeRow(overrides: Partial<RegimeOut> = {}): Pick<RegimeOut, "start_time" | "end_time"> {
  return { start_time: "2026-09-23T00:00:00Z", end_time: null, ...overrides };
}

describe("regimeAtCursor", () => {
  it("an ongoing regime (end_time null) that started before the cursor covers it", () => {
    expect(regimeAtCursor([regimeRow()], CURSOR)).not.toBeNull();
  });

  it("a regime that ended before the cursor does not cover it", () => {
    expect(regimeAtCursor([regimeRow({ end_time: "2026-09-23T10:00:00Z" })], CURSOR)).toBeNull();
  });

  it("no history at all: sem leitura de regime anterior a este instante", () => {
    expect(regimeAtCursor([], CURSOR)).toBeNull();
  });
});
