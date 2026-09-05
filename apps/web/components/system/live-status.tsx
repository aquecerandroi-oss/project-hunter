"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useRef, useState } from "react";

import { computeAgeMs, formatAge, useAgeTicker } from "@/hooks/useAgeTicker";
import { useMarketChannels } from "@/hooks/useMarketChannels";
import type { ExchangeStatus, MarketStatusResponse, RtSystemMessage } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export interface LiveStatusProps {
  /** `/system/market-status` (T1.4), fetched once server-side; only rendered by the caller after a successful fetch. */
  initial: MarketStatusResponse;
  variant: "compact" | "full";
}

type DotState = "ok" | "warn" | "down";

const DOT_CLASSES: Record<DotState, string> = { ok: "bg-green", warn: "bg-warning", down: "bg-red" };
// H8: down is worse than reconnecting is worse than connected -- ranked so a
// "worst of" reduction can never quietly promote a mixed [connected,
// reconnecting] set to green just because nothing in it is fully "down".
const DOT_RANK: Record<DotState, number> = { ok: 0, warn: 1, down: 2 };

function dotState(wsState: string): DotState {
  const normalized = wsState.toLowerCase();
  if (normalized === "connected") return "ok";
  if (normalized === "reconnecting") return "warn";
  return "down";
}

/** The single worst-off exchange row, by the real down > reconnecting > connected ordering (H8) -- not "is anything fully down", which silently let a reconnecting exchange hide behind an otherwise-connected one. */
function worstExchange(exchanges: ExchangeStatus[]): ExchangeStatus {
  return exchanges.reduce((worst, e) => (DOT_RANK[dotState(e.ws_state)] > DOT_RANK[dotState(worst.ws_state)] ? e : worst));
}

function tsOf(value: string | null | undefined): number {
  if (!value) return 0;
  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? 0 : parsed;
}

/** Uppercased as-is -- CONNECTED/RECONNECTING/DOWN/UNAVAILABLE when the backend sends those, never a guessed label for anything else. */
function formatWsState(wsState: string): string {
  return wsState.toUpperCase();
}

/**
 * Sums the live `exchanges` rows -- never `initial.markets_monitored_total`
 * on its own, which stays frozen at fetch time while `rt:system` keeps
 * patching individual rows on top of it. A worker dropping from 200 to 150
 * monitored markets would otherwise update the row but leave the header
 * contradicting it (T1.5 review F7). Falls back to the initial snapshot
 * only for the (currently unreachable, since `LiveStatus` itself bails out
 * before this renders) case of no rows at all.
 */
function totalMonitoredFrom(exchanges: ExchangeStatus[], initialTotal: number): number {
  if (exchanges.length === 0) return initialTotal;
  return exchanges.reduce((sum, e) => sum + e.markets_monitored, 0);
}

function mergeExchangeUpdate(prev: ExchangeStatus[], msg: RtSystemMessage): ExchangeStatus[] {
  const idx = prev.findIndex((e) => e.exchange === msg.exchange);
  const reconnects = idx >= 0 ? (prev[idx]?.reconnects ?? 0) : 0;
  const updated: ExchangeStatus = {
    exchange: msg.exchange,
    ws_state: msg.ws_state,
    last_event_at: msg.last_event_at,
    last_event_age_ms: null,
    markets_monitored: msg.markets_monitored,
    open_gaps: msg.open_gaps,
    reconnects,
  };
  if (idx < 0) return [...prev, updated];
  const next = [...prev];
  next[idx] = updated;
  return next;
}

/**
 * Live Market Status (docs/plans/M1.md T1.5): per-exchange WS state, last
 * event age (ticking live), markets monitored, open gaps. `initial` is
 * `/system/market-status`'s real response; `rt:system` messages patch one
 * exchange at a time on top of it. When the endpoint answered but no
 * exchange has ever reported in, this says so plainly instead of a "0" that
 * reads as a healthy empty market.
 */
export function LiveStatus({ initial, variant }: LiveStatusProps) {
  const { getToken } = useAuth();
  const [exchanges, setExchanges] = useState<ExchangeStatus[]>(initial.exchanges);
  // H6: per-exchange "as of" watermark (the greater of the snapshot's own
  // `updated_at` or a patch's own `ts`) so a fresh server snapshot and a
  // realtime patch can be ordered against each other honestly -- whichever
  // is actually newer wins, in either direction. Neither `initial` nor a
  // `rt:system` payload carries a per-exchange server timestamp, so
  // `initial.updated_at` (the whole snapshot's generation time) stands in
  // for every row it carries.
  const asOfRef = useRef<Record<string, number>>({});

  // `AutoRefresh`'s periodic `router.refresh()` re-renders this component
  // with a fresh `initial` prop; without this effect the component instance
  // (reused across re-renders) kept showing whatever `exchanges` was
  // initialized to at mount forever -- a worker dropping from 200 to 150
  // monitored markets, or disappearing entirely, never reached the screen
  // (H6). Runs on mount too, which is what first populates `asOfRef`.
  useEffect(() => {
    const snapshotTs = tsOf(initial.updated_at);
    setExchanges((prev) => {
      const byExchange = new Map(prev.map((e) => [e.exchange, e] as const));
      for (const row of initial.exchanges) {
        const knownAsOf = asOfRef.current[row.exchange] ?? -Infinity;
        if (snapshotTs < knownAsOf) continue; // a newer patch already beat this (older) snapshot for this exchange
        byExchange.set(row.exchange, row);
        asOfRef.current[row.exchange] = snapshotTs;
      }
      return Array.from(byExchange.values());
    });
  }, [initial]);

  const { status: socketStatus } = useMarketChannels({
    channels: ["rt:system"],
    getAuthToken: () => getToken(),
    onMessage: (channel, payload) => {
      if (channel !== "rt:system") return;
      const msg = payload as RtSystemMessage;
      const patchTs = tsOf(msg.ts);
      const knownAsOf = asOfRef.current[msg.exchange] ?? -Infinity;
      if (patchTs < knownAsOf) return; // an older patch must not undo a newer snapshot/patch (H6)
      asOfRef.current[msg.exchange] = patchTs;
      setExchanges((prev) => mergeExchangeUpdate(prev, msg));
    },
  });
  const now = useAgeTicker();
  // `ws_state`/dots below still reflect the last server-known state even
  // while our own socket is down -- the ticking "há Ns" age already makes
  // that visibly stale, but this is an explicit, honest flag on top
  // (Astra's T1.5 review: don't let the dot alone imply a live feed).
  const liveFeedDown = socketStatus !== "open";

  if (exchanges.length === 0) {
    const message = "Market worker: sem heartbeat";
    if (variant === "compact") {
      return (
        <span className="inline-flex items-center gap-1.5 text-xs text-fg-muted" title={message}>
          <span className="size-2 rounded-full bg-fg-subtle" aria-hidden="true" />
          {message}
        </span>
      );
    }
    return (
      <section className="rounded-lg border border-dashed border-border bg-bg-elevated p-4">
        <h2 className="text-xs font-medium uppercase tracking-wide text-fg-muted">Mercados</h2>
        <p className="mt-2 text-sm text-fg">{message}</p>
      </section>
    );
  }

  if (variant === "compact") return <CompactStatus exchanges={exchanges} now={now} liveFeedDown={liveFeedDown} />;
  return (
    <FullStatus
      exchanges={exchanges}
      now={now}
      totalMonitored={totalMonitoredFrom(exchanges, initial.markets_monitored_total)}
      liveFeedDown={liveFeedDown}
    />
  );
}

/**
 * H8: the exchange's own `ws_state` used to be conveyed by dot colour alone
 * (`aria-hidden`) -- this puts it in the visible text/title too, using the
 * WORST exchange's real ws_state (down > reconnecting > connected, never
 * "is anything fully down", which let a lone reconnecting exchange hide
 * behind an otherwise-connected one). "sem tempo real" is a distinct fact
 * (the browser's OWN socket to the realtime gateway, not any exchange's
 * ws_state) and is spelled out as such so the two are never conflated.
 */
function CompactStatus({ exchanges, now, liveFeedDown }: { exchanges: ExchangeStatus[]; now: number; liveFeedDown: boolean }) {
  const primary = exchanges[0];
  if (!primary) return null;
  const worst = worstExchange(exchanges);
  const worstState = dotState(worst.ws_state);
  const ageMs = computeAgeMs(primary.last_event_at, now);
  const totalMonitored = exchanges.reduce((sum, e) => sum + e.markets_monitored, 0);
  const label =
    exchanges.length === 1
      ? `${primary.exchange} · ${formatWsState(primary.ws_state)} · ${primary.markets_monitored} mercados · ${ageMs !== null ? formatAge(ageMs) : "?"}`
      : `${exchanges.length} exchanges · ${formatWsState(worst.ws_state)} · ${totalMonitored} mercados`;
  const liveFeedNote = "tempo real do navegador interrompido";
  const title = liveFeedDown ? `${label} (${liveFeedNote})` : label;
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-fg-muted" title={title}>
      <span className={cn("size-2 rounded-full", DOT_CLASSES[worstState])} aria-hidden="true" />
      {label}
      {liveFeedDown && <span className="text-fg-subtle">({liveFeedNote})</span>}
    </span>
  );
}

function ExchangeRow({ exchange, now }: { exchange: ExchangeStatus; now: number }) {
  const ageMs = computeAgeMs(exchange.last_event_at, now);
  const state = dotState(exchange.ws_state);
  return (
    <li className="flex items-center justify-between gap-3 py-1 text-sm">
      <span className="flex items-center gap-2">
        <span className={cn("size-2 rounded-full", DOT_CLASSES[state])} aria-hidden="true" />
        <span className="font-medium text-fg">{exchange.exchange}</span>
        <span className="text-xs text-fg-subtle">{formatWsState(exchange.ws_state)}</span>
      </span>
      <span className="font-mono tabular-nums text-xs text-fg-muted">
        {exchange.markets_monitored} mercados · {ageMs !== null ? `há ${formatAge(ageMs)}` : "sem tick"} · {exchange.open_gaps} gaps
      </span>
    </li>
  );
}

function FullStatus({
  exchanges,
  now,
  totalMonitored,
  liveFeedDown,
}: {
  exchanges: ExchangeStatus[];
  now: number;
  totalMonitored: number;
  liveFeedDown: boolean;
}) {
  return (
    <section className="rounded-lg border border-border bg-bg-elevated p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-medium uppercase tracking-wide text-fg-muted">
          Mercados monitorados{liveFeedDown && <span className="ml-2 normal-case text-warning">tempo real interrompido</span>}
        </h2>
        <span className="font-mono text-sm tabular-nums text-fg">{totalMonitored}</span>
      </div>
      <ul className="mt-2 divide-y divide-border">
        {exchanges.map((exchange) => (
          <ExchangeRow key={exchange.exchange} exchange={exchange} now={now} />
        ))}
      </ul>
    </section>
  );
}
