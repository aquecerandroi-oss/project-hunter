"use client";

import { Badge } from "@/components/ui/badge";
import { computeAgeMs, formatAge, useAgeTicker } from "@/hooks/useAgeTicker";

function toNumber(value: string | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Radar's "qualidade" column (brief line 9). Unlike `/markets`'
 * `QualityBadge`, `RadarItemOut` carries neither per-component ages nor a
 * `stale_after_ms` threshold to compare against -- inventing one would be
 * exactly the fabricated signal CLAUDE.md forbids
 * (`.claude/state/notes-T2.7.md` records this decision). What the contract
 * *does* carry is `confidence` (the score's own data-quality measure,
 * `PIPELINE.md` §5) and `last_updated_at`; this shows both, the age
 * literally ticking every second like every other freshness label in the
 * app (`hooks/useAgeTicker.ts`), without asserting a fresh/stale verdict the
 * API never declared a threshold for.
 */
export function QualityCell({ confidence, lastUpdatedAt }: { confidence: string; lastUpdatedAt: string }) {
  const now = useAgeTicker();
  const value = toNumber(confidence);
  const variant = value === null ? "default" : value >= 0.7 ? "positive" : value >= 0.4 ? "default" : "warning";
  const label = value === null ? "confiança indisponível" : `confiança ${confidence}`;
  const ageMs = computeAgeMs(lastUpdatedAt, now);

  return (
    <div className="flex flex-col gap-1">
      <Badge variant={variant}>{label}</Badge>
      <span className="text-[11px] text-fg-subtle">{ageMs !== null ? `atualizado há ${formatAge(ageMs)}` : "sem carimbo"}</span>
    </div>
  );
}
