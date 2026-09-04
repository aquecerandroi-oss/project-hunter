import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { logger } from "@/lib/logger";

describe("logger", () => {
  const originalEnv = process.env.NODE_ENV;

  beforeEach(() => {
    vi.spyOn(console, "log").mockImplementation(() => undefined);
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.stubEnv("NODE_ENV", originalEnv ?? "test");
  });

  it("writes a structured JSON line with level, msg, ts and context", () => {
    logger.info("user_signed_in", { userId: "u_1" });
    expect(console.log).toHaveBeenCalledTimes(1);
    const line = vi.mocked(console.log).mock.calls[0]?.[0] as string;
    const parsed = JSON.parse(line);
    expect(parsed).toMatchObject({ level: "info", msg: "user_signed_in", userId: "u_1" });
    expect(typeof parsed.ts).toBe("string");
  });

  it("routes warn to console.warn and error to console.error", () => {
    logger.warn("slow_response", { ms: 900 });
    logger.error("api_request_failed", { status: 500 });
    expect(console.warn).toHaveBeenCalledTimes(1);
    expect(console.error).toHaveBeenCalledTimes(1);
  });

  it("emits debug logs outside production", () => {
    vi.stubEnv("NODE_ENV", "development");
    logger.debug("cache_miss", {});
    expect(console.log).toHaveBeenCalledTimes(1);
  });

  it("no-ops debug in production", () => {
    vi.stubEnv("NODE_ENV", "production");
    logger.debug("cache_miss", {});
    expect(console.log).not.toHaveBeenCalled();
  });
});
