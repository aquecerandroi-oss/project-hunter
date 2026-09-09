---
tags: ["estrategia", "catalogo", "mean_reversion", "familia"]
strategy: mean_reversion
updated: 2026-09-08
---
# mean_reversion

<!-- generated:start -->
## Versões

| Versão | Propósito | Status | Veredito | Página |
|---|---|---|---|---|
| `v1` | `research_only` | `active` | inconclusivo — 37 avaliáveis (< 100), 11 dias; líquida +0,0938 R, PF 1,186; estresse `frágil a custos` e dependente de metade. | [[mean_reversion-v1]] |
| `v2` | `research_only` | `active` | inconclusivo — 17 avaliáveis, 7 dias; líquida +0,2998 R, PF 2,69; C4 `REJECT` (13/17 decisões em 4 dias de agosto). | [[Estrategias/mean_reversion-v2|mean_reversion-v2]] |
| `v3` | `research_only` | `active` | inconclusivo, `REVISE` no portão — 11 avaliáveis, 4 dias; líquida +0,5131 R; corte de 70,3 % dispara a régua do `EXP-0006`. | [[Estrategias/mean_reversion-v3|mean_reversion-v3]] |
| `v4` | `research_only` | `deprecated` | descartar — K1 (10 decisões); aposentada 2026-09-08T23:34:57Z, sem sucessora. | [[mean_reversion-v4]] |
| `v5` | `research_only` | `deprecated` | descartar — K1 (9 decisões), 44 % fora da banda de stop do `paper_v1`; aposentada 2026-09-08T23:34:59Z, sem sucessora. | [[mean_reversion-v5]] |
| `v6` | `research_only` | `active` | manter em pesquisa — melhor candidata do eixo "stop largo" (guarda 95 % da economia de pedágio); K1 (15 decisões). | [[mean_reversion-v6]] |
| `v7` | `research_only` | `active` | manter em pesquisa com ressalva — só 32 % da economia de pedágio sobrevive; K1 (14 decisões). | [[mean_reversion-v7]] |
| `v8` | `research_only` | `active` | inconclusivo (sinal `negativo` no corpo do EXP) — Δ −0,2006 R contra `v6`; mantida pela mensurabilidade, não pelo mérito. | [[mean_reversion-v8]] |

## Ligações

- Convenção: [[Estrategias/README|Estratégias]]
- Eixo "teto de pedágio" (v1→v2/v3): [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]]
- Eixo "stop largo" (v2→v6/v7, v3→v4/v5): [[EXP-0018-stop-largo]]
- Eixo "piso de ATR%" (v2→v8): [[EXP-0019-piso-atr]]
<!-- generated:end -->


## Notas

**Tabela de versões corrigida e ampliada (`v1` estava marcada `draft`/sem veredito, desatualizada
desde a T3.33b) pela Sexta-feira em 2026-09-08**, a partir de
[[EXP-0009-mean-reversion-pullback-em-tendencia]], `.claude/state/exp-drafts/EXP-0014-mean-reversion-teto-025.md`,
`.claude/state/exp-drafts/EXP-0015-mean-reversion-teto-020.md`, [[EXP-0018-stop-largo]],
[[EXP-0019-piso-atr]] e `.claude/state/notes-T3.47b.md`. O exportador
(`infra/scripts/export_strategies_to_obsidian.py`) não alcança o Postgres da VPS a partir deste host
nesta sessão (`ConnectionRefusedError`) — rodá-lo confirma os campos e substitui esta nota quando o
banco estiver acessível. `EXP-0014` e `EXP-0015` (as versões `v2`/`v3`) continuam como rascunhos em
`.claude/state/exp-drafts/`, não arquivados no vault; os números acima vêm deles diretamente.

