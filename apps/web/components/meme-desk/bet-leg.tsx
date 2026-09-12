/**
 * T4.10b: the leg of a paper bet on the desk (brief T4.10 §Conjuntos de
 * regras): `probe` = "semi-comprado (sonda)" (the small hype probe opened
 * before a line exists), `scale` = "escalado (perna 2)" (the second leg,
 * opened only while the probe is open, `parent_bet_id` pointing at it).
 * `single` and a payload from before the column render nothing.
 *
 * The parent link is an in-page anchor to the probe's own card (every bet
 * card carries `id={betAnchorId(bet.id)}`); when the probe is not on the
 * page (older than the desk's window) the short id is shown as text --
 * never a link that goes nowhere.
 */
import { type MemeDeskBet, readBetLeg } from "@/lib/api/meme-desk-types";

import { betLegLabel } from "./labels";

export function betAnchorId(betId: string): string {
  return `bet-${betId}`;
}

function shortId(id: string): string {
  return id.length <= 8 ? id : id.slice(0, 8);
}

export interface BetLegBadgeProps {
  bet: MemeDeskBet;
  /** Ids of every bet rendered on the page -- the parent link exists only when its target does. */
  knownBetIds: readonly string[];
}

export function BetLegBadge({ bet, knownBetIds }: BetLegBadgeProps) {
  const { leg, parentBetId } = readBetLeg(bet);
  if (leg === null || leg === "single") return null;
  const parentOnPage = parentBetId !== null && knownBetIds.includes(parentBetId);
  return (
    <>
      <span className="rounded-md bg-info-soft px-1.5 py-0.5 text-[11px] font-medium text-info">{betLegLabel(leg)}</span>
      {leg === "scale" && parentBetId !== null && (
        parentOnPage ? (
          <a href={`#${betAnchorId(parentBetId)}`} className="text-[11px] text-fg-muted underline" title="ir para a sonda de origem">
            sonda {shortId(parentBetId)}
          </a>
        ) : (
          <span className="text-[11px] text-fg-subtle" title="a sonda de origem não está nesta página">
            sonda {shortId(parentBetId)}
          </span>
        )
      )}
    </>
  );
}
