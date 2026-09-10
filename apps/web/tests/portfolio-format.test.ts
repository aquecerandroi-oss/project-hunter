import { describe, expect, it } from "vitest";

import {
  brlUnavailableLabel,
  formatPctOrUnavailable,
  killSwitchBadgeVariant,
  killSwitchLabel,
  riskProfileGateReason,
  signColorClass,
  unavailableLabel,
} from "@/components/portfolio/portfolio-format";
import { formatUsdt, formatUsdtSigned } from "@/lib/format";

describe("formatUsdt: never mistaken for US dollars", () => {
  it("appends an explicit USDT suffix instead of a currency symbol", () => {
    expect(formatUsdt("1234.5")).toBe("1,234.50 USDT");
  });

  it("keeps negative amounts signed with the minus outside the number", () => {
    expect(formatUsdt("-1234.5")).toBe("-1,234.50 USDT");
  });
});

describe("formatUsdtSigned", () => {
  it("adds an explicit '+' for a positive amount", () => {
    expect(formatUsdtSigned("10")).toBe("+10.00 USDT");
  });

  it("does not double the sign for a negative amount", () => {
    expect(formatUsdtSigned("-10")).toBe("-10.00 USDT");
  });

  it("does not sign an exact zero", () => {
    expect(formatUsdtSigned("0")).toBe("0.00 USDT");
  });
});

describe("signColorClass: never colors an absent or flat value as a gain", () => {
  it("is neutral for null", () => {
    expect(signColorClass(null)).toBe("text-fg-muted");
  });

  it("is neutral for an exact zero", () => {
    expect(signColorClass("0.0000000000")).toBe("text-fg");
  });

  it("is green for a positive value", () => {
    expect(signColorClass("12.5")).toBe("text-green");
  });

  it("is red for a negative value", () => {
    expect(signColorClass("-12.5")).toBe("text-red");
  });
});

describe("formatPctOrUnavailable: null never becomes 0%", () => {
  it("formats a real percentage", () => {
    const result = formatPctOrUnavailable("-0.01");
    expect(result).toEqual({ text: "-1.00%", isValue: true });
  });

  it("renders 'indisponível' (not '0%') for a null value, with the given note", () => {
    const result = formatPctOrUnavailable(null, "referência do dia ausente");
    expect(result.isValue).toBe(false);
    expect(result.text).toBe("indisponível (referência do dia ausente)");
  });

  it("still renders 'indisponível' without a note", () => {
    expect(formatPctOrUnavailable(null).text).toBe("indisponível");
  });
});

describe("unavailableLabel / brlUnavailableLabel: every reason renders, even an unrecognized one", () => {
  it("labels a known unavailable code", () => {
    expect(unavailableLabel("daily_reference")).toMatch(/referência do dia/);
  });

  it("never drops an unrecognized code silently", () => {
    expect(unavailableLabel("something_new")).toBe("motivo não catalogado: something_new");
  });

  it("labels a known BRL reason", () => {
    expect(brlUnavailableLabel("no_fx_observation")).toMatch(/cotação/);
  });
});

describe("killSwitchLabel / killSwitchBadgeVariant", () => {
  it("labels TRADING_DISABLED as BLOQUEADO", () => {
    expect(killSwitchLabel("TRADING_DISABLED")).toBe("BLOQUEADO");
  });

  it("gives TRADING_DISABLED and EMERGENCY the negative (red) badge variant", () => {
    expect(killSwitchBadgeVariant("TRADING_DISABLED")).toBe("negative");
    expect(killSwitchBadgeVariant("EMERGENCY")).toBe("negative");
  });

  it("gives WARNING the warning variant and ACTIVE the default", () => {
    expect(killSwitchBadgeVariant("WARNING")).toBe("warning");
    expect(killSwitchBadgeVariant("ACTIVE")).toBe("default");
  });
});

describe("riskProfileGateReason (T3.72d): never shows a limit the engine does not apply", () => {
  it("is null when the linked profile matches the engine (source=risk_profile, not diverged)", () => {
    expect(riskProfileGateReason({ source: "risk_profile", diverged_from_engine: false })).toBeNull();
  });

  it("names the missing-link case (source=engine_default, not diverged -- risk_profile_missing proxy)", () => {
    const reason = riskProfileGateReason({ source: "engine_default", diverged_from_engine: false });
    expect(reason).toMatch(/sem perfil de risco vinculado/i);
    expect(reason).toMatch(/ACTIVATION\.md §8b/);
  });

  it("names the divergence case when the linked row differs from PAPER_V1 (source=risk_profile, diverged)", () => {
    const reason = riskProfileGateReason({ source: "risk_profile", diverged_from_engine: true });
    expect(reason).toMatch(/perfil divergente/i);
    expect(reason).toMatch(/ACTIVATION\.md §8b/);
  });

  it("also treats the unreadable-row case as divergence (source=engine_default, forced diverged=true)", () => {
    const reason = riskProfileGateReason({ source: "engine_default", diverged_from_engine: true });
    expect(reason).toMatch(/perfil divergente/i);
  });
});
