import { describe, expect, it } from "vitest";

import {
  BLINDNESS_SENTENCE,
  blindnessGauge,
  budgetShare,
  fastLaneLine,
  formatAgeS,
  formatBudget,
  progressGauge,
  radarStateLabel,
  sourceChip,
  tapeGauge,
} from "@/components/meme/meme-sources-format";
import type { MemeSourceOut, MemeSources } from "@/lib/api/meme-types";

const AS_OF = "2026-09-12T13:00:00Z"; // 10:00 Brasília

function source(overrides: Partial<MemeSourceOut> = {}): MemeSourceOut {
  return {
    name: "pumpfun_rest",
    status: "ok",
    enabled: true,
    connected: null,
    last_observed_at: "2026-09-12T12:59:50Z",
    last_received_at: "2026-09-12T12:59:51Z",
    lag_s: 1.2,
    age_s: 9,
    used_60s: 30,
    budget_60s: 60,
    errors_1h: 0,
    last_error: null,
    last_error_at: null,
    reason: null,
    table: "meme_curve_snapshots",
    last_row_observed_at: "2026-09-12T12:59:50Z",
    row_reason: null,
    ...overrides,
  };
}

export function sourcesPayload(overrides: Partial<MemeSources> = {}): MemeSources {
  return {
    label: "Meme Radar — fontes de dados; só monitoramento, nunca execução (pump.fun)",
    as_of: AS_OF,
    heartbeat_key: "hb:meme:radar",
    heartbeat_ts: "2026-09-12T12:59:55Z",
    heartbeat_age_s: 5,
    radar_status: "alive",
    radar_reason: null,
    sources_at: "2026-09-12T12:59:55Z",
    stalled_after_s: 60,
    tracked: 250,
    budget_used_60s: 30,
    budget_60s: 60,
    gaps_60s: 0,
    ws_malformed_60s: 0,
    last_snapshot_observed_at: "2026-09-12T12:59:50Z",
    lag_s: 1.2,
    trenches_connected: true,
    trenches_patches_60s: 40,
    swap_api_used_60s: 200,
    swap_api_budget_60s: 900,
    discovery_blind_share_1h: 0.16,
    discovery_new_board_entries_1h: 50,
    discovery_non_pump_entries_1h: 8,
    discovery_blind_explanation: "programa fora do escopo do adaptador",
    progress_coverage_pct: 43.3,
    tape_coverage_pct: 39,
    fold_minute: "2026-09-12T12:59:00Z",
    fold_rows: 250,
    tape_tracked_mints: 250,
    tape_covered_mints: 98,
    tape_never_pulled: 12,
    tape_cycle_s: 4.1,
    tape_deferred_60s: 20,
    mayhem_pending: 74,
    mayhem_denominators_60s: 17,
    coverage_explanation: "cobertura do último minuto dobrado",
    sources: [source()],
    ...overrides,
  };
}

describe("formatAgeS / formatBudget / budgetShare", () => {
  it("prints ages as N s | N min | N h with a space before the unit (DESIGN-5)", () => {
    expect(formatAgeS(12)).toBe("12 s");
    expect(formatAgeS(75)).toBe("1 min");
    expect(formatAgeS(3700)).toBe("1 h");
    expect(formatAgeS(0.4)).toBe("0 s");
  });

  it("prints used/limit per minute, and says so when the limit or the count is missing", () => {
    expect(formatBudget(54, 60)).toBe("54/60 req/min");
    expect(formatBudget(30, null)).toBe("30/min (sem limite declarado)");
    expect(formatBudget(null, null)).toBe("orçamento: sem leitura");
    expect(formatBudget(undefined, 60)).toBe("orçamento: sem leitura");
  });

  it("budgetShare is a fraction, null when either side is unknown or the limit is zero", () => {
    expect(budgetShare(54, 60)).toBe(0.9);
    expect(budgetShare(30, null)).toBeNull();
    expect(budgetShare(30, 0)).toBeNull();
  });
});

describe("sourceChip: green connected/fresh, amber lagging or budget ≥ 90 %, red disconnected/errors, grey no reading", () => {
  it("green: a socket that is connected and fresh", () => {
    const chip = sourceChip(source({ name: "pumpportal_ws", status: "connected", connected: true, budget_60s: null, used_60s: 120 }), 60);
    expect(chip.tone).toBe("green");
    expect(chip.state).toBe("conectada");
    expect(chip.name).toBe("PumpPortal (WS)");
    expect(chip.detail).toBe("atraso 1.2 s · 120/min (sem limite declarado)");
    expect(chip.observedAt).toBe("2026-09-12T12:59:50Z");
  });

  it("green: a request source with a recent observation", () => {
    const chip = sourceChip(source(), 60);
    expect(chip.tone).toBe("green");
    expect(chip.state).toBe("em dia");
    expect(chip.detail).toBe("atraso 1.2 s · 30/60 req/min");
  });

  it("amber: nothing received for longer than the radar's own stall threshold", () => {
    const chip = sourceChip(source({ age_s: 75 }), 60);
    expect(chip.tone).toBe("amber");
    expect(chip.state).toBe("atrasada há 1 min");
  });

  it("amber: budget used at or above 90 % of the limit", () => {
    const chip = sourceChip(source({ used_60s: 54, budget_60s: 60 }), 60);
    expect(chip.tone).toBe("amber");
    expect(chip.state).toBe("orçamento 90%");
  });

  it("red: disconnected socket", () => {
    const chip = sourceChip(source({ name: "trenches_ws", status: "disconnected", connected: false }), 60);
    expect(chip.tone).toBe("red");
    expect(chip.state).toBe("desconectada");
    expect(chip.name).toBe("boards do site (WS)");
  });

  it("red: erroring request source names the count and keeps the last error in the title", () => {
    const chip = sourceChip(source({ status: "erroring", errors_1h: 3, last_error: "HTTP 429", last_error_at: "2026-09-12T12:59:58Z" }), 60);
    expect(chip.tone).toBe("red");
    expect(chip.state).toBe("com erro · 3 na hora");
    expect(chip.title).toContain("HTTP 429");
  });

  it("red: errors in the last hour even when the source is observing again (the brief's rule), and red beats amber", () => {
    const chip = sourceChip(source({ status: "ok", errors_1h: 2, used_60s: 59, budget_60s: 60 }), 60);
    expect(chip.tone).toBe("red");
    expect(chip.state).toBe("2 erro(s) na hora");
  });

  it("grey: disabled by switch", () => {
    const chip = sourceChip(source({ name: "indexer_risk", status: "disabled", enabled: false, reason: "disabled" }), 60);
    expect(chip.tone).toBe("grey");
    expect(chip.state).toBe("desligada");
    expect(chip.name).toBe("risco do site (indexer)");
  });

  it("grey: unknown says 'sem leitura' with the worker's reason in plain words, never the raw slug", () => {
    const chip = sourceChip(source({ name: "swap_api", status: "unknown", reason: "never_observed", lag_s: null, age_s: null, last_observed_at: null }), 60);
    expect(chip.tone).toBe("grey");
    expect(chip.state).toBe("sem leitura: nunca observou nada desde que o worker subiu");
    expect(chip.state).not.toContain("never_observed");
    expect(chip.detail).toBe("atraso: sem leitura · 30/60 req/min");
    expect(chip.observedAt).toBeNull();
    expect(chip.name).toBe("fita do site (swap-api)");
  });

  it("grey: heartbeat without this source", () => {
    const chip = sourceChip(source({ status: "unknown", reason: "heartbeat_missing" }), 60);
    expect(chip.state).toBe("sem leitura: o heartbeat não traz esta fonte");
  });

  it("a source name the screen does not know yet still gets a readable label (backend evolves in parallel)", () => {
    const chip = sourceChip(source({ name: "new_feed_x" }), 60);
    expect(chip.name).toBe("new feed x");
  });
});

describe("progressGauge / tapeGauge: the last folded minute's coverage, each with its observed_at", () => {
  it("shows the worker's percentage (0..100 scale) with one decimal and the fold minute", () => {
    const gauge = progressGauge(sourcesPayload());
    expect(gauge.value).toBe("43.3%");
    expect(gauge.reason).toBeNull();
    expect(gauge.observedAt).toBe("2026-09-12T12:59:00Z");
    expect(gauge.detail).toBe("250 linha(s) no minuto · 74 Mayhem sem denominador");
  });

  it("tape: percentage plus covered/tracked mints, cycle, deferred and never-pulled counts", () => {
    const gauge = tapeGauge(sourcesPayload());
    expect(gauge.value).toBe("39.0%");
    expect(gauge.detail).toBe("98 de 250 mints com fita · ciclo 4.1 s · 20 adiado(s)/min · 12 nunca puxado(s)");
  });

  it("null before the first fold says so — never a 0", () => {
    const gauge = progressGauge(sourcesPayload({ progress_coverage_pct: null, fold_minute: null, fold_rows: null }));
    expect(gauge.value).toBeNull();
    expect(gauge.reason).toBe("sem leitura: nenhum minuto dobrado desde que o worker subiu");
  });

  it("null on an empty minute names the empty minute", () => {
    const gauge = tapeGauge(sourcesPayload({ tape_coverage_pct: null, fold_rows: 0 }));
    expect(gauge.reason).toBe("sem leitura: o último minuto dobrado não tem linhas");
  });

  it("a field the API does not send at all (older worker) reads 'o worker não informou'", () => {
    const payload = sourcesPayload();
    delete (payload as Partial<MemeSources>).progress_coverage_pct;
    delete (payload as Partial<MemeSources>).mayhem_pending;
    const gauge = progressGauge(payload);
    expect(gauge.value).toBeNull();
    expect(gauge.reason).toBe("sem leitura: o worker não informou este número");
    expect(gauge.detail).toBe("250 linha(s) no minuto");
  });

  it("a dead radar is the reason when the number is missing", () => {
    const gauge = progressGauge(sourcesPayload({ radar_status: "heartbeat_missing", progress_coverage_pct: null, fold_minute: null }));
    expect(gauge.reason).toBe("sem leitura: sem heartbeat do worker");
  });
});

describe("blindnessGauge: share of the new board the radar cannot see by construction", () => {
  it("shows the 0..1 share as a percentage, the counts and the fixed sentence", () => {
    const gauge = blindnessGauge(sourcesPayload());
    expect(gauge.value).toBe("16.0%");
    expect(gauge.detail).toBe("8 de 50 entradas do board new na hora");
    expect(gauge.observedAt).toBe("2026-09-12T12:59:55Z");
    expect(BLINDNESS_SENTENCE).toBe("moedas de outros launchpads que o radar não vê por construção");
  });

  it("an empty hour is unknown, not full coverage", () => {
    const gauge = blindnessGauge(sourcesPayload({ discovery_blind_share_1h: null, discovery_new_board_entries_1h: 0, discovery_non_pump_entries_1h: 0 }));
    expect(gauge.value).toBeNull();
    expect(gauge.reason).toBe("sem leitura: o board new não listou nada na última hora");
  });

  it("a worker that predates the counter reads 'o worker não informou'", () => {
    const payload = sourcesPayload();
    delete (payload as Partial<MemeSources>).discovery_blind_share_1h;
    delete (payload as Partial<MemeSources>).discovery_new_board_entries_1h;
    delete (payload as Partial<MemeSources>).discovery_non_pump_entries_1h;
    const gauge = blindnessGauge(payload);
    expect(gauge.reason).toBe("sem leitura: o worker não informou este número");
    expect(gauge.detail).toBeNull();
  });
});

describe("fastLaneLine: the 15-second clock's counters and the decision→fill latency (T4.16)", () => {
  it("joins every reported field in Portuguese, never a raw key", () => {
    const line = fastLaneLine(
      sourcesPayload({
        fast_lane_mints: 42,
        fast_lane_reads_60s: 4,
        fast_lane_calls_60s: 84,
        fast_lane_cycle_s: 14.6,
        lab_decision_to_fill_s_p50: 3.2,
        lab_decision_to_fill_s_p95: 18.9,
        lab_bets_indeterminate_total: 5,
      }),
    );
    expect(line).toBe(
      "42 moedas < 5 min no relógio de 15 s · 4 leituras por minuto (15 s) · 84 chamadas por minuto (15 s) · ciclo do relógio de 15 s 14.6 s · decisão → fill p50 (medido) 3.2 s · decisão → fill p95 (medido) 18.9 s · 5 indeterminadas (total)",
    );
  });

  it("is null (never an empty card) when a worker predates every one of these fields", () => {
    expect(fastLaneLine(sourcesPayload())).toBeNull();
  });
});

describe("radarStateLabel: vivo ≠ parado ≠ sem leitura", () => {
  it("alive: heartbeat age from the API's own clock", () => {
    expect(radarStateLabel(sourcesPayload())).toEqual({ tone: "green", label: "radar vivo · heartbeat há 5 s" });
  });

  it("stale: since when, in Brasília", () => {
    const state = radarStateLabel(sourcesPayload({ radar_status: "stale", radar_reason: "radar fields are 1800s old", sources_at: "2026-09-12T12:30:00Z" }));
    expect(state).toEqual({ tone: "red", label: "radar parado desde 12/09 09:30" });
  });

  it("no reading: names the cause in plain words, never the API's English reason", () => {
    expect(radarStateLabel(sourcesPayload({ radar_status: "heartbeat_missing", radar_reason: "no heartbeat hash at the key", sources_at: null }))).toEqual({
      tone: "grey",
      label: "radar: sem leitura (sem heartbeat do worker)",
    });
    expect(radarStateLabel(sourcesPayload({ radar_status: "redis_unavailable", sources_at: null })).label).toBe("radar: sem leitura (Redis indisponível)");
    expect(radarStateLabel(sourcesPayload({ radar_status: "never", sources_at: null })).label).toBe("radar: sem leitura (o worker subiu, mas o radar nunca escreveu seus campos)");
  });

  it("alive without an age still says alive, without inventing seconds", () => {
    expect(radarStateLabel(sourcesPayload({ heartbeat_age_s: null })).label).toBe("radar vivo");
  });
});
