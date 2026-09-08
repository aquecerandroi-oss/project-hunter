import { formatBrasiliaLong } from "@/lib/time";

export interface LabAsOfProps {
  iso: string;
}

/**
 * Full Brasília date+time (brief T3.22, 2026-09-08: every primary timestamp
 * reads in the organization's own timezone, never UTC and never the
 * viewer's browser timezone). The exact UTC instant stays one hover away in
 * the `title` attribute -- the raw ISO string is already UTC and copyable
 * as-is (CLAUDE.md: "Time is always UTC" in storage/API).
 *
 * Deterministic in any runtime timezone (SSR-safe): `Intl.DateTimeFormat`'s
 * explicit `timeZone` option (`lib/time.ts`) resolves Brasília's own offset
 * regardless of where this renders, so -- unlike the previous UTC +
 * browser-local-offset version -- no client-only effect/mount step is
 * needed to avoid baking in the wrong zone.
 */
export function LabAsOf({ iso }: LabAsOfProps) {
  const long = formatBrasiliaLong(iso) ?? "--";
  return (
    <span title={iso} className="font-mono tabular-nums">
      {long}
    </span>
  );
}
