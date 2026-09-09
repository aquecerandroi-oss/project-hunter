---
tags: ["estrategia", "catalogo", "mean_reversion_h1"]
strategy: mean_reversion_h1
version: v1
purpose: research_only
status: "implementado, não ativado — precisa de SHADOW_CONTEXT_MINUTES ≥ 5820 (recomendado 5880) por versão"
code_ref: "hunter_core.strategies.mean_reversion_h1_v1"
params_hash: "985316dde26224666176645749cfae0b7bcba2a8f7300ef0c98f31cb735c53d3"
activated_at: ""
deprecated_at: ""
derived_from: ""
cohorts: []
exp: ["[[EXP-0021-timeframe]]"]
updated: 2026-09-09
---
# mean_reversion_h1 v1 (research_only, implementado — replay pendente)

## Parâmetros

Só três chaves diferem do contrato congelado da mãe (`mean_reversion_v1`), provado por teste
(`test_exactly_three_parameters_differ_from_the_mother`):

| Parâmetro | Mãe (`mean_reversion_v1`) | Esta versão | Descrição |
|---|---|---|---|
| `trend_timeframe` | `1h` | `4h` | timeframe da porta de tendência (SMA das 20 barras anteriores) |
| `atr_timeframe` | `15m` | `1h` | timeframe do ATR de referência |
| `horizon_s` | `14400` (4 h) | `57600` (16 h) | prazo esperado de saída |

**Por que `trend_timeframe = 4h` e não `1h`:** com decisão e tendência na mesma grade, a porta
("fechamento acima da SMA das 20 barras anteriores") e o gatilho ("fechamento ≥ 1 desvio abaixo da
média das 20 barras, ela inclusa") olham a **mesma** janela e se contradizem — a versão nunca
dispararia. A mãe mede tendência no timeframe 4× o da decisão dela; esta faz o mesmo. Todos os
demais parâmetros (z-score de 20 barras, `zscore_depth_min`, custos assumidos, `stop_atr`,
`target_atr`, `target2_atr`) são **idênticos** aos da mãe.

## Origem

**Changelog:** T3.54 (código, commit `eaebf8f`) — módulo plano (348 linhas), 35 testes próprios com
valores exatos escritos à mão, incluindo a prova de não-antecipação (mutar a barra em formação nunca
move a decisão) e o irmão estrutural para a barra de 4 h em formação. `registry.py` (+2 linhas,
fora do fecho de qualquer estratégia) e `constraints_table.py` (+25 linhas) atualizados no mesmo
commit; `infra/scripts/seed_reference.py` ganhou a linha `mean_reversion_h1` (+7 linhas) mas o
`seed --only strategies` que a materializa no banco **ainda não rodou**.

**Quatro decisões de desenho que valem estar registradas** (`.claude/state/notes-T3.54.md` §6.2):

1. Não importa a classe nem o módulo da mãe — o fecho de digest tem de poder divergir sem mover o
   `code_ref` de `mean_reversion_v1` nem de nenhuma versão viva.
2. Não herda a classe: as evidências do envelope da mãe se chamam `close_15m`/`zscore_15m`; herdá-las
   carimbaria uma barra de 1 h com o nome `_15m`.
3. `trend_timeframe = 4h`, não `1h` (ver acima).
4. `_TIMEFRAME_PARAM` local, com `4h`: `schema.TIMEFRAME_PARAM` só aceita `1m/5m/15m/1h` e está
   **dentro do fecho** de `momentum_v1`, `volume_anomaly_v1` e da mãe — acrescentar `4h` lá moveria
   o `code_ref` de toda versão ativada na VPS, linha `paper` inclusive. Pego por
   `test_the_frozen_defaults_validate_against_their_own_schema` antes de qualquer commit.

## Por que não está ativada

`SHADOW_CONTEXT_MINUTES` era, até 2026-09-09 de madrugada, uma constante única do processo
(`1560` min, dimensionada para a mãe). Esta versão precisa de **5 820 min** (recomendado **5 880**,
uma barra de folga) para o ATR de 97 barras de 1 h e a tendência de 21 barras de 4 h caberem sem
`atr_warmup`. **O bloqueio operacional foi removido no mesmo dia** pelo commit `d21a11d` (T3.52/b/c):
a janela de contexto passou a ser `required_context_minutes` **por versão**, com piso 1 560 e teto
`SHADOW_CONTEXT_MAX_MINUTES = 6000` — 5 880 cabe dentro do teto novo. **O que falta** é o passo
operacional: `seed --only strategies`, ativação e replay de 31 dias em 12–16 mercados (só 16 têm
histórico completo — ver [[EXP-0021-timeframe]] §2.1), bootstrap de blocos por dia contra
`mean_reversion v10`.

## Avaliações

Nenhuma ainda. Ver [[EXP-0021-timeframe]] §"Pré-registro para a próxima rodada", item 1 — a predição
declarada antes de rodar é **mesma expectativa por decisão, mais população** (o argumento é o mesmo
que levou `mean_reversion v10`, na grade de 1 h com `atr_bars` encolhido, de 15 a 54 decisões).

## Replicação

não iniciada — ver `docs/plans/REPLICATION.md` quando existir (T3.19).

## Ligações

- Família: [[mean_reversion_h1]]
- Família-mãe (código-fonte, não herança): [[mean_reversion]]
- Experimento: [[EXP-0021-timeframe]]

## Notas

Página criada à mão pela Sexta-feira em 2026-09-09 a partir de `.claude/state/notes-T3.54.md` §6 e
[[EXP-0021-timeframe]] — sem acesso ao Postgres da VPS deste host nesta sessão, e a linha não existe
no banco ainda (`seed --only strategies` pendente). `params_hash` acima é o valor de 64 caracteres
citado no código-fonte (`test_frozen_params_hash`), não uma leitura do banco.
