import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(cleanup);

import { AppearanceForm } from "@/components/settings/appearance-form";
import { isPriceFlashEnabled } from "@/hooks/usePriceFlash";

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-density");
});

describe("AppearanceForm: price flash has a real, production-reachable off switch (T1.5b Astra must-fix #5)", () => {
  it("shows the switch on by default and turns it off on click, persisting to localStorage", () => {
    render(<AppearanceForm />);

    const toggle = screen.getByRole("switch", { name: /Flash de preço/ });
    expect(toggle).toHaveAttribute("aria-checked", "true");
    expect(isPriceFlashEnabled()).toBe(true);

    fireEvent.click(toggle);

    expect(toggle).toHaveAttribute("aria-checked", "false");
    expect(isPriceFlashEnabled()).toBe(false);
  });

  it("reads an already-persisted 'off' setting on mount", () => {
    window.localStorage.setItem("hunter-price-flash-enabled", "off");
    render(<AppearanceForm />);

    expect(screen.getByRole("switch", { name: /Flash de preço/ })).toHaveAttribute("aria-checked", "false");
  });
});

describe("AppearanceForm: a blocked Web Storage must never crash this screen (NEW, Astra, T1.5b fix pass 2)", () => {
  it("still renders with the default density/flash settings when localStorage.getItem throws SecurityError", () => {
    const original = window.localStorage.getItem;
    window.localStorage.getItem = vi.fn(() => {
      throw new DOMException("blocked", "SecurityError");
    });

    try {
      expect(() => render(<AppearanceForm />)).not.toThrow();
      expect(screen.getByRole("radio", { name: "Confortável" })).toHaveAttribute("aria-checked", "true");
      expect(screen.getByRole("switch", { name: /Flash de preço/ })).toHaveAttribute("aria-checked", "true");
    } finally {
      window.localStorage.getItem = original;
    }
  });

  it("does not throw when choosing a density and localStorage.setItem throws SecurityError", () => {
    render(<AppearanceForm />);
    const original = window.localStorage.setItem;
    window.localStorage.setItem = vi.fn(() => {
      throw new DOMException("blocked", "SecurityError");
    });

    try {
      expect(() => fireEvent.click(screen.getByRole("radio", { name: "Compacta" }))).not.toThrow();
      // The choice still applies to this session's DOM even though it failed to persist.
      expect(screen.getByRole("radio", { name: "Compacta" })).toHaveAttribute("aria-checked", "true");
    } finally {
      window.localStorage.setItem = original;
    }
  });
});
