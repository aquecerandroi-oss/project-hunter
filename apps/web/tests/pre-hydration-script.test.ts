import { describe, expect, it } from "vitest";

import { PRE_HYDRATION_SCRIPT } from "@/lib/pre-hydration-script";

describe("PRE_HYDRATION_SCRIPT (app/layout.tsx's pre-paint init)", () => {
  it("reads both the theme and density localStorage keys", () => {
    expect(PRE_HYDRATION_SCRIPT).toContain('localStorage.getItem("hunter-theme")');
    expect(PRE_HYDRATION_SCRIPT).toContain('localStorage.getItem("hunter-density")');
  });

  it("sets data-theme and data-density on the document element", () => {
    expect(PRE_HYDRATION_SCRIPT).toContain('document.documentElement.setAttribute("data-theme"');
    expect(PRE_HYDRATION_SCRIPT).toContain('document.documentElement.setAttribute("data-density"');
  });

  it("wraps each localStorage read in its own try/catch (fails open)", () => {
    const tryCount = (PRE_HYDRATION_SCRIPT.match(/try\{/g) ?? []).length;
    const catchCount = (PRE_HYDRATION_SCRIPT.match(/catch\(e\)\{\}/g) ?? []).length;
    expect(tryCount).toBe(2);
    expect(catchCount).toBe(2);
  });

  it("is valid, immediately-invoked JavaScript", () => {
    expect(() => new Function(PRE_HYDRATION_SCRIPT)).not.toThrow();
  });
});
