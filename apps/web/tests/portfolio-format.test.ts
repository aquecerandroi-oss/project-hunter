import { describe, expect, it } from "vitest";

import {
  brlUnavailableLabel,
  formatBrl,
  formatBrlSigned,
  formatPctOrUnavailable,
  killSwitchBadgeVariant,
  killSwitchLabel,
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

describe("formatBrl / formatBrlSigned", () => {
  it("renders the BRL currency symbol", () => {
    expect(formatBrl("100000")).toBe("R$100,000.00");
  });

  it("signs a positive BRL result explicitly", () => {
    expect(formatBrlSigned("725.185185")).toBe("+R$725.19");
  });

  it("does not double the sign for a negative BRL result", () => {
    expect(formatBrlSigned("-725.185185")).toBe("-R$725.19");
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
