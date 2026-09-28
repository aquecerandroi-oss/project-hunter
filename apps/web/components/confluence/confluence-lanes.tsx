"use client";

import type { IChartApi, Time, UTCTimestamp } from "lightweight-charts";
import { useMemo } from "react";

import type { AnomalyOut } from "@/lib/api/anomalies-types";
import type { SignalListItemOut } from "@/lib/api/lab-types";
import type { DeskOut } from "@/lib/api/market-desk-types";
import type { MarketEventOut } from "@/lib/api/market-events-types";
import type { RegimeOut } from "@/lib/api/regime-types";
import { barIndexContaining } from "@/lib/charts/confluence-series";
import { chartColor } from "@/lib/charts/css-var";

import { deskOrderStatusLabel, MARKET_EVENT_CONFIDENCE_LABEL } from "./labels";

export interface ConfluenceLanesProps {
  chart: IChartApi | null;
  /** Bumped by the chart on every pan/zoom/resize -- the only way this component learns its cached `timeToCoordinate` results are stale. */
  rangeVersion: number;
  candleTimes: readonly UTCTimestamp[];
  timeframeSeconds: number;
  signals: SignalListItemOut[];
  events: MarketEventOut[];
  desk: DeskOut | null;
  anomalies: AnomalyOut[];
  regimeHistory: RegimeOut[];
  selectedSignalId: string | null;
  onSelectSignal: (signal: SignalListItemOut) => void;
  onSelectEvent: (event: MarketEventOut) => void;
}

interface Dot {
  key: string;
  x: number;
  title: string;
  colorVar: string;
  onClick?: (() => void) | undefined;
}

function placeDots(chart: IChartApi, candleTimes: readonly UTCTimestamp[], timeframeS: number, items: { key: string; iso: string; title: string; colorVar: string; onClick?: (() => void) | undefined }[]): Dot[] {
  const dots: Dot[] = [];
  for (const item of items) {
    const idx = barIndexContaining(candleTimes, item.iso, timeframeS);
    if (idx === null) continue;
    const x = chart.timeScale().timeToCoordinate(candleTimes[idx] as Time);
    if (x === null) continue;
    dots.push({ key: item.key, x, title: item.title, colorVar: item.colorVar, onClick: item.onClick });
  }
  return dots;
}

function Lane({ label, dots, emptyNote }: { label: string; dots: Dot[]; emptyNote: string }) {
  // Astra's review of T4.82 (must-fix 7): the label used to live inside a
  // `pl-16` wrapper on the whole lanes block, shifting every `dot.x` (which
  // comes straight from the chart's own `timeToCoordinate`, x=0 at the
  // chart's own left edge) by that same padding relative to the candles
  // above it. The label is now an overlay pinned to the strip's own top-left
  // corner instead of reserving horizontal space, so x=0 here is x=0 on the
  // chart, always.
  return (
    <div className="relative h-7 border-t border-border/60">
      <span className="pointer-events-none absolute left-1 top-0 z-10 rounded bg-bg-elevated/90 px-1 text-[10px] uppercase tracking-wide text-fg-subtle">{label}</span>
      {dots.length === 0 ? (
        <span className="pointer-events-none absolute left-20 top-1/2 -translate-y-1/2 text-[11px] text-fg-subtle">{emptyNote}</span>
      ) : (
        dots.map((dot) => (
          <button
            key={dot.key}
            type="button"
            title={dot.title}
            onClick={dot.onClick}
            className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-1 ring-bg"
            style={{ left: dot.x, backgroundColor: chartColor(dot.colorVar) }}
          />
        ))
      )}
    </div>
  );
}

const REGIME_BAND_COLOR = "--color-border-strong";
const ANOMALY_COLOR = "--color-warning";
const CONFIDENCE_COLOR: Record<string, string> = { confirmed: "--color-fg", reported: "--color-fg-muted", rumor: "--color-fg-subtle" };

/**
 * The four lanes under the chart (design §2-§3): Lab, Notícias, Nossa mesa,
 * Regime e anomalias -- one glance density, bound to the chart's own time
 * scale (`timeToCoordinate`) so a pan/zoom moves the dots with the candles.
 * A dot for an instant outside the loaded candles is simply not drawn (the
 * screen's "nunca aproximar" rule), not hidden behind an approximation.
 */
export function ConfluenceLanes({ chart, rangeVersion, candleTimes, timeframeSeconds, signals, events, desk, anomalies, regimeHistory, selectedSignalId, onSelectSignal, onSelectEvent }: ConfluenceLanesProps) {
  const signalDots = useMemo(() => {
    if (!chart) return [];
    return placeDots(chart, candleTimes, timeframeSeconds, signals.map((signal) => ({
      key: signal.signal_id,
      iso: signal.decision_at,
      title: `sinal ${signal.direction} · ${signal.tracking_state}${signal.signal_id === selectedSignalId ? " (selecionado)" : ""}`,
      colorVar: signal.signal_id === selectedSignalId ? "--color-gold" : "--color-info",
      onClick: () => onSelectSignal(signal),
    })));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `rangeVersion` is the intentional recompute trigger (chart pan/zoom/resize), not a value read inside
  }, [chart, candleTimes, timeframeSeconds, signals, selectedSignalId, onSelectSignal, rangeVersion]);

  const eventDots = useMemo(() => {
    if (!chart) return [];
    return placeDots(chart, candleTimes, timeframeSeconds, events.filter((e) => e.published_at !== null).map((eventItem) => ({
      key: eventItem.id,
      iso: eventItem.published_at as string,
      title: `${eventItem.title} (${MARKET_EVENT_CONFIDENCE_LABEL[eventItem.confidence as keyof typeof MARKET_EVENT_CONFIDENCE_LABEL] ?? eventItem.confidence})`,
      colorVar: CONFIDENCE_COLOR[eventItem.confidence] ?? "--color-fg-subtle",
      onClick: () => onSelectEvent(eventItem),
    })));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chart, candleTimes, timeframeSeconds, events, onSelectEvent, rangeVersion]);

  const deskDots = useMemo(() => {
    if (!chart || !desk) return [];
    const orderItems = desk.orders.map((order) => ({
      key: order.id,
      iso: order.received_at,
      title: `ordem ${deskOrderStatusLabel(order.status)}${order.reason !== null ? ` -- ${order.reason}` : ""}`,
      colorVar: order.status === "refused" || order.status === "failed" ? "--color-red" : "--color-gold",
    }));
    const positionItems = desk.positions.flatMap((position) => {
      const items = [{ key: `${position.id}-entry`, iso: position.entry_at, title: "entrada real spot/1", colorVar: "--color-gold" }];
      if (position.exit_at !== null) items.push({ key: `${position.id}-exit`, iso: position.exit_at, title: "saída real spot/1", colorVar: "--color-gold" });
      return items;
    });
    return placeDots(chart, candleTimes, timeframeSeconds, [...orderItems, ...positionItems]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chart, candleTimes, timeframeSeconds, desk, rangeVersion]);

  const regimeAnomalyDots = useMemo(() => {
    if (!chart) return [];
    const regimeItems = regimeHistory.map((row) => ({ key: `regime-${row.id}`, iso: row.start_time, title: "Regime (global)", colorVar: REGIME_BAND_COLOR }));
    const anomalyItems = anomalies.map((a) => ({ key: `anomaly-${a.id}`, iso: a.detected_at, title: `anomalia: ${a.type}`, colorVar: ANOMALY_COLOR }));
    return placeDots(chart, candleTimes, timeframeSeconds, [...regimeItems, ...anomalyItems]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chart, candleTimes, timeframeSeconds, regimeHistory, anomalies, rangeVersion]);

  if (!chart) return null;

  return (
    <div className="w-full">
      <Lane label="Lab" dots={signalDots} emptyNote="nenhum sinal neste período" />
      <Lane label="Notícias" dots={eventDots} emptyNote="nenhuma notícia registrada" />
      <Lane label="Nossa mesa" dots={deskDots} emptyNote="sem registro da mesa spot/1" />
      <Lane label="Regime/anomalias" dots={regimeAnomalyDots} emptyNote="sem leitura" />
    </div>
  );
}
