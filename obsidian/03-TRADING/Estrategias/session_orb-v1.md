---
tags: ["estrategia", "catalogo", "session_orb"]
strategy: session_orb
version: v1
purpose: research_only
status: deprecated
code_ref: "hunter_core.strategies.session_orb_v1@sha256:a4d514adeb0771d5ae23303878fb4fdac734721d6ac0140801c88d617e878bba"
params_hash: cdb9516b293276095f4a8c2210d60ade0a4448cac46cce827f58bc3f8908d5e0
activated_at: "2026-09-08T19:42:56.116683+00:00"
deprecated_at: "2026-09-09T14:59:24.592397+00:00"
derived_from: ""
cohorts: ["replay:3fb9dda2-256f-49af-9a1e-7ec5bd001d19", "prospective"]
exp: ["[[EXP-0010-session-orb-faixa-de-abertura]]"]
updated: 2026-09-09
---
# session_orb v1 (research_only, deprecated)

## Parâmetros

21 chaves congeladas em `.claude/state/brief-T3.33c-session_orb_v1.md` §7, incluindo as três horas de
abertura em UTC (Ásia 00:00, Europa 07:00, EUA 13:00). Valores citados no corpo do
[[EXP-0010-session-orb-faixa-de-abertura]]: `range_bars = 4` (a primeira hora define a faixa),
`session_window_bars = 20` (a sessão dura 5 h), `rvol_min = 1,3`, `atr_pct_min = 0,006` /
`atr_pct_max = 0,05`, `range_risk_atr_min = 1,0` / `range_risk_atr_max = 2,5`, alvo em **2 R
nominais** (não em ATR — ver a geometria na página do EXP), stop na mínima da faixa, sem invalidação
separada (a mínima da faixa **é** o nível estrutural). Tabela completa não reproduzida aqui — ver o
Protocolo congelado de [[EXP-0010-session-orb-faixa-de-abertura]].

## Origem

**Changelog:** família nova no catálogo (`infra/scripts/seed_reference.py`, T3.33c, commit
`3ed17bb`). Ativada em **2026-09-08T19:42:56,116683Z** (16:42:56 Brasília), `code_ref` conferido no
`--dry-run` antes da escrita. **Aposentada pela via auditada em 2026-09-09T14:59:24Z** (T3.56),
sem sucessora.

## Coortes e sinais

| Coorte | Sinais (`agent_signals`) |
|---|---|
| `replay:3fb9dda2-256f-49af-9a1e-7ec5bd001d19` | 20 (replay de 31 d × 4 mercados, 11 904 barras, 0 erros) |
| `prospective` | 31 avaliáveis na leitura do T3.56 (`as_of` 2026-09-09T14:52Z) |

## Avaliações

As avaliações datadas ficam na página de experimento, nunca duplicadas aqui:

- [[EXP-0010-session-orb-faixa-de-abertura]] — replay do dia um (T3.33g): 20 decisões, 9 dias,
  líquida −0,1928 R, PF 0,662; as três sessões (Ásia/Europa/EUA) dividiram a amostra 30/35/35 % —
  a regra dos 70 % **não** dispara — e perderam com expectancy **indistinguível entre si**, o que
  esvazia a hipótese de sessão pelo outro critério da mesma página.

**Veredito da aposentadoria (T3.56, `as_of` 2026-09-09T14:52Z):** negativa nas duas coortes — replay
−0,1928 R (n=20, sem mudança desde a T3.33g), prospectiva **−0,0266 R (n=31)**. K1 (população mínima
de 30) dispara nas duas. **É a única das sete aposentadorias do T3.56 que o próprio quant-engineer
registrou não defender só pelo número** — n=31 sobre −0,027 R é ruído, não veredito; a direção
(negativa) se mantém, mas a magnitude do brief original (−0,51 R) não reproduz mais. Se a versão
voltar, o caminho é uma `v2` com protocolo e `n` mínimo declarados antes de olhar, não reativar
esta.

## Replicação

não iniciada — ver `docs/plans/REPLICATION.md` quando existir (T3.19).

## Ligações

- Família: [[session_orb]]
- Experimento: [[EXP-0010-session-orb-faixa-de-abertura]]
- Conhecimento: [[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]] ·
  [[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]]

## Notas

Página criada à mão pela Sexta-feira em 2026-09-09 a partir de
[[EXP-0010-session-orb-faixa-de-abertura]] e `.claude/state/notes-T3.56.md` §5.6 e CONCERN 1 — o
host local não alcança o Postgres da VPS (`export_strategies_to_obsidian.py --dry-run` falha com
`ConnectionRefusedError`). Esta é a primeira página desta família no catálogo; ela foi ativada,
replayada e aposentada sem nunca ter tido uma página própria — a lacuna é registrada, não escondida.
