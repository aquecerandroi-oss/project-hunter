import { describe, expect, it } from "vitest";

import { parseDecomposition, parseExplanation, parseFeatureSnapshot } from "@/components/opportunities/decomposition-parse";
import { makeDecomposition, makeExplanation, makeFeatureSnapshot } from "@/tests/fixtures/radar";

describe("parseDecomposition: the real ScoreResult.decomposition() shape", () => {
  it("parses every field of a real decomposition", () => {
    const result = parseDecomposition(makeDecomposition());
    if (!result.recognized) throw new Error("expected recognized decomposition");
    expect(result.score).toBe("70.0000");
    expect(result.direction).toBe("long");
    expect(result.components).toHaveLength(2);
    expect(result.earlyMovement.stage).toBe("EARLY");
    expect(result.baselineIds).toEqual(["33333333-3333-3333-3333-333333333333"]);
  });

  it("never draws an unavailable component as if it observed zero -- available stays false, reason survives", () => {
    const result = parseDecomposition(makeDecomposition());
    if (!result.recognized) throw new Error("expected recognized decomposition");
    const derivatives = result.components.find((c) => c.name === "derivatives");
    expect(derivatives?.available).toBe(false);
    expect(derivatives?.normalized).toBeNull();
    expect(derivatives?.reason).toBe("no_usable_input");
  });

  it("keeps early_movement as a signed value outside the weighted components list", () => {
    const result = parseDecomposition(makeDecomposition());
    if (!result.recognized) throw new Error("expected recognized decomposition");
    expect(result.components.some((c) => c.name === "early_movement")).toBe(false);
    expect(result.earlyMovement.contribution).toBe("2.5000");
  });

  it("fails closed to {recognized: false} when components is missing (a producer-format drift), never throwing or fabricating zeros", () => {
    const result = parseDecomposition({ score: "1" });
    expect(result.recognized).toBe(false);
  });

  it("preserves agreement=null (ScoreResult.agreement: Decimal | None) instead of collapsing it into '0' (Astra's T2.7 diff review, must-fix 5)", () => {
    const result = parseDecomposition(makeDecomposition({ agreement: null }));
    if (!result.recognized) throw new Error("expected recognized decomposition");
    expect(result.agreement).toBeNull();
  });

  it("fails the WHOLE decomposition closed when one component is missing a required numeric field, instead of inventing weight/contribution/confidence '0' for it (Astra's T2.7 diff review, must-fix 5)", () => {
    const raw = makeDecomposition({
      components: [{ name: "momentum", available: true, normalized: "80" }],
    });
    const result = parseDecomposition(raw);
    expect(result.recognized).toBe(false);
  });
});

describe("parseExplanation: the real explain() shape, verbatim pt-BR", () => {
  it("parses resumo and frases as-is", () => {
    const result = parseExplanation(makeExplanation());
    if (!result.recognized) throw new Error("expected recognized explanation");
    expect(result.resumo).toContain("Score 70,00");
    expect(result.frases[0]?.codigo).toBe("score");
  });

  it("fails closed when resumo/frases are missing", () => {
    expect(parseExplanation({}).recognized).toBe(false);
  });
});

describe("parseFeatureSnapshot: real T2.4 envelope shape (vector.values) with the T2.6-assumed fallback (features.values)", () => {
  it("reads the real envelope's vector.values first", () => {
    const result = parseFeatureSnapshot(makeFeatureSnapshot());
    if (!result.recognized) throw new Error("expected recognized feature snapshot");
    expect(result.source).toBe("vector");
    const atr = result.features.find((f) => f.key === "atr_14_pct");
    expect(atr?.value).toBe("0.0123");
    expect(atr?.quality).toBe("ok");
  });

  it("never turns an unavailable feature's null value into a fabricated zero -- it stays null, with its real reason", () => {
    const result = parseFeatureSnapshot(makeFeatureSnapshot());
    if (!result.recognized) throw new Error("expected recognized feature snapshot");
    const relVolume = result.features.find((f) => f.key === "relative_volume_1h");
    expect(relVolume?.value).toBeNull();
    expect(relVolume?.reason).toBe("warmup");
  });

  it("falls back to the notes-T2.6.md-assumed features.values path when vector is absent", () => {
    const result = parseFeatureSnapshot({ features: { values: { atr_14_pct: { value: "0.05", quality: "ok" } } } });
    if (!result.recognized) throw new Error("expected recognized feature snapshot");
    expect(result.source).toBe("features");
  });

  it("fails closed to {recognized: false} for neither shape, never a silently empty table", () => {
    expect(parseFeatureSnapshot({ something_else: true }).recognized).toBe(false);
  });

  it("fails the WHOLE vector closed when any single entry is malformed, instead of silently dropping it into an empty-but-'recognized' table (Astra's T2.7 diff review, must-fix 5)", () => {
    const result = parseFeatureSnapshot({ vector: { values: { atr_14_pct: "not-an-object" } } });
    expect(result.recognized).toBe(false);
  });
});
