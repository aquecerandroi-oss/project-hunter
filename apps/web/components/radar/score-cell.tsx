import { cn } from "@/lib/utils";

function toNumber(value: string | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * `change === 0` is ambiguous on its own: the API computes
 * `change = score - COALESCE(last history sample, score)`
 * (`schemas/radar.py::RadarItemOut.change`), so it reads `0` both for a
 * brand-new episode (nothing to compare against yet) *and* for a mature,
 * perfectly stable episode (score genuinely unchanged since the last
 * history sample). The two are told apart using `first_seen_at`/
 * `last_updated_at`: no history yet means both timestamps were written by
 * the same insert, so they land within a few seconds of each other; a real
 * comparison sample means `last_updated_at` has since moved meaningfully
 * past `first_seen_at`.
 */
const NEW_EPISODE_THRESHOLD_MS = 5_000;

function isNewEpisode(firstSeenAt: string, lastUpdatedAt: string): boolean {
  const firstSeenMs = new Date(firstSeenAt).getTime();
  const lastUpdatedMs = new Date(lastUpdatedAt).getTime();
  if (Number.isNaN(firstSeenMs) || Number.isNaN(lastUpdatedMs)) return false;
  return Math.abs(lastUpdatedMs - firstSeenMs) <= NEW_EPISODE_THRESHOLD_MS;
}

/**
 * Score (0-100, `NUMERIC(5,2)`) as a discrete horizontal bar plus its
 * numeric value and the `change` delta against the last persisted history
 * sample (`RadarItemOut.change` -- `null` only when that history read
 * itself failed, `schemas/radar.py`). `change === 0` is disambiguated via
 * `firstSeenAt`/`lastUpdatedAt` (see `isNewEpisode` above) into "novo
 * episódio" (no history to compare against) vs "sem mudança desde a última
 * leitura" (compared against real history and found stable) -- never the
 * same label for both. Calm by design (docs/DESIGN.md §2: no pulse, no
 * gradient) -- a plain filled bar, gold reserved elsewhere.
 */
export function ScoreCell({
  score,
  change,
  firstSeenAt,
  lastUpdatedAt,
}: {
  score: string;
  change: string | null | undefined;
  firstSeenAt: string;
  lastUpdatedAt: string;
}) {
  const value = toNumber(score);
  const pct = value === null ? 0 : Math.max(0, Math.min(100, value));
  const changeValue = toNumber(change);

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-sm tabular-nums text-fg">{score}</span>
        {changeValue === null ? (
          <span className="text-xs text-fg-muted">mudança indisponível</span>
        ) : changeValue === 0 ? (
          <span className="text-xs text-fg-muted">{isNewEpisode(firstSeenAt, lastUpdatedAt) ? "novo episódio" : "sem mudança desde a última leitura"}</span>
        ) : (
          <span className={cn("font-mono text-xs tabular-nums", changeValue > 0 ? "text-green" : "text-red")}>
            {changeValue > 0 ? "+" : ""}
            {change}
          </span>
        )}
      </div>
      <div className="h-1 w-24 overflow-hidden rounded-full bg-bg-overlay" aria-hidden="true">
        <div className="h-full bg-fg-muted" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
