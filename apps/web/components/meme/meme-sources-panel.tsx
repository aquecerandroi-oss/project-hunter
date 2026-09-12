/**
 * "Fontes" (brief T4.3b): what the Meme Radar is actually reading right now.
 * One chip per source (green connected/fresh, amber lagging or budget at
 * 90 %+, red disconnected/errors in the hour, grey "sem leitura"), the three
 * honest gauges of the last folded minute (progress covered, tape covered,
 * discovery blindness -- the share of the new board the radar cannot see by
 * construction), the radar's heartbeat state and, when the page has it, the
 * lab loop's. Every number carries its `observed_at`; a missing one says
 * "sem leitura: motivo", never a 0.
 *
 * `variant="full"` is the strip under the overview on `/meme`;
 * `variant="line"` is the one wrapping line above the proposals on
 * `/meme/mesa` (details move into `title`). Server Component: the page's
 * own `AutoRefresh` is the polling.
 */
import { loopStateLabel, type LoopTone } from "@/components/meme-desk/meme-desk-format";
import { BrasiliaInstant, BrasiliaShort } from "@/components/time/brasilia-instant";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import type { MemeLoopState } from "@/lib/api/meme-desk-types";
import type { MemeSources } from "@/lib/api/meme-types";

import {
  BLINDNESS_SENTENCE,
  fastLaneLine,
  type Gauge,
  minuteFlags,
  type RadarState,
  radarStateLabel,
  type SourceChip,
  sourceChip,
  sourceGauges,
  type SourceTone,
  trackedLabel,
} from "./meme-sources-format";

const TONE_BADGE: Record<SourceTone, NonNullable<BadgeProps["variant"]>> = { green: "positive", amber: "warning", red: "negative", grey: "default" };
const TONE_DOT: Record<SourceTone, string> = { green: "bg-green", amber: "bg-warning", red: "bg-red", grey: "bg-fg-subtle" };
const STATE_DOT: Record<RadarState["tone"], string> = { green: "bg-green", red: "bg-red", grey: "bg-fg-subtle" };
const LOOP_TONE: Record<LoopTone, RadarState["tone"]> = { alive: "green", stopped: "red", unknown: "grey" };

function Dot({ className }: { className: string }) {
  return <span aria-hidden="true" className={`inline-block size-2 shrink-0 rounded-full ${className}`} />;
}

function StateChip({ tone, label, title }: { tone: RadarState["tone"]; label: string; title?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-xs text-fg-muted" title={title}>
      <Dot className={STATE_DOT[tone]} />
      {label}
    </span>
  );
}

function ObservedAt({ iso, label }: { iso: string | null; label: string }) {
  if (!iso) return <span className="text-[11px] text-fg-subtle">{label}: sem leitura</span>;
  return (
    <span className="text-[11px] text-fg-subtle">
      {label} <BrasiliaShort iso={iso} />
    </span>
  );
}

function ChipCard({ chip }: { chip: SourceChip }) {
  return (
    <li className="flex min-w-0 flex-col gap-1">
      <Badge variant={TONE_BADGE[chip.tone]} title={chip.title} className="max-w-full flex-wrap gap-1.5 self-start whitespace-normal">
        <Dot className={TONE_DOT[chip.tone]} />
        <span>{chip.name}</span>
        <span aria-hidden="true">·</span>
        <span className="font-normal">{chip.state}</span>
      </Badge>
      <span className="font-mono text-[11px] tabular-nums text-fg-subtle">
        {chip.detail} · <ObservedAt iso={chip.observedAt} label="observado" />
      </span>
    </li>
  );
}

function ChipPill({ chip }: { chip: SourceChip }) {
  return (
    <Badge variant={TONE_BADGE[chip.tone]} title={chip.title} className="gap-1.5">
      <Dot className={TONE_DOT[chip.tone]} />
      <span>{chip.name}</span>
      <span aria-hidden="true">·</span>
      <span className="font-normal">{chip.short}</span>
    </Badge>
  );
}

function GaugeCard({ gauge }: { gauge: Gauge }) {
  return (
    <div className="flex flex-col gap-1 rounded-md border border-border p-4">
      <span className="text-xs font-medium uppercase tracking-wide text-fg-muted">{gauge.label}</span>
      {gauge.value === null ? (
        <span className="text-sm text-fg-muted">{gauge.reason}</span>
      ) : (
        <span className="font-mono text-2xl font-semibold tabular-nums text-fg">{gauge.value}</span>
      )}
      {gauge.detail && <span className="font-mono text-[11px] tabular-nums text-fg-subtle">{gauge.detail}</span>}
      <ObservedAt iso={gauge.observedAt} label={gauge.observedLabel} />
      {gauge.key === "blindness" && <span className="text-[11px] text-fg-subtle">{BLINDNESS_SENTENCE}</span>}
    </div>
  );
}

function gaugeTitle(gauge: Gauge): string {
  const lines = [`${gauge.label}: ${gauge.value ?? gauge.reason ?? "sem leitura"}`];
  if (gauge.detail) lines.push(gauge.detail);
  lines.push(`${gauge.observedLabel} (UTC): ${gauge.observedAt ?? "sem leitura"}`);
  if (gauge.key === "blindness") lines.push(BLINDNESS_SENTENCE);
  return lines.join("\n");
}

function GaugeInline({ gauge }: { gauge: Gauge }) {
  if (gauge.value === null) {
    return (
      <span className="text-fg-muted" title={gauge.reason ?? undefined}>
        {gauge.short} sem leitura
      </span>
    );
  }
  return (
    <span title={gaugeTitle(gauge)}>
      {gauge.short} <span className="font-mono tabular-nums text-fg">{gauge.value}</span>
    </span>
  );
}

interface ViewProps {
  sources: MemeSources;
  chips: SourceChip[];
  gauges: Gauge[];
  radar: RadarState;
  loop: ReturnType<typeof loopStateLabel> | null;
  flags: string[];
  /** T4.16: the 15-second clock's counters and the decision→fill latency; `null` on a worker that predates them. */
  fastLane: string | null;
}

function radarTitle(sources: MemeSources): string {
  return [`heartbeat do worker (UTC): ${sources.heartbeat_ts ?? "sem leitura"}`, `campos do radar (UTC): ${sources.sources_at ?? "sem leitura"}`].join("\n");
}

function FullPanel({ sources, chips, gauges, radar, loop, flags, fastLane }: ViewProps) {
  return (
    <section aria-labelledby="meme-sources-heading" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="meme-sources-heading" className="text-sm font-medium text-fg">
          Fontes
        </h2>
        <div className="flex flex-wrap items-center gap-3">
          <StateChip tone={radar.tone} label={radar.label} title={radarTitle(sources)} />
          {loop && <StateChip tone={LOOP_TONE[loop.tone]} label={loop.label} />}
        </div>
      </div>
      <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-xs text-fg-muted">
        <span className="font-mono tabular-nums">{trackedLabel(sources.tracked)}</span>
        {flags.map((flag) => (
          <span key={flag} className="font-mono tabular-nums text-warning">
            {flag}
          </span>
        ))}
        · consultado em <BrasiliaInstant iso={sources.as_of} />
      </p>
      {chips.length === 0 ? (
        <p className="rounded-md border border-border p-3 text-xs text-fg-muted">nenhuma fonte no heartbeat</p>
      ) : (
        <ul className="flex flex-wrap gap-x-4 gap-y-2">
          {chips.map((chip) => (
            <ChipCard key={chip.name} chip={chip} />
          ))}
        </ul>
      )}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {gauges.map((gauge) => (
          <GaugeCard key={gauge.key} gauge={gauge} />
        ))}
      </div>
      {fastLane && <p className="font-mono text-[11px] tabular-nums text-fg-subtle">{fastLane}</p>}
    </section>
  );
}

function LinePanel({ sources, chips, gauges, radar, loop, flags, fastLane }: ViewProps) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-fg-muted">
      <span className="font-medium text-fg">Fontes</span>
      {chips.length === 0 ? <span>nenhuma fonte no heartbeat</span> : chips.map((chip) => <ChipPill key={chip.name} chip={chip} />)}
      {gauges.map((gauge) => (
        <GaugeInline key={gauge.key} gauge={gauge} />
      ))}
      <StateChip tone={radar.tone} label={radar.label} title={radarTitle(sources)} />
      {loop && <StateChip tone={LOOP_TONE[loop.tone]} label={loop.label} />}
      {flags.map((flag) => (
        <span key={flag} className="font-mono tabular-nums text-warning">
          {flag}
        </span>
      ))}
      {fastLane && (
        <span className="font-mono tabular-nums" title={fastLane}>
          15 s: {fastLane}
        </span>
      )}
      <span>
        consultado em <BrasiliaShort iso={sources.as_of} />
      </span>
    </div>
  );
}

export interface MemeSourcesPanelProps {
  sources: MemeSources;
  /** The lab loop's last tick (`/meme/lab`), when the page already reads it; the desk strip shows it on `/meme/mesa`, so that page leaves it out here. */
  loop?: MemeLoopState;
  variant?: "full" | "line";
}

export function MemeSourcesPanel({ sources, loop, variant = "full" }: MemeSourcesPanelProps) {
  const view: ViewProps = {
    sources,
    chips: sources.sources.map((source) => sourceChip(source, sources.stalled_after_s)),
    gauges: sourceGauges(sources),
    radar: radarStateLabel(sources),
    // The API's own clock, so the loop's age is measured against the same instant as the heartbeat's.
    loop: loop ? loopStateLabel(loop, new Date(sources.as_of).getTime()) : null,
    flags: minuteFlags(sources),
    fastLane: fastLaneLine(sources),
  };
  return variant === "line" ? <LinePanel {...view} /> : <FullPanel {...view} />;
}
