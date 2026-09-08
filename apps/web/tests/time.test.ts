import { describe, expect, it, vi } from "vitest";

import {
  BRASILIA_LABEL,
  BRASILIA_TIME_ZONE,
  formatBrasiliaDate,
  formatBrasiliaLong,
  formatBrasiliaShort,
  formatBrasiliaTick,
  formatBrasiliaWithUtcTooltip,
} from "@/lib/time";

// Brazil has observed no DST since 2019 (Decreto 9.772/2019 discontinued the
// last DST cycle that year), so `America/Sao_Paulo` is a flat UTC-03:00 for
// every instant used below -- there is no "summer" fixture to special-case.

describe("BRASILIA_TIME_ZONE / BRASILIA_LABEL: the one place the org's display timezone is defined (brief T3.22)", () => {
  it("is the IANA zone for São Paulo", () => {
    expect(BRASILIA_TIME_ZONE).toBe("America/Sao_Paulo");
  });

  it("is labeled in plain Portuguese, never the IANA name or 'BRT'", () => {
    expect(BRASILIA_LABEL).toBe("Brasília");
  });
});

describe("formatBrasiliaShort: 'DD/MM HH:mm', always Brasília regardless of the runtime's own timezone", () => {
  it("converts a UTC instant to its Brasília wall-clock time (offset -03:00)", () => {
    expect(formatBrasiliaShort("2026-09-08T05:05:00.000Z")).toBe("08/09 02:05");
  });

  it("never calls Date#getTimezoneOffset -- Intl's explicit timeZone option does the conversion, not the runtime's own zone", () => {
    const spy = vi.spyOn(Date.prototype, "getTimezoneOffset");
    formatBrasiliaShort("2026-09-08T05:05:00.000Z");
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });

  it("crosses midnight forward: 23:30 UTC is 20:30 Brasília the same day", () => {
    expect(formatBrasiliaShort("2026-06-15T23:30:00.000Z")).toBe("15/06 20:30");
  });

  it("crosses midnight backward: 02:30 UTC is 23:30 Brasília the PREVIOUS day", () => {
    expect(formatBrasiliaShort("2026-06-15T02:30:00.000Z")).toBe("14/06 23:30");
  });

  it("returns null (never a garbage string) for an invalid timestamp", () => {
    expect(formatBrasiliaShort("not-a-date")).toBeNull();
  });
});

describe("formatBrasiliaLong: 'DD/MM/AAAA HH:mm:ss'", () => {
  it("renders the full Brasília date and time", () => {
    expect(formatBrasiliaLong("2026-09-08T05:05:05.000Z")).toBe("08/09/2026 02:05:05");
  });

  it("carries the year across a backward midnight crossing into the previous year", () => {
    expect(formatBrasiliaLong("2026-01-01T02:30:00.000Z")).toBe("31/12/2025 23:30:00");
  });

  it("returns null for an invalid timestamp", () => {
    expect(formatBrasiliaLong("not-a-date")).toBeNull();
  });
});

describe("formatBrasiliaDate: 'DD/MM/AAAA', day only", () => {
  it("renders the Brasília calendar day", () => {
    expect(formatBrasiliaDate("2026-09-08T05:05:05.000Z")).toBe("08/09/2026");
  });

  it("returns null for an invalid timestamp", () => {
    expect(formatBrasiliaDate("not-a-date")).toBeNull();
  });
});

describe("formatBrasiliaWithUtcTooltip: chart crosshair label, both halves visible (brief item 6)", () => {
  it("shows Brasília first, then UTC, both derived from the same instant", () => {
    expect(formatBrasiliaWithUtcTooltip("2026-09-08T05:05:05.000Z")).toBe("08/09 02:05:05 Brasília · 05:05:05 UTC");
  });

  it("returns an honest placeholder for an invalid timestamp", () => {
    expect(formatBrasiliaWithUtcTooltip("not-a-date")).toBe("--");
  });
});

describe("formatBrasiliaTick: chart axis ticks keyed by lightweight-charts' TickMarkType", () => {
  const epochSeconds = Math.floor(new Date("2026-09-08T05:05:05.000Z").getTime() / 1000);

  it("formats a Year tick (0)", () => {
    expect(formatBrasiliaTick(epochSeconds, 0)).toBe("2026");
  });

  it("formats a Month tick (1) in Brasília, pt-BR abbreviation", () => {
    expect(formatBrasiliaTick(epochSeconds, 1)).toBe("set.");
  });

  it("formats a DayOfMonth tick (2) in Brasília -- 08, not 09 (UTC would still read the 8th here, unlike the midnight-crossing case above)", () => {
    expect(formatBrasiliaTick(epochSeconds, 2)).toBe("08");
  });

  it("formats a Time tick (3) without seconds, in Brasília", () => {
    expect(formatBrasiliaTick(epochSeconds, 3)).toBe("02:05");
  });

  it("formats a TimeWithSeconds tick (4) in Brasília", () => {
    expect(formatBrasiliaTick(epochSeconds, 4)).toBe("02:05:05");
  });
});
