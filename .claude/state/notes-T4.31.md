# T4.31 — E2-b como braço de pesquisa pré-registrado (papel), 2026-09-16

## 1. O que entrou

| peça | arquivo |
|---|---|
| critério na biblioteca de portões | `packages/indicators/hunter_indicators/meme/pedigree_e2b.py` (`pedigree_e2b/1`: `e2b_top_buyer_share_max` 0,35, `e2b_min_buyers` 10, `e2b_born_full_s` 60; recusas `e2b_born_full`, `e2b_top_buyer_share`, `e2b_top_buyer_unknown`) |
| leitura por tick (bounded) | `services/meme-worker/hunter_meme_worker/lab_repo_e2b.py` (`e2b_for`, `e2b_features_from_counts`, `lineage_for`) |
| fiação | `proposals.py` (`evaluate_gate(..., e2b=...)`), `proposals_reasons.py` (bloco `feature: "pedigree_e2b"`), `lab_models.py` (`RuleSetSpec.pedigree_e2b`), `lab.py` + `lab_fast.py` (`lineage_for`) |
| semente | `infra/migrations/ddl/meme_gate_e2b_arm.py` + `infra/migrations/versions/0044_meme_gate_e2b_arm.py` (`flow_v2/6`, id `…0013`) |
| testes | `packages/indicators/tests/unit/test_meme_pedigree_e2b.py` (20), `services/meme-worker/tests/test_proposals_e2b.py` (12), `services/meme-worker/tests/test_lab_e2b_persistence.py` (3, testcontainers), `packages/core/tests/integration/test_migrations.py` (3 novos `test_0044_*`) |
| pré-registro | `obsidian/05-EXPERIMENTS/EXP-M9-pedigree-e2b.md` + 2 linhas no `Experiments Index.md` + linha **M-P50** no INBOX |
| errata | `obsidian/11-KNOWLEDGE/KB-0103-…md` §"Errata 1" (append-only) |
| doc | `docs/DATABASE.md` §53 |

## 2. Qual dado alimenta a fatia do maior comprador (a pergunta do brief)

Conferido antes de escrever: **nada na via rápida carrega o dado**.
- `meme_features_15s` tem `unique_buyers_60s`, `buys_60s`, `sells_60s`, `snipers`, `holders` — e **não diz quem comprou**; a rota de atividade por lote (`meme_market_activity_1m`, §44) é anônima por construção ("The route never says *who* traded").
- `top10_share` só existe em `meme_features_1m` (leitor de holders / board) e é fatia de **oferta detida**, não de SOL pago. **Não há** fatia do holder nº 1 em lugar nenhum do esquema (grep `top1`/`largest_buyer`: nada).
- Única fonte de SOL por carteira: a fita `meme_trades` (`trader`, `side`, `sol_lamports`, `block_time`; índice `ix_meme_trades_mint_block_time`) — a mesma que o SQL de pesquisa `2026-09-16-r13-q04-apostas-medidas-e-e2b.sql` usa (`sum(sol_lamports) group by trader`, `max/sum`).

Então `e2b_for` soma a fita por par **(mint, instante julgado)** desde `created_at − 60 s` (o mesmo *lead* do SQL de pesquisa) até `as_of`, e devolve `top_buyer_share = max/sum` em `Decimal` (lamports são inteiros; divisão sob `hunter_core.strategies.numeric.CONTEXT`, nunca float).

## 3. Taxa esperada de `e2b_top_buyer_unknown` (e por que é uma previsão, não um número)

Não tenho acesso à VPS nesta tarefa, então a previsão está **congelada na página EXP-M9 (P1)**: entre **10 % e 60 %** das linhas avaliadas por `flow_v2/6` nos 7 primeiros dias, **ponto 25 %**. Base do palpite: KB-0105 §0 mede fita em **21–25 %** das graduadas de 12–13/09 (limite inferior: o rastreado é melhor coberto — o diário de 16/09 registra "fita 93 %" / "fita 100 %" para o conjunto rastreado nas janelas em que a API estava de pé). A medida que resolve: recusas por nome em `meme_lab_ticks` ÷ linhas avaliadas do conjunto. **É parte do que o braço mede**, não um efeito colateral.

## 4. Decisões e suposições numéricas (todas declaradas)

1. **`>= 0,35` (inclusivo)**: KB-0103 §3 (regra G) e KB-0105 §2 escrevem "maior comprador ≥ 35 %"; o parâmetro chama-se `…_share_max` mas o corte é inclusivo, documentado no campo e coberto por teste (`0.35` recusa, `0.3499999` passa).
2. **`<= 60 s` inclusivo** e **`fill_seconds` pode ser negativo** (42,7 % das graduadas têm `completed_at ≤ created_at`, KB-0103 §5) — negativo **é** nascida cheia, como no SQL de pesquisa.
3. **A guarda dos 10 compradores não recusa**: abaixo do piso a perna da concentração **não pergunta** (KB-0105 §4 ressalva 2: senão a regra recusa por juventude). Sem fita nenhuma, aí sim, recusa `e2b_top_buyer_unknown`.
4. **`created_at − 60 s`** como início da janela da fita: o `lead` do R13 (compra do mesmo bloco carimbada um triz antes).
5. **Limiares congelados em código**, não nos `params` do conjunto (disciplina de `PEDIGREE_V1`): o conjunto só liga o interruptor `pedigree_e2b: true`. A variante de KB-0105 (`<= 30 s` OR `>= 45 %`) será **versão 2**, nunca edição.
6. **`gate_version` 3** em `flow_v2/6`: os critérios mudaram em relação ao `fluxo_e_holders/2` congelado no braço 2 (a calibração da mesa), e uma proposta `…/2` tem de continuar significando o que significava. A mesa (`operator/5`) segue marcada `/2` no banco porque foi calibrada por `--set-param` ao vivo — divergência registrada aqui, não corrigida por esta tarefa.
7. **`max_snipers: 1000`** entra na calibração porque foi assim que o Everton gravou o piso de snipers (diário 16/09, adendo 16:2x: "`min_snipers` 21, `max_snipers` 1000"); o brief só citava o piso.
8. `flow_v2/6` **não** carrega as chaves de mesa (`ttl_s`, `max_open_positions` 2) — é `research_only`, então usa o TTL do laço e as 5 abertas de `flow_v2/5`.

## 5. Não-antecipação (o que foi preciso fazer para não vazar)

- A fita é somada **por par (mint, as_of)**, via `unnest(:mints, :as_ofs)` — não "até agora". Na lane de 15 s o tick carrega linhas com até `lab_fast_backlog_s` de atraso; somar até o relógio do tick deixaria uma linha velha ler negócios que ainda não existiam. Teste: `test_a_pair_the_caller_did_not_read_refuses_unknown` (unit) e `test_the_tape_is_summed_per_judged_instant_and_never_past_it` (Postgres: o mesmo mint a +20 s e a +60 s devolve 1 comprador/fatia 1 e 11 compradores/fatia 9⁄19).
- `completed_at` só conta quando `completed_at <= as_of` (`CASE WHEN` no SQL): uma curva que enche **depois** não é "nasceu cheia". Teste: `test_a_completion_after_the_judged_instant_is_not_born_full`.

## 6. Consulta nova por tick — limites e `EXPLAIN` (regra pós-incidente da T4.24b)

`e2b_for` roda **uma vez por tick** e **só** quando algum conjunto da lane liga `pedigree_e2b` (`lineage_for`). Limites:
- `ix_meme_trades_mint_block_time` (`mint`, `block_time`) serve o join: um range scan por par julgado;
- `block_time >= :floor` (`min(as_of) − 24 h`) **e** `block_time <= :ceiling` (`max(as_of)`) — os dois absolutos, porque o teto por linha (`<= j.as_of`) é correlacionado e não poda: **medido**, sem o `:ceiling` o plano abria também as partições futuras vazias (`meme_trades_2026_11/12`);
- `SET LOCAL statement_timeout = 8000` dentro de savepoint (padrão `pedigree_for` desde a T4.24b): falha → `{}` → todo conjunto recusa `e2b_top_buyer_unknown`; o laço não morre.

Plano medido (200 026 linhas na fita, 130 pares — `.claude/state/notes-T4.31-explain.txt`, escrito pelo próprio teste):

```
->  Nested Loop  (cost=0.42..5113.34 rows=948 width=51)
      ->  CTE Scan on judged j_1  (cost=0.00..2.60 rows=129 width=48)
      ->  Index Scan using meme_trades_2026_09_mint_block_time_idx on meme_trades_2026_09 tr
            (cost=0.42..39.55 rows=7 width=32)
```

Nenhum `Seq Scan` em `meme_trades`; uma única partição aberta. Ressalva honesta: o lado de `meme_tokens` aparece como `Seq Scan` **nesta fixture** (2 006 linhas); com as ~150 k de produção, `mint = ANY(130 valores)` é busca pela PK.

## 7. Cadeia de migração (resolvida durante a tarefa)

- `0044_meme_gate_e2b_arm` → `down_revision = "0043_meme_events_scan_cursor"`. Quando comecei, a `0043`
  estava **só na árvore de trabalho** (T4.26b em voo); apontar para a `0042` teria criado **duas cabeças**
  e quebrado todo teste de migração localmente, então apontei para a `0043` e deixei o aviso. Ao fim da
  tarefa a T4.26b **commitou** (`4b2e84db`): a cadeia está íntegra no HEAD, sem rebase pendente.
- `packages/core/tests/integration/test_migrations.py`: quando fui commitar, o diff do arquivo já era
  **só meu** (o da T4.26b entrou no commit deles). Mexi em três coisas: `HEAD_REVISION → 0044`, a constante
  nova `EVENTS_SCAN_CURSOR_REVISION` e o `test_0043_refuses_a_downgrade_while_a_match_exists`, que usava
  `"-1"` do head e passou a estagiar em `0043` (padrão `_staged_at`, exigido pelo brief).
- **Enquanto eu trabalhava, outro agente pôs `0046_meme_rule_set_history` na árvore com
  `down_revision = "0044_meme_gate_e2b_arm"`** (mais `ddl/meme_gate_refusals.py` e modelos ORM novos, ainda
  não commitados). Enquanto esses arquivos estiverem no disco sem migração commitada, `upgrade head` vai
  além da `0044` e `command.check` acusa diff de autogenerate — foi assim que validei os meus três testes:
  cópia de `infra/migrations` sem a `0046` via `HUNTER_MIGRATIONS_DIR` (o mecanismo que o próprio conftest
  documenta). Quem commitar a `0045`/`0046` sobe o `HEAD_REVISION` de novo.
- **`docs/DATABASE.md` §53 (a minha seção) entrou no commit `7f7039a4` da T4.33**, que commitou o arquivo
  inteiro por pathspec enquanto a minha edição estava na árvore. Não há o que desfazer; fica o registro.

## 8. Falhas **pré-existentes** encontradas (não são minhas; não mexi)

Verificadas com a `0044` removida do disco (baseline) — falham igual:
1. `services/meme-worker/tests/test_lab_operator_3.py::test_the_seed_hands_the_desk_to_operator_4_on_the_flow_gate_arm_2` e `::test_operator_4_proposes_the_same_coin_as_flow_v2_2_…` — `KeyError: 'operator/4'`: o conjunto foi aposentado pela `0039` (T4.24) e esses dois testes nunca foram retrofitados para `operator/5`.
2. `services/meme-worker/tests/test_lab_lines.py::test_a_probe_scales_once_when_the_line_is_born_and_sells_when_it_breaks` — `report.fills.filled == 0`.
3. Da T4.26b (em voo, arquivos deles): `test_events_persistence.py::test_a_pair_matched_once_stays_matched_across_ticks` (falha de asserção) e, no arquivo de migrações, `test_0043_a_pair_matched_once_stays_matched` — o *teardown* apaga `meme_events` **antes** de `meme_event_matches` e bate na FK; `test_persistence.py::test_retention_prunes_only_what_aged_out_and_needs_the_marker` quebra por uma linha `T426B_RETRO` deixada em `meme_event_matches`.

## 9. Commit

Por pathspec, sem `git add` de diretório: os 12 arquivos de código/migração/testes, a página EXP-M9, as
duas linhas de índice, a linha do INBOX, a errata do KB-0103 e estas notas (+ o plano do `EXPLAIN`).
`docs/DATABASE.md` **não** entra (já commitado pela T4.33, §7).
