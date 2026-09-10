import { describe, expect, it } from "vitest";

import { latencyHopSchema, latencyOutSchema, latencySloStatusSchema } from "@/lib/api/latency-types";

// The exact JSON frozen in `.claude/state/notes-T3.79.md` §4 --
// `hunter_api.schemas.latency.LatencyOut`'s worked example.
const FROZEN_CONTRACT = {
  hops: [
    { hop: "ingest", p50_s: 0.09, p95_s: 0.31, target_p50_s: 0.5, target_p95_s: 1.0, status: "ok" },
    { hop: "flush", p50_s: 1.03, p95_s: 3.9, target_p50_s: 0.5, target_p95_s: 1.0, status: "critical" },
    { hop: "decision", p50_s: 45.0, p95_s: 180.0, target_p50_s: 5.0, target_p95_s: 20.0, status: "critical" },
    { hop: "admission", p50_s: null, p95_s: null, target_p50_s: 1.0, target_p95_s: 2.0, status: "unknown" },
    { hop: "fill", p50_s: null, p95_s: null, target_p50_s: 1.0, target_p95_s: 2.0, status: "unknown" },
  ],
  end_to_end: { hop: "end_to_end", p50_s: null, p95_s: null, target_p50_s: 5.0, target_p95_s: 10.0, status: "unknown" },
  generated_at: "2026-09-10T16:24:00Z",
};

describe("latencyOutSchema: parses the frozen T3.79 contract verbatim", () => {
  it("accepts the exact worked example from notes-T3.79.md §4", () => {
    const parsed = latencyOutSchema.parse(FROZEN_CONTRACT);
    expect(parsed.hops).toHaveLength(5);
    expect(parsed.end_to_end.status).toBe("unknown");
    expect(parsed.end_to_end.p50_s).toBeNull();
    expect(parsed.hops[0]?.p50_s).toBe(0.09);
  });

  it("never coerces null p50_s/p95_s to 0 -- a real 0 and 'no reading yet' must stay distinguishable", () => {
    const parsed = latencyOutSchema.parse(FROZEN_CONTRACT);
    const admission = parsed.hops.find((hop) => hop.hop === "admission");
    expect(admission?.p50_s).toBeNull();
    expect(admission?.p95_s).toBeNull();
  });

  it("rejects a status outside ok/warn/critical/unknown", () => {
    expect(() => latencySloStatusSchema.parse("healthy")).toThrow();
  });

  it("rejects a hop missing its required target fields", () => {
    expect(() =>
      latencyHopSchema.parse({ hop: "ingest", p50_s: 0.1, p95_s: 0.2, status: "ok" }),
    ).toThrow();
  });

  it("rejects p50_s/p95_s sent as Decimal strings -- this contract is float, unlike lab-daily-goal's money fields", () => {
    expect(() =>
      latencyHopSchema.parse({
        hop: "ingest",
        p50_s: "0.09",
        p95_s: "0.31",
        target_p50_s: 0.5,
        target_p95_s: 1.0,
        status: "ok",
      }),
    ).toThrow();
  });
});
