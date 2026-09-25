---
tags: [meme, pumpfun, features, 15s, cadeia, porta, defasagem, m4, t4.40]
data: 2026-09-16
janela_medida: 16/09/2026 16:00-18:00 BRT (19:00-21:00 UTC) para as linhas; 09:00-18:00 BRT para as propostas
medido_em: 2026-09-16 (banco da VPS, SELECT)
fonte: meme_features_15s, meme_curve_snapshots, meme_proposals, meme_tokens
sql: infra/scripts/sql/research/2026-09-16-r37-q0{1,2,3,4}-*.sql
owner: astra-quant
status: vivo
confianca: alta (n = 53.441 linhas de 15 s; n = 76 propostas)
updated: 2026-09-16
tipo: leitura
hipotese: —
variavel: —
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: —
classe_de_perda: —
mercado: meme
---

# KB-0117 — O progresso da série de 15 s está atrasado (e por quanto)

> **Pergunta do R35:** às 17:35:24 BRT a `meme_features_15s.curve_progress_pct` da KITTYGBIKE dizia
> **37,7 %** enquanto a curva tinha **0,014 SOL reais**. É um caso ou é a regra?
>
> **Resposta medida: a defasagem é a regra, o tamanho dela não.** A linha nunca reaproveita foto
> velha (p99 = 14,8 s de idade de foto), mas **a foto já nasce ~12 s atrasada** — o RPC é lido em
> commitment `finalized` e `observed_at` é o *block time* do slot servido. Somada à idade da própria
> linha quando a porta a lê, a decisão sai sobre um estado de curva de **20,7 s (p50) / 30,8 s (p90)**.
> Em **9,0 %** das linhas isso já é um erro de mais de 50 % no SOL real.

## 1. De onde vem o número (código)

`fast_lane.fast_once` → `chain.get_curve_states` (RPC, `commitment = finalized`) → `collect.persist_reading`
→ `meme_curve_snapshots (source = solana_rpc)`; depois `fold_fast` → `repo_fast.load_fast_points`
(`observed_at > as_of - 180 s AND received_at <= as_of`) → `hunter_indicators.meme.fast.compute_fast`
→ `curve_progress_pct = 1 - real_token_reserves / meme_tokens.initial_real_token_reserves` **da foto
mais nova recebida até `as_of`**. Não há REST em cache nem fita nesse caminho: `pumpfun_rest` só entra
quando é a foto mais nova do mint (4,1 % das linhas). `packages/exchange-adapters/.../rpc_curves.py`:
`observed_at = block_time or received_at`, `commitment = FINALIZED` — **é aqui que nascem os 12 s**.

## 2. Os números (16/09, 19:00-21:00 UTC)

`as_of - snapshot_observed_at` (idade da foto na linha), por fonte:

| fonte | linhas | p50 | p90 | p99 | max | > 60 s | > 120 s |
|---|---|---|---|---|---|---|---|
| `solana_rpc` | 51.227 | **12,3 s** | 13,1 s | 14,8 s | 70,5 s | **1** | 0 |
| `pumpfun_rest` | 2.214 | 6,0 s | 11,5 s | 13,7 s | 15,7 s | 0 | 0 |

**Reaproveitamento de foto velha não existe** (1 linha em 51 mil acima de 60 s). O atraso é constante
e estrutural: `received_at - observed_at` ≈ 11,5 s em todas as fotos da KITTYGBIKE — a assinatura de
`finalized` (32 slots ≈ 12,8 s), não de um bug do worker.

SOL real da foto que a linha carrega × leitura RPC mais próxima de `as_of` (+/- 30 s):

| fonte | linhas | erro > 50 % | % | linha otimista (> 2× a cadeia) |
|---|---|---|---|---|
| `solana_rpc` | 51.227 | 4.608 | **9,00 %** | 3.145 (6,1 %) |
| `pumpfun_rest` | 2.214 | 435 | **19,65 %** | 290 (13,1 %) |

Idade do estado **no instante da proposta** (`proposed_at - snapshot_observed_at`, 76 propostas do dia):
**p50 20,7 s · p90 30,8 s · p99 = max 36,1 s**; 40 propostas (53 %) acima de 20 s, 10 (13 %) acima de
30 s, **nenhuma acima de 60 s**.

## 3. O caso KITTYGBIKE, linha a linha

| `as_of` | foto | prog | SOL real da foto |
|---|---|---|---|
| 20:34:58 | 20:34:58 | 37,65 % | 11,569 |
| 20:35:10 | 20:34:58 | **37,65 %** | 11,569 | ← a linha que a mesa usou
| 20:35:26 | 20:35:14 | 0,88 % | 0,197 |
| 20:35:42 | 20:35:23 | 0,06 % | **0,014** |

A proposta saiu às **20:35:24** sobre a linha de **20:35:10**, cuja foto é de **20:34:58**: idade do
estado = **26 s**. Nesses 26 s a curva foi de 11,57 para 0,20 SOL reais. A linha não estava presa: ela
estava **26 s atrás de um rug de 26 s**. O executor, que relê a curva ao vivo, viu 0,063 % e recusou.
(Cuidado ao consultar: há **três** mints com o símbolo `KITTYGBIKE` no mesmo intervalo — filtre por mint.)

## 4. A regra que fica

> **Nenhuma decisão de meme deve ser tomada sobre `meme_features_15s` sem carimbar a idade do estado.
> A série é boa para tendência e péssima para "está vivo agora": 9 % das linhas erram o SOL real por
> mais de 50 %, e sempre para mais (6 % dizem o dobro ou mais). Quem decide dinheiro relê a curva.**
> Corolário: a checagem `curve_progress` do admissor (leitura RPC ao vivo) **não é burocracia — é o
> único componente com o estado atual**. Nunca frouxar por "a feature já disse".

## 5. Correção proposta (não aplicada — é decisão de política)

O patch do brief (`snapshot_age_s > 60 s` → `progress_reason = stale_snapshot` → porta recusa
`curve_state_stale`) **é um no-op medido**: pegaria **1 linha em 51.227** e **0 propostas em 76**.
O limiar que morde é sobre a idade **no instante da decisão**, não sobre a linha:

1. `features_fast.Fast15sRow` já carrega `as_of` e `snapshot_observed_at`: `snapshot_age_s` é derivável,
   **sem migração e sem coluna nova** (`GateRow.snapshot.observed_at` chega inteiro à porta).
2. `proposals.evaluate_gate(...)`: parâmetro `max_state_age_s: int | None = None`; antes de
   `entry_features_of`, se `now - row.snapshot.observed_at > max_state_age_s`, conta
   `refusals["curve_state_stale"] += 1` e segue (nome já existente na admissão — reuso, não invenção).
3. Ligar em `lab_fast.py` por config (`meme_gate_max_state_age_s`), **não hardcoded**.

**Custo medido do limiar** (76 propostas do dia): 30 s recusa 13 %; 25 s recusa ~30 %; 20 s recusa 53 %.
Como 12 s do atraso são estruturais (`finalized`), abaixo de ~18 s a porta fecha sozinha. Recomendação:
**30 s** como teto duro (corta a cauda, custa 13 %) **e** atacar a causa — ler a curva em `confirmed`
para a série de 15 s (mantendo `finalized` para dinheiro), o que devolveria ~11 s dos 20,7 s de p50.
Isso é mudança de fonte, não de feature: vira `meme_features_15s_v2`, nunca edição da v1.

## 6. Ligações

[[KB-0115-volta-ao-piso-e-real-ou-artefato|KB-0115]] (desfecho pela cadeia) ·
[[KB-0113-ate-onde-as-series-acompanham-uma-aposta|KB-0113]] (pinos) ·
[[03-TRADING/Meme/Candidatas/2026-09-16-17h56-brt|R35 §1]] (o achado original)
