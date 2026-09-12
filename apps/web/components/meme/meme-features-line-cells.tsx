/**
 * T4.10b: the trend-line and hype cells of the per-minute features table
 * (`meme-features-table.tsx`). Same rule as every other cell there: a value
 * OR a named reason, never a blank and never a `0`/`false` standing in for
 * "not measured". When the line is not traceable the three line cells
 * collapse into one that carries the reason once, instead of repeating it.
 */
import type { MemeFeaturePoint } from "@/lib/api/meme-types";
import { formatPct } from "@/lib/format";

import { memeHypeReasonLabel } from "./labels";
import { formatRatio, formatSol } from "./meme-format";
import { hypeText, lineReading, lineReadingText, readHype, readLineFields } from "./meme-lines";

const LINE_CELL = "hidden px-3 py-2 text-right md:table-cell";

function yesNo(value: boolean | null): string {
  if (value === null) return "sem leitura";
  return value ? "Sim" : "Não";
}

/** Three `<td>`s (support with its distance, higher lows, breakout) or one collapsed `<td colSpan=3>` with the reason. */
export function LineCells({ row }: { row: MemeFeaturePoint }) {
  const fields = readLineFields(row);
  const reading = lineReading(fields);
  if (reading.kind !== "traced") {
    // A breakout can be known against the previous high even before two lows exist -- said beside the reason, never dropped.
    const breakout = reading.kind === "untraceable" && fields.breakout15m !== null ? ` · rompimento 15 min: ${yesNo(fields.breakout15m)}` : "";
    return (
      <td colSpan={3} className="hidden px-3 py-2 text-left text-fg-subtle md:table-cell">
        {lineReadingText(reading)}
        {breakout}
      </td>
    );
  }
  return (
    <>
      <td className={LINE_CELL}>
        <span className="tabular-nums">{formatSol(reading.supportLineSol)}</span>
        {reading.distanceToSupportPct !== null && (
          <span className="ml-1 text-[11px] tabular-nums text-fg-subtle" title="distância do mcap ao suporte">
            {formatPct(reading.distanceToSupportPct, { signed: true })}
          </span>
        )}
      </td>
      <td className={LINE_CELL}>
        <span className={reading.higherLows === null ? "text-fg-subtle" : undefined}>{yesNo(reading.higherLows)}</span>
      </td>
      <td className={LINE_CELL}>
        <span className={reading.breakout === null ? "text-fg-subtle" : undefined}>{yesNo(reading.breakout)}</span>
      </td>
    </>
  );
}

/** `hype_score` (0..1, documented weights in the contract) with `hype_reason` beside it; null names why. */
export function HypeCell({ row }: { row: MemeFeaturePoint }) {
  const hype = readHype(row);
  if (hype.score === null) {
    return (
      <td className="px-3 py-2 text-right">
        <span className="text-fg-subtle">{hypeText(hype)}</span>
      </td>
    );
  }
  return (
    <td className="px-3 py-2 text-right">
      <span className="tabular-nums">{formatRatio(hype.score)}</span>
      {hype.reason && (
        <span className="ml-1 text-[11px] text-fg-subtle" title={memeHypeReasonLabel(hype.reason)}>
          parcial
        </span>
      )}
    </td>
  );
}
