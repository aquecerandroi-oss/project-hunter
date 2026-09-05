import { act, renderHook } from "@testing-library/react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import { describe, expect, it, vi } from "vitest";

import { useArrowKeyRowSelection } from "@/hooks/useArrowKeyRowSelection";

function makeContainer(scrollTop = 0): HTMLElement {
  const el = document.createElement("div");
  el.scrollTop = scrollTop;
  return el;
}

function fakeKeyEvent(key: string, sameTarget: boolean, container: HTMLElement): ReactKeyboardEvent<HTMLElement> {
  const target = sameTarget ? container : document.createElement("button");
  return {
    key,
    target,
    currentTarget: container,
    preventDefault: vi.fn(),
  } as unknown as ReactKeyboardEvent<HTMLElement>;
}

describe("useArrowKeyRowSelection: ArrowDown/ArrowUp move, Enter opens (T1.5b)", () => {
  it("starts at row 0 on the first ArrowDown, moves within bounds", () => {
    const container = makeContainer();
    const { result } = renderHook(() =>
      useArrowKeyRowSelection({ rowCount: 3, rowHeight: 40, viewportHeight: 480, getScrollContainer: () => container, onOpen: vi.fn() }),
    );

    act(() => result.current.handleKeyDown(fakeKeyEvent("ArrowDown", true, container)));
    expect(result.current.selectedIndex).toBe(0);
  });

  it("calls onOpen with the selected index on Enter", () => {
    const container = makeContainer();
    const onOpen = vi.fn();
    const { result, rerender } = renderHook(
      (props: { rowCount: number }) =>
        useArrowKeyRowSelection({ rowCount: props.rowCount, rowHeight: 40, viewportHeight: 480, getScrollContainer: () => container, onOpen }),
      { initialProps: { rowCount: 3 } },
    );

    act(() => result.current.handleKeyDown(fakeKeyEvent("ArrowDown", true, container)));
    rerender({ rowCount: 3 });
    act(() => result.current.handleKeyDown(fakeKeyEvent("Enter", true, container)));

    expect(onOpen).toHaveBeenCalledWith(0);
  });
});

describe("useArrowKeyRowSelection: ignores keydowns bubbled from nested controls (T1.5b Astra must-fix #3)", () => {
  it("does not call onOpen for an Enter that bubbled from a nested button/link, even with a row already selected", () => {
    const container = makeContainer();
    const onOpen = vi.fn();
    const { result } = renderHook(() =>
      useArrowKeyRowSelection({ rowCount: 3, rowHeight: 40, viewportHeight: 480, getScrollContainer: () => container, onOpen }),
    );

    act(() => result.current.handleKeyDown(fakeKeyEvent("ArrowDown", true, container)));
    // Enter bubbling up from a nested element (a sort button, a row Link) --
    // `target !== currentTarget` -- must be ignored, not treated as "open
    // the keyboard-selected row".
    act(() => result.current.handleKeyDown(fakeKeyEvent("Enter", false, container)));

    expect(onOpen).not.toHaveBeenCalled();
  });

  it("does not move selection for an ArrowDown that bubbled from a nested control", () => {
    const container = makeContainer();
    const { result } = renderHook(() =>
      useArrowKeyRowSelection({ rowCount: 3, rowHeight: 40, viewportHeight: 480, getScrollContainer: () => container, onOpen: vi.fn() }),
    );

    act(() => result.current.handleKeyDown(fakeKeyEvent("ArrowDown", false, container)));

    expect(result.current.selectedIndex).toBe(-1);
  });
});

describe("useArrowKeyRowSelection: keeps the selected row clear of a sticky header (T1.5b Astra must-fix #4, H4 fix pass)", () => {
  it("scrolls to the row's own top when a sticky header is present (the header term cancels out on this edge)", () => {
    const container = makeContainer(50); // scrolled down enough that row 0 is already hidden above scrollTop
    const { result } = renderHook(() =>
      useArrowKeyRowSelection({
        rowCount: 5,
        rowHeight: 40,
        viewportHeight: 480,
        stickyHeaderHeight: 32,
        getScrollContainer: () => container,
        onOpen: vi.fn(),
      }),
    );

    // Row 0's real offset in the scrollable content is `32 + 0*40 = 32`
    // (the header occupies the first 32px); to sit its top exactly at the
    // bottom edge of the pinned header (screen position 32), `scrollTop`
    // must become `32 - 32 = 0` -- the two `stickyHeaderHeight` terms cancel
    // algebraically on this edge. The OLD (buggy) code computed `scrollTop =
    // rowTop - stickyHeaderHeight = 0 - 32 = -32`, an impossible negative
    // offset that encoded the bug rather than the real table geometry.
    act(() => result.current.handleKeyDown(fakeKeyEvent("ArrowDown", true, container)));

    expect(container.scrollTop).toBe(0);
  });

  it("without a sticky header (default 0), scrolls exactly to the row's own top", () => {
    const container = makeContainer(50);
    const { result } = renderHook(() =>
      useArrowKeyRowSelection({ rowCount: 5, rowHeight: 40, viewportHeight: 480, getScrollContainer: () => container, onOpen: vi.fn() }),
    );

    act(() => result.current.handleKeyDown(fakeKeyEvent("ArrowDown", true, container)));

    expect(container.scrollTop).toBe(0);
  });

  it("comfortable density (40px rows): scrolling to a row whose bottom would sit under the fold accounts for the header, leaving the row fully visible below it", () => {
    const container = makeContainer(0);
    const { result } = renderHook(() =>
      useArrowKeyRowSelection({
        rowCount: 20,
        rowHeight: 40,
        viewportHeight: 480,
        stickyHeaderHeight: 32,
        getScrollContainer: () => container,
        onOpen: vi.fn(),
      }),
    );

    // Row 11's real bottom is `32 (header) + 12*40 = 512`, which is past the
    // 480px viewport -- the OLD code compared `rowBottom = 12*40 = 480`
    // against `480` (never `> 480`, so it never scrolled at all), leaving
    // only `480 - (32 + 11*40) = 8px` of the row visible under the header.
    for (let i = 0; i <= 11; i++) {
      act(() => result.current.handleKeyDown(fakeKeyEvent("ArrowDown", true, container)));
    }

    expect(result.current.selectedIndex).toBe(11);
    expect(container.scrollTop).toBe(32); // realBottom(512) - viewportHeight(480)
  });

  it("compact density (32px rows): same accounting applies with a smaller row height", () => {
    const container = makeContainer(0);
    const { result } = renderHook(() =>
      useArrowKeyRowSelection({
        rowCount: 20,
        rowHeight: 32,
        viewportHeight: 480,
        stickyHeaderHeight: 32,
        getScrollContainer: () => container,
        onOpen: vi.fn(),
      }),
    );

    // Row 14's real bottom is `32 (header) + 15*32 = 512`, past the 480px
    // viewport by 32px -- before this fix the 15th compact row would have
    // been entirely below the viewport.
    for (let i = 0; i <= 14; i++) {
      act(() => result.current.handleKeyDown(fakeKeyEvent("ArrowDown", true, container)));
    }

    expect(result.current.selectedIndex).toBe(14);
    expect(container.scrollTop).toBe(32); // realBottom(512) - viewportHeight(480)
  });
});
