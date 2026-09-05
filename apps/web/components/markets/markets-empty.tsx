import Link from "next/link";

export interface MarketsEmptyProps {
  orgSlug: string;
}

/**
 * Honest empty universe (docs/plans/M1.md T1.5): the API answered, there is
 * just nothing monitored yet. Worded as a thing to check, not an asserted
 * fact (T1.5b joint decision #8: "vazio não afirma que o worker parou") --
 * a genuinely empty (but successful) response doesn't prove the worker
 * stopped, only that nothing is monitored right now. "System → Workers" is
 * a real link (T1.5b Astra review nice-to-have), not just styled text.
 */
export function MarketsEmpty({ orgSlug }: MarketsEmptyProps) {
  return (
    <div className="rounded-lg border border-dashed border-border bg-bg-elevated p-10 text-center">
      <p className="text-sm text-fg">Nenhum mercado monitorado ainda.</p>
      <p className="mt-1 text-sm text-fg-muted">
        Verifique se o market-worker está rodando em{" "}
        <Link href={`/${orgSlug}/system`} className="font-medium text-fg underline underline-offset-2 hover:text-gold">
          System → Workers
        </Link>
        .
      </p>
    </div>
  );
}
