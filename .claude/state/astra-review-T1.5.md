**T1.5 is not ready for acceptance.** Reviewed the uncommitted diff and untracked `apps/web` files, including comparison with the current API contracts. No files modified. This was a static review; I did not run tests or a build.

**Must-fix — with failure scenarios**

1. **[P1] Successful API responses crash System and market detail.** Three contract mismatches:
   - `/system/workers` returns an array; the web expects `{ workers, exchanges }`, then accesses `workers.length` on `undefined`.
   - `/candles` returns an array; the detail loader reads `.items`, passing `undefined` into `CandlesChart`.
   - Book levels are `{ price, qty }` objects; `withCumulative` destructures them as tuples, throwing on a populated book.

   Align with T1.4 and consume generated types as T1.5 requires. Add tests using actual API response shapes. See [workers adapter](C:/dev/project-hunter/apps/web/lib/api/system.ts:14), [detail loader](C:/dev/project-hunter/apps/web/app/(app)/[orgSlug]/markets/[exchange]/[symbol]/page.tsx:30), [book renderer](C:/dev/project-hunter/apps/web/components/markets/order-book.tsx:16).

2. **[P1] Disconnecting never changes an `OK` market to stale.** `QualityBadge` only advances age when its initial quality is already `stale`; realtime patches never update quality or component timestamps. Load healthy data, disconnect, wait 15 seconds: the badge remains green indefinitely. Conversely, initially unavailable/degraded rows never recover. Compute freshness from required components as time advances and refresh authoritative quality/gap state. [quality-badge.tsx](C:/dev/project-hunter/apps/web/components/markets/quality-badge.tsx:24), [markets-table.tsx](C:/dev/project-hunter/apps/web/components/markets/markets-table.tsx:62).

3. **[P1] Most market data freezes after initial load.** Detail realtime updates only price/bid/ask; candles, book, trades, mark, OI and funding remain initial props. List spread, volume, percentage change and summary counts also freeze. Leave a detail open during active trading: the headline moves while book/trades/chart silently stop. Add bounded refresh or appropriate realtime updates, with visible freshness for each displayed snapshot. [market-detail-view.tsx](C:/dev/project-hunter/apps/web/components/markets/market-detail-view.tsx:23), [markets-table.tsx](C:/dev/project-hunter/apps/web/components/markets/markets-table.tsx:62).

4. **[P1] Fetch failures are misrepresented as empty data.** A workers endpoint failure becomes “Nenhum worker registrado”; dashboard market-status failure invents “0” monitored markets and says the feature arrives in M1; the topbar hides its widget. A running deployment with a failed status endpoint therefore looks unconfigured. Render an explicit unavailable/error state with retry, reserving empty wording for successful empty responses. [System fallback](C:/dev/project-hunter/apps/web/app/(app)/[orgSlug]/system/page.tsx:45), [dashboard fallback](C:/dev/project-hunter/apps/web/app/(app)/[orgSlug]/dashboard/page.tsx:56), [topbar](C:/dev/project-hunter/apps/web/components/layout/topbar.tsx:87).

5. **[P1] Operational health remains falsely healthy after updates stop.** Workers render fixed `alive`/age values; `revalidate = 15` does not refresh an already-open browser page. Live Status ignores browser connection status and keeps its last green `CONNECTED` state after worker/network loss. Its headline monitored total also never changes with realtime exchange counts. Refresh heartbeats, distinguish last-reported connection state from current observation freshness, and update totals consistently. [workers-table.tsx](C:/dev/project-hunter/apps/web/components/system/workers-table.tsx:60), [live-status.tsx](C:/dev/project-hunter/apps/web/components/system/live-status.tsx:60).

6. **[P2] `degraded` falsely asserts a gap.** Missing book or mark with no ingestion gap still renders “gap”. A stale component can also display “atrasado 0s” because age uses the freshest aggregate update. Use accurate degraded wording and the relevant component age. [quality-badge.tsx](C:/dev/project-hunter/apps/web/components/markets/quality-badge.tsx:33).

7. **[P2] Search can hide matching rows after scrolling.** Scroll deep into 200 rows, then search for one symbol: `startIndex` retains the old offset, producing an empty slice and oversized spacer despite a match. Reset/clamp scroll and virtualization bounds when filtering changes. [markets-table.tsx](C:/dev/project-hunter/apps/web/components/markets/markets-table.tsx:83).

8. **[P2] Chart errors and theme changes are not handled visibly.** Initialization failures only log, leaving a blank chart area. Switching dark to light retains the initial canvas colors, undermining the required light theme. Show a chart error state and reapply token colors on theme changes; remove hardcoded hex fallbacks. [candles-chart.tsx](C:/dev/project-hunter/apps/web/components/markets/candles-chart.tsx:46).

**Nice-to-have**

- Fix descending sorts putting nulls first; sort against displayed live values. [markets-table.tsx](C:/dev/project-hunter/apps/web/components/markets/markets-table.tsx:49).
- Support `next_cursor` or disclose the 200-row cap; configured larger universes are silently truncated.
- Add `aria-sort`, the specified 300ms price background flash, and right alignment for worker numeric columns.
- Expose WS state and gaps in the compact topbar’s accessible text; currently the connection indication is color-only.

**Agreements**

- Real API adapters and realtime channels replace placeholders; I found no production fixture prices or invented market rows.
- Raw price strings preserve precision, and missing prices render `--`.
- Market fetch errors have a working retry action; genuine empty book/trade states have clear text.
- Table density, monospace numbers, semantic bid/ask colors and most token usage follow DESIGN.md.
- Independent age ticking and derivative component ages are good foundations. Existing tests verify static rendering, but miss the contract mismatches and the required healthy → disconnected → stale scenario.