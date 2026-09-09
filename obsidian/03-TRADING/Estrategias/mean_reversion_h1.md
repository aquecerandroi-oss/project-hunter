---
tags: ["estrategia", "catalogo", "mean_reversion_h1", "familia"]
strategy: mean_reversion_h1
updated: 2026-09-09
---
# mean_reversion_h1

<!-- generated:start -->
## Versões

| Versão | Propósito | Status | Veredito | Página |
|---|---|---|---|---|
| `v1` | `research_only` | `implementado, não ativado` | sem avaliação — replay pendente. | [[mean_reversion_h1-v1]] |

## Ligações

- Convenção: [[Estrategias/README|Estratégias]]
- Família-mãe: [[mean_reversion]]
- Eixo "timeframe": [[EXP-0021-timeframe]]
<!-- generated:end -->


## Notas

**Família nova, criada pela Sexta-feira em 2026-09-09** a partir de `.claude/state/notes-T3.54.md`
§6 (T3.54, commit `eaebf8f`) e [[EXP-0021-timeframe]] (braço C1). `mean_reversion_h1_v1` é a irmã
**plana** de `mean_reversion_v1` que decide em barras de **1 h** (tendência em 4 h, ATR em 1 h,
horizonte de 16 barras) — não uma herdeira: não importa a mãe, não herda a classe dela, tem fecho de
digest isolado (`("aggregate","base","canonical","envelope","indicators","mean_reversion_h1_v1",
"numeric","schema")`) e `params_hash` próprio. Ver a página da versão para o porquê de cada uma
dessas quatro decisões.

Sem acesso ao Postgres da VPS deste host nesta sessão, esta página não pôde ser gerada por
`infra/scripts/export_strategies_to_obsidian.py` — foi reconciliada à mão a partir do código e do
EXP. O `seed --only strategies` que cria a linha `strategies.key = 'mean_reversion_h1'` ainda não
rodou.
