import type { AssumedCostsOut, VersionSummaryOut } from "@/lib/api/lab-types";

/**
 * Assumed costs are per-`strategy_version` (`coverage.assumed_costs`) and
 * may legitimately differ between versions, or be unset. Astra's S3b
 * hierarchy review (must-fix): a fixed top banner that always displays the
 * FIRST version's numbers would misrepresent every other version whose
 * costs differ -- the banner may only claim a shared number when every
 * version in view actually agrees on it.
 */
function costsEqual(a: AssumedCostsOut, b: AssumedCostsOut): boolean {
  return (
    a.assumed_spread_bps === b.assumed_spread_bps &&
    a.slippage_bps === b.slippage_bps &&
    a.fee_bps === b.fee_bps &&
    a.max_entry_delay_s === b.max_entry_delay_s
  );
}

/** The shared `assumed_costs` across every version, or `null` when any two versions disagree (or there are none). */
export function commonAssumedCosts(versions: VersionSummaryOut[]): AssumedCostsOut | null {
  const [first, ...rest] = versions;
  if (!first) return null;
  const base = first.coverage.assumed_costs;
  return rest.every((v) => costsEqual(v.coverage.assumed_costs, base)) ? base : null;
}

/** Renders `null` cost fields honestly instead of `0` or `--` standing in for "unknown". */
export function formatAssumedCosts(costs: AssumedCostsOut): string {
  const spread = costs.assumed_spread_bps ?? "desconhecido";
  const slippage = costs.slippage_bps ?? "desconhecido";
  const fee = costs.fee_bps ?? "desconhecido";
  return `spread ${spread} bps, slippage ${slippage} bps/lado, taxa ${fee} bps/lado`;
}
