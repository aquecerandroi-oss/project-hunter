# Brief T3.26b — arquivar o EXP-0006 (momentum v4, piso de custo) no Obsidian e ligar o backlog

**Dona:** sexta-feira. **Não commitar.** **Regra operacional: nunca shell em background; comandos em primeiro plano com timeout <= 5 min; a árvore é compartilhada — nunca `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a`; não tocar `.env*`; não parar nem recriar contêineres.** Base: `main` em `be3674a`. Em voo: T3.18b (`apps/api/**`), T3.7d (`services/market-worker/**`), audit de design (`.claude/state/design/**`) — não editar esses caminhos. Só `obsidian/**`.

## Fonte
`.claude/state/exp-drafts/EXP-0006-momentum-piso-de-custo.md` (rascunho do quant, T3.26), `.claude/state/notes-T3.26.md` (a tabela pai × variante e os 4 grupos pareados — a evidência de que a diferença vem de 5 resultados), `.claude/state/brief-T3.27-momentum-v2-invalidacao.md` (a variante B vira versão de código; os braços INV-* já existem como políticas de saída).

## Entregar
1. `obsidian/05-EXPERIMENTS/EXP-0006-momentum-piso-de-custo.md` no formato do `_TEMPLATE-EXP.md` (Hipótese/Protocolo congelados; primeira avaliação datada 2026-09-08 rotulada **replay**, veredito `inconclusivo`; a tabela pareada inteira — é o detalhe que Everton pediu: "cada detalhe, cada diâmetro").
2. `obsidian/11-KNOWLEDGE/Strategy Backlog.md`: item 1 (piso de custo) aponta para EXP-0006 com estado "no Lab desde 2026-09-08 (momentum v4)"; item 2 (invalidação) aponta para o brief T3.27 como "próximo: replayar os braços INV-* antes de escrever código".
3. KB-0008: apêndice datado com o achado "o piso corta 86 % das decisões na janela de replay; acima de 70 % é outra estratégia" e o achado dos grupos pareados (o lado acima do piso foi o pior sobre a população do pai).
4. `python infra/scripts/export_strategies_to_obsidian.py` **não** — a página de catálogo de v4 nasce sem `derived_from` na VPS (concern 1 da T3.26); registre isso em `obsidian/00-INBOX/` como pendência operacional com a correção proposta (uma linha de UPDATE em `changelog`, decisão de Everton).
5. `uv run python infra/scripts/obsidian_lint.py` verde.

## Provar
Relatório em português, formato estendido; anexar em `.claude/state/notes-T3.26.md` a seção "T3.26b".
