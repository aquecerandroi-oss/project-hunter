---
tags: [experimento, momentum, paper-trading, d10]
updated: 2026-09-08
status: em-andamento
owner: sexta-feira
exp: EXP-0005
strategy: momentum
version: v3
result: inconclusivo
evaluable: 30
days: 1
last_eval: 2026-09-08
---

# EXP-0005 — momentum v1 em carteira paper (D10)

> Experimento aberto em **2026-09-08** pela decisão delegada **D10** do Everton
> (`.claude/state/decisions-delegated-2026-09-07.md`). A linha paper do `momentum v1`
> nasce como **linha nova e congelada** com `purpose = paper`, ao lado da coorte
> `research_only` do [[EXP-0001-momentum-v1]] — assim o mesmo gatilho fica medido
> pelas barras (EXP-0001) e pela carteira (EXP-0005), e dá para comparar. A
> ativação é ato auditado (`infra/scripts/activate_strategy_version.py --paper-line`)
> e **continua sendo decisão do Everton**: sete condições em `docs/plans/M3.md`
> (D10) precisam ser cumpridas antes. A seção "Hipótese" e a seção "Protocolo"
> são escritas uma vez e **nunca** mudam; as avaliações são **acrescentadas**
> abaixo, datadas. Ver [[Experiments Index]], [[EXP-0001-momentum-v1]],
> [[Risk Engine]] e `docs/plans/M3.md` (D10).

> [!decisao] Quem decide, e o que já está decidido
> **D10** (Everton, delegada em 2026-09-07): a linha paper sai do `momentum`, nasce **nova e
> congelada**, com a coorte `research_only` do [[EXP-0001-momentum-v1]] intocada ao lado.
> **Ativar continua sendo dele** — sete condições escritas em `docs/plans/M3.md`, e a ativação é ato
> auditado (`infra/scripts/activate_strategy_version.py --paper-line`). Nenhum plantão ativa isto
> porque um número ficou bonito.

> [!medido] O que já foi medido nesta linha
> **Até 2026-09-08 (madrugada): nada, e por um motivo mecânico** — a coorte paper não existia no
> banco; ela só nasceria quando a migração `0010` (`6b837ac`) chegasse à VPS e a versão fosse
> ativada. Era o estado com `evaluable = 0`, `days = 0`, `result = nao-iniciado`.
> **Desde 2026-09-08 05:57:30Z a linha existe e emite:** o Everton ativou a `v3` (`purpose = paper`)
> pelo caminho auditado, e o plantão do meio-dia registrou a primeira avaliação datada — **30**
> outcomes avaliáveis em **1** dia, `result = inconclusivo`. A carteira continua intocada
> (`ENABLE_PAPER_AUTONOMY=false`; 0 propostas, 0 posições, 0 trades). O frontmatter e a Base
> `Experimentos.base` seguem esses números.

> [!alerta] Divergência de numeração entre o Protocolo congelado e o catálogo
> O Protocolo abaixo, escrito em 2026-09-08 e **imutável**, chama a linha paper de **`v1` com
> `purpose = paper`**. O catálogo de estratégias exportado do banco por T3.20 a registra como
> **`v3`** ([[momentum-v3-paper]], `derived_from: [[momentum-v2]]`). É a **mesma linha** — mesmo
> `params_hash` (`40e1688e…c41ac2f3`), mesmo `code_ref` da v2 —, só numerada de formas diferentes
> pelos dois registros. O frontmatter desta página usa `version: v3`, que é o que existe no
> catálogo; o Protocolo **não foi editado** e não será. Quando a linha for ativada, o `activated_at`
> da versão `v3` é a data de início da coleta.

## Hipótese (congelada)

Sobre as **mesmas entradas** do `momentum v1` já medidas pelo Shadow Lab em
[[EXP-0001-momentum-v1]] — mesmo gatilho, mesmos parâmetros, mesmo `code_ref` —,
a execução paper numa carteira real (perfil `paper_v1`, SPOT only, custos SPOT
declarados) produz uma diferença de `R_net` por sinal em relação ao `R_net`
hipotético do Shadow Lab que é **menor que 0,05 R** em mediana, e essa diferença
sobrevive a Holm a 5% sobre a família de contrastes entrada-a-entrada. Se a
diferença for maior, ela é explicável pela geometria da execução real (slippage,
reserva vencida, stop tocado intrabar, funding) e não por defeito do instrumento.

## Protocolo (congelado — nunca editar)

- **Strategy:** `strategies.key = momentum`; versão `v1` com `purpose = paper`
  (linha nova e congelada, ativada por `activate_strategy_version.py --paper-line`;
  a coorte `research_only` do [[EXP-0001-momentum-v1]] permanece viva ao lado,
  intocada).
- **code_ref:** `hunter_core.strategies.momentum_v1@sha256:…` — o mesmo módulo
  do [[EXP-0001-momentum-v1]]; o digest é o da árvore inteira após a normalização
  CRLF→LF (ver [[Open Bugs]], HIGH do `code_ref` não portátil).
- **params_hash / params_format:** `40e1688e…c41ac2f3` / `1` — idêntico ao
  EXP-0001 (`default_parameters` e `parameters_schema` bit a bit os mesmos).
- **Parameters (`default_parameters` congelados, nada implícito):**

```json
{
  "assumed_spread_bps": "2", "atr_bars": "97", "atr_pct_max": "0.05", "atr_pct_min": "0.003",
  "atr_period": "14", "atr_timeframe": "15m", "base_confidence": "0.5", "fee_bps": "4",
  "horizon_s": "14400", "lookback_closes": "20", "max_entry_delay_s": "120", "return_min": "0",
  "rvol_min": "1.5", "rvol_window": "96", "slippage_bps": "5", "stop_atr": "1.5",
  "target2_atr": "3", "target3_atr": "4.5", "target_atr": "1.5"
}
```

- **Carteira:** `portfolio_id = 01a07a1e-f6ae-7366-a7fe-ab3d9c83d488` (org `ever`,
  `type = paper`, `base_currency = USDT`, aberta em 2026-09-07 04:27:24Z com
  R$ 100.000 → 19.333,0111164813 USDT a 5,1725). Ver [[Portfolio]].
- **Risk Engine:** perfil `paper_v1` (contrato v2.2.1, `docs/RISK_ENGINE.md`).
  `evaluate` e `evaluate_exit` com `paper_v1`; kill switch durável com transição
  auditada; participação de 1 % do minuto medida no venue de execução (D2);
  execução no spot, decisão pelo perpétuo, basis registrado por fill (D1).
- **Spot only:** `MARKET_SPOT_ENABLED` e `ENABLE_PAPER_AUTONOMY` permanecem
  `false` até a ativação auditada; SPOT only, sem alavancagem, sem perpétuo na
  execução. A ponte sinal → admissão (T3.14) só cria o grupo de consumo quando
  `ENABLE_PAPER_AUTONOMY = true`, e só admite sinais com `purpose = paper`
  (T3.15b, `56d2dea`); `research_only` e `live` são recusados por nome.
- **Custos SPOT declarados (hipóteses, não tarifas verificadas):** spread total
  2 bps, slippage 5 bps por lado, taxa 4 bps por lado, funding assinado.
  `AssumedCosts(spread_bps=2, slippage_bps=5, fee_bps=4)` em `Decimal` —
  `float` é aceito pelo construtor ([[Open Bugs]]) mas não entra no `code_ref`.
- **Timeframe de decisão / de outcome:** 15 min (fechamentos distintos, UTC) /
  1 min — idêntico ao EXP-0001.
- **Entrada:** open da primeira barra de 1 min estritamente posterior a
  `decision_at`, com `entry_bar_open − source_bar_close ≤ 120 s`
  (`max_entry_delay_s`); senão `no_entry: late:*`. Geometria revalidada com
  `P_entry` (`stop < P_entry < target1`), senão `no_entry: geometry`. A entrada
  paper admite reserva viva e slippage real do livro spot; a entrada do Shadow
  Lab é hipotética.
- **Saída:** gap na abertura primeiro, depois toques intrabar; stop e alvo na
  mesma barra → **stop** (convenção pessimista); prioridade `stop > target >
  expired > invalidated`; horizonte **4 h** contado da entrada. A saída paper
  executa no livro spot; a do Shadow Lab é hipotética.
- **Métricas com denominador:** `R_net` por sinal (lucro líquido / risco);
  `taxa_alvo` = `target / (target + stop)`; `taxa_lucro` = `R_net > 0` /
  avaliáveis; `expectancy_R` = média de `R_net`; `profit_factor` = Σ R+ / |Σ R−|;
  `PnL_carteira` e `max_drawdown` **são aplicáveis** aqui (há carteira, ao
  contrário do Shadow Lab).
- **Limiar editorial:** abaixo de **100 outcomes avaliáveis E 30 dias distintos**,
  o campo `Result` só pode ser `inconclusivo`. Acima disso continua sendo
  pesquisa, nunca promessa.
- **Cohort:** `paper` (linha nova, `purpose = paper`; não `prospective`, não
  `replay`). A coorte `prospective` do [[EXP-0001-momentum-v1]] é **outra
  população** e não se soma nem se continua.
- **Universo elegível:** top 50 por volume 24 h do `market-worker`, com a
  composição do instante gravada no envelope de cada sinal; `tracking_hold`
  mantém a coleta de um mercado excluído enquanto houver acompanhamento aberto.
- **Markets:** Binance USDS-M, perpétuos USDT para a **decisão**, spot USDT para
  a **execução** (D1: spot executa, perpétuo decide). LONG apenas.
- **Isolamento:** todo sinal carrega `purpose = paper` e é admitido pela ponte
  (T3.14/T3.15b) quando `ENABLE_PAPER_AUTONOMY = true`. Nada é ordenado antes da
  ativação auditada e da decisão do Everton.
- **Data de início da coleta:** **a definir** — a linha paper nasce quando a
  migração `0010` (`6b837ac`) chegar à VPS no segundo deploy e o Everton ativar
  a versão com `--paper-line`. A data de início da coleta é o `activated_at` da
  linha `purpose = paper` em `strategy_versions`.

## Avaliações (acrescentadas, nunca reescritas)

### Avaliação de <próxima data>

<acrescente uma seção nova; não edite a anterior>

Nenhuma avaliação ainda. A coorte paper não existe no banco até a ativação
auditada pela decisão do Everton (D10, sete condições em `docs/plans/M3.md`).

> [!veredito] Resultado corrente
> **`nao-iniciado`** — não é "inconclusivo", que é o veredito de quem mediu e não pôde concluir.
> Aqui não houve medição nenhuma porque a população não existe. Abaixo de **100 outcomes avaliáveis
> E 30 dias distintos** o campo `Result` só poderá ser `inconclusivo`; acima disso continua sendo
> pesquisa, nunca promessa.

### Avaliação de 2026-09-08 (plantão do meio-dia) — **primeira** — `as_of = 2026-09-08T12:00:00Z`, `read_at = 2026-09-08T12:34:22.305724Z`

**A linha paper nasceu.** O Everton ativou a versão em **2026-09-08 05:57:30.922979+00** pelo
caminho auditado (`strategy_version_activated`, changelog congelado
`D10_coorte_paper_ativada_por_Everton_2026-09-08`) — 02:57 de Brasília. `momentum v3`,
`purpose = paper`, `status = active`,
`code_ref = hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c`
(o mesmo da `v2` de pesquisa), `params_hash = 40e1688e…c41ac2f3`. Primeiro sinal às **06:00:09.802884Z**.

**Duas divergências entre o Protocolo congelado e o que o banco fez — registradas, não corrigidas.**

1. O Protocolo diz `Cohort: paper`. No banco os 154 sinais da `v3` saem com
   `supporting_features->>'cohort' = 'prospective'` e `purpose = 'paper'`. Quem separa a população
   é o `strategy_version_id` (que entra no `uuid5` de cada sinal) e o `purpose`, não o rótulo de
   coorte. O Protocolo **não foi editado** e não será; fica aqui a leitura correta do filtro.
2. O Protocolo diz que `PnL_carteira` e `max_drawdown` **são aplicáveis** aqui. Neste corte eles
   **não são**, por um motivo mecânico medido abaixo: nada chegou à carteira.

**Semântica do corte.** Idêntica às EXP-0001/0002 deste turno: população congelada por
`decision_at <= as_of`, estados num único snapshot `REPEATABLE READ READ ONLY` em `read_at`, gate de
avaliável = `is_evaluable()` da S3a. **Não é reconstruível.**

**SQL usado:** `/tmp/p0908a.sql` (inventário de versões), `/tmp/p0908b.sql` (cobertura e métricas —
texto integral colado na [[EXP-0001-momentum-v1]]), `/tmp/p0908d.sql` (excursões),
`/tmp/p0908h.sql` (contribuição de R) e `/tmp/p0908g.sql` (carteira), todos por
`ssh hunter-vps` → `docker exec hunter-postgres-1 psql -f …` com o mesmo `as_of`.

**Saída real (colada):**

```
   key    | version |   status   | purpose |         activated_at          | deprecated_at
----------+---------+------------+---------+-------------------------------+---------------
 momentum | v3      | active     | paper   | 2026-09-08 05:57:30.922979+00 |

   key    | version | purpose |   cohort    | count
----------+---------+---------+-------------+-------
 momentum | v3      | paper   | prospective |   154

   key    | version |   cohort    | emitidos | pendentes | entradas | ne_late_delay | ne_geometry | ne_outros | ativos | target | stop | expired | invalidated | censurados | funding_indisp | mercados | dias_decisao
----------+---------+-------------+----------+-----------+----------+---------------+-------------+-----------+--------+--------+------+---------+-------------+------------+----------------+----------+--------------
 momentum | v3      | prospective |      143 |         0 |      143 |             0 |           0 |         0 |      2 |     41 |   44 |       1 |          55 |          0 |             10 |      110 |            1

   key    | version |   cohort    | avaliaveis | funding_nao_liquidavel | aval_target | aval_stop | aval_invalidated | aval_expired | taxa_alvo_toques | taxa_lucro_liquido | expectancy_r | soma_r  | soma_r_pos | soma_r_neg_abs | profit_factor | mat_avaliaveis | mat_dias
----------+---------+-------------+------------+------------------------+-------------+-----------+------------------+--------------+------------------+--------------------+--------------+---------+------------+----------------+---------------+----------------+----------
 momentum | v3      | prospective |         31 |                      1 |          11 |        11 |                8 |            1 |           0.5000 |             0.3667 |      -0.2550 | -7.6491 |     8.2923 |        15.9414 |        0.5202 |             30 |        1

   key    | version |   cohort    | outcomes | mfe_nulo | mae_nulo
----------+---------+-------------+----------+----------+----------
 momentum | v3      | prospective |      143 |       44 |       46

   key    | version |   cohort    |           primeiro            |            ultimo             | dias_emissao
----------+---------+-------------+-------------------------------+-------------------------------+--------------
 momentum | v3      | prospective | 2026-09-08 06:00:09.802884+00 | 2026-09-08 11:46:02.861196+00 |            1

-- carteira (/tmp/p0908g.sql)
 trade_proposals | positions | trades
-----------------+-----------+--------
               0 |         0 |      0
```

**A carteira não foi tocada, e o motivo é uma variável de ambiente.** No `execution-worker` da VPS,
`ENABLE_PAPER_AUTONOMY=false` (lido em 12:41Z). A ponte sinal → admissão só cria o grupo de consumo
quando essa chave é `true`; com ela desligada, os 154 sinais `purpose = paper` são emitidos,
acompanhados e precificados pelo Shadow Lab, e **nenhum** vira proposta. Confirmado pelos três
zeros acima e pelo heartbeat `hb:execution:paper`:

```
equity                19333.0111164813
kill_switch           ACTIVE
open_positions        0
pending_requests      0
unreadable_requests   0
```

`kill_switch = ACTIVE` é o estado **menos restritivo** da escala
(`ACTIVE < WARNING < TRADING_DISABLED < EMERGENCY`, `hunter_core.domain.enums`) — não é alarme.
A equity está intacta nos 19.333,0111164813 USDT da abertura.

**Cobertura.** 2 ativos + 41 + 44 + 1 + 55 = **143**, fecha. Zero pendente, zero recusa de entrada,
zero censura, 110 mercados, 1 dia, janela de emissão 06:00:09Z → 11:46:02Z.

**Métricas (denominador em cada linha):**

| Métrica | Valor | Denominador |
|---|---|---|
| taxa de alvo entre toques resolvidos | **0,5000** | 11 target + 11 stop = 22 toques resolvidos |
| taxa de lucro líquido | **0,3667** | 30 avaliáveis com `R_net` (11 com `R_net > 0`) |
| expectancy líquida hipotética em R | **−0,2550** | os mesmos 30 |
| profit factor | **0,5202** | 8,2923 / 15,9414 |
| soma de R hipotético | **−7,6491** | 30; soma escalar, **não é equity** |
| MFE/MAE | `mfe` nulo em 44 de 143, `mae` nulo em 46 | toda a coorte |
| **PnL de carteira** | **não aplicável neste corte** | 0 trades, 0 posições, 0 propostas |
| **Max Drawdown de carteira** | **não aplicável neste corte** | idem |

**Contribuição de R por resultado (30 avaliáveis com `R_net`):**

| Resultado | n | Média R | Soma R | Mín | Máx |
|---|---|---|---|---|---|
| `target` | 10 | +0,8164 | +8,1641 | +0,3639 | +1,1553 |
| `stop` | 11 | −1,1106 | −12,2165 | −1,2958 | −1,0315 |
| `expired` | 1 | +0,1283 | +0,1283 | +0,1283 | +0,1283 |
| `invalidated` | 8 | −0,4656 | −3,7249 | −0,8118 | −0,2654 |

10 + 11 + 1 + 8 = **30**, fecha.

**A `v3` é um sub-recorte da `v2`, e dá para ver.** Mesmo código, mesmos parâmetros, mesmos
mercados; a `v2` começou às 04:45Z e a `v3` às 06:00Z. Os extremos de R coincidem exatamente
(`target` máx +1,1553 dentro do +1,6818 da v2; `stop` mín −1,2958 nas duas; `expired` +0,1283 nas
duas; `invalidated` −0,8118/−0,2654 nas duas). Não são duas hipóteses: são a mesma hipótese com
menos horas. Comparar −0,2550 R (v3, 30 resultados) com −0,1363 R (v2, 49) seria comparar uma
amostra com o conjunto que a contém.

- **Maturação:** 31 avaliáveis, 1 sem `R_net` por funding → **30** nas métricas de R, em **1** dia.
- **Result:** **inconclusivo.** 30 outcomes avaliáveis em 1 dia, contra o limiar de 100 **E** 30
  dias. Falham os dois lados. Não é mais `nao-iniciado` porque agora **houve** medição.
- **Conclusion:** a hipótese congelada desta página — que a diferença de `R_net` entre a execução
  paper e o Shadow Lab fique abaixo de 0,05 R em mediana — **não foi testada e não pôde ser**, porque
  não existe execução paper: com `ENABLE_PAPER_AUTONOMY=false` os dois lados do contraste são o
  mesmo lado. O que esta avaliação de fato prova é operacional e vale registrar: a linha paper foi
  criada e ativada pelo caminho auditado, emite sob `purpose = paper`, e **nada** dela chegou à
  carteira — que é exatamente o comportamento projetado enquanto a chave está desligada.
- **Next Action:** nenhuma automática. Ligar `ENABLE_PAPER_AUTONOMY` em produção é **decisão do
  Everton** (`CLAUDE.md`, lista do que só ele decide), com as condições de [[Open Bugs]] cumpridas
  antes. Enquanto isso, uma avaliação por plantão, e as duas linhas de `PnL de carteira` continuam
  em "não aplicável".

## Relacionadas

[[Experiments Index]] · [[EXP-0001-momentum-v1]] · [[Risk Engine]] · [[Portfolio]] ·
[[Paper Trading]] · [[Execution Engine]] · [[Open Bugs]] ·
`docs/plans/M3.md` (D10, D1, D2) · `.claude/state/decisions-delegated-2026-09-07.md` ·
`docs/RISK_ENGINE.md` v2.2.1

## Fontes

`docs/plans/M3.md` (D10–D13) · `.claude/state/decisions-delegated-2026-09-07.md` ·
`packages/core/hunter_core/strategies/momentum_v1.py` ·
`infra/scripts/activate_strategy_version.py` ·
`docs/RISK_ENGINE.md` v2.2.1 (contrato) ·
`docs/decisions/0005-carteira-virtual-e-risk-engine-paper-v1.md` (ADR)
