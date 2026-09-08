# Notes T3.10 — consolidação de documentação do M3

**Autor:** documentation-writer. **Base:** `main` em `d6b8b37`. **Escopo tocado:**
`docs/reports/M3.md` (reescrito), `docs/ARCHITECTURE.md`, `docs/PRODUCT.md`, `docs/ROADMAP.md`,
`README.md`. **Não editei:** `docs/DESIGN.md`, `docs/DATABASE.md`, `docs/PIPELINE.md`,
`docs/DEPLOYMENT.md` (só leitura, achados abaixo), `docs/RISK_ENGINE.md` (contrato, fora da lista
explícita de edição desta tarefa — deixei como está), `obsidian/**`, código, `.env*`. Nenhum
commit feito.

## O que li (lista completa, para quem revisar)

`docs/plans/M3.md`, `docs/reports/M3.md` (rascunho de `700d58f`), `docs/ACTIVATION.md`,
`docs/plans/REPLICATION.md`, `docs/HERMES.md`, `docs/OBSIDIAN.md`, `docs/DATABASE.md` §18–§25,
`docs/PIPELINE.md` (índice completo de seções), `docs/DEPLOYMENT.md` §9 (VPS) e índice completo,
`docs/RISK_ENGINE.md` (completo, §1–§2), `docs/PRODUCT.md`, `docs/ARCHITECTURE.md`,
`docs/ROADMAP.md`, `README.md`, `git log --oneline f33548f..d6b8b37` (147 commits),
`.claude/state/decisions-delegated-2026-09-0{7,8}.md`,
`.claude/state/{notes,review}-T3.*.md` (todas as ~70 listadas em `.claude/state/`, algumas por
grep dirigido em vez de leitura integral — ver "Notas lidas por amostragem" abaixo),
`obsidian/07-BUGS/Open Bugs.md` (integral, 708 linhas), `.claude/state/milestone.json`,
`obsidian/05-EXPERIMENTS/EXP-0005-momentum-paper.md`, `obsidian/09-OPERATIONS/Diario/2026-09-08.md`.

**Notas lidas por amostragem dirigida (grep dos números/testes, não o arquivo inteiro), por causa
do volume (mais de 70 arquivos em `.claude/state/notes-T3.*.md`/`review-T3.*.md`):**
`notes-T3.0f.md`, `notes-T3.7b.md`, `notes-T3.11a.md`, `notes-T3.15c.md`, `notes-T3.17.md`,
`notes-T3.17b.md`, `notes-T3.19b.md`, `notes-T3.19c.md`, `notes-T3.19d.md`, `notes-T3.20.md`,
`notes-T3.21.md`, `notes-T3.22.md`, `notes-T3.5f.md`, `review-T3.15-security.md`,
`review-T3.1-security.md`. Se algum número citado no relatório estiver desatualizado por uma
revisão posterior que eu não tenha visto integralmente, a nota original é a fonte de verdade —
citei o arquivo e a data em cada número.

## Divergências encontradas nos contratos que não editei

**Nenhuma divergência de schema entre `docs/DATABASE.md`/`docs/PIPELINE.md` e o código foi
encontrada.** As seções §18–§25 de `DATABASE.md` e §1c/§1d/§2b/§6b/§6c/§8 de `PIPELINE.md` parecem
ter sido escritas pelos próprios especialistas na mesma tarefa que criou o código (a nota da
T3.19b, por exemplo, diz textualmente "docs/PIPELINE.md (§6c novo)" entre os arquivos que ela
tocou) — não achei texto que descreva um comportamento que o código não tem, nem código sem
contrato correspondente nessas duas seções.

**Um achado real em `docs/DEPLOYMENT.md` §9.4 (Backup), que não editei por estar na lista de
"só leitura" desta tarefa:**

> §9.4 descreve o backup como um fato operacional em andamento: *"`pg_dump -Fc` diário às 03:17
> (hora da máquina) para `/opt/backups`, retenção de 7 dias, via `/etc/cron.d/hunter-backup`."*
> Isso é **verdade como desenho**, mas **falso como fato**: `obsidian/07-BUGS/Open Bugs.md`
> ("Abertos no plantão da tarde de 2026-09-06") registra que o cron falha **todo dia** desde a
> instalação (`Permission denied` — o script está `100644` no git e o cron o invoca sem `bash`),
> e `/opt/backups` não tem um único dump. A seção não é tecnicamente incorreta (descreve o
> mecanismo pretendido), mas um operador que a lesse sem cruzar com `Open Bugs` concluiria que
> existem backups. **Proposta:** acrescentar, no início de §9.4, uma frase como *"Estado em
> 2026-09-08: o cron falha por permissão de arquivo desde a instalação; não existe nenhum dump.
> Ver `obsidian/07-BUGS/Open Bugs.md`."* — quem tiver permissão de editar `DEPLOYMENT.md` decide o
> texto exato; deixei a correção fora desta tarefa porque o arquivo estava na lista de
> "não toque, só leia".

Nenhum outro achado de divergência contrato-vs-código em `DATABASE.md`/`PIPELINE.md`/`DEPLOYMENT.md`/
`DESIGN.md`.

## O que escrevi

1. **`docs/reports/M3.md` — reescrito por completo**, formato §77 estendido pedido (COMPLETED ·
   FILES CREATED · FILES MODIFIED · DATABASE CHANGES 0006–0013 · TESTS CREATED · TEST RESULTS ·
   REAL DATA CONNECTED · MOCKS REMAINING · BUGS · SECURITY ISSUES · OBSIDIAN UPDATED · NEXT STEP ·
   NEXT MILESTONE), marcado **RASCUNHO — parecer da Sexta-feira pendente**. Cada número citado tem
   a nota/commit de origem entre parênteses ou na tabela — não inventei nenhum. Incorporei o que a
   onda 5 produziu além do plano original (T3.11–T3.25: FX, spot como serviço próprio, β, T3.9b,
   replicação, replay, catálogo Obsidian, Hermes, Lab em dinheiro, horário de Brasília, T3.25
   despachada) e deixei explícito o que ainda **não** está feito: `0012`/`0013` não aplicadas em
   nenhum stack, T3.25 só despachada (nem API nem web), segunda opinião da Astra pendente (volta em
   2026-09-12), backfill de β não confirmado concluído.

2. **`docs/ARCHITECTURE.md`** — nova seção curta `4.1 Carteira paper, Risk Engine e o caminho SPOT
   (M3)`: tabela de onde cada peça vive com ponteiro para o contrato/detalhe (nunca duplica),
   parágrafo sobre replay/replicação e sobre o catálogo Obsidian. Nada de `DATABASE.md`/
   `PIPELINE.md`/`RISK_ENGINE.md` foi copiado — só apontado.

3. **`docs/PRODUCT.md`** — tabela de navegação (§4) ganhou uma coluna "Estado real (2026-09-08)"
   com três valores (implementada / dado real, tela pendente / planejada), citando a T3.25 como
   origem da mudança para Trades/Strategies/Backtests/Risk Center. Nova subseção `4.1 Lab, replay e
   replicação` explicando ao leitor de produto o que aquelas duas camadas são e não são (nunca
   tocam a carteira).

4. **`docs/ROADMAP.md`** — M3: bloco de status datado 2026-09-08 apontando para o relatório e
   citando o que falta. M4: reescrito — deixa de ser "construir a ponte" (que o M3 já entregou) e
   passa a ser "ativar em produção" + página de Agents (a única sem dado real hoje) + replicação em
   produção. M5: nota de que o motor de Trades/Risk Center foi antecipado pelo M3/T3.25. M6:
   nota de que o motor de replay **é**, na prática, o Backtest Engine descrito ali (mesma função de
   decisão, sem look-ahead por construção, provado por teste de mutação) — falta a tela e a camada
   de validação estatística (walk-forward, overfitting/leakage), que continuam em aberto.

5. **`README.md`** — "Estado atual" corrigido (estava parado no M0/M1, o repositório já passou do
   M3 em código); nova seção "Como rodar hoje" com a tabela stack-local-vs-VPS, o comando de deploy
   exato (`MARKET_SPOT=1 MARKET_SHARDS=4 bash infra/vps/compose.sh update`) e a tabela dos scripts
   operacionais (`open_paper_wallet`, `activate_strategy_version`, `replicate_strategy_version`,
   `request_backfill`, `export_strategies_to_obsidian`, `obsidian_lint`); tabela de documentação
   ganhou `ACTIVATION.md`, `OBSIDIAN.md`, `HERMES.md`, `plans/REPLICATION.md`, `plans/SHADOW-LAB.md`,
   `reports/` e os planos M1–M3 que faltavam.

## Varredura de links quebrados

Script próprio (`uv run python`, regex de `[texto](alvo)`) sobre `docs/**/*.md` + `README.md`
(**não** varri `obsidian/**`, que usa `[[wikilinks]]` e tem linter próprio, `docs/OBSIDIAN.md` §5).
**Um único achado, falso positivo:** `docs/reports/M2.md:367` tem
`` `deque[NormalizedCandle](maxlen=…)` `` dentro de um code span — a regex de link casou o colchete
e o parêntese de uma assinatura de tipo Python, não um link real (nem passa pela sintaxe de link do
Markdown, porque está dentro de crase). **Não há link quebrado real em `docs/**/*.md` nem em
`README.md`.** Reexecutei a varredura depois de todas as minhas edições: mesmo resultado, nenhum
link novo quebrado.

## Concerns / coisas que a Sexta-feira ou o Everton devem saber antes de aprovar

1. **O rascunho anterior do relatório (`700d58f`) estava desatualizado desde a tarde de
   2026-09-07** — a diretiva do orquestrador já dizia isso. O que eu incorporei de novo: T3.11a
   (FX), T3.0e/T3.0f (spot como serviço próprio), T3.7b (produtor de β), T3.14b/T3.15/T3.15b/c/e
   (rótulo `paper` e a ponte julgando a coluna), T3.16–T3.18 (Lab em dinheiro), T3.19/T3.19b–d
   (replicação e replay, migrações `0012`/`0013`), T3.20/T3.21 (catálogo e higiene do Obsidian),
   T3.22 (horário de Brasília), T3.5f (dívida de pyright paga), o pacote Hermes, e o brief da T3.25
   (ainda não executado).
2. **Não tenho como confirmar, nesta consolidação, se o backfill de β na VPS terminou** (pedido às
   ~04:35Z de 2026-09-08, estimativa de conclusão ~12:00Z na própria nota de ativação) nem se a
   `0012`/`0013` foram aplicadas em algum stack depois do commit mais recente que li. Marquei os
   dois como "pendente/não confirmado" no relatório em vez de assumir que aconteceram — quem tiver
   acesso a uma sessão SSH na VPS deveria confirmar antes do parecer final.
3. **Não escrevi nenhuma entrada nova em `obsidian/`** (fora da lista de edição desta tarefa,
   apesar de o brief original da T3.10 no plano pedir "Obsidian... changelog, diário" — isso ficou
   descoberto: o diário e o changelog não têm entradas desde a madrugada de 2026-09-08 para os
   commits de T3.0e em diante. Registro aqui para quem fizer o próximo plantão, mas não escrevi em
   `obsidian/**` porque a diretiva desta tarefa especificamente proibiu.
4. **Não toquei `docs/RISK_ENGINE.md`** apesar de ele não estar na lista explícita de "não toque"
   do brief — é um contrato normativo pela regra geral do `documentation-writer`
   (`.claude/agents/documentation-writer.md`), e o brief não pediu nenhuma mudança nele. Se algo
   nele precisar de correção, é uma tarefa própria com revisão do `risk-engine-guardian`.
5. **Ninguém rodou, nesta janela, uma suíte única e datada do repositório inteiro** depois de
   T3.19–T3.22. Os números de teste no relatório são por tarefa, cada um citado com a nota de
   origem — não há uma prova de que tudo passa junto no mesmo commit. Registrei isso como NEXT STEP
   #4 do relatório em vez de fingir que existe.
