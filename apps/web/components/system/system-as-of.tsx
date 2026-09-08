import { formatBrasiliaLong } from "@/lib/time";

export interface SystemAsOfProps {
  iso: string;
}

/**
 * Full Brasília date+time (brief T3.22, 2026-09-08: every primary timestamp
 * reads in the organization's own timezone, never UTC and never the
 * operator's browser timezone) -- mirrors `components/portfolio/portfolio-as-of.tsx`
 * and `components/lab/lab-as-of.tsx` exactly, and for the same reason: this
 * domain (`system/`) keeps its own copy rather than importing another
 * screen's component, same convention as those two siblings duplicating
 * instead of sharing. The exact UTC instant -- the System page's own
 * "operator detail" (brief item 8) -- stays one hover away in the `title`
 * attribute: the raw ISO string is already UTC and copyable as-is.
 *
 * Deterministic in any runtime timezone (SSR-safe): `Intl.DateTimeFormat`'s
 * explicit `timeZone` option (`lib/time.ts`) resolves Brasília's own offset
 * regardless of where this renders, so no client-only effect/mount step is
 * needed (unlike the previous UTC + browser-local-offset version).
 */
export function SystemAsOf({ iso }: SystemAsOfProps) {
  const long = formatBrasiliaLong(iso) ?? "--";
  return (
    <span title={iso} className="font-mono tabular-nums">
      {long}
    </span>
  );
}
