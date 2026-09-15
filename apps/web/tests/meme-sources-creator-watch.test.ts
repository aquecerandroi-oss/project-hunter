/**
 * T4.2h-b: the "Fontes" panel's creator-watch line -- the dev's own token
 * account read from the chain every 15 s, and the one number that says whether
 * the loop is fast enough. Its own file so
 * `tests/meme-sources-format.test.ts` stays inside the 350-line budget.
 *
 * The rule every case below defends: an **unmeasured** number is left out of
 * the sentence, never rendered as `0`. "0 s de venda vista ate a saida" is the
 * shape of a perfect loop; it must never be what a loop that measured nothing
 * looks like.
 */
import { describe, expect, it } from "vitest";

import { creatorWatchLine } from "@/components/meme/meme-sources-format";

import { sourcesPayload } from "./meme-sources-format.test";

// T4.2h-b: the creator watch -- the dev's own token account read from the chain
// every 15 s -- and the one number that says whether it is fast enough. The
// measured seen-sale -> exit latency was 149 s on 15/09 (the exit needed one
// photo to decide and another to price); the target is one photo, <= 30 s.
describe("creatorWatchLine: the creator watch's counters and the measured sale → exit latency (T4.2h-b)", () => {
  it("joins every reported field in Portuguese, never a raw key", () => {
    const line = creatorWatchLine(
      sourcesPayload({
        creator_watch_mints: 12,
        creator_watch_live_mints: 2,
        creator_watch_calls_60s: 4,
        creator_watch_drops_1h: 27,
        creator_watch_missing: 3,
        creator_watch_cycle_s: 0.42,
        creator_watch_sale_to_exit_s_p50: 15,
        creator_watch_sale_to_exit_s_p95: 28,
        creator_watch_sale_to_exit_n: 27,
      }),
    );
    expect(line).toBe(
      "12 criadores vigiados (2 com posição real) · 4 chamadas por minuto · 27 venda(s) do dev vista(s) na última hora · 3 sem conta de token (não medido) · ciclo da vigilância 0.4 s · venda vista → saída p50 (medido) 15 s · venda vista → saída p95 (medido) 28 s · 27 saída(s) medida(s)",
    );
  });

  it("shows a real 0 of unmeasured creators -- the declared blindness of this watch", () => {
    const line = creatorWatchLine(sourcesPayload({ creator_watch_mints: 5, creator_watch_missing: 0 }));
    expect(line).toBe("5 criadores vigiados · 0 sem conta de token (não medido)");
  });

  it("says nothing about a latency nobody measured yet, instead of 0 s", () => {
    const line = creatorWatchLine(sourcesPayload({ creator_watch_mints: 5, creator_watch_sale_to_exit_n: 0 }));
    expect(line).toBe("5 criadores vigiados · 0 saída(s) medida(s)");
    expect(line).not.toContain("p50");
  });

  it("renders a slow latency in whole minutes, so 149 s reads as the incident it was", () => {
    const line = creatorWatchLine(sourcesPayload({ creator_watch_sale_to_exit_s_p95: 149 }));
    expect(line).toBe("venda vista → saída p95 (medido) 2 min");
  });

  it("is null (never an empty line) on a worker that predates the watch", () => {
    expect(creatorWatchLine(sourcesPayload())).toBeNull();
  });
});

// T4.2g: the batch tape's own heartbeat (`activity_*`) -- the proof the 1-minute
// window is alive is `activity_live_1m > 0`; a real 0 next to `activity_dark_60s`
// says the route answered null for everyone and nothing was written as a zero.
