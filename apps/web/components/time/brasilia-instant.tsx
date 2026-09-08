import { formatBrasiliaLong, formatBrasiliaShort } from "@/lib/time";

/**
 * Brief T3.22 (2026-09-08, Everton: "sou de sao paulo intao horario tem que
 * ser de brasilia"): every primary timestamp reads in Brasília, the
 * organization's one display timezone -- never UTC, never the viewer's own
 * browser zone (a member reading from abroad still sees the wallet's own
 * day). The exact UTC instant stays one hover away in `title`: the raw ISO
 * string is already UTC and copyable as-is (CLAUDE.md: "Time is always UTC"
 * in storage/API).
 *
 * Deterministic in any runtime timezone (SSR-safe, `lib/time.ts`), so --
 * unlike the previous UTC + browser-local-offset components this replaces
 * (`PortfolioAsOf`/`SystemAsOf`/`LabAsOf` keep their own thin copies for
 * their respective screens; every other single-timestamp call site across
 * Radar/Markets/Dashboard/Opportunities uses this shared pair instead) --
 * no client-only effect/mount step is needed.
 */
export function BrasiliaInstant({ iso, className }: { iso: string; className?: string }) {
  return (
    <span title={iso} className={className}>
      {formatBrasiliaLong(iso) ?? "--"}
    </span>
  );
}

/** Compact "DD/MM HH:mm" form for table cells / dense "consultado em" notes -- same tooltip contract as `BrasiliaInstant`. */
export function BrasiliaShort({ iso, className }: { iso: string; className?: string }) {
  return (
    <span title={iso} className={className}>
      {formatBrasiliaShort(iso) ?? "--"}
    </span>
  );
}
