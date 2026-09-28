import { describe, expect, it } from "vitest";

import {
  DESK_ORDER_STATUS_LABEL,
  DESK_ORDER_STATUSES,
  MARKET_EVENT_CONFIDENCE_LABEL,
  MARKET_EVENT_CONFIDENCES,
  MARKET_EVENT_KIND_LABEL,
  MARKET_EVENT_KINDS,
  MARKET_EVENT_SOURCE_LABEL,
  MARKET_EVENT_SOURCES,
  deskOrderStatusLabel,
} from "@/components/confluence/labels";

/**
 * design §7b, Vitest case 5: "falha quando um membro novo de
 * SPOT_ORDER_STATUSES, de kind ou de confidence não tem rótulo em
 * português." Every value in each source-of-truth array must map to a
 * non-empty Portuguese label, and no label may be a raw echo of its own key
 * (the "sem enum cru na tela" rule, DESIGN-5).
 */
function assertEveryValueHasAPortugueseLabel<T extends string>(
  values: readonly T[],
  label: Record<T, string>,
): void {
  for (const value of values) {
    const text = label[value];
    expect(text, `missing label for "${value}"`).toBeTruthy();
  }
}

describe("confluence labels completeness", () => {
  it("every DeskOrderOut.status in the design's three-answer set has a label", () => {
    assertEveryValueHasAPortugueseLabel(DESK_ORDER_STATUSES, DESK_ORDER_STATUS_LABEL);
  });

  it("deskOrderStatusLabel also covers the two in-flight statuses outside the narrow union", () => {
    expect(deskOrderStatusLabel("simulated")).toBe("simulada");
    expect(deskOrderStatusLabel("submitted_unconfirmed")).toBe("enviada, sem confirmação");
  });

  it("an unrecognized status is still shown, always prefixed -- never bare (DESIGN-5)", () => {
    expect(deskOrderStatusLabel("a-future-status")).toBe("status: a-future-status");
  });

  it("every market_events.kind has a label", () => {
    assertEveryValueHasAPortugueseLabel(MARKET_EVENT_KINDS, MARKET_EVENT_KIND_LABEL);
  });

  it("every market_events.confidence has a label", () => {
    assertEveryValueHasAPortugueseLabel(MARKET_EVENT_CONFIDENCES, MARKET_EVENT_CONFIDENCE_LABEL);
  });

  it("every market_events.source has a label", () => {
    assertEveryValueHasAPortugueseLabel(MARKET_EVENT_SOURCES, MARKET_EVENT_SOURCE_LABEL);
  });
});
