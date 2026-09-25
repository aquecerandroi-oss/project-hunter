import { describe, expect, it } from "vitest";

import { ruleSetStatusLabel } from "@/components/meme-lab/labels";
import { MEME_LAB_RULE_SET_STATUSES } from "@/lib/api/meme-lab-types";

describe("ruleSetStatusLabel: every MemeLabRuleSetStatus has a clean pt label", () => {
  it.each(MEME_LAB_RULE_SET_STATUSES)("%s", (status) => {
    const label = ruleSetStatusLabel(status);
    expect(label).not.toBe(status);
    expect(label).not.toMatch(/_/);
  });

  it("never disappears for an unrecognized status", () => {
    expect(ruleSetStatusLabel("some_new_status")).toBe("estado não previsto");
  });
});
