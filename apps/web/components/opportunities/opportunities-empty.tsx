import Link from "next/link";

import { formatScoreWhole, WATCHING_THRESHOLD } from "@/components/radar/radar-coverage-format";
import { RADAR_COVERAGE_STRIP_ID } from "@/components/radar/radar-coverage-strip";
import type { RadarCoverageOut } from "@/lib/api/radar-coverage-types";

export interface OpportunitiesEmptyProps {
  orgSlug: string;
  hasFilters: boolean;
  /**
   * T3.46 (`.claude/state/notes-T3.46.md`): the "Só HOT/ENTRY_CANDIDATE"
   * quick filter (`opportunities-filters.tsx`) always lands here today --
   * not because the filter is wrong, but because no episode has ever
   * cleared `WATCHING_THRESHOLD`. `undefined`/`null` (coverage read failed,
   * or the caller has not wired it) skips the note rather than guessing.
   */
  coverage?: RadarCoverageOut | null | undefined;
}

/** Same fact `radar-empty.tsx::NeverLitNote` renders, worded for this page's own quick filter. */
function NeverLitNote({ coverage }: { coverage: RadarCoverageOut | null | undefined }) {
  if (!coverage) return null;
  const score = formatScoreWhole(coverage.max_score_ever);
  if (score === null || Number(coverage.max_score_ever) >= WATCHING_THRESHOLD) return null;
  return (
    <p className="mt-3 text-sm text-fg-muted">
      Isto não é "nada interessante agora": desde que o Radar existe, nenhum episódio passou de NORMAL (maior score já visto {score}, primeiro degrau {WATCHING_THRESHOLD}).{" "}
      <a href={`#${RADAR_COVERAGE_STRIP_ID}`} className="font-medium text-fg underline underline-offset-2 hover:text-gold">
        Veja o estado completo do Radar acima
      </a>
      .
    </p>
  );
}

/** Same two-case honesty as `radar-empty.tsx`: a filtered miss is not the same fact as "no episode scored yet". */
export function OpportunitiesEmpty({ orgSlug, hasFilters, coverage }: OpportunitiesEmptyProps) {
  if (hasFilters) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-bg-elevated p-10 text-center">
        <p className="text-sm text-fg">Nenhuma oportunidade encontrada para estes filtros.</p>
        <NeverLitNote coverage={coverage} />
      </div>
    );
  }
  return (
    <div className="rounded-lg border border-dashed border-border bg-bg-elevated p-10 text-center">
      <p className="text-sm text-fg">Nenhuma oportunidade pontuada ainda.</p>
      <p className="mt-1 text-sm text-fg-muted">
        Verifique se o scanner está rodando em{" "}
        <Link href={`/${orgSlug}/system`} className="font-medium text-fg underline underline-offset-2 hover:text-gold">
          System → Workers
        </Link>
        . O radar completo, com mais filtros, vive em{" "}
        <Link href={`/${orgSlug}/radar`} className="font-medium text-fg underline underline-offset-2 hover:text-gold">
          /radar
        </Link>
        .
      </p>
      <NeverLitNote coverage={coverage} />
    </div>
  );
}
