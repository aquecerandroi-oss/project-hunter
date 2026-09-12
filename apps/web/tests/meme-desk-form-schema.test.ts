import { describe, expect, it } from "vitest";

import { deskParamsFormSchema, formValuesFromSuggested, manualBuyFormSchema, toApproveBody, toManualBody } from "@/lib/api/meme-desk-form-schema";

const VALID = { sizeSol: "0.2", targetX: "2", trailingPct: "30", maxHoldS: "900", note: "" };

describe("formValuesFromSuggested: the sheet is pre-filled from the loop's suggestion", () => {
  it("copies the four parameters as strings", () => {
    expect(formValuesFromSuggested({ size_sol: "0.2", target_x: "2", trailing_pct: "30", max_hold_s: 900, note: null })).toEqual(VALID);
  });

  it("leaves a missing suggestion blank -- never an invented default", () => {
    expect(formValuesFromSuggested({ size_sol: null, target_x: null, trailing_pct: null, max_hold_s: null, note: null })).toEqual({
      sizeSol: "",
      targetX: "",
      trailingPct: "",
      maxHoldS: "",
      note: "",
    });
    expect(formValuesFromSuggested(null).sizeSol).toBe("");
  });
});

describe("deskParamsFormSchema: the API's bounds, checked before any request", () => {
  it("accepts the suggested values", () => {
    expect(deskParamsFormSchema.safeParse(VALID).success).toBe(true);
  });

  it("refuses a zero size", () => {
    const result = deskParamsFormSchema.safeParse({ ...VALID, sizeSol: "0" });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]?.message).toContain("maior que zero");
  });

  it("refuses a target at or below 1×", () => {
    expect(deskParamsFormSchema.safeParse({ ...VALID, targetX: "1" }).success).toBe(false);
    expect(deskParamsFormSchema.safeParse({ ...VALID, targetX: "0.9" }).success).toBe(false);
  });

  it("refuses a trailing outside (0, 100)", () => {
    expect(deskParamsFormSchema.safeParse({ ...VALID, trailingPct: "100" }).success).toBe(false);
    expect(deskParamsFormSchema.safeParse({ ...VALID, trailingPct: "0" }).success).toBe(false);
    expect(deskParamsFormSchema.safeParse({ ...VALID, trailingPct: "99.5" }).success).toBe(true);
  });

  it("refuses a non-integer or zero hold", () => {
    expect(deskParamsFormSchema.safeParse({ ...VALID, maxHoldS: "1.5" }).success).toBe(false);
    expect(deskParamsFormSchema.safeParse({ ...VALID, maxHoldS: "0" }).success).toBe(false);
  });

  it("refuses a comma decimal (the API wants a dot)", () => {
    expect(deskParamsFormSchema.safeParse({ ...VALID, sizeSol: "0,2" }).success).toBe(false);
  });
});

describe("toApproveBody / toManualBody: the wire shape, money as strings", () => {
  it("keeps decimals as strings and parses the hold as an integer", () => {
    expect(toApproveBody({ ...VALID, note: "ok" })).toEqual({ size_sol: "0.2", target_x: "2", trailing_pct: "30", max_hold_s: 900, note: "ok" });
  });

  it("sends null for an empty note", () => {
    expect(toApproveBody(VALID).note).toBeNull();
  });

  it("manual buy needs a mint of plausible length", () => {
    expect(manualBuyFormSchema.safeParse({ ...VALID, mint: "short" }).success).toBe(false);
    const parsed = manualBuyFormSchema.safeParse({ ...VALID, mint: " Fh42kAfy27CGoUA8CgFwpTGMubzndaAyTy2gghu5pump " });
    expect(parsed.success).toBe(true);
    if (parsed.success) expect(toManualBody(parsed.data).mint).toBe("Fh42kAfy27CGoUA8CgFwpTGMubzndaAyTy2gghu5pump");
  });
});
