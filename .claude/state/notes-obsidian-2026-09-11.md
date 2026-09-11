# notes-obsidian-2026-09-11 — plantão de arquivamento (noite 10/09 + manhã 11/09)

**Escopo de escrita:** `obsidian/**` e este arquivo. Nenhum código tocado, nenhuma suíte de código
rodada (só o linter da base), `.env*` intocado, nada commitado. `git log`/`ls`/leitura de arquivo só
lidos (foreground, `timeout 290`). Nenhum shell em segundo plano. Janela: 2026-09-10 15:30 BRT →
2026-09-11 08:15 BRT.

## Fontes lidas (todas, antes de escrever)

`git -C C:/dev/project-hunter log --since="2026-09-10 15:30" --format="%h %s"` (21 commits novos
desde o último arquivamento, `e7255bb..3e7bfe9`) · `.claude/state/notes-T3.74e.md` ·
`-T3.74f.md` · `-T3.74g.md` · `-T3.82.md` (vazio de conteúdo relevante — a decisão está na página de
decisão, não na nota) · `-T3.83.md` · `-T3.84.md` (os três passos, incl. o achado do Redis §9 e o
veredito §5) · `-T3.85.md` · `-T3.86.md` · `-T3.87.md` · `-D-P19.md` ·
`.claude/state/brief-T3.84-lote-diario-5min.md` (a citação do `decision_lag_p50_s 2,2 s` que libera o
experimento de 5 min) · `.claude/state/proposta-carteira-2026-09-09.md` (seção D-P19, confirmação) ·
`obsidian/09-OPERATIONS/Diario/2026-09-10.md` (estado antes da edição) ·
`obsidian/11-KNOWLEDGE/KB-0087-o-atraso-de-decisao-e-as-tres-correcoes.md` (para confirmar que NÃO
cobre sharding/universo — condição do brief para decidir nota nova vs. apêndice) ·
`obsidian/11-KNOWLEDGE/KB-0088-o-teto-de-participacao-nos-motores-de-backtest.md` (já escrita pelo
próprio plantão de mercado — só linkada) · `obsidian/11-KNOWLEDGE/Index.md` ·
`obsidian/07-BUGS/Open Bugs.md` (seções T3.87/T3.85/T3.83, para as citações exatas dos itens
pendentes — não editado) · `obsidian/06-DECISIONS/2026-09-10-universo-de-pesquisa-90-dias.md` (já
existia, linkada de volta) · `obsidian/08-CHANGELOG/Changelog.md` (para achar onde a última sessão
parou: `e81d53e`, já logado) · `docs/OBSIDIAN.md` · `obsidian/_TEMPLATE-NOTE.md` (o de
`11-KNOWLEDGE`, único com esse nome) · `ls obsidian/11-KNOWLEDGE` (próximos números livres: KB-0089,
KB-0090) · `.claude/state/plantao/2026-09-11-0625-lane1.md` (para a citação exata do item Gatto/SSRN
403, run 9).

## Arquivos escritos

- `obsidian/09-OPERATIONS/Diario/2026-09-10.md` (editado) — seção nova "## Noite (15:39–20:21 BRT)"
  com quatro callouts e duas subseções: a continuação da campanha de latência (T3.74e/f/g, a
  concorrência que não bastou e o sharding que resolveu) e a decisão T3.82 (universo de 90 dias).
  "Relacionadas" ampliada com KB-0089 e o diário de 11/09. `updated` para 2026-09-11 (data desta
  edição, não da data do conteúdo).
- `obsidian/09-OPERATIONS/Diario/2026-09-11.md` (novo) — quatro callouts, cinco seções numeradas: o
  fechamento da campanha de latência em `decision_lag_p50_s = 2,2 s`; T3.87 (o portão do replay
  cegado pelo próprio sharding, corrigido); T3.84 passo 3 (a irmã de 5 minutos morta pelo motivo
  oposto ao pré-registrado — sinal desapareceu, não custo subiu); D-P19 (a meta em dinheiro); os dois
  incidentes de infraestrutura sem dono nesta sessão (Redis reiniciando sozinho às 06:25 BRT, o
  `STRATEGY_SHARDS` que o operador precisa lembrar). Tabela "O que espera o Everton" com os seis
  itens do brief (`agents`, `recompute_funding`, `v14 --force-paper`, faxina do Redis, grupo órfão,
  e-mail ao Gatto). Tabela "Saúde" com a ressalva de que nada foi relido por SSH nesta sessão.
- `obsidian/11-KNOWLEDGE/KB-0089-o-teto-de-cpu-de-um-processo-so.md` (novo) — próximo número livre
  depois de KB-0088. **Decisão sobre "nota nova vs. apêndice a KB-0087"**: li KB-0087 por inteiro
  antes de decidir — ela cobre só as três causas medidas até o deploy `e81d53e` (despacho serial,
  replay no worker vivo, flush de 1,0 s), nunca sharding nem universo. Como o brief condiciona
  "apêndice" a "KB-0087 já cobrir sharding/universo" (que não cobre), escrevi nota nova, explicitando
  no corpo que é continuação direta da KB-0087 (mesma métrica, mesma noite, quarta causa). Registrada
  em `Index.md` (tema + tabela de notas).
- `obsidian/11-KNOWLEDGE/KB-0090-a-meta-em-dinheiro.md` (novo) — próximo número livre depois de
  KB-0089. Síntese da D-P19 (teto/esperado por mercado e hora, o teto de vagas×horizonte, a
  sensibilidade de participação e de impacto). Registrada em `Index.md` (linha nova na tabela de
  temas "Dimensionamento e risco" + tabela de notas).
- `obsidian/11-KNOWLEDGE/Index.md` (editado) — linha de "Diagnóstico do nosso próprio resultado"
  ganhou KB-0089; linha de "Dimensionamento e risco (Risk Engine M3/M4)" ganhou KB-0090; duas linhas
  novas na tabela "Notas". `updated` já estava em 2026-09-11 (editado por outra tarefa nesta mesma
  janela — plantão de mercado, KB-0088 — não sobrescrevi a data).
- `obsidian/08-CHANGELOG/Changelog.md` (editado) — duas inserções: (1) bloco de 8 commits
  (`e7255bb..2509ceb`, 15:39–20:21 BRT) dentro do `## 2026-09-10` já existente, logo depois da
  entrada `e81d53e`; (2) seção nova `## 2026-09-11` no topo (mais recente primeiro) com os 13
  commits de `6fa5c7b` a `3e7bfe9`. Cada entrada segue o padrão de comprimir a mensagem do commit
  (que já é densa) preservando todo número, linkando KB/EXP/decisão onde existe. `updated` para
  2026-09-11.

## O que eu NÃO fiz

- Não dupliquei o trabalho do plantão de mercado (runs 6–9, já em `.claude/state/plantao/**` e nas
  suas próprias notas/KB) — só linkei o que ele já tinha escrito (KB-0088) e cito os runs no diário
  sem reescrever o conteúdo deles.
- Não toquei `docs/**` nem código de nenhum serviço, nem `Open Bugs.md` — os itens pendentes citados
  no diário (grupo órfão, faxina do Redis) já estão lá com todo o detalhe técnico; linkei em vez de
  duplicar.
- Não rodei `docker`/SSH/`psql` — todos os números desta sessão vêm das notas dos agentes, nunca de
  leitura própria da VPS.
- Não commitei nada.
- Não usei `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a` em nenhum momento — a
  árvore é compartilhada e outras tarefas estão em voo nela.

## Verificação

```
$ cd C:/dev/project-hunter && timeout 290 uv run python infra/scripts/obsidian_lint.py
LINT DA BASE OBSIDIAN — 255 NOTA(S) ANALISADA(S)
Resumo — Links mortos: 0, Links ambíguos: 0, Notas órfãs: 0, Frontmatter incompleto: 0,
Valores fora do vocabulário: 0, Procedência da Knowledge Base (KB-*): 0,
Reescrita de experimentos (append-only): 0.

RESULTADO: base limpa
```
