import Link from "next/link";

export interface RadarEmptyProps {
  orgSlug: string;
  hasFilters: boolean;
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
export function RadarEmpty({ orgSlug, hasFilters }: RadarEmptyProps) {
  if (hasFilters) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-bg-elevated p-10 text-center">
        <p className="text-sm text-fg">Nenhum episódio encontrado para estes filtros.</p>
        <p className="mt-1 text-sm text-fg-muted">Ajuste os filtros acima para ver mais oportunidades.</p>
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
    </div>
  );
}
