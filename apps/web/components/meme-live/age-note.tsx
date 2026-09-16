/**
 * A one-line "atualizado há Xmin" (or a custom prefix, e.g. "recarregado há
 * Xmin") for a Server Component -- no client ticker, the age is computed once
 * against the `nowMs` the page already resolved server-side. Shared by
 * `live-executor-panel.tsx` and `auto-stage1-panel.tsx` (T4.28c) so the two
 * panels never diverge on what "sem leitura" means.
 */
import { computeAgeMs, formatAge } from "@/lib/age";

export function AgeNote({
  iso,
  nowMs,
  prefix = "atualizado",
}: {
  iso: string | null | undefined;
  nowMs: number;
  prefix?: string;
}) {
  const age = computeAgeMs(iso, nowMs);
  if (age === null) return <span className="text-fg-subtle">sem leitura</span>;
  return (
    <span className="text-fg-subtle">
      {prefix} há {formatAge(age)}
    </span>
  );
}
