import { describe, expect, it } from "vitest";

import { readyLabel, WORKER_ROLE_VALUES, WORKER_STATUS_VALUES, workerRoleLabel, workerStatusLabel } from "@/components/system/labels";

function isCleanLabel(label: string): boolean {
  return !label.includes("_") && label !== label.toUpperCase();
}

describe("workerRoleLabel: every WORKER_ROLE_VALUES member has a clean Portuguese label", () => {
  it.each(WORKER_ROLE_VALUES)("%s", (role) => {
    const label = workerRoleLabel(role);
    expect(isCleanLabel(label)).toBe(true);
  });

  it("never drops an unrecognized role silently", () => {
    expect(workerRoleLabel("analytics")).toBe("analytics");
  });
});

describe("workerStatusLabel: every WORKER_STATUS_VALUES member has a clean Portuguese label", () => {
  it.each(WORKER_STATUS_VALUES)("%s", (status) => {
    const label = workerStatusLabel(status);
    expect(isCleanLabel(label)).toBe(true);
  });

  it("labels alive/late/dead", () => {
    expect(workerStatusLabel("alive")).toBe("vivo");
    expect(workerStatusLabel("late")).toBe("atrasado");
    expect(workerStatusLabel("dead")).toBe("morto");
  });
});

describe("readyLabel", () => {
  it("translates Ready/Not Ready", () => {
    expect(readyLabel(true)).toBe("Pronto");
    expect(readyLabel(false)).toBe("Não pronto");
  });
});
