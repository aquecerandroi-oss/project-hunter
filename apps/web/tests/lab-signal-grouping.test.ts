import { describe, expect, it } from "vitest";

import { dedupeByIdentity, groupSignalsByIdentity, hasMultipleVersions } from "@/components/lab/lab-signal-grouping";
import { exampleNearMissSignal, exampleSiblingSignals } from "@/tests/fixtures/lab-pagination";
import { makeSignal } from "@/tests/fixtures/lab";

describe("groupSignalsByIdentity: sibling-version signals collapse into one row (brief T3.38, Everton's screenshot)", () => {
  it("three identical signals (same identity_key, three different versions) become one group with three members", () => {
    const groups = groupSignalsByIdentity(exampleSiblingSignals());
    expect(groups).toHaveLength(1);
    expect(groups[0]?.members).toHaveLength(3);
    expect(groups[0]?.versionIds).toEqual(["v4-id", "v2-id", "v3-id"]);
    // `primary` is the first-loaded member (measured order: v4, v2, v3).
    expect(groups[0]?.primary.signal_id).toBe("sig-v4");
  });

  it("a near-miss (different exit -> different identity_key) never joins the group -- two groups", () => {
    const rows = [...exampleSiblingSignals(), exampleNearMissSignal()];
    const groups = groupSignalsByIdentity(rows);
    expect(groups).toHaveLength(2);
    expect(groups[0]?.members).toHaveLength(3);
    expect(groups[1]?.members).toHaveLength(1);
    expect(groups[1]?.primary.signal_id).toBe("sig-v5-near-miss");
  });

  it("a single version selected changes nothing -- two same-version rows sharing an identity_key never merge (never drops a real row)", () => {
    // Same identity_key, but only one strategy_version_id in the loaded page
    // (mirrors filtering the signals list down to one version) -- `versionIds`
    // never exceeds 1, so nothing merges visually; both rows keep showing.
    const rows = [
      makeSignal({ signal_id: "a", identity_key: "same-key" }),
      makeSignal({ signal_id: "b", identity_key: "same-key" }),
    ];
    const groups = groupSignalsByIdentity(rows);
    expect(groups).toHaveLength(2);
    expect(groups.map((g) => g.primary.signal_id)).toEqual(["a", "b"]);
  });

  it("rows missing identity_key never group by accident -- each falls back to its own signal_id", () => {
    const rows = [
      makeSignal({ signal_id: "a", identity_key: "", strategy_version_id: "v1" }),
      makeSignal({ signal_id: "b", identity_key: "", strategy_version_id: "v2" }),
    ];
    const groups = groupSignalsByIdentity(rows);
    expect(groups).toHaveLength(2);
  });

  it("a merged group sits at its first member's position; a later repeat of the same key is never re-emitted", () => {
    const rows = [
      makeSignal({ signal_id: "first", identity_key: "k1", strategy_version_id: "v1" }),
      makeSignal({ signal_id: "second", identity_key: "k2", strategy_version_id: "v1" }),
      makeSignal({ signal_id: "third-repeats-k1", identity_key: "k1", strategy_version_id: "v3" }),
    ];
    const groups = groupSignalsByIdentity(rows);
    // k1 spans two versions (v1, v3) -> merges at position 0; k2 is a
    // single-version singleton at position 1 -- never three groups, never
    // reordered.
    expect(groups).toHaveLength(2);
    expect(groups[0]?.key).toBe("idk:k1");
    expect(groups[0]?.members.map((m) => m.signal_id)).toEqual(["first", "third-repeats-k1"]);
    expect(groups[1]?.primary.signal_id).toBe("second");
  });
});

describe("hasMultipleVersions", () => {
  it("is true once the loaded page spans more than one strategy_version_id", () => {
    expect(hasMultipleVersions(exampleSiblingSignals())).toBe(true);
  });

  it("is false for a single-version page (T3.38: 'com uma única versão selecionada nada muda')", () => {
    expect(hasMultipleVersions([makeSignal({ signal_id: "a" }), makeSignal({ signal_id: "b" })])).toBe(false);
  });
});

describe("dedupeByIdentity: the totals card's own 'first occurrence' rule (brief T3.38 item 3)", () => {
  it("keeps exactly one row per identity_key, the first loaded", () => {
    const unique = dedupeByIdentity(exampleSiblingSignals());
    expect(unique).toHaveLength(1);
    expect(unique[0]?.signal_id).toBe("sig-v4");
  });

  it("keeps every row when every identity_key is distinct", () => {
    const rows = [exampleNearMissSignal({ signal_id: "x" }), exampleNearMissSignal({ signal_id: "y", identity_key: "other-key" })];
    expect(dedupeByIdentity(rows)).toHaveLength(2);
  });
});
