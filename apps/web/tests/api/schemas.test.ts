import { describe, expect, it } from "vitest";

import {
  MIN_VIRTUAL_CAPITAL,
  invitationCreateSchema,
  invitationEmailSchema,
  memberRoleSchema,
  monitoredExchangesSchema,
  objectiveSchema,
  onboardingCreateOrgSchema,
  organizationNameSchema,
  riskPresetSchema,
  virtualCapitalSchema,
} from "@/lib/api/schemas";

describe("objectiveSchema", () => {
  it("accepts every WorkspaceObjective member", () => {
    for (const value of ["explore", "paper_trading", "research", "automated_trading"]) {
      expect(objectiveSchema.safeParse(value).success).toBe(true);
    }
  });

  it("rejects an unknown objective", () => {
    expect(objectiveSchema.safeParse("live_trading").success).toBe(false);
  });
});

describe("virtualCapitalSchema", () => {
  it(`rejects a value below the ${MIN_VIRTUAL_CAPITAL} floor (apps/api MIN_VIRTUAL_CAPITAL)`, () => {
    expect(virtualCapitalSchema.safeParse("999.99").success).toBe(false);
    expect(virtualCapitalSchema.safeParse("0").success).toBe(false);
  });

  it("accepts the floor exactly", () => {
    expect(virtualCapitalSchema.safeParse(String(MIN_VIRTUAL_CAPITAL)).success).toBe(true);
  });

  it("accepts a decimal value above the floor", () => {
    expect(virtualCapitalSchema.safeParse("25000.50").success).toBe(true);
  });

  it("rejects a non-numeric string", () => {
    expect(virtualCapitalSchema.safeParse("ten thousand").success).toBe(false);
  });

  it("rejects a negative value", () => {
    expect(virtualCapitalSchema.safeParse("-5000").success).toBe(false);
  });

  it("rejects scientific notation and other non-plain-decimal shapes", () => {
    expect(virtualCapitalSchema.safeParse("1e4").success).toBe(false);
  });
});

describe("riskPresetSchema", () => {
  it("accepts every RiskPreset member", () => {
    for (const value of ["conservative", "balanced", "aggressive", "custom"]) {
      expect(riskPresetSchema.safeParse(value).success).toBe(true);
    }
  });

  it("rejects an unknown preset", () => {
    expect(riskPresetSchema.safeParse("yolo").success).toBe(false);
  });
});

describe("monitoredExchangesSchema", () => {
  it("accepts the known M0 exchange codes", () => {
    expect(monitoredExchangesSchema.safeParse(["binance", "bybit"]).success).toBe(true);
  });

  it("accepts an empty list", () => {
    expect(monitoredExchangesSchema.safeParse([]).success).toBe(true);
  });

  it("rejects a code outside the seeded set", () => {
    expect(monitoredExchangesSchema.safeParse(["kraken"]).success).toBe(false);
  });

  it("rejects duplicated overflow beyond the max length", () => {
    const tooMany = Array.from({ length: 11 }, () => "binance");
    expect(monitoredExchangesSchema.safeParse(tooMany).success).toBe(false);
  });
});

describe("organizationNameSchema / onboardingCreateOrgSchema", () => {
  it("rejects an empty name", () => {
    expect(organizationNameSchema.safeParse("").success).toBe(false);
    expect(organizationNameSchema.safeParse("   ").success).toBe(false);
  });

  it("accepts a valid name with an optional workspace name", () => {
    const result = onboardingCreateOrgSchema.safeParse({ name: "Acme Capital", workspaceName: "Main" });
    expect(result.success).toBe(true);
  });

  it("rejects a name over 120 characters", () => {
    expect(organizationNameSchema.safeParse("a".repeat(121)).success).toBe(false);
  });
});

describe("invitationEmailSchema / invitationCreateSchema", () => {
  it("accepts a well-formed email and lowercases it", () => {
    const result = invitationEmailSchema.safeParse("Someone@Example.com");
    expect(result.success).toBe(true);
    if (result.success) expect(result.data).toBe("someone@example.com");
  });

  it("rejects a malformed email", () => {
    expect(invitationEmailSchema.safeParse("not-an-email").success).toBe(false);
  });

  it("rejects an invitation with an unknown role", () => {
    expect(invitationCreateSchema.safeParse({ email: "a@b.com", role: "SUPERADMIN" }).success).toBe(false);
  });
});

describe("memberRoleSchema", () => {
  it("accepts every OrganizationRole member", () => {
    for (const value of ["OWNER", "ADMIN", "TRADER", "ANALYST", "VIEWER"]) {
      expect(memberRoleSchema.safeParse(value).success).toBe(true);
    }
  });

  it("rejects a lowercase role (case-sensitive, mirrors the Postgres enum)", () => {
    expect(memberRoleSchema.safeParse("owner").success).toBe(false);
  });
});
