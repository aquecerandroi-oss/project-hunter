---
tags: [knowledge, indice, variaveis, dicionario]
tipo: consolidado
mercado: meme
status: vivo
owner: sexta-feira
updated: 2026-09-25
---

# Dicionário de Variáveis

Toda variável que o sistema consegue medir para uma decisão — meme (`hunter_meme_worker`,
`hunter_indicators.meme`) e cripto normal (`hunter_indicators.features`, o Radar do M2). Existe para
duas coisas: **achar rápido** onde uma variável vive quando alguém for propor uma hipótese, e ser a
**semente da próxima leva de hipóteses** — a coluna "já testada?" separa o que já foi julgado do que
nunca foi olhado. Números aqui são copiados de `docs/DATABASE.md`, do código ou das notas linkadas;
nada foi inventado. `—` = não medido / não se aplica.

Como ler "já testada?": link para a hipótese (`H-0xx`, [[Fila de Hipoteses]]) ou nota (`KB-0xxx`) que
mediu a variável, com o veredito entre parênteses (`confirma`/`nao_confirma`/`refuta`/
`limite_de_dado`/`em_curso`). "Não" = nunca entrou num estudo pré-registrado. Vocabulário de veredito
em `docs/RESEARCH.md`.

## A — Cripto normal (Radar M2, `packages/indicators/hunter_indicators/features/`)

Fonte primária: [[Strategy Backlog]] "Features do M2 disponíveis" (verificado em 2026-09-06, com as
correções da mesma página) + grep de `key=` nos calculadores. Toda feature é uma
`FeatureDefinition` versionada (`hunter_indicators.features.definitions`); "onde vive" aponta o
arquivo que a calcula.

| variável | o que mede | onde vive | desde quando | cobertura / limites | já testada? | resultado |
|---|---|---|---|---|---|---|
| `return_1m/5m/15m/1h/4h` (+ `_live`) | retorno no horizonte, com sufixo `_live` quando a vela ainda está se formando | `features/price.py:53` | M2 (2026-09-06) | `return_24h` **não existe**; `_live` não tem coverage própria de book/trade (tem timestamp próprio) | `momentum_15m` via H-005; `return_4h` via H-008 (ambas em população **substituta**, não a verbatim) | H-005 [[Fila de Hipoteses|nao_confirma]] · H-008 [[Fila de Hipoteses|em_curso]] (estudo inválido por censura) |
| `distance_from_24h_high` / `_low` | distância percentual da máxima/mínima de 24 h | `features/price.py:106` | M2 | existe mas **não estava no envelope da v1** da `momentum` — bloqueada por medição de redundância nunca feita ([[Strategy Backlog]] item 8) | não | — |
| `atr_14_pct` | ATR de 14 períodos, em % do preço | `features/trend.py:78` | M2 | é o **checkpoint ancorado do M2**; a `momentum_v1` de fato consome outro instrumento (`rolling_window_v1`, `atr_bars=97`) — dois instrumentos com o mesmo apelido ([[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]]) | diagnóstico por decil (item 3 do backlog) | especificada, nunca rodada |
| `momentum_15m` | retorno de 15 min, feature nomeada (distinta de `return_15m`) | `features/trend.py:130` | M2 | — | [[Fila de Hipoteses#H-005 — Piso de impulso recente (momentum_15m ≤ 2,0)\|H-005]] | **nao_confirma** — 0 sinais têm a variável no envelope verbatim; medida em população substituta (censura 51,7 %) |
| `momentum_acceleration` | 2ª derivada do momentum | `features/trend.py:169` | M2 | — | não | — |
| `breakout_strength_20` | força do rompimento sobre 20 barras | `features/trend.py:206` | M2 | — | não | — |
| `relative_volume_5m/15m/1h` | volume relativo à média | `features/volume.py:54` | M2 | `volume_ratio_5m` (nome usado nas hipóteses) é este campo | [[Fila de Hipoteses#H-007 — Teto de volume relativo (exaustão)\|H-007]] | **refuta** (teto em 12 não paga vantagem de +0,10 R; quanto a +0,02 R, frágil a semente) |
| `volume_acceleration` | derivada do volume relativo | `features/volume.py:108` | M2 | — | não | — |
| `funding_rate` | taxa de funding do instante | `features/deriv.py:66` | M2 | computa (só depende do snapshot `deriv`) | não (H-022 do backlog nunca virou hipótese formal) | — |
| `funding_change_8h` | variação de funding em 8 h | `features/deriv.py:141` | M2 | **NÃO COMPUTA em produção** — `load_deriv_history` sem chamada, `Scanner.deriv_history` sempre vazio → `missing_input` em toda barra ([[KB-0020-funding-change-8h-nunca-calcula]]) | diagnóstico do bloqueio | confirmado como bloqueio, não como hipótese de mercado |
| `open_interest_change_1h/4h` | variação de open interest | `features/deriv.py:94` | M2 | mesmo bloqueio de `funding_change_8h` — `missing_input` sempre | idem | idem |
| `spread_pct` | spread cotado, em % | `features/micro.py:86` | M2 | mediana 2,30 bps medida no R6 do conhecimento (não é o M2, é a rodada de execução) — o M2 assume 2 bps fixos | cobertura/distribuição nunca virou hipótese formal | — |
| `orderbook_imbalance_{depth}` | desequilíbrio do livro em N níveis | `features/micro.py:121` | M2 | **retirada do backlog em 2026-09-06**: razão invariante a escala, não mede profundidade ([[KB-0012-ofi-nao-e-o-nosso-orderbook-imbalance]]) | descartada antes de testar | — |
| `{buy\|sell}_pressure_{Nm}` | pressão agressora compradora/vendedora | `features/micro.py:179` | M2 | disponibilidade operacional **nunca medida** (deixou de estar bloqueada por `covered_until` em 2026-09-06) | não | — |
| `trade_velocity_{Nm}` | negócios por unidade de tempo | `features/micro.py:221` | M2 | idem `buy/sell_pressure` | não | — |
| `taker_buy_volume` (vela) | volume comprado pelo agressor, na vela de 1 min | schema de `candles` | M2 | cobertura de **100 %** (519 422 velas, 222 mercados) mas **descartado na agregação 1m→5m** (`aggregate.py:40,77`) | [[Fila de Hipoteses#H-006 — Desequilíbrio agressor na barra do sinal\|H-006]] (`taker_imbalance_5m`) | **nao_confirma** — falha por 1 ponto-base do MRE, seis condições ao mesmo tempo |
| `market_betas` (β vs. BTC) | beta contra BTCUSDT, com validade | `packages/beta` (`beta_v1`) | M3 | tabela **existe e está vazia** (0 linhas na VPS, conferir estado atual) | não | — |
| `liquidations` (notional) | fluxo forçado por amostragem | tabela `liquidations` | M2 | **8 421 linhas, 197 mercados**; notional com **defeito de semântica** (`q`/`z`, `p`/`ap` sem separação correta) | não | — |

## B — Meme: porta de entrada (`hunter_indicators.meme.rules.EntryFeatures`, decompostas em `meme_proposals.reasons` por `hunter_meme_worker/proposals_reasons.py`)

Cada bloco só aparece em `reasons` quando o conjunto de regras (`rule_set`) pergunta por ele — a
decomposição é congelada por conjunto (EXP-M1's invariant).

| variável | bloco em `reasons` | o que mede | desde quando | cobertura / limites | já testada? | resultado |
|---|---|---|---|---|---|---|
| `age_s` | sempre | idade do mint em segundos, no instante da decisão | T4.10 | uma das **13 variáveis esgotadas** do R65 | R65 (idade) | **nenhuma das 13 sobrevive** — p mais baixo 0,046 contra limiar 0,0077 ([[KB-0149-o-que-a-mesa-real-ensinou]] item 11) |
| `curve_progress_pct` | sempre | progresso da bonding curve (fração 0–1) | T4.10 | — | R65 (progresso) | esgotada, não sobrevive |
| `creator_net_seller` | sempre | se o criador é vendedor líquido no instante | T4.10 | — | não isolada (compõe `equilibrio`, H-013) | H-013 [[Fila de Hipoteses|limite_de_dado]] |
| `participation_pct` | sempre | fração do tamanho da aposta sobre o volume da curva no minuto | T4.16 | — | não | — |
| `higher_lows`, `breakout_15m`, `distance_to_support_pct` | `line` (T4.10) | estrutura de linha de tendência sobre a curva | T4.10 | só gravado quando o conjunto usa `require_higher_lows`/`require_breakout_15m`/teto de distância | não | — |
| `hype_score`, `dev_share`, `snipers` | `hype` (T4.10) | pontuação de hype; fração do dev; contagem de snipers | T4.10 | uma das 13 esgotadas cada (dev share, snipers) | R65 (snipers, dev_share) | esgotadas: snipers p=0,52, dev_share p=0,67 |
| `net_sol_flow_1m`, `mcap_delta_60s`, `buys_1m`, `sells_1m`, `unique_buyers_1m`, `holders_rising`, `progress_rising` | `flow` (T4.16, EXP-M5) | fluxo do minuto e holders | T4.16 | `buys_1m`, `sells/buys`, `compradores únicos`, `fluxo do criador`, `holders`, `carteiras novas`, `flip rápido` estão entre as 13 esgotadas | R65 + R67 (`buys_1m`) | esgotadas; `buys_1m ≤ 25` **não confirmou fora da amostra** (D=+0,036, IC [−0,058,+0,136], p=0,43 — R67) |
| `creator_prior_mints_1h`, `symbol_dup_24h`, `creator_prior_dump_count`, `creator_prior_dead_count` | `pedigree` (T4.16/T4.24, EXP-M6) | pedigree do criador: mints prévios, símbolo duplicado, dumps/mortes anteriores | T4.16/T4.24 | contadas em `meme_tokens` na hora da proposta | não isolada dos testes de H-014/H-015 (rede/slot) | ver H-014, H-015 |
| `top_buyer_share`, `buyers`, `fill_seconds` | `pedigree_e2b` (T4.31, EXP-M9) | maior fração de comprador único no preenchimento inicial (E2-b) | T4.31 | só quando `spec.pedigree_e2b` | E2b (R57/60/61 — copiar carteiras) | descartado (R57/KB-0136) |
| `has_twitter`, `twitter_kind`, `twitter_post_age_s`, `twitter_reuse_count`, `has_website`, `has_telegram`, `description_len` | `identity` (T4.26, EXP-M8) | identidade social do token | T4.26 | só quando `require_twitter`; o link cru vive em `meme_tokens.twitter`, gravado **só** pela leitura REST da pump.fun (`social_observed_at` NULL = não observado) — **parada desde 25/09 17:13:16Z** (0 moedas com identidade depois); `twitter_reuse_count` é do indexador (mutável, janela alheia, lida depois — não serve como feature de decisão) | [[Fila de Hipoteses#H-020 — Identidade social reciclada (o mesmo X/Twitter em várias moedas)\|H-020]] (`reuso_social` recalculado do link, `sem_social`) | **nao_confirma** — reuso ≥ 1 × 0: D −0,0525 [−0,123, +0,016], p 0,18; golpe 1,02×; some com o que a base sabia em T (+0,009) ([[KB-0160-o-link-reciclado-nao-avisa-o-golpe]]) |
| `is_mayhem` | `mayhem` (T4.27) | se o programa é o "Mayhem" (excluído por padrão) | T4.27 | só quando `declares_mayhem` | não | — |
| `kind`, `confidence`, `title`, `source`, `observed_at`, `match_kind` | `event` (T4.26, EXP-M8) | evento externo casado ao mint (KOL/call) | T4.26 | só quando `require_event` | [[Fila de Hipoteses|KOL/call]] (R61) | KOL/call **confirma, não antecipa** — bum começa 16 s depois do sinal, R −0,07, acerto 15 % ([[KB-0142-kol-e-call-antecipam-ou-confirmam]]) |
| bloco `absorb` | `absorb` (T4.79, EXP-M22) | absorção de venda ≥5 % da curva em 30 s | T4.79 | só quando `require_absorb_confirmed`/`require_absorb_sell_seen` | [[Fila de Hipoteses#H-001 — Absorção de uma venda grande (EXP-M22)\|H-001]] | **em_curso** — amostra insuficiente (14 apostas, mínimo 20/lado) |
| `holders`, `holders_prev` | `EntryFeatures` (não decomposto sempre) | contagem de holders e leitura anterior | T4.16 | uma das 13 esgotadas | R65 (holders) | esgotada |
| `recent_drawdown_pct`, `recent_drawdown_peak_age_s` | não decomposto em `reasons` hoje | recuo recente desde o pico, em janela curta | — | usado internamente pela porta; não aparece na decomposição | relacionado a H-016/H-017 (entrada no recuo) | ver H-016 (refuta), H-017 (limite de dado) |
| `early_retention_pct`, `early_age_s` | não decomposto hoje | retenção dos primeiros compradores | — | ver H-002 | [[Fila de Hipoteses#H-002 — Retenção dos primeiros compradores (EXP-M19)\|H-002]] | **em_curso** — braço `flow_v2/10` com 0 apostas |

## C — Meme: a fita do instante da decisão (`meme_decision_tapes`, T4.89, `docs/DATABASE.md` §64)

O que a mesa **viu**, gravado no instante — não reconstruído depois de `meme_trades` (que atrasa
mediana 43,6 s, p90 ≈ 129 s, e não serve para medir o instante da decisão — R73/[[KB-0153-o-maior-comprador-nao-estava-no-arquivo]]).

| variável | campo | o que mede | desde quando | cobertura / limites | já testada? | resultado |
|---|---|---|---|---|---|---|
| janelas `10s`/`30s`/`60s` (`buys`, `sells`, `buy_sol`, `sell_sol`, `net_sol`, `unique_buyers`) | `derived.windows` | fluxo de compra/venda em três janelas curtas, sem o criador | T4.89 (`0062`) | `{"reason": "window_not_covered"}` quando a assinatura não cobre a janela | `aceleracao_compra` = (SOL 10s/10) ÷ (SOL 60s/60) — [[Fila de Hipoteses#H-019 — Fluxo desacelerando na hora da compra (o topo local visto pela fita de 10 s)\|H-019]] | **refuta** pela cláusula (c); sinal saiu ao contrário da tese ([[KB-0159-a-desaceleracao-nao-avisa-o-topo]]) |
| `largest_net_buyer` (`share_of_real_sol`, `is_creator`) | `derived.largest_net_buyer` | maior comprador líquido em SOL desde a assinatura | T4.89 | cobertura no instante da decisão medida em **1/91** antes da `0062` (R73); melhora com a fita própria | [[Fila de Hipoteses#H-010 — Concentração do maior comprador (o dono que pode afundar)\|H-010]] | **limite_de_dado** (cobertura < 60 %) |
| `largest_holder` (`share_of_supply`) | `derived.largest_holder` | maior saldo negociado desde a assinatura, em tokens | T4.89 | idem | não isolada | ver H-010 |
| `creator` (posição líquida) | `derived.creator` | posição do criador desde a assinatura | T4.89 | — | não | — |
| `ledger` (`reconcile_gap_sol`, `reason`) | `derived.ledger` | reconciliação "desde o nascimento" contra `real_sol` da curva (tolerância 1 %) | T4.89b | `not_covered_from_birth`, `coverage_gap`, `wallets_overflow`, `tokens_missing` | usado como filtro de cobertura em todas as H de rede/slot | — |
| `creation_bundle` (`creation_slot`, `sol`, `wallets`, `creator_buy_sol`) | `derived.creation_bundle` | SOL/carteiras que compraram no slot da criação | T4.89b | `creation_slot` é **inferido**, nunca provado (primeira troca vista, não a tx `create`) | H-015 usa `early_slots`, não este bloco diretamente | ver `early_slots` |
| `early_slots` (até 5, `sol_others`, `wallets_others`, `creator_sol`) | `derived.creation_bundle.early_slots` | SOL de outras carteiras por slot, nos primeiros slots desde a assinatura | T4.89b | resolvido contra o slot real da criação via `create_signature` + RPC, quando disponível | [[Fila de Hipoteses#H-015 — Compra no slot de criação (o "bundle" do lançamento)\|H-015]] (`sol_no_slot_de_criacao`) | **refuta** pela cláusula (c) — teto no tercil alto mataria 36,5 % das vencedoras |
| `rede_financiadora_pct` (primeiro financiador comum) | derivada via Helius, **não persistida** na fita | fração de compradoras pré-decisão com o mesmo financiador | R76 (medição ad-hoc) | resolvido em 98,0 % das compradoras pré-decisão no estudo | [[Fila de Hipoteses#H-014 — Rede coordenada de compradores (o golpe em um bloco só)\|H-014]] | **nao_confirma** |

## D — Meme: séries persistidas (`meme_features_1m`, `meme_features_15s`)

| variável | tabela | o que mede | desde quando | cobertura / limites | já testada? | resultado |
|---|---|---|---|---|---|---|
| `curve_progress_pct` + `progress_reason` | `meme_features_1m` | progresso da curva, com motivo quando nulo | M18 | fração 0–1; motivo `denominator_unknown` etc | esgotada (R65 "progresso") | — |
| `mcap_sol` + `curve_reason` | `meme_features_1m` | market cap em SOL | M18 | `no_holders_reader`/outros motivos | não isolada | — |
| `unique_buyers` + `reason` | `meme_features_1m` | compradores únicos no minuto | M18 | `no_trade_feed` até o decodificador on-chain (T4.2b) existir | esgotada | — |
| `buy_sell_ratio` + `reason` | `meme_features_1m` | razão compras/vendas do minuto | M18 | idem | esgotada (R65 "sells/buys absoluto"); percentil na coorte via H-004 | H-004 **nao_confirma** (curva é pico, só 1/7 limiares exclui zero) |
| `top10_share` + `reason` | `meme_features_1m` | concentração dos 10 maiores holders | M18 | `no_holders_reader` | esgotada (R65 "top10") | — |
| `creator_sold` + `reason` | `meme_features_1m` | se o criador vendeu no minuto | M18 | `no_holders_reader` | alimenta pedigree (`creator_prior_dump_count`) | — |
| `age_minutes` | `meme_features_1m` | idade em minutos | M18 | anulável sem coluna de motivo (só quando `created_at` é desconhecido) | esgotada (R65 "idade") | — |
| `mcap_delta_60s`, `mcap_slope_60s` | `meme_features_15s` | variação/inclinação do mcap em 60 s | T4.16/`0030` | OLS de ln(mcap) entre referência de 60 s e a foto mais nova | não isolada (compõe `equilibrio`, H-013) | ver H-013 |
| `progress_delta_60s`, `progress_rising` | `meme_features_15s` | variação/tendência do progresso em 60 s | T4.16 | — | compõe `equilibrio` | ver H-013 |
| `holders_rising`, `holders_prev` | `meme_features_15s` | tendência de holders | T4.16 | — | esgotada (R65 "holders") | — |
| `buys_60s`, `sells_60s`, `unique_buyers_60s`, `net_sol_flow_60s`, `curve_volume_60s_sol` | `meme_features_15s` | fluxo do minuto corrente, na via de 15 s | T4.16 | via de 15 s (`meme_event_gate_v1`/`lab_fast`), atraso máximo 45 s | compõe `equilibrio`, `flow` | ver H-013 |

## O que nunca foi testado (semente da próxima leva de hipóteses)

Contagem manual das tabelas A–D acima (53 linhas ao todo): **30 nunca foram testadas de forma
independente** — coluna "já testada?" diz `não`, ou diz que a variável só aparece **dentro** de
outra (`equilibrio`, `flow`, pedigree) sem nunca ter sido isolada, ou foi descartada por raciocínio
antes de qualquer teste (`orderbook_imbalance`). As dez mais prontas para virar hipótese
pré-registrada (dado já existe, ninguém mediu):

1. `distance_from_24h_high`/`_low` (cripto) — bloqueada só por uma medição de redundância nunca feita.
2. `open_interest` **em nível** (não a variação) como profundidade — item 14 do [[Strategy Backlog]], nunca rodado.
3. `{buy,sell}_pressure_{Nm}` e `trade_velocity_{Nm}` (cripto) — disponibilidade operacional nunca medida desde que o bloqueio de `covered_until` caiu.
4. `higher_lows`/`breakout_15m`/`distance_to_support_pct` (meme, bloco `line`) — nunca isolado de um conjunto que já os usa.
5. ~~`has_twitter`/`twitter_kind`/`twitter_reuse_count` (meme, `identity`) — coletado desde T4.26, nunca virou hipótese.~~ Virou a H-020 (R80, 26/09): **NÃO CONFIRMA** ([[KB-0160-o-link-reciclado-nao-avisa-o-golpe]]).
6. `is_mayhem` (meme) — excluído por padrão, nunca medido se a exclusão paga.
7. `top_buyer_share`/`fill_seconds` (meme, `pedigree_e2b`) — a família E2-b morreu como "seguir carteira", nunca como o **preenchimento** em si.
8. `market_betas` (cripto) — tabela existe, nunca populada o suficiente para medir.
9. `holders_rising`/`progress_rising` (meme, `meme_features_15s`) isolados — só medidos hoje **dentro** de `equilibrio` (H-013, que morreu por 1 caso).
10. `liquidations` notional (cripto) — 8 421 linhas já coletadas, defeito de semântica nunca corrigido nem a série testada.

## Relacionado

[[Mapa de Estrategias]] · [[Strategy Backlog]] · [[Fila de Hipoteses]] · [[KB-0149-o-que-a-mesa-real-ensinou]] ·
[[Perdas/Index|Perdas]] · `docs/DATABASE.md` §64 · `docs/PIPELINE.md` · `docs/RESEARCH.md`
