
## 72. O gêmeo do `absorb_v0/2` sem a saída `creator_dump` — `absorb_semdump_v0/1` — H-031b (`0069_meme_absorb_semdump_arm`)

**Por quê (H-031b, EXP-M27).** A H-031 (R88, KB-0188) achou que a fatia do maior comprador no instante da decisão não
separa o retorno do papel, mas a saída `creator_dump` disparou 2,11× mais no braço de fatia alta. Se é a saída que
esconde a diferença só se vê com a mesma aposta **sem** ela. Rota (2) do Defensor; aprovada pelo Everton em 07/10/2026.

**O que a `0069` faz:** **uma linha** em `meme_rule_sets` (`01994d00-6c1a-7000-8000-000000000022`,
`absorb_semdump_v0/1`, `kind = research_only`, `exp_ref = 'EXP-M27'`, `status = 'active'`, `code_ref` igual ao da
`0058`). Nenhuma tabela, coluna, índice, vista, enum, política, grant ou partição; nada aposentado; a mesa e
`absorb_v0/2` não são tocados. DDL em `ddl/meme_absorb_semdump_arm.py`; slug de 28 caracteres (§17.6). Encadeada em
`0068_meme_wallet_exceptions` — **a `0069_meme_mature_chart_arms` (EXP-M26, não commitada) também desce da `0068`;
alguém precisa linearizar as duas antes do deploy** (duas cabeças fazem `upgrade head` falhar). O id é o seguinte livre
depois dos `…001f`/`…0020`/`…0021` daquela revisão. `meme_rule_sets` é global (§34.1): sem `organization_id`, sem RLS.

**Copiado da linha VIVA de `absorb_v0/2`, mais uma chave** — o desvio declarado da §67: o seed é `absorb_v0/2.params
|| '{"exit_on_creator_dump": false}'`, no mesmo `INSERT … SELECT` com o mesmo predicado das guardas (`id`, `name =
'absorb_v0'`, `version = '2'`, `status = 'active'`). Porta, ficha, tetos (3 posições, perda diária 0,20 SOL, carteira
2,0 SOL) e as demais saídas são as do original. `test_migration_0069` prova `gêmeo − exit_on_creator_dump = original`,
chave a chave, e carrega a linha pelo caminho do robô (`RuleSetSpec.from_params` → `effective_params`): a saída sai
desligada e a aposta grava `false`.

- **A guarda recusa** (nada semeado, revisão fica em `0068`): `absorb_v0/2` ausente ou não ativo; `params ->> 'clock'`
  diferente de `'15s'`; `exit_on_creator_dump` presente e diferente de `true` no original (o gêmeo seria cópia); e,
  depois do `INSERT … ON CONFLICT DO NOTHING`, qualquer linha sob o nome congelado que não seja exatamente essa cópia
  com esse id (um estranho).
- **A chave tem de ser lida.** `RuleSetSpec.from_params` lê `exit_on_creator_dump` como booleano JSON estrito (string
  recusada) e `EffectiveParams.as_json` grava a chave em **toda** aposta nova (`true` ou `false`); aposta anterior sem a
  chave correu com `true`. Sem esse código o gêmeo seria uma cópia do original — o teste da migração falha nesse caso.

**Papel por construção.** `research_only`: o executor só seleciona `rs.kind = 'operator'` (`test_migration_0069` roda
`auto_approve.operator_proposals` contra uma proposta do gêmeo e ela não volta). As apostas do gêmeo são **subtraídas**
do `creator_prior_dump_count` da mesa pela lista de ids já existente (`lab_repo_pedigree`, parâmetro
`:mature_rule_set_ids`, sem mudar o texto do SQL fixado por hash). Ao contrário do recuo (§65/§67), o gêmeo **fixa** o
mint no rastreador: sem fotos, a cauda depois do `creator_dump` do original — o que o experimento mede — sumiria.
Resíduo declarado (EXP-M27): a dobra do minuto pode gravar `meme_features_1m.creator_sold` de um mint que só o gêmeo
mantém, e cada mint fixado estreita o teto do rastreador (no máximo 3 posições do gêmeo).

**Downgrade (§17.7):** recusa enquanto `meme_proposals`, `meme_paper_bets`, `meme_rule_set_param_history` ou
`meme_gate_refusals_by_mint` referenciam o gêmeo; no upgrade, dois blocos `DO` e um `INSERT … SELECT`; nenhuma janela
de manutenção.
