# A4.0g — evidence ledger

Research date: 2026-09-12. All access times below are Brasília (BRT, UTC−03).
Role: documentation-writer. Outputs: `docs/plans/T4-CANTOS.md`, appended M-P rows in
`obsidian/00-INBOX/Hipoteses-do-plantao.md`, and this ledger. No login, social interaction,
wallet connection, credential generation, transaction, code change, or commit.

The task brief authorizes this documentation work. TDD for production code does not apply;
the existing Obsidian linter was run before editing, then rerun after the append.
The existing hypothesis rows are preserved, including H-P27/H-P28 revisions.
`docs/PUMPFUN.md` was absent when searched; this is not proof that T4.0c is canceled.
Other workers own the API, program, feature and terminal inventories.

## Evidence classification

- Web reader: page content can be indexed/cached; consultation time is not freshness proof.
- Direct GET: local anonymous HTTP fetch; response time and status recorded when available.
- Static JS: product labels/code only, no proof of enabled UI, backend availability or public API.
- Announcements: distinguish publication time from deployment time.
- Inference/proposal: no measured trading performance or causal result.

## Opened sources

| ID | URL | Access BRT | Result and bounded use |
| --- | --- | --- | --- |
| S01 | https://pump.fun/docs/fees | 02:39 | Web content; updated 2026-05-20. Current published fee bands, canonical/non-canonical distinction, USDC start date and mobile caveat |
| S02 | https://medium.com/@pumpdotfun_/pump-fun-github-creator-fee-claiming-guide-d6f04af1acf6 | 02:40–02:41 | Official blog, dated 2026-02-12; useful for fee recipients/claiming; editing-authority description is older than S04/S05 |
| S03 | https://raw.githubusercontent.com/pump-fun/pump-public-docs/main/docs/instructions/COLLECT_CREATOR_FEE.md | 02:43–02:44 | Official raw doc: separate vaults and permissionless collection to the defined recipient; not evidence of creator intent |
| S04 | https://raw.githubusercontent.com/pump-fun/pump-public-docs/main/docs/instructions/CREATOR_FEE_SHARING.md | 02:43–02:44 | Official raw doc: one final update and admin revocation; no calls executed |
| S05 | https://t.me/s/pump_tech_updates | 02:40–02:43 | Official channel linked by pump.fun. Direct HTML used at 02:43 for post timestamps; publication, not chain activation |
| S06 | https://pump.fun/board | 02:41 | Web redirects to https://pump.fun/explore; tab labels observed, ranking formula absent |
| S07 | https://pump.fun/ | 02:40 | Navigation shell; no usable homepage ranking contract |
| S08 | https://intercom.help/pumpfun-web/en/articles/11638371-how-to-get-rtmp-key-mobile | 02:40 | Official tutorial dated 2025-06-22; documentation only, no RTMP key obtained |
| S09 | https://intercom.help/pumpfun-web/en/articles/11399886-livestream-moderation-policy | 02:43 | Official policy dated 2025-05-18 |
| S10 | https://pump.fun/docs/livestream-moderation-policy | 02:39–02:40 | Official web policy; archival availability not guaranteed |
| S11 | https://pump.fun/live | 02:42 | Public listing opened through site's Live link; no audience/conversion measurement |
| S12 | https://pump.fun/docs/dmca-policy | 02:43 | Recognizes comments as removable site content; no comment API contract |
| S13 | https://terminal.pump.fun/assets/index-DKS5eDgr.js | 02:42:47; 02:43:15 | Direct GET 200, 5,199,858 decoded characters; targeted snippets only: tracker, account actions, feed launch setting, internal route prefix |
| S14 | https://terminal.pump.fun/assets/index-Choz2jFk.js | 02:43:42; 02:43:56 | Direct GET 200, 3,175 decoded characters; tracker widget, filters, floating/docked presentation |
| S15 | https://threadreaderapp.com/user/Pumpfun | 02:41–02:42 | Third-party mirror of official account: Ascend 2025-09-02, DMs 2025-03-13, GO Jun 4 without visible year |
| S16 | https://blockworks.com/news/pumpdotfun-fee-model | 02:41 | Secondary chronology, published 2025-09-03 and refers to announcement the previous day; not current fee authority |
| S17 | https://pump.fun/docs/tokenized-agent-disclaimer | 02:39–02:40 failed; 02:41:44 / 02:42:10 direct | Web 403. Direct GET 200; initial stdout encoding failed, rerun with UTF-8 read body successfully. No editorial date visible |
| S18 | https://pump.fun/docs/go-fun-terms | 02:40 | Web body opened, updated 2026-05-13. Date of terms is not launch date |
| S19 | https://pump.fun/docs/charitycoins | 02:39–02:40 failed; 02:41:45 / 02:42 / 02:42:50 direct | Web 403. Direct GET 200; UTF-8 rerun read body and later date check confirmed 2026-04-27 |
| S20 | https://intercom.help/pumpfun-web/en/articles/11519827-coin-isn-t-showing-when-i-search-on-the-mobile-app | 02:40–02:41 | Official help dated 2026-02-06; origin label may persist after first buy |
| S21 | https://docs.padre.gg/ | 02:41; direct 02:41:46 | Web 403; direct request ended at https://trade.padre.gg/ with HTTP 200 and title only. Search index describes features, but those were not adopted as current verified functionality |
| S22 | https://apps.apple.com/us/app/pump-fun/id6717572591 | 02:44 | Opened as https://apps.apple.com/us/app/pump-fun-speculate-on-trends/id6717572591; app description/version history, not authenticated app audit |
| S24 | https://medium.com/@pumpdotfun_ | 02:39–02:40 | Blog index linked by pump.fun; no quantitative livestream/volume estimate found in consulted official material |
| S24b | https://docs.bitquery.io/docs/mcp/trading/examples/pumpfun-launch-pulse/ | 02:41 | Supplier's 2026-04-23 example, 36 h. Query asks distinct new tokens that traded; not a validated all-creations seasonal dataset |
| S25 | https://frontend-api-v3.pump.fun/mayhem/overview | 02:42:47.299 | Direct anonymous GET 200, response 279 decoded characters; projection below |
| S26 | https://pump.fun/mayhem | 02:40 | Web HTML exposes 24h/7d labels, screener statuses and sort controls; no full numerical hourly series |

S23 in the main map points to this ledger's failure section. It is not a positive external source.

## Additional opens and failed access

| URL | Access BRT | Outcome |
| --- | --- | --- |
| https://pump.fun/docs | 02:39 | Reader could not open (non-retryable safety/fetch error); no content adopted |
| https://intercom.help/pumpfun-web/en/ | 02:39 | Opened; traversed mobile and fee collections |
| https://intercom.help/pumpfun-web/en/collections/18327741-mobile-app | 02:39–02:40 | Opened; source of S08/S20 links |
| https://intercom.help/pumpfun-web/en/collections/12247592-tokenomics-fees | 02:39–02:40 | Opened; no KOTH contract |
| https://pump.fun/advanced | 02:40 | Reader reports redirect failure toward trade.padre.gg; no functioning authenticated Terminal |
| https://pump.fun/mayhem/overview | 02:39 failed; direct 02:41:46.857 | Reader failed; local GET 200 returned site navigation only. Not the API host |
| https://trade.padre.gg | 02:41 | Reader 403; local docs redirect gave title only |
| https://docs.padre.gg/llms.txt | 02:41 | Reader 403 |
| https://docs.padre.gg/app-guide/trenches | 02:42 | Reader 403 |
| https://pump.fun/livestreams | 02:41 | Reader could not open; canonical Live link /live did open |
| https://pump.fun/docs/livestreaming | 02:42 | Reader error; no content |
| https://pump.fun/docs/creator-fees | 02:42 | Reader could not open; used official blog/raw docs instead |
| https://pump.fun/docs/king-of-the-hill | 02:42 | Reader could not open; no ranking/duration threshold adopted |
| https://pump.fun/2vYwrQ6UJVrzprqeUZjMeqB6PePMAFvrVC5j134Gpump | 02:43 | Reader cache miss; no live chat measurement obtained |
| https://pump.fun/go | 02:44 | Reader 403; terms accessible, GO feed not audited |
| https://cryptoprocent.com/king-of-the-hill/ | 02:44 | Reader cache miss; search excerpt not adopted as official ranking rules |
| https://apps.apple.com/app/apple-store/id6717572591?ct=Buy+My+Bags&mt=8&pt=127479163 | 02:44 | Reader cache miss; public country-specific S22 opened |
| https://t.me/pump_tech_updates/38 | 02:42 | Embed shell; actual text/time read through S05 |
| https://t.me/pump_tech_updates/39 | 02:42 | Embed shell; actual text/time read through S05 |
| https://github.com/pump-fun/pump-public-docs/blob/main/README.md | 02:41–02:42 | Opened current README; sharing section not present there, so used dedicated raw instruction documents |
| https://terminalreview.com/ | 02:42 | Opened independent affiliate review; not used to prove current feature behavior or official X account-selection policy |
| https://terminal.pump.fun/assets/TrackerFilter-PpFMiJP6.js | 02:44:12 | Direct GET 200, 4,041 decoded characters; filter component does not establish default tracked-account list |

The original X announcement linked by S16 returned a reader error at 02:42; its text and exact
target were not recovered. A direct reread of S16 at 02:55:03 to retrieve that link returned
HTTP 403. The accessible web-reader article and S15 support the limited historical attribution;
no login attempted.
Searches for KOTH, X Feed selection and livestream/volume mainly returned unofficial marketing
or irrelevant pages. No unsupported threshold, correlation coefficient, traffic guarantee,
universal API absence or paid-service recommendation was adopted.

## Mayhem observation and arithmetic

S25 projection from direct GET (not a complete payload; omitted fields are not null):

```json
{"activeCoins":64,"coinsCreated":{"24h":10774,"7d":59644},"coinsCreatedByMode":{"auto":{"24h":8579,"7d":46576},"manual":{"24h":2195,"7d":13068}},"updatedAt":1789191117629}
```

Python Decimal calculations, executed at 02:43:15 BRT:

```text
overview 24h vs 7d/day 1.264469183824022533699953055
overview preceding6d/day 8145
overview ratio preceding6d 1.322774708410067526089625537
updatedAt UTC 2026-09-12T05:31:57.629000+00:00
```

Interpretation is conditional on shared population/window cutoffs. One cached observation is
not a seasonal time series. No extrapolation to all pump.fun creations, graduation or returns.

Timestamp extraction from public Telegram message HTML:

```text
TELEGRAM 38 DATE ['2026-03-13T15:41:17+00:00']
TELEGRAM 39 DATE ['2026-03-24T16:20:05+00:00']
```

## Review and verification

Independent specialist dispatch was attempted through the collaboration tool. It failed with
`collab spawn failed: no thread with id`. No independent review ran; do not claim concurrence.
Local self-review checks source/announcement date distinctions, no look-ahead, unknown versus
zero, numerator/denominator and overlapping windows. The scoped brief prohibits writing other
review artifacts; no recursive astra.sh run was used.

Baseline command, foreground, process timeout 290 seconds:

```text
uv run python infra/scripts/obsidian_lint.py
LINT DA BASE OBSIDIAN — 258 NOTA(S) ANALISADA(S)
Resumo — Links mortos: 0, Links ambíguos: 0, Notas órfãs: 0, Frontmatter incompleto: 0, Valores fora do vocabulário: 0, Procedência da Knowledge Base (KB-*): 0, Reescrita de experimentos (append-only): 0.

RESULTADO: base limpa
exit_code: 0
```

Windows wrapper used: `& 'C:\Program Files\Git\usr\bin\timeout.exe' 290 uv run python infra/scripts/obsidian_lint.py`.
Research helper commands used the same timeout wrapper with `uv run python -`, no helper files.
Final lint, after appending M-P6–M-P16 (same command/wrapper, exit 0):

```text
LINT DA BASE OBSIDIAN — 264 NOTA(S) ANALISADA(S)
Resumo — Links mortos: 0, Links ambíguos: 0, Notas órfãs: 0, Frontmatter incompleto: 0, Valores fora do vocabulário: 0, Procedência da Knowledge Base (KB-*): 0, Reescrita de experimentos (append-only): 0.

RESULTADO: base limpa
```

Concurrent work added the meme module pages and M-P1–M-P5 while research was underway.
Read the new module/decision pages, then assigned this task M-P6–M-P16 without modifying
the other task's rows. Baseline 258 versus final 264 reflects the shared tree, not new
Obsidian pages created by this task. The first append had a PowerShell stdin encoding issue;
only this task's 11 rows were corrected with UTF-8-safe patches before final verification.

In-memory checks, `timeout 290 uv run python -`, exit 0, completed before 02:54:46 BRT:

```text
Existing 104033-byte prefix preserved: OK
11 UTF-8 rows, M-P6-M-P16, five columns, status nova: OK
Source references and final hypothesis mapping: OK
```

Preserved prefix SHA-256: `fdb9407343fab24490dcb52557c2bcafc3ecfc387d57b38a3ce3664b71da49f8`.
`git diff --numstat -- obsidian/00-INBOX/Hipoteses-do-plantao.md` returned
`11  0  obsidian/00-INBOX/Hipoteses-do-plantao.md`.
`git diff --check -- docs/plans/T4-CANTOS.md obsidian/00-INBOX/Hipoteses-do-plantao.md .claude/state/notes-A4.0g.md`
returned exit 0 with no whitespace findings (Git emitted its CRLF-to-LF advisory).
The two new Markdown files were also checked for source-reference resolution and UTF-8 decoding;
no executable code or tests were added. No pytest/lint/typecheck suites outside the brief were run.

Final review outcome: no unresolved defect in the scoped documentation. Research limitations
remain explicit: KOTH/trending formula and duration, X feed selection/API, authenticated client
exclusivity and numerical livestream/volume correlation. These do not justify invented values.
Candidate tests still require instrument coverage and a frozen prospective protocol before use.
