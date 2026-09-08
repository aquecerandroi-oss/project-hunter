import { formatRounded, reasonLabel, signColorClass } from "@/components/lab/lab-format";
import type { ReplayBlockOut } from "@/lib/api/lab-types";
import { formatBrasiliaShort } from "@/lib/time";

export interface LabReplayBlockProps {
  replay: ReplayBlockOut;
}

function windowText(from: string | null, to: string | null): string {
  const fromText = from ? (formatBrasiliaShort(from) ?? from) : "—";
  const toText = to ? (formatBrasiliaShort(to) ?? to) : "—";
  return `janela ${fromText}–${toText} (Brasília)`;
}

/**
 * The Placar card's "Replay" block (brief T3.24b addendum A1, D14): the mass
 * (`decisions_simulated`) vs. evidence (`operations_closed`) pair for a
 * version's own replay cohorts, rendered only when the API sends a non-null
 * `row.replay` -- never mixed into the prospective verdict/maturity above it
 * (D15's own isolation: a replay-positive, prospective-negative version
 * still shows the prospective verdict, proven in
 * `tests/lab-scoreboard-card.test.tsx`).
 */
export function LabReplayBlock({ replay }: LabReplayBlockProps) {
  const expectancy = formatRounded(replay.expectancy_r.value, replay.expectancy_r.reason ?? null, "R");
  const pf = formatRounded(replay.profit_factor.value, replay.profit_factor.reason ?? null);

  return (
    <div data-testid="lab-replay-block" className="mt-3 rounded-md border border-border bg-bg-overlay/40 p-3">
      <p className="text-[11px] text-fg-subtle">{replay.label}</p>
      <div className="mt-1.5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div>
          <p className="text-[11px] text-fg-muted">Decisões simuladas</p>
          <p className="font-mono text-sm tabular-nums text-fg">{replay.decisions_simulated}</p>
        </div>
        <div>
          <p className="text-[11px] text-fg-muted">Operações fechadas</p>
          <p className="font-mono text-sm tabular-nums text-fg">{replay.operations_closed}</p>
        </div>
        <div>
          <p className="text-[11px] text-fg-muted">Expectância</p>
          <p className={`font-mono text-sm tabular-nums ${expectancy.isValue ? signColorClass(replay.expectancy_r.value) : "text-fg-muted"}`}>
            {expectancy.text}
          </p>
        </div>
        <div>
          <p className="text-[11px] text-fg-muted">PF</p>
          <p className={`font-mono text-sm tabular-nums ${pf.isValue ? "text-fg" : "text-fg-muted"}`}>
            {pf.isValue ? pf.text : reasonLabel(replay.profit_factor.reason ?? "")}
          </p>
        </div>
      </div>
      <p className="mt-1.5 text-[11px] text-fg-subtle">{windowText(replay.window_from, replay.window_to)}</p>
      <p className="text-[11px] text-fg-subtle">
        {replay.distinct_days} dias · {replay.distinct_markets} mercados
      </p>
    </div>
  );
}
