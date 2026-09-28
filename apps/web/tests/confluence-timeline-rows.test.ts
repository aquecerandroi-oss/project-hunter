import { describe, expect, it } from "vitest";

import { buildBlockBRows, buildBlockCRows } from "@/components/confluence/confluence-timeline-rows";
import { windowBounds } from "@/components/confluence/confluence-window";
import type { DeskOrderOut, DeskOut } from "@/lib/api/market-desk-types";
import type { MarketEventOut } from "@/lib/api/market-events-types";

const CURSOR = "2026-09-23T11:45:00Z";
const BOUNDS = windowBounds(CURSOR, 15); // [11:30, 12:00]

function order(overrides: Partial<DeskOrderOut> = {}): DeskOrderOut {
  return {
    id: "order-fixture",
    signal_id: "signal-fixture",
    side: "buy",
    status: "refused",
    reason: "parity_above_cap",
    attempt: 1,
    admission: {},
    quote: null,
    tx_signature: null,
    received_at: "2026-09-23T11:41:00Z",
    admitted_at: null,
    settled_at: null,
    ...overrides,
  };
}

function desk(orders: DeskOrderOut[]): DeskOut {
  return {
    label: "spot/1",
    as_of: CURSOR,
    since: BOUNDS.since,
    until: BOUNDS.until,
    desk_market: null,
    orders,
    positions: [],
    orders_truncated: false,
    positions_truncated: false,
  };
}

describe("buildBlockBRows: orders (Astra's round-4 review, must-fix 3)", () => {
  it("a row refused at creation shows the refusal immediately, at received_at, inside the window", () => {
    const rows = buildBlockBRows(CURSOR, BOUNDS, [], [], desk([order({ received_at: "2026-09-23T11:41:00Z" })]));
    expect(rows).toHaveLength(1);
    expect(rows[0]?.text).toContain("Recusa: paridade da curva acima do teto");
    expect(rows[0]?.iso).toBe("2026-09-23T11:41:00Z");
  });

  it("an admitted order not yet settled shows a neutral 'received' row, never a status", () => {
    const rows = buildBlockBRows(
      CURSOR,
      BOUNDS,
      [],
      [],
      desk([order({ received_at: "2026-09-23T11:41:00Z", status: "admitted", reason: null, admitted_at: "2026-09-23T11:41:00Z", settled_at: null })]),
    );
    expect(rows).toHaveLength(1);
    expect(rows[0]?.text).toBe("Ordem recebida, admitida, aguardando confirmação");
  });

  it("an admitted order whose settlement ALSO falls in the window gets its own second row, at its own instant", () => {
    const rows = buildBlockBRows(
      CURSOR,
      BOUNDS,
      [],
      [],
      desk([
        order({
          received_at: "2026-09-23T11:46:00Z",
          status: "confirmed",
          reason: null,
          admitted_at: "2026-09-23T11:46:00Z",
          settled_at: "2026-09-23T11:50:00Z",
        }),
      ]),
    );
    expect(rows).toHaveLength(2);
    const byIso = new Map(rows.map((r) => [r.iso, r.text]));
    expect(byIso.get("2026-09-23T11:46:00Z")).toBe("Ordem recebida, admitida, aguardando confirmação");
    expect(byIso.get("2026-09-23T11:50:00Z")).toBe("Ordem confirmada");
  });

  it("the exact review scenario: received 11:46 (inside ±15), confirmed 13:00 (outside ±15) -- B shows ONLY the receipt, never retrodates the outcome onto 11:46", () => {
    const rows = buildBlockBRows(
      CURSOR,
      BOUNDS,
      [],
      [],
      desk([
        order({
          received_at: "2026-09-23T11:46:00Z",
          status: "confirmed",
          reason: null,
          admitted_at: "2026-09-23T11:46:00Z",
          settled_at: "2026-09-23T13:00:00Z",
        }),
      ]),
    );
    expect(rows).toHaveLength(1);
    expect(rows[0]?.text).toBe("Ordem recebida, admitida, aguardando confirmação");
  });
});

describe("buildBlockCRows: order outcomes discovered after the cursor (Astra's round-4 review, must-fix 3)", () => {
  it("a settlement strictly after the cursor surfaces in C, at its own settled_at, regardless of the ±N window", () => {
    const rows = buildBlockCRows(
      CURSOR,
      [],
      [],
      desk([
        order({
          received_at: "2026-09-23T11:46:00Z",
          status: "confirmed",
          reason: null,
          admitted_at: "2026-09-23T11:46:00Z",
          settled_at: "2026-09-23T13:00:00Z",
        }),
      ]),
    );
    expect(rows).toHaveLength(1);
    expect(rows[0]?.iso).toBe("2026-09-23T13:00:00Z");
    expect(rows[0]?.text).toBe("Ordem confirmada");
  });

  it("a settlement at or before the cursor never appears in C -- it was already known", () => {
    const rows = buildBlockCRows(
      CURSOR,
      [],
      [],
      desk([order({ status: "confirmed", reason: null, admitted_at: "2026-09-23T11:41:00Z", settled_at: "2026-09-23T11:42:00Z" })]),
    );
    expect(rows).toHaveLength(0);
  });
});

function event(overrides: Partial<MarketEventOut> = {}): MarketEventOut {
  return {
    id: "event-fixture",
    market_id: null,
    exchange: "binance",
    symbol: "BTCUSDT",
    source: "manual",
    kind: "narrative",
    title: "Título de teste",
    url: null,
    published_at: "2026-09-23T11:40:00Z",
    observed_at: "2026-09-23T11:40:00Z",
    ingested_at: "2026-09-23T11:41:00Z",
    confidence: "reported",
    notes: {},
    recorded_by: "everton",
    ...overrides,
  } as MarketEventOut;
}

describe("buildBlockCRows: every event unknown at the cursor gets a destination (Astra's round-4 review, must-fix 4)", () => {
  it("published before the cursor, ingested after: the original design §4C case", () => {
    const rows = buildBlockCRows(CURSOR, [], [event({ published_at: "2026-09-23T11:40:00Z", ingested_at: "2026-09-23T13:00:00Z" })], null);
    expect(rows).toHaveLength(1);
    expect(rows[0]?.text).toContain("publicada antes, ingerida depois");
  });

  it("no published_at at all (observed-only), ingested after the cursor: still lands in C, not nowhere", () => {
    const rows = buildBlockCRows(
      CURSOR,
      [],
      [event({ published_at: null, observed_at: "2026-09-23T11:46:00Z", ingested_at: "2026-09-23T11:47:00Z" })],
      null,
    );
    expect(rows).toHaveLength(1);
    expect(rows[0]?.text).toContain("ingerida depois deste instante");
  });

  it("published AFTER the cursor and also ingested after it: still lands in C, not nowhere", () => {
    const rows = buildBlockCRows(
      CURSOR,
      [],
      [event({ published_at: "2026-09-23T11:46:00Z", ingested_at: "2026-09-23T11:47:00Z" })],
      null,
    );
    expect(rows).toHaveLength(1);
    expect(rows[0]?.text).toContain("ingerida depois deste instante");
  });

  it("known by the cursor (ingested before it): never appears in C", () => {
    const rows = buildBlockCRows(CURSOR, [], [event({ ingested_at: "2026-09-23T11:41:00Z" })], null);
    expect(rows).toHaveLength(0);
  });
});
