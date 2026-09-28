"use client";

import type { IChartApi } from "lightweight-charts";
import Link from "next/link";
import { useCallback, useMemo, useState, type KeyboardEvent } from "react";

import { BrasiliaInstant } from "@/components/time/brasilia-instant";
import type { AnomalyOut } from "@/lib/api/anomalies-types";
import type { SignalListItemOut } from "@/lib/api/lab-types";
import type { DeskOut } from "@/lib/api/market-desk-types";
import type { MarketEventOut } from "@/lib/api/market-events-types";
import type { RegimeOut } from "@/lib/api/regime-types";
import type { Candle } from "@/lib/api/types";
import { barIndexContaining, confluenceCandleTimes } from "@/lib/charts/confluence-series";

import { ConfluenceChart } from "./confluence-chart";
import { ConfluenceEventList } from "./confluence-event-list";
import { ConfluenceInstantPanel } from "./confluence-instant-panel";
import { ConfluenceLanes } from "./confluence-lanes";
import { DEFAULT_WINDOW_MINUTES, WIDE_WINDOW_MINUTES } from "./confluence-window";

export interface TimeframeLink {
  timeframe: string;
  href: string;
  active: boolean;
}

export interface ConfluenceViewProps {
  timeframeSeconds: number;
  timeframeLinks: TimeframeLink[];
  widenHref: string;
  candles: Candle[];
  candlesError: string | null;
  signals: SignalListItemOut[];
  signalsError: string | null;
  desk: DeskOut | null;
  deskError: string | null;
  events: MarketEventOut[];
  eventsError: string | null;
  regimeHistory: RegimeOut[];
  regimeError: string | null;
  anomalies: AnomalyOut[];
  anomaliesError: string | null;
  strategyVersionLabels: Record<string, string>;
  /** Astra's review of T4.82 (must-fix 5): names of every source whose own row cap bit in this window -- a silent truncation must never read as "nada aconteceu". */
  truncationNotes: string[];
}

function ErrorNote({ label, reason }: { label: string; reason: string | null }) {
  if (reason === null) return null;
  return <p className="text-xs text-red">{label} indisponíveis: {reason}</p>;
}

interface ConfluenceHeaderProps {
  cursorIso: string | null;
  cursorCandle: Candle | null;
  timeframeLinks: TimeframeLink[];
  windowMinutes: number;
  onWindowMinutesChange: (minutes: number) => void;
}

/** The instant title plus the timeframe/window controls -- split out purely to keep `ConfluenceView` under the file's own line/complexity budget. */
function ConfluenceHeader({ cursorIso, cursorCandle, timeframeLinks, windowMinutes, onWindowMinutesChange }: ConfluenceHeaderProps) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-3">
      <h1 className="text-sm font-semibold text-fg">
        {cursorIso !== null ? (
          <>
            Instante: <BrasiliaInstant iso={cursorIso} />
            {cursorCandle && <span className="ml-2 font-mono tabular-nums text-fg-muted">{cursorCandle.close}</span>}
          </>
        ) : (
          "Nenhum instante carregado"
        )}
      </h1>
      <div className="flex items-center gap-2 text-xs">
        {timeframeLinks.map((link) => (
          <Link key={link.timeframe} href={link.href} className={`rounded-md border px-2 py-1 ${link.active ? "border-gold text-gold" : "border-border text-fg-muted hover:border-border-strong"}`}>
            {link.timeframe}
          </Link>
        ))}
        {[DEFAULT_WINDOW_MINUTES, WIDE_WINDOW_MINUTES].map((minutes) => (
          <button
            key={minutes}
            type="button"
            onClick={() => onWindowMinutesChange(minutes)}
            className={`rounded-md border px-2 py-1 ${windowMinutes === minutes ? "border-gold text-gold" : "border-border text-fg-muted"}`}
          >
            ±{minutes} min
          </button>
        ))}
      </div>
    </header>
  );
}


/**
 * The confluence screen's client half (design §7b): owns the cursor and the
 * ±N reading window, composes the chart, the four lanes, the "Neste
 * instante" panel and the period list. Every data source arrives already
 * fetched (one `try`/`catch` each, in the Server Component) -- this
 * component never fetches on its own; moving the cursor only ever re-reads
 * data already in memory (design §4: click fixes, arrow keys step one bar).
 */
export function ConfluenceView({
  timeframeSeconds,
  timeframeLinks,
  widenHref,
  candles,
  candlesError,
  signals,
  signalsError,
  desk,
  deskError,
  events,
  eventsError,
  regimeHistory,
  regimeError,
  anomalies,
  anomaliesError,
  strategyVersionLabels,
  truncationNotes,
}: ConfluenceViewProps) {
  const candleTimes = useMemo(() => confluenceCandleTimes(candles), [candles]);
  const lastBarIso = candleTimes.length > 0 ? new Date((candleTimes[candleTimes.length - 1] as number) * 1000).toISOString() : null;

  const [cursorIso, setCursorIso] = useState<string | null>(lastBarIso);
  const [windowMinutes, setWindowMinutes] = useState(DEFAULT_WINDOW_MINUTES);
  const [selectedSignalId, setSelectedSignalId] = useState<string | null>(null);
  const [chart, setChart] = useState<IChartApi | null>(null);
  const [rangeVersion, setRangeVersion] = useState(0);

  const moveCursorByBars = useCallback(
    (delta: number) => {
      if (cursorIso === null || candleTimes.length === 0) return;
      const currentIdx = barIndexContaining(candleTimes, cursorIso, timeframeSeconds);
      const base = currentIdx ?? (delta > 0 ? -1 : candleTimes.length);
      const nextIdx = Math.min(candleTimes.length - 1, Math.max(0, base + delta));
      setCursorIso(new Date((candleTimes[nextIdx] as number) * 1000).toISOString());
    },
    [cursorIso, candleTimes, timeframeSeconds],
  );

  const onKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (candleTimes.length === 0) return;
      if (event.key === "ArrowLeft") moveCursorByBars(event.shiftKey ? -10 : -1);
      else if (event.key === "ArrowRight") moveCursorByBars(event.shiftKey ? 10 : 1);
      else if (event.key === "Home") setCursorIso(new Date((candleTimes[0] as number) * 1000).toISOString());
      else if (event.key === "End") setCursorIso(lastBarIso);
      else if (event.key === "Escape") setCursorIso(lastBarIso);
      else return;
      event.preventDefault();
    },
    [candleTimes, lastBarIso, moveCursorByBars],
  );

  const cursorBarIdx = cursorIso !== null ? barIndexContaining(candleTimes, cursorIso, timeframeSeconds) : null;
  const cursorCandle = cursorBarIdx !== null ? (candles[cursorBarIdx] ?? null) : null;
  const selectedSignal = signals.find((s) => s.signal_id === selectedSignalId) ?? null;

  function selectSignal(signal: SignalListItemOut) {
    setSelectedSignalId(signal.signal_id);
    setCursorIso(signal.decision_at);
  }

  function selectEvent(event: MarketEventOut) {
    const iso = event.published_at ?? event.observed_at;
    setCursorIso(iso);
  }

  const errors: { label: string; reason: string | null }[] = [
    { label: "Candles", reason: candlesError },
    { label: "Sinais do Lab", reason: signalsError },
    { label: "Mesa spot/1", reason: deskError },
    { label: "Notícias", reason: eventsError },
    { label: "Regime", reason: regimeError },
    { label: "Anomalias", reason: anomaliesError },
  ];

  return (
    <div className="flex flex-col gap-4" onKeyDown={onKeyDown} tabIndex={0} role="group" aria-label="Confluência de mercado">
      <ConfluenceHeader cursorIso={cursorIso} cursorCandle={cursorCandle} timeframeLinks={timeframeLinks} windowMinutes={windowMinutes} onWindowMinutesChange={setWindowMinutes} />

      {errors.map((e) => (
        <ErrorNote key={e.label} label={e.label} reason={e.reason} />
      ))}

      {truncationNotes.length > 0 && (
        <p className="text-xs text-warning">
          Dados truncados nesta janela — {truncationNotes.join(", ")}. Estreite o período para ver o restante.
        </p>
      )}

      {candles.length === 0 && candlesError === null && (
        <p className="text-sm text-fg-muted">
          Sem candles neste período para este mercado. <Link href={widenHref} className="text-info underline">ampliar para 24 h</Link>
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="flex flex-col gap-0 rounded-lg border border-border bg-bg-elevated p-4">
          <ConfluenceChart
            candles={candles}
            timeframeSeconds={timeframeSeconds}
            positions={desk?.positions ?? []}
            selectedSignal={selectedSignal}
            onBarClick={setCursorIso}
            onReady={setChart}
            onRangeChange={() => setRangeVersion((v) => v + 1)}
          />
          <ConfluenceLanes
            chart={chart}
            rangeVersion={rangeVersion}
            candleTimes={candleTimes}
            timeframeSeconds={timeframeSeconds}
            signals={signals}
            events={events}
            desk={desk}
            anomalies={anomalies}
            regimeHistory={regimeHistory}
            selectedSignalId={selectedSignalId}
            onSelectSignal={selectSignal}
            onSelectEvent={selectEvent}
          />
        </div>
        <div className="lg:sticky lg:top-4 lg:max-h-[calc(100vh-6rem)] lg:overflow-y-auto">
          {cursorIso !== null ? (
            <ConfluenceInstantPanel
              cursorIso={cursorIso}
              windowMinutes={windowMinutes}
              candle={cursorCandle}
              signals={signals}
              signalsError={signalsError}
              desk={desk}
              deskError={deskError}
              events={events}
              regimeHistory={regimeHistory}
              anomalies={anomalies}
              strategyVersionLabels={strategyVersionLabels}
              selectedSignalId={selectedSignalId}
              onSelectSignal={selectSignal}
            />
          ) : (
            <p className="text-sm text-fg-muted">Sem candles carregados para escolher um instante.</p>
          )}
        </div>
      </div>

      <section className="rounded-lg border border-border bg-bg-elevated p-4">
        <h2 className="mb-2 text-xs font-medium uppercase tracking-wide text-fg-muted">Todos os acontecimentos do período</h2>
        <ConfluenceEventList signals={signals} events={events} desk={desk} onSelectSignal={selectSignal} selectedSignalId={selectedSignalId} />
      </section>
    </div>
  );
}
