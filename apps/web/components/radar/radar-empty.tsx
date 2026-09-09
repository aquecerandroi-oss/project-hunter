import Link from "next/link";

import { formatScoreWhole, WATCHING_THRESHOLD } from "@/components/radar/radar-coverage-format";
import { RADAR_COVERAGE_STRIP_ID } from "@/components/radar/radar-coverage-strip";
import type { RadarCoverageOut } from "@/lib/api/radar-coverage-types";

export interface RadarEmptyProps {
  orgSlug: string;
  hasFilters: boolean;
  /** T3.46 -- when present and no episode ever reached `WATCHING_THRESHOLD`, this is *why* the list is empty, not "adjust your filters". `undefined`/`null` (coverage read failed, or the caller has not wired it) skips the note rather than guessing. */
  coverage?: RadarCoverageOut | null | undefined;
}

/** "Nada aconteceu" would be a guess; this is the one fact `coverage` actually proves -- never rendered when `max_score_ever` is missing or already clears the threshold. */
function NeverLitNote({ coverage }: { coverage: RadarCoverageOut | null | undefined }) {
  if (!coverage) return null;
  const score = formatScoreWhole(coverage.max_score_ever);
  if (score === null || Number(coverage.max_score_ever) >= WATCHING_THRESHOLD) return null;
  return (
    <p className="mt-3 text-sm text-fg-muted">
      Isto não é "nada acontecendo agora": desde que o Radar existe, nenhum episódio passou de NORMAL (maior score já visto {score}, primeiro degrau {WATCHING_THRESHOLD}).{" "}
      <a href={`#${RADAR_COVERAGE_STRIP_ID}`} className="font-medium text-fg underline underline-offset-2 hover:text-gold">
        Veja o estado completo do Radar acima
      </a>
      .
    </p>
  );
}

/**
 * Two distinct honest empty states (docs/DESIGN.md §2, T1.5b joint decision
 * #8), not one message doing double duty:
 *
 * - `hasFilters`: the current filters simply matched nothing -- "Nenhum
 *   resultado", the same case as `/markets`' search-with-no-match.
 * - no filters at all: the radar has **no scored episode**. The API's own
 *   contract (`schemas/radar.py`) is one row per `opportunities` episode --
 *   a monitored market without one simply does not appear, and today (M2,
 *   before T2.5's scanner-worker exists) *nothing* has one yet. This never
 *   claims the scanner "stopped" (a genuinely empty response does not prove
 *   that), mirroring `markets-empty.tsx`'s wording.
 */
export function RadarEmpty({ orgSlug, hasFilters, coverage }: RadarEmptyProps) {
  if (hasFilters) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-bg-elevated p-10 text-center">
        <p className="text-sm text-fg">Nenhum episódio encontrado para estes filtros.</p>
        <p className="mt-1 text-sm text-fg-muted">Ajuste os filtros acima para ver mais oportunidades.</p>
        <NeverLitNote coverage={coverage} />
      </div>
    );
  }
  return (
    <div className="rounded-lg border border-dashed border-border bg-bg-elevated p-10 text-center">
      <p className="text-sm text-fg">Nenhuma oportunidade pontuada ainda.</p>
      <p className="mt-1 text-sm text-fg-muted">
        O Radar mostra uma linha por episódio de oportunidade pontuado (não por mercado) -- verifique se o scanner está rodando em{" "}
        <Link href={`/${orgSlug}/system`} className="font-medium text-fg underline underline-offset-2 hover:text-gold">
          System → Workers
        </Link>
        .
      </p>
      <NeverLitNote coverage={coverage} />
    </div>
  );
}
