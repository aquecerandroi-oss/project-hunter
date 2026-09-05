"use client";

import { useState, type KeyboardEvent } from "react";

export interface UseArrowKeyRowSelectionOptions {
  rowCount: number;
  rowHeight: number;
  viewportHeight: number;
  /** Height of a `position: sticky` header inside the same scroll container, occluding that much of the top of `viewportHeight` (default 0). */
  stickyHeaderHeight?: number;
  getScrollContainer: () => HTMLElement | null;
  /** Called with the currently-selected index on Enter. */
  onOpen: (index: number) => void;
}

export interface UseArrowKeyRowSelectionResult {
  /** -1 means no keyboard selection yet -- the first ArrowDown starts it at row 0, never jumps straight to "open". */
  selectedIndex: number;
  handleKeyDown: (event: KeyboardEvent<HTMLElement>) => void;
  reset: () => void;
}

/**
 * Keyboard row navigation for a virtualized table (docs/DESIGN.md §3's
 * markets-table anchor, T1.5b joint decision #7/#9): ArrowUp/ArrowDown move
 * a single selected row, scrolling the (manually windowed) container just
 * enough to keep it visible, Enter opens it. Extracted out of
 * `components/markets/markets-table.tsx` so both files stay well under the
 * lint config's per-function line/statement budget and this logic is
 * independently unit-testable.
 */
export function useArrowKeyRowSelection({
  rowCount,
  rowHeight,
  viewportHeight,
  stickyHeaderHeight = 0,
  getScrollContainer,
  onOpen,
}: UseArrowKeyRowSelectionOptions): UseArrowKeyRowSelectionResult {
  const [selectedIndex, setSelectedIndex] = useState(-1);

  // The sticky `<thead>` occupies real space in the scrollable content (it
  // is the first `stickyHeaderHeight` pixels of it, then rows follow) even
  // though it stays pinned to the top of the viewport while scrolling -- a
  // row's actual offset from the top of the scrollable content is therefore
  // `stickyHeaderHeight + index * rowHeight`, never `index * rowHeight`
  // alone (H4, T1.5b fix pass). Using the bare `index * rowHeight` for the
  // BOTTOM edge undershot every scroll-into-view by exactly
  // `stickyHeaderHeight`, leaving the newly selected row partly hidden below
  // the fold in both densities. (The top-edge case happens to cancel the
  // header term back out algebraically -- `realTop - stickyHeaderHeight`
  // reduces to `index * rowHeight` -- which is why only the bottom edge was
  // visibly broken, even though both comparisons now use the same
  // `realTop`/`realBottom` for clarity.)
  function ensureVisible(index: number): void {
    const container = getScrollContainer();
    if (!container) return;
    const realTop = stickyHeaderHeight + index * rowHeight;
    const realBottom = realTop + rowHeight;
    if (realTop - stickyHeaderHeight < container.scrollTop) container.scrollTop = realTop - stickyHeaderHeight;
    else if (realBottom > container.scrollTop + viewportHeight) container.scrollTop = realBottom - viewportHeight;
  }

  function move(delta: 1 | -1): void {
    setSelectedIndex((prev) => {
      const next = Math.min(rowCount - 1, Math.max(0, prev + delta));
      ensureVisible(next);
      return next;
    });
  }

  function handleKeyDown(event: KeyboardEvent<HTMLElement>): void {
    // Only react to a keydown that landed directly on the grid container
    // itself (the element this handler is bound to), never one that bubbled
    // up from a nested focusable element -- a row's `<Link>`, a header sort
    // `<button>`, the search input. Without this guard, tabbing off the grid
    // onto any of those and pressing Enter also re-triggered `onOpen` for
    // whatever row the arrow keys had last selected, hijacking that
    // control's own native activation (T1.5b Astra must-fix #3).
    if (event.target !== event.currentTarget) return;
    if (rowCount === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      move(1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      move(-1);
    } else if (event.key === "Enter" && selectedIndex >= 0) {
      event.preventDefault();
      onOpen(selectedIndex);
    }
  }

  return { selectedIndex, handleKeyDown, reset: () => setSelectedIndex(-1) };
}
