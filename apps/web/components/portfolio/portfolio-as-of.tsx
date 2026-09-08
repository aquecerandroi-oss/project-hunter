import { formatBrasiliaLong } from "@/lib/time";

export interface PortfolioAsOfProps {
  iso: string;
}

/**
 * Full Brasília date+time (brief T3.22, 2026-09-08: every primary timestamp
 * reads in the organization's own timezone, never UTC and never the
 * viewer's browser timezone) -- mirrors `components/lab/lab-as-of.tsx`
 * exactly, and for the same reason: a Server Component on this screen
 * (`PortfolioHeader`, `PortfolioResultCard`, `PortfolioProposalsEmpty`) can
 * render this directly. The exact UTC instant stays one hover away in the
 * `title` attribute -- the raw ISO string is already UTC and copyable as-is.
 *
 * Deterministic in any runtime timezone (SSR-safe): `Intl.DateTimeFormat`'s
 * explicit `timeZone` option (`lib/time.ts`) resolves Brasília's own offset
 * regardless of where this renders, so no client-only effect/mount step is
 * needed (unlike the previous UTC + browser-local-offset version, which had
 * to wait for the browser's own zone to be knowable).
 */
export function PortfolioAsOf({ iso }: PortfolioAsOfProps) {
  const long = formatBrasiliaLong(iso) ?? "--";
  return (
    <span title={iso} className="font-mono tabular-nums">
      {long}
    </span>
  );
}
