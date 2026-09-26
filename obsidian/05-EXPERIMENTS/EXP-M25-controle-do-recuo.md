---
tags: [experimento, meme, entrada, recuo, controle, h-017, m4, r79, t4-95]
status: pré-registrado — braço de papel `recuo_ctrl_v1/1` semeado pela migração `0065` (T4.95); nada real
owner: sexta-feira
updated: 2026-09-25
origem: R79 (25/09/2026) — a sombra de papel do `operator/5`, controle da H-017 no EXP-M24, só nasce quando a mesa real aceita; 39 de 171 armações tinham par (122 recusadas pelo `auto_stage1`, 9 expiradas, 1 sem proposta). Decisão do coordenador (T4.95): um controle de entrada imediata que não dependa da mesa real.
previsao: operacional — toda armação de `recuo_v1/1` depois do deploy tem, na mesma decisão, uma proposta de `recuo_ctrl_v1/1`; ≥ 150 pares resolvidos em ~1,5–2 dias. O julgamento é o da H-017, sem mudança de régua
tipo: pesquisa
hipotese: H-017
variavel: controle de entrada imediata em t0 (recuo_ctrl_v1 = recuo_v1 sem entry_pullback_pct/entry_pullback_window_s)
populacao: armacoes de recuo_v1/1 depois do deploy da 0065, uma por mint, emparelhadas com recuo_ctrl_v1/1 na mesma (mint, t0)
efeito: —
ic: —
veredito: —
proximo_passo: deploy da 0065; registrar md5 das duas linhas e a hora; conferir o par nas 10 primeiras armacoes
classe_de_perda: —
mercado: meme
---

# EXP-M25 — O controle de entrada imediata do recuo (fornece o controle da H-017)

## O que este experimento é

- **Não é hipótese nova.** Fornece o **controle** que faltava à [[Fila de Hipoteses|H-017]], testada pelo
  [[EXP-M24-entrada-no-recuo]]. A previsão e a régua da H-017 não mudam; muda só **contra o quê** o braço é comparado.
- **Por que (R79, `.claude/state/notes-R79.md` §1 "Achado estrutural" e §4):** o protocolo do EXP-M24 emparelhava cada
  armação com a sombra de papel do `operator/5` na mesma decisão. Essa sombra só existe quando a mesa real **aceita** a
  proposta. Das 171 armações de 24–25/09, **39** tinham par; 122 foram recusadas pelo `auto_stage1` (`creator_flow_unknown`
  38, `below_min_sol` 29, `participation_above_cap` 16, …), 9 expiraram e 1 ficou sem proposta. O braço é
  `research_only` e não passa por esses checks: opera decisões que a mesa recusou. O controle faltava **por
  construção**, e o ritmo de pares dependia da mesa real ligada e a aceitar.
- **A saída do R79 que isto executa:** a avaliação de 25/09 do EXP-M24 ("Próximo passo", 3.º item) — "um controle que
  não dependa da mesa real (braço `research_only` de entrada imediata com os mesmos `params`) … seria EXP nova ou emenda
  declarada, com decisão do coordenador". É esta EXP nova, por decisão do coordenador na T4.95.
- **Nada real.** A decisão de dinheiro real continua a ser do Everton.

## Braço (congelado — mudar qualquer item é braço novo e EXP nova, nunca edição desta linha)

- **Conjunto:** `recuo_ctrl_v1/1` (`01994d00-6c1a-7000-8000-00000000001e`), `kind = research_only`, `exp_ref = EXP-M25`,
  migração `0065_meme_pullback_control_arm` (`docs/DATABASE.md` §67).
- **Documento:** o `params` **vivo** de `recuo_v1/1` na hora da migração, **menos** `entry_pullback_pct` e
  `entry_pullback_window_s` — e nada mais. Mesma porta (a de `operator/5` copiada pela `0063`), mesma saída (1,15× ·
  trailing 10 % armado na entrada · 300 s), mesmo tamanho (0,07 SOL), mesmos tetos de papel (25 posições,
  `daily_loss_cap_sol "10.0"`, `wallet_max_sol "100.0"`), relógio `15s`. `test_migration_0065` prova `controle = braço −
  as 2 chaves`, byte a byte. **Depois do deploy, registrar aqui o `md5(params::text)` de `recuo_v1/1` e de
  `recuo_ctrl_v1/1` e a hora do deploy** (início da coorte). Uma edição posterior de qualquer das duas linhas separa
  coortes.
- **Entrada:** imediata em `t0`. Sem `entry_pullback_pct`, o conjunto propõe como todo conjunto sempre propôs.
- **Papel por construção:** `research_only` — o executor só seleciona `rs.kind = 'operator'`
  (`hunter_meme_executor.auto_approve._OPERATOR_PROPOSED`; o teste da `0065` roda essa consulta contra uma proposta do
  controle e ela não volta). A proposta nasce `approved` por `rules` e o motor de papel do Lab a preenche.
- **Não altera a mesa:** as apostas do controle são subtraídas do pedigree da mesa (`lab_repo_fast._PEDIGREE`) e não
  fixam o mint no rastreador (`tracker_pins`), como as de `recuo_v1/1` (T4.91). Isto importa mais aqui: o controle
  entra justamente nas decisões que a mesa **recusou**.

## Como o par nasce

- Os dois conjuntos são `15s` e são julgados na **mesma** avaliação da mesma linha pela pista de eventos
  (`event_gate_eval.evaluate_mint`). O braço arma (`entry_pullback_armed`, `as_of = t0`); o controle propõe com
  `features_end_time = t0`. É o mesmo mecanismo que já dava uma proposta do `operator/5` em 170 das 171 armações do R79.
- **Onde o par pode faltar (contado, nunca preenchido):** o controle também é julgado pela pista de 15 s (o braço não);
  se essa pista o fizer entrar no mint **antes** da pista de eventos, a proposta em `t0` é recusada por `already_open`.
  Também falta se o controle bater um teto próprio (25 abertas) ou a inserção falhar.
- Provado na pista de eventos real (`services/meme-worker/tests/test_pullback_control.py`): a mesma avaliação arma o
  braço e grava a proposta do controle em `t0`, aprovada por `rules`; com o mint já aberto no controle, o braço arma e o
  controle não propõe.

## Protocolo (congelado)

- **População:** só armações de `recuo_v1/1` com `t0` **depois do deploy da `0065`**; uma por mint — a **primeira**
  linha `entry_pullback_armed` do mint (a regra do EXP-M24: um reinício pode rearmar).
- **Par:** para essa armação, a proposta de `recuo_ctrl_v1/1` do **mesmo mint** com `features_end_time = t0` e a sua
  aposta de papel (`leg = 'single'`). É a primeira aposta do controle naquela decisão.
- **Métrica:** a do EXP-M24, calculada como no R79 §2.2: `r = pnl_sol ÷ SOL gasto` (`entry.sol_spent`).
  - Braço: aposta resolvida → `r`; 1.ª linha de desfecho do recuo na trilha depois de `t0` = `no_pullback` ou
    `pullback_killed:*` → **`r = 0`** (não entrou).
  - Fora dos dois lados, **contados**: `pullback_censored:*`, `pullback_dropped_cap`,
    `pullback_not_inserted`/`pullback_insert_failed`/`pullback_insert_saturated`, aposta `indeterminate`, armação sem
    desfecho (reinício); e, do lado do controle, proposta ausente em `(mint, t0)`, `unfilled`, `indeterminate` ou não
    resolvida.
- **Duas comparações:** (a) `D = média(r_braço − r_controle)` emparelhado, IC 95 % bootstrap por mint (10 000);
  (b) braço contra "não comprar nada" (retorno 0), mesmo IC.
- **Julgamento — o da H-017, sem mudança:** só com **≥ 150 pares resolvidos**. CONFIRMA se `D ≥ +2 pp` por SOL decidido
  com IC acima de zero **e** o braço bate "não comprar nada". REFUTA se o limite superior do IC fica abaixo de +1 pp,
  **ou** o braço não bate "não comprar nada". Menos de 150 = limite de dado: esperar, não julgar.
- **Descritivo, sem peso no rótulo:** o par com a sombra do `operator/5` onde ela existir (a leitura do R79 continua);
  por dia UTC; e a parte de `D` que vem de pares em que os dois lados preencheram na mesma foto (ressalva abaixo).

## Ressalva de fidelidade do papel (R79 §4, declarada antes de qualquer dado)

O papel preenche "na primeira foto depois de `decided_at`". O controle decide em `t0` e preenche na foto seguinte
(mediana ~9,6 s depois de `t0` no R79, como a sombra do `operator/5`). O braço decide no gatilho (mediana 5,5 s); quando
o gatilho vem **antes** dessa foto, os dois preenchem **na mesma foto**, com retorno idêntico — diferença zero por
construção (22 de 34 pares que entraram no R79). Nesses pares o papel não mede a melhora de preço que a H-017 procura;
ela só aparece nos pares em foto posterior e nas não-entradas. **Este controle não corrige isso — só faz o par existir
sem depender da mesa real** (salvo as faltas contadas em "Como o par nasce"). A leitura de nível do braço continua sujeita à distância papel × real (R77/KB-0157).

## Verificação do mecanismo (não é julgamento)

Nas **10 primeiras armações** depois do deploy, conferir e reportar:

1. cada armação tem uma proposta de `recuo_ctrl_v1/1` no mesmo mint com `features_end_time = t0`;
2. todas as propostas do controle estão `decided_by = 'rules'` e nenhuma virou posição real (`meme_live_positions`);
3. o `md5(params::text)` das duas linhas bate com o registrado no deploy.

Item 1 ou 2 falho = defeito do mecanismo (parar o controle e corrigir).

## Ritmo esperado

R79: 171 armações em 41,3 h (~4/h, ~99/dia), 166 resolvidas. Com par em ~99 % das armações (o que a proposta do
`operator/5` já mostrava), 150 pares resolvidos chegam em **~1,5–2 dias** depois do deploy, com a mesa real ligada ou
não. A trilha `meme_gate_refusals_by_mint` (onde vivem `entry_pullback_armed`/`no_pullback`/`pullback_killed`) é podada
em 7 d: guardar o recorte antes da poda.

## Relacionado

[[EXP-M24-entrada-no-recuo]] · [[Fila de Hipoteses]] (H-017) · [[KB-0157-esperar-o-recuo-nao-paga]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]] · [[EXP-M23-desfecho-das-recusadas]]

## Avaliações (acrescentadas, nunca reescritas)
