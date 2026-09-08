# Brief T3.30 — a revisão da Astra sobre o Lab (2026-09-08) entra no Obsidian e vira pendências rastreáveis

**Dona:** sexta-feira. **Não commitar.** **Regra operacional: nunca shell em background; comandos em primeiro plano ≤ 5 min; árvore compartilhada — nunca `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a`; não tocar `.env*`.** Só `obsidian/**`. Base: `main` em `50932ec`.

## Fonte
`.claude/state/astra-review-lab-pronto-2026-09-08.md` (a revisão, com arquivo:linha), `.claude/state/brief-T3.29-autonomy-acceptance-run.md` (o que já virou tarefa), `.claude/state/notes-T3.28a.md`.

## Entregar
1. `obsidian/06-DECISIONS/Revisoes-Astra/2026-09-08-shadow-lab-pronto.md`: a revisão inteira, no formato das outras páginas dessa pasta, com links `[[...]]` para EXP-0006, Shadow Lab, Execution Engine, Risk Engine, Open Bugs.
2. `07-BUGS`/`Open Bugs`: um item por MUST-FIX com estado "aberto 2026-09-08 (Astra)", o arquivo:linha, e a tarefa que o cobre (T3.29 para a autonomia; T3.18c para replicação/avaliável/irmãs — brief a escrever pelo orquestrador; T3.28a-seguimento para o DoS compartilhado). Backup: registrar como "a comprovar em T3.29", não como bug.
3. `EXP-0006`: seção datada "Próximas medições (Astra)" com os 5 pontos de "O que eu faria diferente" (seleção × rearme, oportunidade por tempo, decomposição de custos, dependência/influência dos 5 resultados, proveniência) — sem inventar números.
4. `Execution Engine`/`Paper Trading` e `Risk Engine`: pré-requisitos efetivos da autonomia = os 7 itens do brief T3.29, com o estado atual ("não medido").
5. `00-HOME.md` e `09-OPERATIONS/Diario/2026-09-08.md`: reconciliar (momentum v3 paper ativa desde 02:57; 154 sinais paper, 0 propostas/posições; deploys de hoje 385dac6 e 50932ec; Clerk de teste destravado; achado do 429).
6. `docs/plans/REPLICATION.md` §46/§78 têm a linguagem estatística errada (√2, não ~2×) — não edite `docs/`; anote em `Open Bugs` como correção de texto para o orquestrador.
7. `uv run python infra/scripts/obsidian_lint.py` verde.

## Provar
Relatório em português, formato estendido; `.claude/state/notes-T3.30.md`.
