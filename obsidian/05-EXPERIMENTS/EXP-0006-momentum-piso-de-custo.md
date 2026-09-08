---
tags: [experimento, momentum, shadow-lab, custos]
updated: 2026-09-08
status: em-andamento
owner: sexta-feira
exp: EXP-0006
strategy: momentum
version: v4
result: inconclusivo
evaluable: 30
days: 9
last_eval: 2026-09-08
---

# EXP-0006 — piso de custo no momentum (`atr_pct_min = 0,0089`)

> **Arquivado pela Sexta-feira em 2026-09-08 (T3.26b)** a partir do rascunho do `quant-engineer`
> (`.claude/state/exp-drafts/EXP-0006-momentum-piso-de-custo.md`, T3.26). Hipótese e Protocolo vêm do
> rascunho **sem alteração de conteúdo** — são as seções congeladas. A avaliação de abertura é
> **replay**, e está rotulada como tal.
>
> Experimento aberto em **2026-09-08** com a derivação e a ativação auditadas de `momentum v4`
> (derivada às 13:04:37 UTC, ativada às 13:05:13 UTC). A seção "Protocolo" é escrita uma vez e
> **nunca** muda; as avaliações são **acrescentadas** abaixo, datadas. Candidata #2 do
> [[Strategy Backlog]] (T-007 do [[Registro de Tentativas]]); pai em [[EXP-0001-momentum-v1]];
> origem em [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]]. Ver [[Experiments Index]].

> [!alerta] O que esta página **não** é
> A avaliação de abertura roda sobre **a mesma janela e a mesma população que geraram a hipótese**.
> Ela descreve; não confirma nada
> ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]). O que vale como teste é a coorte
> `prospective` que começou em 2026-09-08 13:05 UTC, na janela futura reservada — e nem ela ativa
> coisa alguma sozinha.

## Hipótese (congelada)

Exigir ATR%(Wilder 14 × 15 min) ≥ **0,89%** no instante da decisão — em vez de 0,3% — deixa o custo
assumido de 20 bps consumindo no máximo ~15% do risco **nominal** de 1 R, e a expectancy líquida
hipotética do `momentum` melhora por isso. **A hipótese é sobre o efeito da correção, não sobre a
aritmética**: que 20 bps sejam 39,2% de 1 R efetivo no piso antigo é conta fechada
([[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]]); que subir o piso melhore o resultado é o que este
experimento existe para descobrir, e ele exige **janela futura reservada** — o replay de abertura
abaixo é a mesma população que gerou a suspeita.

## Protocolo (congelado na primeira ativação — nunca editar)

- **Strategy:** `strategies.key = momentum`; versão `v4` (`strategy_version_id`
  `44d106b6-bb87-40a7-85e4-fa3cb80c8060`), derivada de `v2`
  (`3e655c2a-4ef1-492b-ae80-46ec6f26321c`) por `infra/scripts/derive_variant.py` (T3.26) e ativada
  por `infra/scripts/activate_strategy_version.py` em **2026-09-08 13:05:13,558855+00**.
  `purpose = research_only`, `status = active`.
- **code_ref:** `hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c`
  — **idêntico ao do pai `v2`**. Uma variante de parâmetro roda exatamente o código que o pai rodou;
  o script recusa se o digest deste build não reproduzir o congelado.
- **params_hash / params_format:** `46635ed2bff220e687dcec2a235c8cddc0fb2669d7d262d5154dd5ba11d5a8b1` / `1`.
  O do pai é `40e1688e6b5f6385674cb47a81e542b215b320eb5643a1375f6401f5c41ac2f3` (o mesmo de `v1` e
  `v2`, [[EXP-0001-momentum-v1]]). **Um único parâmetro separa as duas populações.**
- **Parameters (`default_parameters` congelados, nada implícito):**

```json
{
  "assumed_spread_bps": "2", "atr_bars": "97", "atr_pct_max": "0.05", "atr_pct_min": "0.0089",
  "atr_period": "14", "atr_timeframe": "15m", "base_confidence": "0.5", "fee_bps": "4",
  "horizon_s": "14400", "lookback_closes": "20", "max_entry_delay_s": "120", "return_min": "0",
  "rvol_min": "1.5", "rvol_window": "96", "slippage_bps": "5", "stop_atr": "1.5",
  "target2_atr": "3", "target3_atr": "4.5", "target_atr": "1.5"
}
```

- **O que mudou em relação ao pai:** `atr_pct_min` `0.003` → `0.0089`. **Nada mais.** Verificado por
  SQL no instante da ativação: `default_parameters - 'atr_pct_min'` e `parameters_schema` são
  idênticos aos de `v2` (`t` nas duas comparações), e `params_format`, `code_ref` e o timeframe são
  os mesmos.
- **Timeframe de decisão / de outcome:** 15 min (fechamentos distintos, UTC) / 1 min.
- **Agregação e ATR:** 1 m → 15 m só com barras UTC contíguas e finais até `source_bar_close`;
  ATR = Wilder(14) de 15 min sobre `atr_bars = 97`, seed/âncora persistidos. Um minuto ausente na
  janela torna a avaliação `unavailable: gap`.
- **Entrada:** open da primeira barra de 1 min estritamente posterior a `decision_at`, com
  `entry_bar_open − source_bar_close ≤ 120 s`; geometria revalidada com `P_entry`, senão
  `no_entry: geometry`.
- **Saída:** gap na abertura primeiro, depois toques intrabar; stop e alvo na mesma barra →
  **stop**; horizonte **4 h** contado da entrada; invalidação = fechamento de 15 min abaixo da
  máxima dos 20 fechamentos anteriores (**não muda nesta variante** — é a candidata #1 do backlog e
  exige código novo, brief em `.claude/state/brief-T3.27-momentum-v2-invalidacao.md`).
- **Custos assumidos (hipóteses declaradas, não tarifas verificadas):** spread total 2 bps,
  slippage 5 bps por lado, taxa 4 bps por lado, funding assinado; `R_net = null` com motivo quando o
  funding aplicável não é apurável.
- **Política de reentrada:** um acompanhamento `pending_entry|active` por
  `(strategy_version_id, market_id, cohort)`; rearme só após barra elegível com a condição falsa
  **depois** do término anterior. **Consequência que esta variante torna visível e que precisa ser
  citada em toda comparação:** como `v4` recusa sinais que `v2` aceita, o slot de `v4` fica livre em
  instantes em que o de `v2` está ocupado — as duas populações **não** são "a mesma menos um filtro".
- **Cohort:** `prospective` (a partir de 2026-09-08 13:05:13 UTC) e
  `replay:d9f7a1f8-0a41-4315-8692-517e1d264c96` (o replay de abertura, abaixo).
- **Universo elegível:** o do `market-worker` no instante, gravado no envelope imutável de cada
  sinal. No replay, o universo é o **de hoje**, não o da janela (limitação declarada do motor,
  `docs/PIPELINE.md` §6c).
- **Markets:** Binance USDⓈ-M, perpétuos USDT, **LONG apenas**.
- **Data de início da coleta:** 2026-09-08 (prospectiva); o replay cobre 2026-08-08 → 2026-09-08.
- **Isolamento:** `purpose = research_only`; nenhuma linha em `agents` autoriza esta versão em
  carteira; a ponte de execução recusa `research_only` pelo nome e a coorte `replay:` por nome; um
  replay não escreve `shadow_outbox` (medido: 0 linhas).

## Avaliações (acrescentadas, nunca reescritas)

### Avaliação de 2026-09-08 — replay de abertura, `as_of = 2026-09-08T13:09:41Z`

**Rótulo obrigatório: isto é REPLAY, não coleta prospectiva.** Coorte
`replay:d9f7a1f8-0a41-4315-8692-517e1d264c96`, janela `2026-08-08 → 2026-09-08` (semiaberta), quatro
mercados (ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT), em duas fatias contíguas com a **mesma** coorte.
A população do pai é o replay `replay:f8d8279c-1fba-42ae-95ef-202042f96c60`, **mesma janela, mesmos
mercados, mesmo motor, mesmo `decision_lag_s = 2`**.

> [!alerta] Duas lacunas de proveniência desta avaliação, declaradas em vez de disfarçadas
> **1. O texto do SQL não foi colado.** O rascunho cita `/tmp/q7.sql` na VPS ("mesma forma do placar
> T3.18") e não trouxe a consulta. O template desta base exige o SQL literal; ele **não** está aqui,
> e por isso esta leitura é rastreável só pelos recibos do motor e pela descrição da consulta.
> Recuperar o texto de `/tmp/q7.sql` e colá-lo é entrega da **próxima** avaliação — e não se corrige
> esta seção para isso: é seção datada, e o que ela não teve, não teve.
> **2. O `read_at` não foi registrado.** Só o `as_of` (`13:09:41Z`) está declarado. Como
> `signal_outcomes` avança no lugar, sem `read_at` a leitura não é sequer descritível como snapshot;
> a partir da próxima avaliação os dois carimbos vão no título, como manda o plantão.

**Recibos (livro-razão do motor, `system_events` + JSONL `/tmp/replay-momentum-v4-piso.jsonl`):**

```
fatia 1  2026-08-08 → 2026-08-23   5 760 barras   89,841 s   64,11 barras/s   0 erros
         estados: unavailable 448 | not_triggered 5 256 | triggered 56
fatia 2  2026-08-23 → 2026-09-08   6 144 barras   94,850 s   64,78 barras/s   0 erros
         estados: not_triggered 6 120 | triggered 24
total   11 904 barras avaliadas (= 31 × 96 × 4, exatamente o planejado)
        31 sinais · 31 desfechos resolvidos · 0 abertos · 0 censurados
```

O pai, na mesma janela: 11 904 barras, `triggered` 460, **224 sinais**.

**Comandos exatos (VPS):**

```bash
docker exec -i hunter-api-1 python - momentum v2 --set atr_pct_min=0.0089 \
  --changelog 'KB-0008: piso de custo — candidata #2 do Strategy Backlog (T3.26)' \
  < infra/scripts/derive_variant.py
docker exec -i hunter-api-1 python - momentum v4 \
  --changelog 'T3.26: coorte de pesquisa da variante de piso de custo aberta (research_only, sem carteira)' \
  < infra/scripts/activate_strategy_version.py
docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.run \
  --version momentum:v4 --from 2026-08-08 --to 2026-08-23 \
  --markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT --workers 3 \
  --cohort replay:d9f7a1f8-0a41-4315-8692-517e1d264c96 \
  --ledger /tmp/replay-momentum-v4-piso.jsonl      # e a fatia 2026-08-23 → 2026-09-08
```

**Cobertura (contagens completas, as duas coortes):**

| versão | emitidos | pendentes | entradas | não entradas (motivo) | ativos | target | stop | expired | invalidated | censurados | `R_net` nulo | funding indisp. | mercados | dias |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `v2` (pai) | 224 | 0 | 224 | 0 | 0 | 91 | 45 | 6 | 82 | 0 | 2 | 2 | 4 | 24 |
| `v4` (piso) | 31 | 0 | 30 | 1 (`geometry`) | 0 | 11 | 10 | 0 | 9 | 0 | 0 | 0 | 4 | 9 |

As contagens fecham nos dois lados: `v2` 91 + 45 + 6 + 82 = 224; `v4` 11 + 10 + 0 + 9 = 30, mais a
única não entrada por `geometry` = 31 emitidos. **Nada de `unavailable` nesta coorte** — os 448
`unavailable` do recibo são barras do motor que nem chegaram a virar decisão, não sinais perdidos.

**Métricas (distintas, com denominador explícito):**

| Métrica | `v2` (pai) | `v4` (piso) | Denominador |
|---|---:|---:|---|
| Resultados avaliáveis | 222 | **30** | `terminal` com `r_multiple` não nulo |
| Dias distintos de decisão | 24 | **9** | `date(emitted_at)` |
| Taxa de alvo entre toques resolvidos | 0,6691 | **0,5238** | `target ÷ (target + stop)` — **não** é taxa de lucro |
| Taxa de lucro líquido | 0,4144 | **0,3667** | `R_net > 0` / avaliáveis |
| Expectancy líquida hipotética (R) | −0,1717 | **−0,1506** | média de `R_net` nos avaliáveis |
| Σ R positivos / Σ \|R negativos\| | 69,40 / 107,53 | **11,73 / 16,25** | — |
| Profit Factor | 0,6454 | **0,7220** | Σ pos ÷ \|Σ neg\| |
| R médio dos `target` | +0,7599 | **+1,0667** | outcomes `target` |
| R médio dos `stop` | −1,1883 | **−1,0957** | outcomes `stop` |
| R médio dos `invalidated` | −0,6462 | **−0,5884** | outcomes `invalidated` |
| MFE / MAE | **nulo (não extraído)** | **nulo (não extraído)** | esta leitura não consultou `meta.excursions`; nulo por ausência de consulta, não por OHLC indeterminado |
| **PnL de carteira** | **não aplicável** | **não aplicável** | não há carteira no Shadow Lab |
| **Max Drawdown de carteira** | **não aplicável** | **não aplicável** | idem |

A **taxa de alvo entre toques resolvidos** é razão das contagens de cobertura desta mesma leitura
(91/136 e 11/21); ela não veio de consulta própria, e está aqui porque o template a exige e omiti-la
deixaria a métrica mais fácil de confundir com a taxa de lucro sem contraditório. O Profit Factor
**não** é nulo em nenhum dos dois lados: há perdas nos dois denominadores.

**Quantas oportunidades sobram (o número que a [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]]
exigiu que fosse reportado):** 31 de 224 decisões, **−86,2%**. Pelo próprio critério dessa nota
("um piso que elimina 70% dos sinais é outra estratégia, não a mesma com menos ruído"), `v4` está
**bem acima** desse limite. Este é o achado operacional do dia.

**Decomposição do efeito — e é aqui que a leitura ingênua se desfaz:**

| Grupo | n | avaliáveis | expectancy (R) |
|---|---:|---:|---:|
| decisões de `v2` **já acima** do piso 0,0089 | 31 | 31 | **−0,2135** |
| decisões de `v2` **abaixo** do piso (as que `v4` elimina) | 193 | 191 | **−0,1650** |
| decisões de `v4` **na mesma barra e mercado** que uma de `v2` | 25 | 25 | **−0,2352** |
| decisões de `v4` **sem par** em `v2` (slot livre por rearme) | 6 | 5 | **+0,2722** |

- Nas **25 decisões pareadas** (mesmo mercado, mesma `observation_ts`), `v4` e `v2` produziram
  **exatamente o mesmo resultado e o mesmo `R_net`** — 0 divergências. É a prova de que a variante
  não mexeu em nada além do filtro: mesmo código, mesmos níveis, mesmo caminho de saída.
- Sobre a **população do próprio pai**, o subconjunto que o piso preserva teve expectancy **pior**
  (−0,2135) do que o subconjunto que ele elimina (−0,1650). Nesta janela, o piso maior **não**
  selecionou as operações melhores.
- A diferença de expectancy entre as duas coortes (−0,1717 → −0,1506) vem, portanto, das **6
  decisões que o pai nunca tomou** (5 avaliáveis, média +0,2722 R) — instantes em que o slot de `v4`
  estava livre porque ele havia recusado a operação anterior. Cinco resultados.
- O mecanismo aritmético que a KB-0008 previu **aparece** onde deveria: o `target` médio sobe de
  +0,7599 para +1,0667 R, porque os 20 bps pesam menos sobre um risco nominal maior. Isso é
  geometria medida, não vantagem demonstrada.

- **Dias distintos com outcome avaliável:** 9 (`v4`) contra 24 (`v2`).
- **Versão da métrica / proveniência:** `q7.sql` da VPS (mesma forma do placar T3.18), tabelas
  `agent_signals` + `signal_outcomes` + `strategy_versions`; recibos em `system_events`
  (`component = 'replay_engine'`). Texto do SQL não colado — ver o alerta acima.
- **Result:** **inconclusivo** — obrigatório: 30 resultados avaliáveis e 9 dias, contra o limiar
  editorial de **100 E 30**. E, mesmo que o limiar fosse atingido, **este replay não confirma nada**:
  é a mesma janela e a mesma população que produziram a hipótese
  ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]).
- **Conclusion:** as duas versões perdem na janela. O piso corta 86% das decisões, deixa uma
  amostra pequena, melhora o `R` médio dos alvos pelo motivo aritmético previsto, e **não** melhora a
  seleção: na população do pai, o lado acima do piso foi o pior dos dois. A vantagem aparente de
  0,021 R apoia-se em cinco operações que só existiram porque o slot ficou livre.
- **Next Action:** deixar a coorte `prospective` de `v4` correr ao lado da de `v2` na janela futura
  reservada, que é o que a candidata #2 do backlog sempre exigiu; reportar novamente com pelo menos
  100 avaliáveis e 30 dias; **nunca** ativar automaticamente a variante "vencedora". O diagnóstico
  por decil de ATR% (candidata #3) é o próximo passo barato e responde por que o lado acima do piso
  foi pior — a resposta pode matar esta variante sem gastar mais dia de sombra.

> [!veredito] Em uma frase
> `inconclusivo`, duas vezes: pelo limiar editorial (30 avaliáveis e 9 dias contra 100 **E** 30) e
> por construção (replay na população que gerou a hipótese). O único achado firme do dia é
> operacional: **o piso corta 86% das decisões**.

### Pendências desta página (não são avaliação; são o que a próxima avaliação tem de trazer)

1. Texto integral de `/tmp/q7.sql`, colado.
2. `read_at` junto do `as_of`, no título da seção.
3. MFE/MAE por coorte, com o motivo de cada nulo (`meta.excursions`).
4. A proporção de corte na coorte **prospectiva**, com o universo inteiro em vez de quatro mercados
   — os 86% são da janela de replay e não valem para a coleta viva.
5. A linhagem `derived_from=v2` no `changelog` da linha ativada na VPS, hoje perdida — pendência
   operacional registrada em
   [[2026-09-08-linhagem-de-momentum-v4-no-changelog-da-vps|00-INBOX: linhagem de `momentum v4`]],
   com a correção proposta e a decisão pendente do Everton.

### Próximas medições (Astra) — 2026-09-08

**Isto não é uma avaliação: nenhum número novo foi medido aqui.** É o que a revisão da Astra de
2026-09-08 ([[2026-09-08-shadow-lab-pronto]], transcrição em
`.claude/state/astra-review-lab-pronto-2026-09-08.md`) exige da **próxima** avaliação desta página,
antes de qualquer variante nova. Ela concordou com o `inconclusivo` por duas razões independentes —
30 avaliáveis / 9 dias contra 100 **E** 30, **e** o replay ser a mesma janela que gerou a hipótese —
e disse que a igualdade dos 25 pares é verificação de consistência, **não** prova de equivalência.

1. **Separar seleção de rearme.** Medir o **filtro** sobre as entradas congeladas do pai e,
   separadamente, a **trajetória completa com slots**. As 25 decisões comuns têm diferença zero;
   falta investigar as **seis decisões do pai acima do piso que não aparecem** entre essas 25, além
   das seis exclusivas da variante. A tabela pareada da avaliação de 2026-09-08 permite identificar
   essa lacuna, mas não a fecha.
2. **Medir oportunidade por tempo.** Sinais por mercado/dia, tempo ocupado, tempo exposto, motivos de
   bloqueio/rearme e soma de `R` por período sob uma convenção fixa. Média por operação **sozinha**
   não compara políticas com frequências tão diferentes — e aqui uma delas toma 86% menos decisões.
3. **Decompor custos e risco.** Resultado bruto contra líquido, custo em `R`, funding, distância do
   stop, MFE/MAE, duração e cauda negativa; estratificado por mercado, por dia e por faixas de ATR%
   **definidas previamente**.
4. **Medir dependência e influência.** Intervalo da diferença reamostrando dias/blocos comuns às duas
   versões; e análise retirando um dia/mercado por vez, mostrando a contribuição individual dos
   **cinco resultados exclusivos avaliáveis** que hoje sustentam sozinhos a vantagem aparente de
   0,021 R.
5. **Fechar proveniência e cobertura.** SQL integral colado, `as_of` **e** `read_at` no título,
   faltantes por braço e comparação prospectiva no universo comum — as mesmas lacunas que as
   Pendências acima já declaram.

**Ressalva dela, e vale como regra:** *não* usar os decis de ATR% para escolher imediatamente outro
piso na mesma amostra. Isso iniciaria **outra tentativa exploratória**, a registrar como tal no
[[Registro de Tentativas]] — não é a continuação desta.

### Avaliação de <próxima data>

<acrescente uma seção nova; não edite a anterior>

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| `atr_pct_min = 0,0089` (`momentum v4`) | 2026-09-08 | [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]], candidata #2 | esta página; `system_events` `strategy_version_variant_derived`; T-007 do [[Registro de Tentativas]] |
| invalidação (`INV-B/C/E`) | — | exige código novo (`momentum_v2`), não é parâmetro | `.claude/state/brief-T3.27-momentum-v2-invalidacao.md`; candidata #1 do [[Strategy Backlog]] |

## Relacionadas

[[Experiments Index]] · [[EXP-0001-momentum-v1]] · [[EXP-0004-politicas-de-saida]] ·
[[Strategy Backlog]] · [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] ·
[[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]] · [[Registro de Tentativas]] ·
[[2026-09-08-linhagem-de-momentum-v4-no-changelog-da-vps|00-INBOX: linhagem de `momentum v4`]]

## Fontes

`infra/scripts/derive_variant.py` · `infra/scripts/activate_strategy_version.py` ·
`services/strategy-worker/hunter_strategy_worker/replay/run.py` · `/tmp/q7.sql` (VPS) ·
`system_events` (`component = 'activate_strategy_version'`, eventos
`strategy_version_variant_derived` e `strategy_version_activated`; `component = 'replay_engine'`) ·
`/tmp/replay-momentum-v4-piso.jsonl` (dentro de `hunter-strategy-worker-1`) ·
`.claude/state/notes-T3.26.md` · `.claude/state/exp-drafts/EXP-0006-momentum-piso-de-custo.md`
