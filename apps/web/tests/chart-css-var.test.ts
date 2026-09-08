import { afterEach, describe, expect, it, vi } from "vitest";

import { chartColor, cssVar } from "@/lib/charts/css-var";
import { logger } from "@/lib/logger";

describe("cssVar (T3.31)", () => {
  afterEach(() => {
    document.documentElement.style.removeProperty("--color-test-token");
  });

  it("returns the computed value when the token resolves", () => {
    document.documentElement.style.setProperty("--color-test-token", "#123456");
    expect(cssVar("--color-test-token", "#000000")).toBe("#123456");
  });

  it("falls back to the given hex and warns exactly once when the token is missing/empty, never on repeat calls", () => {
    const warn = vi.spyOn(logger, "warn").mockImplementation(() => undefined);
    expect(cssVar("--color-does-not-exist-a", "#abcdef")).toBe("#abcdef");
    expect(cssVar("--color-does-not-exist-a", "#abcdef")).toBe("#abcdef");
    expect(cssVar("--color-does-not-exist-a", "#abcdef")).toBe("#abcdef");
    expect(warn).toHaveBeenCalledTimes(1);
    expect(warn).toHaveBeenCalledWith("chart_css_var_missing", { name: "--color-does-not-exist-a", fallback: "#abcdef" });
    warn.mockRestore();
  });

  it("warns again for a *different* missing token (the dedup key is the token name)", () => {
    const warn = vi.spyOn(logger, "warn").mockImplementation(() => undefined);
    cssVar("--color-does-not-exist-b", "#111111");
    cssVar("--color-does-not-exist-c", "#222222");
    expect(warn).toHaveBeenCalledTimes(2);
    warn.mockRestore();
  });
});

describe("chartColor (T3.31)", () => {
  it("falls back to the known dark-theme hex for a recognised token when jsdom has no value for it", () => {
    expect(chartColor("--color-border")).toBe("#232323");
    expect(chartColor("--color-green")).toBe("#22c55e");
  });

  it("falls back to a neutral grey for a token with no known fallback", () => {
    expect(chartColor("--color-totally-unmapped-token")).toBe("#a3a3a3");
  });
});
