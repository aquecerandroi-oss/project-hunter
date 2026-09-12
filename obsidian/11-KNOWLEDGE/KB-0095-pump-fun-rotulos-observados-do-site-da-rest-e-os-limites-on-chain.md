---
tags: [knowledge, nota, plantao, meme, pumpfun, mayhem, holder-rewards, instrumento]
tema: memecoin / pump.fun / rótulos observados do site (bundle i18n e página SSR) e da REST — Mayhem (`enabled`, `active`, `paused`, `completed`; `auto` = "Classic", `manual` = "Trigger"; `pause_reason`/`complete_reason`) e destinatário das recompensas ("Rewards → creator / holders · {{percent}}% / traders") — e os limites da correspondência on-chain
fonte: página pública `https://pump.fun/coin/{mint}` (HTML servido sem login; dicionário i18n do bundle, 4 230 pares, 286 selecionados) ×4; `frontend-api-v3.pump.fun` (`/coins` 70 mais novas, `/coins?complete=true` ×2, `/coins/mayhem-mode?limit=60`, `/coins/{mint}` ×10, `/coins-v2/{mint}/mayhem-state` ×3); `docs/PUMPFUN.md` §1.1/§1.3/§4.3 (T4.0c, 02:18–02:41 BRT); `services/meme-worker/hunter_meme_worker/mayhem_labels.py`; `packages/core/hunter_core/db/models/meme.py`; `packages/exchange-adapters/hunter_exchanges/pumpfun/mayhem_state.py`
fonte_url: https://pump.fun/coin/25xPUKHqporrJqzKgdShSuckPPPmTMdyVp5Ue256pump
lido_em: 2026-09-12
evidencia: medição própria (plantão T4.64, run 17, lane 1, 17:43:36–17:49:32 BRT — 30 GETs públicos, 30 × HTTP 200; brutos em `.claude/state/plantao-meme/raw-lane17/`) + registro anterior do projeto (T4.0c, 02:32–02:37 BRT) + código do próprio Radar; templates do bundle não são renderização comprovada nem semântica on-chain validada; nenhuma moeda holder-rewards observada; duração de `enabled` não medida
hipotese_testavel: sim
astra: ver seção Astra (run 17; parecer em `.claude/state/astra-review-plantao-meme-20260912-1740.md`)
status: vivo
owner: sexta-feira
updated: 2026-09-12
confiança: "?"
---

# KB-0095 — pump.fun: rótulos observados do site, da REST e os limites da correspondência on-chain

**Plantão T4.64, run 17, lane 1 (17:40–18:1x BRT).** Rascunho: `.claude/state/plantao-meme/2026-09-12-1740-lane1.md` (itens 1, 2, 7 e tabela de rótulos). Brutos:
`.claude/state/plantao-meme/raw-lane17/` (`14_coin_01_25xPUK.json` … `23_coin_10_HGqM9W.json`, `24–26_mayhemstate_*.json`, `27–29_coinpage_*.json` — texto extraído,
`30_coinpage_i18n_extract_25xPUK.json` — chaves i18n, `13_coins_mayhem_mode60_trim.json`). Nasce do parecer da Astra: "o problema de vocabulário e proveniência atravessa o
upgrade e inclui rótulo comprovadamente anterior" — por isso é nota própria, e a [[KB-0094-pump-fun-upgrade-de-12-09-2026-holder-rewards-e-bonding-curve-v2|KB-0094]] leva só o adendo cronológico.

## O que afirma

O site da pump.fun emite, para a mesma moeda, rótulos em **três camadas que não coincidem**: (1) **templates** do dicionário i18n do bundle (o que a interface *pode* mostrar);
(2) **valores numa moeda** na REST e no HTML servido (o que foi visto numa data e hora); (3) **semântica validada** contra a cadeia (o que o Radar pode usar como feature). Hoje
só a camada 2 está medida; a camada 3 **não existe** para nenhum destes rótulos — a conta `MayhemState` decodificada pela T4.2e expõe janela, mint, fluxos líquidos e uma cauda
sem interpretação, **não** estado, razão nem instante da primeira transação (`mayhem_state.py:50,180`); o byte `is_holder_reward` da `BondingCurve` (KB-0094) ainda não foi
lido em moeda nenhuma. Regra de casa: cada rótulo entra no Radar como **"observado na REST/página"**, com fonte, endpoint, `received_at` e versão; nunca como estado on-chain.

## Tabela por campo · fonte · data (valor visto ≠ template ≠ semântica)

| campo / rótulo | template do bundle (i18n, `pump.fun/coin/{mint}`, 17:49:32 BRT) | valor visto numa moeda (fonte, hora BRT) | semântica validada on-chain | inferência (não medida) |
|---|---|---|---|---|
| `mayhem_state = enabled` | `status_explainer_enabled` = "Mayhem mode is enabled and will activate shortly. The agent is preparing to begin trading."; `waiting` = "Waiting on first mayhem agent transaction..." | listagem `/coins` **02:32–02:37** (T4.0c, `docs/PUMPFUN.md` §4.3: 3/653, **antes do deploy das 12:24**); worker às **16:4x** em `25xPUKHq…` (Lizardboy, criada 16:39:39), depois `paused`; **0/270 linhas e 0/10 detalhes às 17:43–17:44** | **nenhuma** | estado curto entre criação e primeira operação do agente — hipótese; duração não medida |
| `mayhem_state = active` | `status_explainer_active` = "... The agent can trade at any time over the next 24 hours."; `lifecycle_active_summary` = "Agent is online — trades may fire at any time." | 23/270 linhas; detalhes baby/watch (17:44:10–17:44:13) | nenhuma | — |
| `mayhem_state = paused` + `pause_reason` | `paused_status_description` = "Mayhem paused as the coin dropped below the minimum market cap required for acting. {{amount}} SOL to reactivate the agent."; `paused_low_mcap_auto`, `paused_low_mcap_manual`, `paused_low_reserves` = "Agent reserves low, activity required to continue"; `reactivate_agent_with` = "Reactivate agent with {{amount}} {{symbol}}" | 70/270; `pause_reason` ∈ {**`low_sol_reserves`** (Lizardboy 17:43:59/17:44:15, ASD ×2, H O L D, cap), **`below_initial_buy_floor`** (DERP 17:44:08; já em `docs/PUMPFUN.md` #15)}; página de Lizardboy (17:44:20): "Reactivate agent with 0.05 SOL · Classic-executing mayhem agent paused due to low coin market cap" | nenhuma | mapeamento `pause_reason` → texto da UI não verificado (a UI fala em "market cap", a API em "sol_reserves"); o floor de criação (`min_quote_required_description` = "Mayhem requires at least {{min_amount}} {{quote_symbol}} during creation.") é candidato a explicar `below_initial_buy_floor` |
| `mayhem_state = completed` + `complete_reason` | `status_explainer_completed` = "... either the 24-hour window expired or the SOL reserves were depleted."; `current_state_completed` = "... Tokens the agent held have been burned." | 26/270; `complete_reason` = **`sell_zero_amount`** (`J4dhS8…`, 17:44:02 e 17:44:16) — chave e valor **não documentados** em `docs/PUMPFUN.md` | nenhuma | "tokens queimados" é afirmação do site |
| `mayhem.mode` | `auto` = **"Classic"** (`auto_mode_title` "Classic mode", `badge_classic_countdown` "Mayhem Classic {{countdown}}", `auto_executing` "Agent classic executing"); `manual` = **"Trigger"** (`badge_trigger` "Mayhem Trigger", `manual_executing` "Mayhem agent in trigger mode"); `agent_mode_auto` = auto, `agent_mode_manual` = manual | objeto `mayhem` do `/coins/{mint}` (auto 6, manual 3 em 9) e `/coins-v2/{mint}/mayhem-state`; **chave `mayhem_mode` ausente em todas as fontes** (57/59/27/52 chaves por fonte); página: "Mayhem Classic 00:00:00" (ASD), "Paused: Classic" (Lizardboy) — contador zerado no SSR, não interpretável | nenhuma | `Classic`/`Trigger` são nomes de UI; a API mantém `auto`/`manual` |
| Mayhem × BOOST · slippage · comportamento do agente | `boost_skipped_note_mayhem` = "This coin does not have BOOST Mode as it is a mayhem coin. All future graduations will include BOOST Mode for non mayhem coins."; `footer_warning` = "Mayhem slippage stays at {{percentage}}% to protect your transactions."; `auto_mode_description` = "... The more organic activity on a coin, the more activity the Mayhem agent produces."; `activity_disclaimer_suffix` = "The agent decides per-coin based on engagement, capacity, and randomization." | `boost_mode` NONE em 23/23 Mayhem `complete=true` (17:43:51–17:43:54) | nenhuma | regras declaradas pelo site, não medidas |
| destinatário das recompensas (`rewards_recipient_label` = "Creator rewards recipient") | `rewards_to_creator` = "Rewards → creator" ("Creator rewards from trading fees go to the coin's creator."); `rewards_to_holders` = "Rewards → holders" ("Holder rewards are on: creator rewards from trading fees go to the coin's holders."); `rewards_to_holders_with_fee` = **"Rewards → holders · {{percent}}%"** ("Holder rewards are on: the {{percent}}% creator fee on every trade goes to the coin's holders."); `rewards_to_traders` = "Rewards → traders" ("Cash back is on: creator rewards from trading fees go to traders."); `creator_fee_share_text` = "{{percent}}% of creator fees are currently being sent to agent revenue wallet." | "Rewards → creator" em Lizardboy (Mayhem, 17:44:20), aizen (não-Mayhem, 17:44:22), ASD (criador em série, 17:44:25); run 15: "Rewards → creator" (ANTROGPT, INCOME) e "Rewards → traders" (baton, `is_cashback_enabled` true); **"Rewards → holders" nunca visto numa moeda**; `is_holder_reward` ausente em 270/270 linhas REST e em 0/52 chaves de detalhe | **nenhuma** (o byte `is_holder_reward` da `BondingCurve`/`CreateEvent` — KB-0094 — ainda não foi lido) | `holders` e `holders · %` são a mesma classe econômica com taxa opcional (consistente com `creator_fee_bps` configurável); classes do classificador de página: `creator` / `traders` / `holders` (+ taxa) / **desconhecido** |
| `is_cashback_enabled` | `cashback_rewards` = "Cashback rewards"; `rewards_to_traders` | false em 279/280 (70 + 140 + 60 + 10); true 1/60 no `/coins/mayhem-mode` | nenhuma | cashback encerrado para moedas novas (docs do programa, KB-0094); o flag persiste nas antigas |

Denominadores: 270 linhas de listagem (70 mais novas + 140 completas + 60 do `mayhem-mode`; 237 mints únicos) + 10 detalhes + 3 `mayhem-state` — **observações repetidas de
mints, não ensaios independentes**; a raridade de `enabled` (0/280) não tem precisão calculável.

## O que o Radar faz de errado hoje (medido)

- `meme_tokens`/`meme_curve_snapshots` só aceitam `active`/`paused`/`completed`/`unknown` (`meme.py:77`, `MAYHEM_STATES`); às 16:4x o loop morreu no CHECK ao receber
  `enabled` (RestartCount 1, quatro tracebacks em seis minutos, deploy 1033999 — docstring de `mayhem_labels.py`) e o remendo mapeia rótulo desconhecido → `unknown`, que
  **funde** "o site disse `enabled`" com "duas fontes discordam" (semântica de `unknown` em `meme.py:49`).
- O docstring de `mayhem_labels.py` atribui `enabled` ao upgrade ("after the holder-rewards upgrade the REST API started emitting"); o rótulo está registrado às 02:32 BRT.
- `docs/PUMPFUN.md` #15 lista só `pause_reason` (`below_initial_buy_floor`); faltam `low_sol_reserves` e a chave `complete_reason` (`sell_zero_amount`).

## Como mediríamos aqui (M-D11)

Alinhar **normalizador, contratos e CHECKs juntos** (só o CHECK mantém `enabled → unknown`; só o normalizador reintroduz a rejeição); guardar rótulo bruto + fonte + endpoint +
`request_started`/`received_at` + hora da fonte + slot/commitment + motivo de indisponibilidade/conflito em colunas separadas; manter tolerância a rótulos futuros; medir
**separadamente** (i) duração do rótulo por fonte, (ii) espera pela primeira operação atribuída ao agente (exige histórico de transações do agente com cobertura desde a criação),
(iii) atraso de publicação entre lista, detalhe e `mayhem-state` — DERP (`active` na lista 17:43:40, `paused` no detalhe 17:44:08) e baby (17:44:10 → 17:44:18) são **observações
divergentes a 28 s e 8 s**, não transições (lista em cache é cenário plausível); transições registradas por fonte com retornos, saltos e lacunas, sem cadeia irreversível imposta;
primeiro registro já `active` = início desconhecido; acompanhamento encerrado em `enabled` = duração incompleta.

## Hipótese testável no Lab

**M-D11** (diagnóstico, primeira da ordem da Astra) e **M-P37** (prospectiva, última: estado observado na REST em L = criação on-chain + 5 min como feature incremental sobre
conclusão futura e retenção pós-migração; previsão padrão: sem ganho detectável) — linhas em [[00-INBOX/Hipoteses-do-plantao]].

## Por que pode falhar

Templates podem nunca renderizar (chaves mortas no bundle); a UI pode mudar nomes sem mudar a API (ou o inverso); o rótulo da lista pode vir de cache; `enabled` pode ter
duração de segundos (invisível a um poll por minuto) ou ser emitido em condições que a amostra de hoje não cobriu; a correspondência com a cadeia exige um decoder que hoje
não existe para estado/razão; dois criadores dominam a amostra Mayhem da noite (18/60 do `mayhem-mode`).

## Astra
Parecer do run 17 (`.claude/state/astra-review-plantao-meme-20260912-1740.md`, 17:58:54–18:02:23 BRT): recomenda esta KB ("organizaria por campo/fonte/data, separando template
do bundle, valor numa moeda, semântica validada e inferência; evitaria chamar de máquina de estados completa"); must-fixes 1–3 e 7 aplicados aqui; resumo na nota do dia
[[02-MARKET/Meme/2026-09-12]] (seção "Run 17").

## Ligações
[[02-MARKET/Meme/2026-09-12]] · [[00-INBOX/Hipoteses-do-plantao]] · [[KB-0094-pump-fun-upgrade-de-12-09-2026-holder-rewards-e-bonding-curve-v2]] · [[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]] · [[README-meme]]
