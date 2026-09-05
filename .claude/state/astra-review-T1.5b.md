The direction is sound, but I would not sign off yet. I reviewed the diff and untracked `apps/web` files, with **“Decisão conjunta de design” taking precedence**. No files were modified.

**Must-fix**

1. **“Sem verificação” remains unreachable for missing configuration.** [topbar.tsx:31](C:/dev/project-hunter/apps/web/components/layout/topbar.tsx:31) handles `null`, but the real `ready()` catches missing `API_URL` and returns both dependencies as false. **Scenario:** an unconfigured check displays “Sistema indisponível,” falsely reporting an outage. I reproduced this. Preserve the unchecked state through the actual loader; the new tests bypass it with mocks. Joint decision **#5**.

2. **The palette can open a market from the previous query.** [command-palette.tsx:131](C:/dev/project-hunter/apps/web/components/layout/command-palette.tsx:131) retains actionable results while another query loads. **Scenario:** search BTC, replace it with ETH, press Enter immediately—BTCUSDT opens. Reproduced. Invalidate selection/results when the query changes and allow navigation only for matching completed results. Also, the initial debounce currently displays “Nenhum mercado encontrado” before searching. Decisions **#7–8**.

3. **Table keyboard handling overrides focused controls.** [useArrowKeyRowSelection.ts:56](C:/dev/project-hunter/apps/web/hooks/useArrowKeyRowSelection.ts:56) handles bubbled events from links and header buttons. **Scenario:** select row A with arrows, Tab to a different market or a sort button, then press Enter—the selected row opens instead. Reproduced with a nested button. Restrict row navigation to the grid’s own focus, preserving native control activation. Decision **#9**.

4. **Keyboard selection is not reliably visible during virtualization.** [useArrowKeyRowSelection.ts:42](C:/dev/project-hunter/apps/web/hooks/useArrowKeyRowSelection.ts:42) ignores the 32px sticky header. **Scenario:** in comfortable density, selecting row 12 leaves scrolling at zero although that row ends at 512px inside a 480px viewport. Manual scrolling can also unmount the row referenced by `aria-activedescendant`. Account for the header and keep the active descendant mounted or deliberately update selection. Decisions **#6/#9**.

5. **The flash control is unavailable in production, and rapid ticks break its reset.** The only UI calling `setPriceFlashEnabled` is [motion-showcase.tsx:32](C:/dev/project-hunter/apps/web/components/design/motion-showcase.tsx:32), under the development preview. **Scenario:** a user distracted by flashes cannot disable them in Markets or Settings. Separately, [usePriceFlash.ts:74](C:/dev/project-hunter/apps/web/hooks/usePriceFlash.ts:74) cancels the reset timeout on the next tick, then exits through the rate limiter. Two updates 50ms apart left direction `"up"` after 450ms in my check; subsequent same-direction updates may not restart the CSS animation. Expose the persisted setting and separate animation cleanup from incoming ticks. Decision **#4**.

6. **Accessibility checks miss actual backgrounds and focus states.** The new `fg-subtle` colors measure **4.27:1 on light overlay**, and **3.47:1 dark / 4.33:1 light on the palette’s selected gold background**. That affects exchange identification in [command-palette.tsx:198](C:/dev/project-hunter/apps/web/components/layout/command-palette.tsx:198). Its search input also removes the outline without providing a focus indicator. **Scenario:** a low-vision keyboard user cannot clearly distinguish the selected exchange or locate input focus. Test the composed backgrounds and add visible gold focus treatment. Decision **#9**.

7. **The added content needs responsive layout treatment.** [topbar.tsx:107](C:/dev/project-hunter/apps/web/components/layout/topbar.tsx:107) adds a full search button and shortcut to an already crowded, fixed-height, nonwrapping header. [recent-trades.tsx:44](C:/dev/project-hunter/apps/web/components/markets/recent-trades.tsx:44) adds an unshrinkable dual-clock timestamp alongside price and quantity. **Scenario:** on a narrow phone, shell controls overflow or trade values compete for insufficient width. Add responsive priority rules and a wrapping/two-line trade layout while keeping timestamps accessible. This is a source-level finding; browser measurements remain necessary. Decision **#9**.

**Nice-to-have / remaining alignment gaps**

- Finish the five-size typography scale: actual tables remain 13px, detail price remains 24px, and new labels introduce 10/11px.
- Make “System → Workers” in the empty state a real link; give palette failures an explicit retry action.
- Address existing gaps explicitly: missing 24h change still renders green, and quality badges lack the requested per-component explanation. These predate this patch but remain inconsistent with the target design.

**Agreements**

- Markets-first dashboard hierarchy and removal of financial placeholders improve usefulness.
- Green/red candles, deferred sparklines, and snapshot labels respect what the data supports.
- API-backed search with exchange labels, explicit volume units, and shared density constants are the right choices.

Validation used read-only inspection and in-memory React/Node reproductions. I did not run the full checks, capture browser screenshots, or perform the required 30-second live-data calm test; visual acceptance remains unverified.