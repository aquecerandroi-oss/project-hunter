import { describe, expect, it } from "vitest";

import { exitReasonLabel } from "@/components/meme-desk/labels";
import { labContextReasonLabel, lineReasonLabel, pnlUsdBasisLabel, pnlUsdReasonLabel, testKindLabel, testStatusLabel, walletsSourceLabel, yesNoLabel } from "@/components/meme-tests/labels";
import { MEME_EXIT_REASONS } from "@/lib/api/meme-desk-types";
import { MEME_LAB_CONTEXT_REASONS, MEME_PNL_USD_BASES, MEME_PNL_USD_REASONS, MEME_TEST_KINDS, MEME_WALLETS_SOURCES, isMemeTestKind } from "@/lib/api/meme-tests-types";

describe("meme-tests labels are exhaustive and never leak a raw enum", () => {
  it("every kind", () => {
    expect(MEME_TEST_KINDS).toEqual(["paper", "real_observed"]);
    for (const kind of MEME_TEST_KINDS) expect(testKindLabel(kind)).not.toBe(kind);
    expect(testKindLabel("real_observed")).toBe("REAL — observado na cadeia");
    expect(testKindLabel("weird")).toBe("tipo não previsto");
    expect(isMemeTestKind("paper")).toBe(true);
    expect(isMemeTestKind("live")).toBe(false);
  });

  it("every wallets source (the API's own Portuguese literals)", () => {
    expect(MEME_WALLETS_SOURCES).toEqual(["observada", "não observada", "leitura indisponível"]);
    for (const source of MEME_WALLETS_SOURCES) expect(walletsSourceLabel(source).length).toBeGreaterThan(10);
    expect(walletsSourceLabel("não observada")).toBe("sem carteira observada ainda");
    expect(walletsSourceLabel("nope")).toBe("estado da carteira não previsto");
  });

  it("every PnL US$ basis and reason", () => {
    for (const basis of MEME_PNL_USD_BASES) expect(pnlUsdBasisLabel(basis)).not.toBe(basis);
    expect(pnlUsdBasisLabel("entry_quote_provisional")).toContain("provisório");
    expect(pnlUsdBasisLabel(null)).toBeNull();
    expect(pnlUsdBasisLabel("weird")).toBe("base não prevista");
    for (const reason of MEME_PNL_USD_REASONS) expect(pnlUsdReasonLabel(reason)).not.toBe(reason);
    expect(pnlUsdReasonLabel(null)).toBe("sem US$ registrado");
  });

  it("every lab-context reason, and the line reasons", () => {
    for (const reason of MEME_LAB_CONTEXT_REASONS) expect(labContextReasonLabel(reason)).not.toBe(reason);
    expect(labContextReasonLabel("manual_no_minute")).toContain("manual");
    expect(labContextReasonLabel(null)).toBeNull();
    expect(lineReasonLabel("too_few_points")).toContain("5 fotografias");
    expect(lineReasonLabel("brand_new")).toBe("motivo: brand_new");
    expect(lineReasonLabel(null)).toBe("sem motivo registrado");
  });

  it("status and yes/no", () => {
    expect(testStatusLabel("open")).toBe("aberta");
    expect(testStatusLabel("closed")).toBe("fechada");
    expect(testStatusLabel("x")).toBe("estado não previsto");
    expect(yesNoLabel(true)).toBe("sim");
    expect(yesNoLabel(false)).toBe("não");
    expect(yesNoLabel(null)).toBe("sem leitura");
    expect(yesNoLabel(undefined, "sem fita")).toBe("sem fita");
  });

  // The API's `ExitReason` grew to nine members (T4.10a); the desk dictionary
  // must cover every one -- three production builds broke on a missing label.
  it("the nine exit reasons, including max_loss and line_broken, have labels", () => {
    expect(MEME_EXIT_REASONS).toHaveLength(9);
    expect(MEME_EXIT_REASONS).toContain("max_loss");
    expect(MEME_EXIT_REASONS).toContain("line_broken");
    expect(exitReasonLabel("max_loss")).toBe("perda máxima (piso)");
    expect(exitReasonLabel("line_broken")).toBe("linha rompida");
  });
});
