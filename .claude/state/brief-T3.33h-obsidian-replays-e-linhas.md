# Brief T3.33h — as avaliações do dia um (EXP-0008/0009), a morte da EXP-0011 na pré-checagem, e as linhas de tendência (KB-0077 com as figuras) entram no Obsidian

**Dona:** sexta-feira. **Não commitar.** **Regra operacional: nunca shell em background; comandos em primeiro plano ≤ 5 min; árvore compartilhada — nunca `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a`; não tocar `.env*`.** Só `obsidian/**`. Base: `main` em `bef3ee7`.

## Fontes
`.claude/state/notes-T3.33e.md` + `exp-drafts/EXP-0008-*.md` e `EXP-0009-*.md` (seções "Avaliação de 2026-09-08 — replay de abertura": breakout 0 decisões, 14/14 `geometry_invalidation`, K1 dispara, recomendação descartar/v2; mean_reversion 37 decisões, bruta +0,32 R, líquida +0,094 R, PF 1,19, saldo inteiro nas 6 saídas por horizonte, inconclusivo; ativações às 16:23:39Z e 16:32:33Z; capacidade ok). `.claude/state/notes-T3.33d.md` + `exp-drafts/EXP-0011-*.md` (bloqueada na pré-checagem: 5 fundings negativos em 31 d × 4 mercados; reexecutar ~2026-10-06; aviso do piso 0,006). `.claude/state/notes-T3.33c.md` + `exp-drafts/EXP-0010-*.md` (session_orb_v1 commitada em 3ed17bb; ativação/replay em voo na T3.33f — não inventar avaliação). `.claude/state/notes-T3.34.md`, `exp-drafts/KB-0077-linhas-de-tendencia.md`, `.claude/state/astra-review-T3.34-trendlines.md`, figuras em `.claude/state/design/trendlines/*.png` (6). Revisões: `review` da T3.33a+b (aprovar com ressalvas: faixa 0,0050–0,0059 do piso; fórmula do z diverge da candidata da Astra; portão C1–C8 foi autoavaliação) e da T3.33c (constraints extraído; horizonte transborda de sessão; divergência assumida contra a Astra sobre "sessão").

## Entregar
1. `EXP-0008`, `EXP-0009`: seções datadas de avaliação (rotuladas **REPLAY**), portão C1–C8 preenchido com os vereditos (`REVISE` com as divergências declaradas, dizendo que foi autoavaliação do quant, não revisão viva da Astra), `result` (0008 → `inconclusivo` + "recomendação: descartar v1 / v2 por parâmetro em voo"; 0009 → `inconclusivo`), linhagem/ativação; `Registro de Tentativas` T-035/T-036 com início = timestamps de ativação.
2. `EXP-0011`: `bloqueado-por-precheck`, a tabela da pré-checagem, a data de reexecução (~2026-10-06); `Registro de Tentativas` T-038 marcado "não iniciada — pré-checagem".
3. `EXP-0010`: portão C1–C8 e o teto de pedágio (0,3333 R); avaliação **pendente** (T3.33f).
4. `KB-0077-linhas-de-tendencia.md` em `11-KNOWLEDGE/` (renumerar se 0077 estiver tomado): as regras em português, parâmetros e defaults, as seis figuras movidas para `obsidian/attachments/trendlines/` e embutidas, a seção "o que um humano traçaria diferente" (6 pontos), as três correções da Astra, o ponto aberto da T3.34b (onde o código mora sem mover o digest). Índice da KB.
5. `Strategy Backlog`: breakout v2 por parâmetro (em voo), variantes V1/V2 do momentum (T3.32) ainda não derivadas, derivatives reexecução em outubro, `patterns v2` (aposentar linha rompida, leque, nível horizontal), T3.34b trendline_breakout.
6. `Diario/2026-09-08.md` (bloco novo): deploys da tarde (b5d4f9b, 6fbc199, 8d8656b/0014, cf51c7d), o primeiro resultado líquido positivo em replay (mean_reversion, 37 decisões, honesto: inconclusivo), a pendência do operador `seed.py` (descrições das estratégias na tela do Lab estão velhas) e a hipótese de o piso 0,006 morder demais.
7. `Open Bugs`: "replay não persiste o motivo por barra" (T3.33f resolve com --explain-ledger), "market_regimes tem 1 linha" (C4 impossível em replay), "test_isolation não cobre /risk/limits" (T3.37c achado 3).
8. `uv run python infra/scripts/obsidian_lint.py` verde.

## Provar
Relatório em português, formato estendido; `.claude/state/notes-T3.33h.md`.
