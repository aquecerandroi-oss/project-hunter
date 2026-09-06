import Link from "next/link";

export interface OpportunitiesEmptyProps {
  orgSlug: string;
  hasFilters: boolean;
}

/** Same two-case honesty as `radar-empty.tsx`: a filtered miss is not the same fact as "no episode scored yet". */
export function OpportunitiesEmpty({ orgSlug, hasFilters }: OpportunitiesEmptyProps) {
  if (hasFilters) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-bg-elevated p-10 text-center">
        <p className="text-sm text-fg">Nenhuma oportunidade encontrada para estes filtros.</p>
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
    </div>
  );
}
