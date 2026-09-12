/**
 * The "Fontes" panel (brief T4.3b): chips per source, three honest gauges,
 * the radar's and the loop's state -- every number with its observed_at, and
 * "sem leitura: motivo" where there is none, never a zero.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { MemeSourcesPanel } from "@/components/meme/meme-sources-panel";
import type { MemeSources } from "@/lib/api/meme-types";

import { source, sourcesPayload } from "./meme-sources-format.test";

afterEach(cleanup);

describe("MemeSourcesPanel (full)", () => {
  it("renders the chips, the three gauges with their observed_at, the blindness sentence and the consulted-at line", () => {
    render(<MemeSourcesPanel sources={sourcesPayload()} />);
    expect(screen.getByRole("heading", { name: "Fontes" })).toBeInTheDocument();
    expect(screen.getByText("pump.fun (REST)")).toBeInTheDocument();
    expect(screen.getByText("em dia")).toBeInTheDocument();
    expect(screen.getByText("43.3%")).toBeInTheDocument();
    expect(screen.getByText("39.0%")).toBeInTheDocument();
    expect(screen.getByText("16.0%")).toBeInTheDocument();
    expect(screen.getByText("moedas de outros launchpads que o radar não vê por construção")).toBeInTheDocument();
    expect(screen.getByText("radar vivo · heartbeat há 5 s")).toBeInTheDocument();
    // The fold minute (12:59Z = 09:59 Brasília) is the observed_at of both coverage gauges.
    expect(screen.getAllByTitle("2026-09-12T12:59:00Z").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/consultado em/)).toBeInTheDocument();
    expect(screen.getByText("250 mints rastreados")).toBeInTheDocument();
  });

  it("says 'sem leitura: motivo' for every missing number and never prints a 0 %", () => {
    render(
      <MemeSourcesPanel
        sources={sourcesPayload({
          radar_status: "heartbeat_missing",
          radar_reason: "no heartbeat hash at the key",
          sources_at: null,
          heartbeat_age_s: null,
          tracked: null,
          progress_coverage_pct: null,
          tape_coverage_pct: null,
          fold_minute: null,
          fold_rows: null,
          discovery_blind_share_1h: null,
          discovery_new_board_entries_1h: null,
          sources: [],
        })}
      />,
    );
    expect(screen.getAllByText(/^sem leitura: /).length).toBeGreaterThanOrEqual(3);
    expect(screen.queryByText(/0\.0%/)).toBeNull();
    expect(screen.queryByText(/^0%/)).toBeNull();
    expect(screen.getByText("radar: sem leitura (sem heartbeat do worker)")).toBeInTheDocument();
    expect(screen.getByText("rastreados: sem leitura")).toBeInTheDocument();
    expect(screen.getByText("nenhuma fonte no heartbeat")).toBeInTheDocument();
    expect(screen.queryByText("no heartbeat hash at the key")).toBeNull();
  });

  it("tolerates a payload with the optional T4.2d/T4.2e fields absent (older API)", () => {
    const absent = new Set(["progress_coverage_pct", "tape_coverage_pct", "fold_minute", "fold_rows", "tape_cycle_s", "discovery_blind_share_1h", "mayhem_pending"]);
    const payload = Object.fromEntries(Object.entries(sourcesPayload()).filter(([key]) => !absent.has(key))) as MemeSources;
    render(<MemeSourcesPanel sources={payload} />);
    expect(screen.getAllByText("sem leitura: o worker não informou este número").length).toBe(3);
  });

  it("shows the lab loop when given, in the desk's own words", () => {
    render(<MemeSourcesPanel sources={sourcesPayload()} loop={{ lastTickAt: "2026-09-12T12:59:20Z", reason: null }} />);
    expect(screen.getByText("laço vivo · último tick há 40 s")).toBeInTheDocument();
  });

  it("flags gaps and malformed messages in the last minute only when there were any", () => {
    render(<MemeSourcesPanel sources={sourcesPayload({ gaps_60s: 2, ws_malformed_60s: 1 })} />);
    expect(screen.getByText("2 gap(s) no último minuto")).toBeInTheDocument();
    expect(screen.getByText("1 mensagem(ns) malformada(s) no último minuto")).toBeInTheDocument();
  });

  it("shows nothing about the 15-second clock for a worker that predates it (never an empty card)", () => {
    render(<MemeSourcesPanel sources={sourcesPayload()} />);
    expect(screen.queryByText(/relógio de 15 s/)).not.toBeInTheDocument();
  });

  it("shows the 15-second clock's decision→fill latency once the worker reports it (T4.16)", () => {
    render(<MemeSourcesPanel sources={sourcesPayload({ fast_lane_mints: 42, lab_decision_to_fill_s_p50: 3.2, lab_decision_to_fill_s_p95: 18.9, lab_bets_indeterminate_total: 5 })} />);
    expect(screen.getByText(/42 moedas < 5 min no relógio de 15 s/)).toBeInTheDocument();
    expect(screen.getByText(/decisão → fill p50 \(medido\) 3.2 s/)).toBeInTheDocument();
  });

  // T4.2g / T4.20: the batch tape (`swap_api_activity`) and its heartbeat counters.
  it("shows nothing about the batch tape for a worker that predates it (never an empty line)", () => {
    render(<MemeSourcesPanel sources={sourcesPayload()} />);
    expect(screen.queryByText(/fita por lote/)).not.toBeInTheDocument();
  });

  it("names the batch tape source and its counters once the worker reports them", () => {
    const batch = source({ name: "swap_api_activity", status: "ok", used_60s: 3, budget_60s: 3 });
    render(<MemeSourcesPanel sources={sourcesPayload({ sources: [source(), batch], activity_mints: 130, activity_live_1m: 98, activity_dark_60s: 0, tape_activity_pct: 12.5 })} />);
    expect(screen.getByText("fita por lote (swap-api)")).toBeInTheDocument();
    expect(screen.getByText(/moedas no lote 130 · janela de 1 min viva 98 · lote sem janela de 1 min \(60 s\) 0/)).toBeInTheDocument();
    expect(screen.getByText(/cobertura da fita por lote 12.5%/)).toBeInTheDocument();
  });
});

describe("MemeSourcesPanel (line)", () => {
  it("is one wrapping line: chips, the three gauges and the radar state, details in titles", () => {
    render(<MemeSourcesPanel sources={sourcesPayload()} variant="line" />);
    expect(screen.queryByRole("heading")).toBeNull();
    expect(screen.getByText("Fontes")).toBeInTheDocument();
    expect(screen.getByText("43.3%")).toBeInTheDocument();
    expect(screen.getByText("39.0%")).toBeInTheDocument();
    expect(screen.getByText("16.0%")).toBeInTheDocument();
    expect(screen.getByText("radar vivo · heartbeat há 5 s")).toBeInTheDocument();
    expect(screen.getByTitle(/atraso 1.2 s · 30\/60 req\/min/)).toBeInTheDocument();
  });

  it("line: a missing gauge reads 'sem leitura' with the reason in its title", () => {
    render(<MemeSourcesPanel sources={sourcesPayload({ tape_coverage_pct: null, fold_rows: 0 })} variant="line" />);
    const missing = screen.getByTitle("sem leitura: o último minuto dobrado não tem linhas");
    expect(missing).toHaveTextContent("fita sem leitura");
  });

  it("line: the batch tape's counters ride the same line, prefixed, with the full text in the title", () => {
    render(<MemeSourcesPanel sources={sourcesPayload({ activity_mints: 130, activity_live_1m: 98 })} variant="line" />);
    const line = screen.getByTitle("moedas no lote 130 · janela de 1 min viva 98");
    expect(line).toHaveTextContent("fita por lote: moedas no lote 130 · janela de 1 min viva 98");
  });
});
