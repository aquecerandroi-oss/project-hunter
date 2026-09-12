import { describe, expect, it } from "vitest";

import { reasonText } from "@/components/meme-desk/proposal-card";

/**
 * `meme_proposals.reasons[i]` (T4.10a decomposition, `proposals_reasons.py`):
 * a string, a `{rule}` block (optionally carrying `series` since T4.16 for
 * the 15-second clock) or a `{feature, value, window?, cap?}` block.
 * `String(obj)` used to print "[object Object]" -- every shape must read as
 * Portuguese words.
 */
describe("reasonText: every reasons[i] shape reads as words, never [object Object]", () => {
  it("a plain string passes through unchanged", () => {
    expect(reasonText("progress_gate")).toBe("progress_gate");
  });

  it("a rule block on the closed-minute clock keeps its plain wording", () => {
    expect(reasonText({ rule: "flow_v2/1" })).toBe("regra flow_v2/1");
  });

  // T4.16: the fast lane's rows carry `series: "meme_features_15s_v1"`.
  it("a rule block whose series is the 15-second clock says so", () => {
    expect(reasonText({ rule: "flow_v2/1", series: "meme_features_15s_v1" })).toBe("regra flow_v2/1 · porta de 15 s");
  });

  it("a rule block on an unrelated/older series keeps the plain wording (only the 15s clock is named)", () => {
    expect(reasonText({ rule: "flow_v2/1", series: "meme_features_1m_v1" })).toBe("regra flow_v2/1");
  });

  it("a feature block renders feature = value, with the optional window/cap", () => {
    expect(reasonText({ feature: "age_s", value: 42, window: [30, 300] })).toBe("age_s = 42 (janela 30–300)");
    expect(reasonText({ feature: "participation_pct", value: "2.5", cap: "5" })).toBe("participation_pct = 2.5 (teto 5)");
  });

  it("never prints [object Object] for an unrecognized object shape", () => {
    expect(reasonText({ weird: true })).not.toContain("[object Object]");
  });
});
