---
tags: [revisao-astra, meme, creator-dump, gemeo, migracao, h-031b]
date: 2026-10-07
updated: 2026-10-07
status: registro
owner: quant-engineer
decided_on: 2026-10-07
by: astra
tarefa: H-031b — diff do gêmeo `absorb_semdump_v0/1` (migração `0069`, chave `exit_on_creator_dump` na aposta, patch sequenciado de `lab_models`)
veredito: "BLOCKED com 3 must-fix (janela de deploy, corrida guarda × cópia, null aceito como True) — os três absorvidos; nenhum caminho de saída do papel vende por creator_dump no gêmeo com o patch completo"
---

# Revisão da Astra — diff da H-031b

**Pedido:** rever o diff (`lab_params`, `lab_repo_pedigree`, a `0069` e os testes) e o patch sequenciado de
`lab_models` (`.claude/state/h031b/sequenced.patch`), cinco perguntas: algum caminho do papel ainda vende por
`creator_dump` no gêmeo; guardas e cópia da migração; leitores de `meme_paper_bets.params` que quebrem com a chave
sempre gravada; ordem de deploy; validação de `--set-param` com a string `"false"`. Transcrição:
`.claude/state/astra-review-H-031b-diff.md`. Ela rodou só `git apply --check` (passa) e `git diff --check`.

**Concordou com:** com o patch completo, nenhum caminho gera `creator_dump` no gêmeo — a vigia (`lab_bets.py:213`), o
motor (`paper_engine.decide_exit_at` → `bet.params.exit_rules()`), o pool (`lab_bets_pool`) e o point read (só executa
a razão recebida); a pista de lançamento lê relógio `event`, não o gêmeo. Copiar o `params` vivo com `ON CONFLICT DO
NOTHING` + pós-checagem estrita. Nenhum leitor quebra pela chave nova (a API projeta campos nomeados). `research_only`
nunca chega ao executor. Com o patch, `"false"` (string JSON) vira `WouldNotLoad` no `--set-param`.

**Três must-fix, todos absorvidos:**

1. **Janela de deploy (alta).** O `compose.sh` aplica a migração antes de trocar os serviços; o worker antigo, ainda
   vivo, lê o gêmeo ativo sem entender a chave e abre apostas com a saída ligada — e a retomada lê o `params` gravado.
   O teste da migração é necessário, não suficiente. → **deploy em duas etapas** (código antes, `0069` depois) escrito
   no [[EXP-M27-gemeo-sem-creator-dump]] e na `docs/DATABASE.md` §72; e a **emenda 2** da H-031b exclui da coorte
   toda aposta do gêmeo sem `"exit_on_creator_dump": false` no `params` (dado da entrada, não desfecho).
2. **Corrida guarda × cópia (média).** Três `op.execute` separados: um `--set-param` concorrente entre a guarda e o
   `INSERT` faria a cópia de um documento recusável, e a pós-checagem aceitaria. → `SELECT … FOR UPDATE` na linha do
   original antes das guardas; cópia e pós-checagem só aceitam a origem válida (`15s`, chave ausente ou `true`).
   Provado por comportamento (`test_migration_0069_guards`): com a trava segura por outra transação a migração espera;
   ao mudar o relógio para `1m` e confirmar, ela recusa pelo nome.
3. **`null` aceito como `True` (média).** O "estrito" tratava `None` como ausência; `--set-param
   exit_on_creator_dump=null` religaria a saída em silêncio. → `switch_of(params, name, default)`: padrão **só** com a
   chave ausente; presente, tem de ser booleano (`null`, strings e números recusados), no conjunto e na aposta.

**Nice-to-have:** o teste pelo laço real (vigia carimba a venda, a próxima foto não fecha o gêmeo, a retomada mantém a
saída desligada) foi escrito — `test_creator_watch_twin.py`, no patch sequenciado; o arquivo de teste da migração foi
dividido (`test_migration_0069.py` + `_guards.py`). **Não feito:** expor a chave na API (`meme_desk_out`) — fora do
escopo, sem leitor que precise hoje.

**Revisão de banco depois desta:** [[H-031b-db-review]] — a trava virou `FOR NO KEY UPDATE` (a `FOR UPDATE` também
travava as inserções do worker que referenciam `absorb_v0/2`), e o teste da trava deixou de depender de `sleep`.

**Onde isto vive:** [[EXP-M27-gemeo-sem-creator-dump]] · [[Fila de Hipoteses]] (H-031b, emenda 2) · pré-registro:
[[H-031b-prereg]] · [[Revisoes-Astra/Index|índice das revisões]]
