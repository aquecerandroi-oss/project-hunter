# notes-T3.33h — as avaliações do dia um, a morte da EXP-0011 na pré-checagem e as linhas de tendência entram no Obsidian

**Data:** 2026-09-08 · **Dona:** sexta-feira · **Base:** `main` em `bef3ee7` (HEAD ao terminar:
`9e1e0c9`, o commit do próprio brief) · **Nada commitado.** Escopo de escrita: **só `obsidian/**`**
(inclusive `obsidian/attachments/trendlines/`, seis PNGs copiados). Nenhum `.env*` tocado, nenhum
comando em segundo plano, nenhum `git stash/checkout --/restore/reset/clean/commit -a`.

## STATUS

`DONE`. Os oito itens do brief entregues; o linter da base fecha **verde** (saída real abaixo).

| Item do brief | Resultado |
|---|---|
| 1. EXP-0008/0009: avaliação datada (REPLAY), portão C1–C8, `result`, linhagem, T-035/T-036 | **OK** |
| 2. EXP-0011: `bloqueado-por-precheck`, tabela da pré-checagem, ~2026-10-06, T-038 "não iniciada" | **OK** |
| 3. EXP-0010: portão C1–C8 (REVISE 62,5) e teto de pedágio 0,3333 R; avaliação **pendente** | **OK** |
| 4. KB-0077 em `11-KNOWLEDGE/` com as 6 figuras embutidas + índice da KB | **OK** (número 0077 estava livre) |
| 5. `Strategy Backlog`: B1–B6 e a lembrança de V1/V2 não derivadas | **OK** |
| 6. `Diario/2026-09-08.md`: bloco novo do plantão da tarde | **OK** |
| 7. `Open Bugs`: os três novos | **OK** |
| 8. `obsidian_lint.py` verde | **OK** — exit 0 |

## FILES

**Modificados (10) e criados (1 nota + 6 figuras), todos em `obsidian/**`:**

| arquivo | o quê |
|---|---|
| `obsidian/05-EXPERIMENTS/EXP-0008-breakout-compressao-de-volatilidade.md` | frontmatter (`status: em-andamento`, `result: inconclusivo`, `last_eval`), portão C1–C8 preenchido (REVISE 66,0) marcado como **autoavaliação do quant**, seção do teto de custo (0,2921 R no piso, 29,2 % > 25 %), **avaliação datada de 2026-09-08 (REPLAY)**, linha de variante `breakout v2` |
| `obsidian/05-EXPERIMENTS/EXP-0009-mean-reversion-pullback-em-tendencia.md` | frontmatter (`evaluable: 37`, `days: 11`, `result: inconclusivo`), portão C1–C8 (REVISE 65,5) + divergência de fórmula do `z` registrada, teto de pedágio 0,3333 R, **avaliação datada de 2026-09-08 (REPLAY)** completa, duas variantes propostas |
| `obsidian/05-EXPERIMENTS/EXP-0010-session-orb-faixa-de-abertura.md` | `status: em-andamento`, portão C1–C8 (REVISE 62,5) com as quatro divergências, teto de pedágio (0,3333 R / 0,0160 R) e tabela de geometria; avaliação **pendente** (T3.33f), `result` continua `nao-iniciado` |
| `obsidian/05-EXPERIMENTS/EXP-0011-derivatives-reversao-de-funding.md` | `status: bloqueado-por-precheck`, portão C1–C8 (REVISE 63,5) com o limite do próprio portão, teto 0,1667 R, **avaliação datada da pré-checagem** com as 5 saídas SQL verbatim, `Next Action` em três caminhos |
| `obsidian/05-EXPERIMENTS/Experiments Index.md` | acréscimo datado + as 8 linhas de tabela das quatro (índice, não página de experimento) |
| `obsidian/07-BUGS/Open Bugs.md` | seção nova com 3 bugs (replay sem motivo por barra · `market_regimes` com 1 linha · `test_isolation` sem `/risk/limits`) |
| `obsidian/09-OPERATIONS/Diario/2026-09-08.md` | bloco "Plantão da tarde" (deploys, o primeiro líquido positivo, seed pendente, piso 0,006) |
| `obsidian/11-KNOWLEDGE/Index.md` | linha da KB-0077 na tabela de notas + tema "análise técnica clássica" |
| `obsidian/11-KNOWLEDGE/Registro de Tentativas.md` | acréscimo datado: T-035/T-036 com início = ativação, T-037 sem início, T-038 "não iniciada — pré-checagem"; multiplicidade 3 → 5 |
| `obsidian/11-KNOWLEDGE/Strategy Backlog.md` | acréscimo datado com B1–B6 e o achado do piso 0,006 |
| `obsidian/11-KNOWLEDGE/KB-0077-linhas-de-tendencia.md` | **nova** — regras, parâmetros, 6 figuras, §7 "o que um humano traçaria diferente", 3 correções da Astra, §9 o ponto aberto da T3.34b |
| `obsidian/attachments/trendlines/*.png` | **6 novas** — cópias de `.claude/state/design/trendlines/` (originais intactos) |

**Não tocados:** tudo fora de `obsidian/**`. `git status` confirma que os arquivos modificados em
`services/`, `packages/`, `docs/` e `.claude/` são de outras tarefas em voo, não desta.

## LINT (saída real)

```
$ uv run python infra/scripts/obsidian_lint.py
LINT DA BASE OBSIDIAN — 193 NOTA(S) ANALISADA(S)
Resumo — Links mortos: 0, Links ambíguos: 0, Notas órfãs: 0, Frontmatter incompleto: 0,
Valores fora do vocabulário: 0, Procedência da Knowledge Base (KB-*): 0,
Reescrita de experimentos (append-only): 0.

RESULTADO: base limpa
exit=0
```

Duas checagens que o linter faz e que valem citar: **append-only** (nenhuma seção `### Avaliação de
<data>` existente foi removida ou reescrita — as novas são acrescentadas) e **notas órfãs** (a
KB-0077 é referenciada por `11-KNOWLEDGE/Index`, `Strategy Backlog`, `Open Bugs`, o diário e as
páginas de experimento).

## CONCERNS

1. **As figuras foram embutidas com markdown (`![alt](../attachments/...)`), não com `![[...]]`.**
   O linter indexa como alvo de wikilink apenas `.md`, `.base` e `.canvas`: um `![[ethusdt-1h.png]]`
   sairia como **link morto** e derrubaria o lint. A sintaxe markdown com caminho relativo renderiza
   igual no Obsidian e é ignorada pelo checador de links. Se a base passar a indexar PNG como alvo,
   dá para trocar.
2. **Copiei as figuras, não movi.** O brief dizia "movidas"; o meu recorte dizia "copiadas". Os seis
   PNGs continuam em `.claude/state/design/trendlines/` (são a proveniência do `plot_trendlines.py`,
   que fica ao lado deles). Se a intenção era esvaziar `.claude/state/design/`, é um `rm` de uma
   linha, e não o fiz sem pedir.
3. **Editei linhas de tabela do `Experiments Index`, que não estava na lista do brief.** Sem isso o
   índice diria `nao-iniciado` para quatro páginas que dizem outra coisa — contradição dentro da
   própria base. É um **índice**, não uma página de experimento: a regra append-only vale para as
   avaliações datadas, e elas foram acrescentadas, nunca reescritas. Está declarado na própria seção
   nova do índice.
4. **`result: inconclusivo` na EXP-0011 é o vocabulário, não a leitura exata.** O linter só aceita
   `inconclusivo | validada | reprovada | nao-iniciado`, e a leitura honesta desta página é "a
   hipótese não foi testada; a viabilidade do protocolo de dia um é que foi refutada". Quem carrega
   o estado real é `status: bloqueado-por-precheck` e o texto da avaliação. Um valor
   `bloqueado-por-precheck` em `result` exigiria mudar `ENUM_VOCAB` em
   `infra/scripts/obsidian_lint_rules.py` — código, fora deste brief.
5. **O `Changelog` continua sem os nove commits do dia** (`6e9eaa2`, `db798b8`, `b5d4f9b`, `6fbc199`,
   `47d8a11`, `3ed17bb`, `641e120`, `8d8656b`, `cf51c7d`). Não estava no brief e não inventei escopo;
   fica registrado aqui porque "changelog por commit" é dever permanente e a dívida é visível.
6. **Nada aqui foi medido por mim.** Todos os números vêm de `notes-T3.33c/d/e` e `notes-T3.34`
   (`as_of` das corridas 16:34–16:41Z de 2026-09-08, `read_at ≈ 16:50Z`). Não reli o banco, não rodei
   SQL, não toquei em container. As páginas dizem isso; esta nota repete para que a data da leitura
   não se confunda com a data do arquivamento.
7. **Duas obrigações de portão continuam sem resposta e viraram bug**, não nota de rodapé: a
   decomposição por `squeeze_ratio` (C2 da EXP-0008) e o corte por regime de BTC (C4 das quatro).
   A primeira depende do `--explain-ledger` (T3.33f, em voo); a segunda, de `market_regimes` ter mais
   de uma linha. Enquanto isso, dizer "quebramos por regime" seria inventar corte.
8. **A recomendação de descartar a `breakout v1` está registrada e não executada.** Ela segue
   `active`/`research_only` custando 216 avaliações por corte de 15 min e produzindo zero decisão.
   Depreciar é ato auditado e é decisão do Everton — está em "O que preciso do Everton" no diário.
