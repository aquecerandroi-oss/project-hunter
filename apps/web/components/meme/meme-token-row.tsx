import Link from "next/link";

import { BrasiliaShort } from "@/components/time/brasilia-instant";
import type { MemeToken } from "@/lib/api/meme-types";

import { memeSourceLabel, memeTokenStateLabel } from "./labels";
import { formatMemePct, formatSol } from "./meme-format";

function truncateAddress(address: string): string {
  return address.length <= 10 ? address : `${address.slice(0, 4)}…${address.slice(-4)}`;
}

function formatAge(minutes: number | null): string {
  if (minutes === null) return "idade desconhecida";
  if (minutes < 60) return `${minutes} min`;
  if (minutes < 60 * 24) return `${Math.floor(minutes / 60)} h`;
  return `${Math.floor(minutes / (60 * 24))} d`;
}

export interface MemeTokenRowProps {
  orgSlug: string;
  row: MemeToken;
  rowHeight: number;
}

/** One `<tr>` of `MemeTokensTable` -- every "no data yet" field renders an honest placeholder, never a fabricated zero/dash standing in for a real value (docs/DESIGN.md). */
export function MemeTokenRow({ orgSlug, row, rowHeight }: MemeTokenRowProps) {
  return (
    <tr className="border-t border-border odd:bg-bg-overlay/40" style={{ height: rowHeight }}>
      <td className="px-3 py-2">
        <Link href={`/${orgSlug}/meme/${row.mint}`} className="font-medium text-fg hover:underline">
          {row.name ?? "(nome desconhecido)"}
        </Link>
        <div className="text-[11px] text-fg-subtle">{row.symbol ?? "(símbolo desconhecido)"}</div>
      </td>
      <td className="px-3 py-2 text-right text-fg-muted">{formatAge(row.age_minutes)}</td>
      <td className="px-3 py-2 text-right tabular-nums">{row.mcap_sol === null ? <span className="text-fg-subtle">sem dado</span> : formatSol(row.mcap_sol)}</td>
      <td className="px-3 py-2 text-right tabular-nums">
        {row.curve_progress_pct === null ? <span className="text-fg-subtle">sem dado</span> : formatMemePct(row.curve_progress_pct)}
      </td>
      <td className="hidden px-3 py-2 md:table-cell">
        <span className="text-fg-muted">{memeTokenStateLabel(row.state)}</span>
        {row.mayhem_state && <div className="text-[11px] text-fg-subtle">Mayhem: {row.mayhem_state}</div>}
      </td>
      <td className="hidden px-3 py-2 font-mono text-[11px] text-fg-subtle md:table-cell">
        {row.creator ? truncateAddress(row.creator) : "desconhecido"}
      </td>
      <td className="hidden px-3 py-2 text-right md:table-cell">
        {row.snapshot_observed_at ? (
          <>
            <BrasiliaShort iso={row.snapshot_observed_at} className="text-fg-muted" />
            <div className="text-[11px] text-fg-subtle">{row.snapshot_source ? memeSourceLabel(row.snapshot_source) : ""}</div>
          </>
        ) : (
          <span className="text-fg-subtle">sem observação ainda</span>
        )}
      </td>
    </tr>
  );
}
