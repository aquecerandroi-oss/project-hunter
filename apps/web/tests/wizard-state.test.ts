import { describe, expect, it } from "vitest";

import {
  DEFAULT_DATA,
  STEP_COUNT,
  canAdvance,
  createInitialState,
  goBack,
  goNext,
  setOrgCreated,
  updateData,
  validateStep,
  type WizardState,
} from "@/components/onboarding/wizard-state";

function withData(state: WizardState, patch: Partial<typeof DEFAULT_DATA>): WizardState {
  return updateData(state, patch);
}

describe("wizard-state: initial state", () => {
  it("starts at step 1 with no org", () => {
    const state = createInitialState();
    expect(state.step).toBe(1);
    expect(state.minStep).toBe(1);
    expect(state.org).toBeNull();
    expect(state.data).toEqual(DEFAULT_DATA);
  });

  it("resumes at step 2 when an org identity is provided (?org=<slug>)", () => {
    const state = createInitialState({ orgSlug: "acme", orgId: "org-1", workspaceId: "ws-1" });
    expect(state.step).toBe(2);
    expect(state.minStep).toBe(2);
    expect(state.org).toEqual({ orgSlug: "acme", orgId: "org-1", workspaceId: "ws-1" });
  });
});

describe("wizard-state: step order", () => {
  it("has 6 steps", () => {
    expect(STEP_COUNT).toBe(6);
  });

  it("advances step by step when each step is valid", () => {
    let state = withData(createInitialState(), { orgName: "Acme" });
    state = setOrgCreated(state, { orgSlug: "acme", orgId: "1", workspaceId: "2" });
    expect(state.step).toBe(2);

    state = goNext(state); // objective (default "explore" is valid)
    expect(state.step).toBe(3);

    state = goNext(state); // capital (default "10000" is valid)
    expect(state.step).toBe(4);

    state = goNext(state); // risk preset (default "balanced" is valid)
    expect(state.step).toBe(5);

    state = goNext(state); // exchanges (empty array is valid)
    expect(state.step).toBe(6);

    state = goNext(state); // summary is the last step
    expect(state.step).toBe(6);
  });

  it("does not advance past the last step", () => {
    const state = createInitialState({ orgSlug: "acme", orgId: "1", workspaceId: "2" });
    let s = state;
    for (let i = 0; i < 10; i++) s = goNext(s);
    expect(s.step).toBe(STEP_COUNT);
  });

  it("goBack steps back one at a time, floored at minStep", () => {
    const state = createInitialState({ orgSlug: "acme", orgId: "1", workspaceId: "2" });
    let s = goNext(goNext(state)); // step 4
    expect(s.step).toBe(4);
    s = goBack(s);
    expect(s.step).toBe(3);
    s = goBack(goBack(goBack(s)));
    expect(s.step).toBe(2); // floored at minStep=2, never reaches step 1
  });

  it("raises minStep to 2 once the organization is created, even for a fresh (non-resumed) wizard", () => {
    // Step 1 is a real mutation (creates a row) -- once it has run, going
    // back to it and pressing "next" again must not silently create a
    // second, orphaned organization. See setOrgCreated's own docstring.
    let s = withData(createInitialState(), { orgName: "Acme" });
    expect(s.minStep).toBe(1);
    s = setOrgCreated(s, { orgSlug: "acme", orgId: "1", workspaceId: "2" }); // step 2
    expect(s.minStep).toBe(2);
    s = goBack(s);
    expect(s.step).toBe(2); // floored at the new minStep, never reaches step 1 again
  });
});

describe("wizard-state: validation per step", () => {
  it("step 1 rejects an empty organization name", () => {
    const state = createInitialState();
    expect(validateStep(1, state.data)).not.toHaveLength(0);
    expect(canAdvance(state)).toBe(false);
  });

  it("step 1 accepts a non-empty organization name", () => {
    const state = withData(createInitialState(), { orgName: "Acme" });
    expect(validateStep(1, state.data)).toHaveLength(0);
  });

  it("step 3 rejects capital below the 1000 floor", () => {
    const state = createInitialState({ orgSlug: "a", orgId: "1", workspaceId: "2" });
    const withCapital = withData(goNext(state), { virtualCapital: "500" });
    expect(validateStep(3, withCapital.data).length).toBeGreaterThan(0);
  });

  it("step 3 rejects a non-numeric capital string", () => {
    const state = createInitialState({ orgSlug: "a", orgId: "1", workspaceId: "2" });
    const withCapital = withData(goNext(state), { virtualCapital: "abc" });
    expect(validateStep(3, withCapital.data).length).toBeGreaterThan(0);
  });

  it("step 3 accepts the 1000 floor exactly and above", () => {
    const state = createInitialState({ orgSlug: "a", orgId: "1", workspaceId: "2" });
    expect(validateStep(3, { ...state.data, virtualCapital: "1000" })).toHaveLength(0);
    expect(validateStep(3, { ...state.data, virtualCapital: "25000" })).toHaveLength(0);
  });

  it("step 5 accepts zero monitored exchanges", () => {
    const state = createInitialState({ orgSlug: "a", orgId: "1", workspaceId: "2" });
    expect(validateStep(5, { ...state.data, monitoredExchanges: [] })).toHaveLength(0);
  });

  it("step 5 rejects an exchange code outside the known M0 set", () => {
    const state = createInitialState({ orgSlug: "a", orgId: "1", workspaceId: "2" });
    expect(validateStep(5, { ...state.data, monitoredExchanges: ["kraken"] }).length).toBeGreaterThan(0);
  });

  it("a wizard cannot advance past an invalid step even after later steps are pre-filled", () => {
    let s = createInitialState({ orgSlug: "a", orgId: "1", workspaceId: "2" }); // step 2
    s = withData(s, { objective: "explore" });
    s = goNext(s); // step 3
    s = withData(s, { virtualCapital: "not-a-number" });
    expect(canAdvance(s)).toBe(false);
    expect(goNext(s).step).toBe(3);
  });
});
