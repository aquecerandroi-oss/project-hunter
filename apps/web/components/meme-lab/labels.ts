/**
 * Meme arms board vocabulary (DESIGN-5 "sem backstage na copy"): rule set
 * `status`, the only enum this board renders that `components/meme-desk/labels.ts`
 * does not already cover (`ruleSetKindLabel` there handles `kind`).
 * `tests/meme-arms-labels.test.ts` iterates `MEME_LAB_RULE_SET_STATUSES` for
 * the exhaustiveness check.
 */
import { MEME_LAB_RULE_SET_STATUSES, type MemeLabRuleSetStatus } from "@/lib/api/meme-lab-types";

const STATUS_LABEL: Record<MemeLabRuleSetStatus, string> = {
  active: "ativo",
  retired: "aposentado",
};

export function ruleSetStatusLabel(status: string): string {
  return (MEME_LAB_RULE_SET_STATUSES as readonly string[]).includes(status) ? STATUS_LABEL[status as MemeLabRuleSetStatus] : "estado não previsto";
}
