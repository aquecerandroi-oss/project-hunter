import { formatWhenShort } from "@/components/lab/lab-format";

export interface WhenCellProps {
  iso: string | null;
  className?: string;
}

/**
 * One-line date+time, fixed width so it never wraps (brief T3.17b item 3:
 * "05:05:05 UTC (02:05:05 -03:00)" -- the previous text -- had no date at
 * all and wrapped across four lines, so two different days looked identical
 * on screen). Brief T3.22 (2026-09-08, Everton: "sou de sao paulo intao
 * horario tem que ser de brasilia") made this Brasília, the organization's
 * one display timezone, instead of UTC -- the "Quando" column header itself
 * now says "Quando (Brasília)" once (`lab-signals-table-head.tsx`), so this
 * cell no longer repeats a timezone suffix. The exact UTC instant stays one
 * hover away in the `title` attribute: the raw ISO string is already UTC
 * and copyable as-is (CLAUDE.md: "Time is always UTC" in storage/API), so no
 * separate formatting is needed for that half.
 *
 * Deterministic in any runtime timezone (SSR-safe): `Intl.DateTimeFormat`'s
 * explicit `timeZone` option (`lib/time.ts`) resolves Brasília's own offset
 * regardless of where this renders, so -- unlike the previous UTC+
 * browser-local-offset version -- no client-only effect is needed to avoid a
 * hydration mismatch (H2 no longer applies once the display timezone is
 * fixed rather than the browser's own).
 */
export function WhenCell({ iso, className }: WhenCellProps) {
  const fallbackClass = className ?? "whitespace-nowrap font-mono tabular-nums";
  if (iso === null) return <span className={fallbackClass}>--</span>;

  const short = formatWhenShort(iso);
  if (short === null) return <span className={fallbackClass}>--</span>;

  return (
    <span title={iso} className={fallbackClass}>
      {short}
    </span>
  );
}
