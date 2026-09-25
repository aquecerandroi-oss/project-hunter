---
tags: [experimento, meme, entrada, recuo, h-017, m4, r77, t4-91]
status: pré-registrado — braço de papel `recuo_v1/1` semeado pela migração `0063` (T4.91); nada real
owner: sexta-feira
updated: 2026-09-23
origem: R77 / KB-0157 (23/09/2026) — a H-016 refutou (esperar um recuo de 5 % não paga), mas a célula X = 3 % / W = 60 s deu +2,28 pp por SOL no papel (IC [+0,69, +3,89], Holm 0,052), com o ganho vindo do PREÇO de entrada. Achado da mesma população → só se julga em coorte nova (H-017). Everton, 23/09 ~22 h: "faz ligada, quero ir vendo o teste".
previsao: diferença emparelhada ≥ +2 pp por SOL decidido contra comprar em t0, IC 95 % (bootstrap por mint) acima de zero, e melhor que "não comprar nada"
tipo: pesquisa
hipotese: H-017
variavel: recuo_v1 (entrada com recuo de 3% em ate 60s, braco de papel real)
populacao: decisoes pos-deploy da T4.91, emparelhadas com a sombra de operator/5
efeito: —
ic: —
veredito: limite_de_dado
proximo_passo: R79 (25/09): 39 decisoes emparelhadas contra o minimo de 150; nao julgada
classe_de_perda: —
mercado: meme
---

# EXP-M24 — Recuo pequeno como melhora de preço (H-017, coorte nova)

## O que este experimento é

- **Testa a [[Fila de Hipoteses|H-017]]**, não a H-016. A H-016 (esperar 5 %) foi **refutada** pelo R77 ([[KB-0157-esperar-o-recuo-nao-paga]]). O que sobrou foi uma pista: a célula **3 % / 60 s** melhorou o preço de entrada em +2,28 pp por SOL no papel. Como essa pista nasceu da mesma população em que foi achada, **só vale julgada em coorte nova** — as decisões **depois do deploy da T4.91**.
- **A leitura de 10 entradas que o Everton pediu é verificação do mecanismo, não julgamento.** 10 entradas **não estimam 2 pp**: um único despejo do criador (−50 %) ou uma única vitória de 1,15× move a soma de 10 apostas mais do que o efeito inteiro que se procura.
- **A decisão de dinheiro real continua a ser do Everton.** Nada aqui liga nada em dinheiro real.

## Braço (congelado — mudar qualquer item é braço novo e EXP nova, nunca edição desta linha)

- **Conjunto:** `recuo_v1/1` (`01994d00-6c1a-7000-8000-00000000001d`), `kind = research_only`, `exp_ref = EXP-M24`, migração `0063_meme_pullback_entry_arm`.
- **Porta:** a de `operator/5` **como ela roda** (`fluxo_e_holders/2`, pista por evento `meme_event_gate_v1`) — os `params` efetivos de `operator/5` são **copiados na hora da migração** (na VPS: a linha editada à mão por `--set-param`; num banco novo: o seed da `0039`). O teste `test_migration_0063` prova que `recuo_v1/1 − as 13 chaves do braço = operator/5 − as mesmas 13`, byte a byte. **Depois do deploy, registrar aqui o `md5(params::text)` de `operator/5` e de `recuo_v1/1` e a hora do deploy** (início da coorte); uma edição posterior de `operator/5` separa coortes (o braço não a acompanha).
- **Saída e tamanho (os da mesa):** 0,07 SOL nominal (`size_sol` = `max_sol_per_bet` = `max_exposure_per_mint_sol`), alvo **1,15×**, trailing **10 %** armado na entrada (`trailing_arm_x null`), `max_hold` **300 s**; `exit_on_line_break` e `max_loss_pct` os de `operator/5`.
- **Tetos de papel (declarados, não os da mesa):** `max_open_positions 25`, `daily_loss_cap_sol "10.0"`, `wallet_max_sol "100.0"` — o raciocínio do `0060`: nos tetos da mesa o braço travaria pela própria banca e mediria isso, não a entrada.
- **Célula:** `entry_pullback_pct "3"`, `entry_pullback_window_s 60` — a melhor célula do R77. Outra célula = **EXP nova**.
- **Papel por construção:** `research_only` — o executor só seleciona `rs.kind = 'operator'` (`hunter_meme_executor.auto_approve._OPERATOR_PROPOSED`; o teste da `0063` roda essa consulta contra uma proposta do braço e ela não volta).

## Mecanismo (T4.91 — `hunter_meme_worker.entry_pullback`, `entry_pullback_book`, `event_gate_pullback`)

- **Armar:** a porta aprova em `t0` na pista por evento → o braço **não** propõe; grava na trilha `entry_pullback_armed` (`as_of = t0`, `limit = 3`) com a fita de `t0`.
- **Preço:** `virtual_sol / virtual_token` depois de cada `TradeEvent` (as fotos `accountNotification` não criam máxima nem disparam — R77 §1.3). Máxima inicial `M` = o estado conhecido em `t0` (último ponto, troca ou foto).
- **Gatilho:** o primeiro trade com preço `≤ M × (1 − 3/100)`, `M` = a máxima **antes** desse trade. Janela `(t0, t0 + 60 s]` no `received_at` — o fim é **inclusivo**; só contam trades dobrados **depois** do armar.
- **Rechecagem no gatilho (falha fechada):** **censura** (`pullback_censored:<motivo>`) se o mint saiu do livro, se houve buraco de feed desde `t0`, se o conjunto mudou desde `t0`, sem linha-base ou com o fluxo do criador estourado — perda operacional, fora dos dois lados; **mata** (`pullback_killed:<motivo>`) se o **criador vendeu** desde `t0` ou se a porta, julgada de novo no instante da decisão, recusa por qualquer critério **fora** da lista de dispensa (momentum já julgado em `t0` — fluxo, compradores, razão vendas/compras, holders/progresso subindo, linha, carteiras novas, quick-flip — e `age_above_max`). `recent_drawdown`, participação no volume, teto de compras, pedigree, E2-b, Mayhem, curva, `already_open` e todo `*_unknown` **matam**.
- **Proposta:** no instante da decisão (`proposed_at`), com a cotação desse instante, `features_end_time = t0`, as razões de `t0` + o bloco `{"feature": "entry_pullback", "t0", "armed_max_price", "t0_price", "trigger_price", "trigger_at", "trigger_signature", "trigger_slot", "pct", "window_s", "waited_s"}`. Trilha `refusal = NULL` só para a proposta que **entrou** no banco.
- **Não-entradas com nome (trilha `meme_gate_refusals_by_mint`, com fita):** `no_pullback` (`value` = recuo mais fundo visto, %; `limit` = 3), `pullback_censored:feed_lost` (sem prova, em 30 s, de que a fila processou tudo até o prazo; ou buraco/saída do livro), `pullback_censored:<motivo>` (perda operacional no gatilho — o mesmo nome com ou sem toque depois), `pullback_killed:<motivo>` (julgamento), `pullback_dropped_cap` (mais de 256 armados), `pullback_not_inserted` / `pullback_insert_failed` / `pullback_insert_saturated` (a inserção roda fora do laço de avaliação, num conjunto limitado a 8 em voo). Um frame recebido até `t0` mas dobrado depois do armar (fila atrasada) é o estado de `t0`: atualiza `M` e nunca dispara. Uma escrita da trilha que falha volta para a fila (reescrita idempotente).
- **Memória:** só em memória; uma armação por (conjunto, mint) enquanto dura a marca de "gasto" (1 h, até 4 096 marcas — muito mais que a janela de idade da porta) **dentro de uma execução do processo**; um reinício perde os armados (a linha `entry_pullback_armed` fica sem desfecho) e pode rearmar o mesmo mint → **a análise usa a primeira linha `armed` por mint**.
- **Heartbeat:** `event_gate_pullback_{armed_now, armed_total, triggered_total, proposed_total, not_inserted_total, expired_no_pullback_total, censored_total, killed_by_recheck_total, dropped_cap_total, trail_dropped_total, trail_write_failed_total}`.
- **Pedigree da mesa:** as apostas de papel do braço são **subtraídas** da leitura de pedigree da mesa (`lab_repo_fast._PEDIGREE`, como o `refused_probe_v0/1` da T4.85) — uma aposta do braço, aberta mais tarde que a sombra da mesa, pode ver uma venda do criador que a mesa não viu e mudaria o `creator_repeat_dumper` de `operator/5`.
- **Rastreador:** as apostas abertas do braço **não fixam** o mint (`tracker_pins`). Fixado, o mint continuaria a gerar linhas de `meme_features_1m` (com `creator_sold`, que alimentam o pedigree da mesa sem id para subtrair) e estreitaria o teto do rastreador para todos. Custo declarado: sob pressão do teto, uma aposta do braço pode perder fotos na cauda (até ~60 s depois da sombra da mesa, ou a aposta inteira quando a mesa não pegou o mint) e fechar por leitura pontual ou `indeterminate` — essas saem dos dois lados e são contadas.

## Protocolo (congelado)

- **População:** só decisões do braço **depois do deploy da T4.91**; uma por mint (a primeira linha `entry_pullback_armed`).
- **Controle emparelhado:** para cada decisão do braço em `t0`, a **sombra de papel de `operator/5` na mesma decisão** (mesmo mint, mesma porta, mesmo `t0`, entrada imediata). Decisão sem controle correspondente sai dos dois lados e é contada.
- **Métrica:** retorno líquido por SOL decidido, `ret = pnl_sol / size_sol`; **`no_pullback` e `pullback_killed:*` = 0** no braço (não entrou); `pullback_censored:*`, `pullback_dropped_cap`, `pullback_not_inserted`/`pullback_insert_failed`/`pullback_insert_saturated`, apostas `indeterminate` e armações sem desfecho (reinício) ficam **fora dos dois lados** e são contados.
- **Duas comparações:** (a) braço − controle, emparelhado por decisão; (b) braço contra **"não comprar nada"** (retorno 0).
- **Julgamento (H-017):** com **≥ 150 decisões resolvidas**. CONFIRMA se a diferença emparelhada é **≥ +2 pp por SOL decidido** com IC 95 % (bootstrap por mint, 10 000) acima de zero **e** o braço bate "não comprar nada". REFUTA se o limite superior do IC fica abaixo de +1 pp, **ou** não bate "não comprar nada". Menos de 150 decisões resolvidas = limite de dado: **esperar, não julgar**.

## Verificação do mecanismo — a leitura de 10 entradas (não é julgamento)

Depois de **10 entradas resolvidas** (pode ser no mesmo dia), conferir e reportar:

1. todo `trigger_price ≤ armed_max_price × 0,97` nos blocos `entry_pullback` das propostas;
2. **zero** entradas depois de uma venda do criador (conferido na fita da decisão);
3. a **soma das diferenças emparelhadas** (braço − sombra de `operator/5`, `no_pullback` = 0), **reportada, sem decidir nada**;
4. a divergência entre o preço de entrada simulado pelo R77 e o preço de entrada ao vivo (fill do papel), decisão a decisão.

Os itens 1–2 falhos = **defeito do mecanismo** (parar o braço e corrigir). O item 3 **não é critério**: 10 entradas não estimam 2 pp.

## Diferenças declaradas entre o R77 e o braço ao vivo

- Relógio: o R77 usa o tempo de bloco; o braço usa o `received_at` (o que sabíamos quando).
- O braço **recheca** no gatilho (criador, pedigree, curva, …) e o R77 não — o braço entra **menos** vezes.
- Pouso: o R77 simula gatilho + 1,6 s; o papel preenche na primeira foto depois de `decided_at`.
- Cotação e rechecagem leem o estado no instante da decisão, que pode incluir trocas da mesma notificação posteriores ao gatilho (o bloco guarda `trigger_at`; `proposed_at` é a decisão).

## Como ligar em outro conjunto de papel (não executado)

`--set-param` grava uma chave por chamada e recusa um documento que o Lab não carrega; `entry_pullback_pct` é o interruptor, então **a janela vem primeiro**:

```
uv run python infra/scripts/meme_rule_set.py --set-param entry_pullback_window_s=60 --rule-set <nome>/<versão> --reason "EXP-M24: janela do recuo"            # dry-run
uv run python infra/scripts/meme_rule_set.py --set-param entry_pullback_window_s=60 --rule-set <nome>/<versão> --apply --reason "EXP-M24: janela do recuo"
uv run python infra/scripts/meme_rule_set.py --set-param 'entry_pullback_pct="3"' --rule-set <nome>/<versão> --reason "EXP-M24: liga a entrada no recuo"      # dry-run
uv run python infra/scripts/meme_rule_set.py --set-param 'entry_pullback_pct="3"' --rule-set <nome>/<versão> --apply --reason "EXP-M24: liga a entrada no recuo"
```

Só em conjunto `clock = "15s"` (outro relógio recusa). Desligar: `--set-param entry_pullback_pct=null`.

## Relacionado

[[Fila de Hipoteses]] · [[KB-0157-esperar-o-recuo-nao-paga]] · [[KB-0149-o-que-a-mesa-real-ensinou]] · [[EXP-M23-desfecho-das-recusadas]] · [[EXP-M22-absorcao-de-venda]] · [[Registro de Tentativas]]

## Avaliações (acrescentadas, nunca reescritas)

### Avaliação 2026-09-25 (R79, ~23:50Z) — `LIMITE DE DADO`, não julgado

**Coorte:** 171 armações `entry_pullback_armed` (1.ª por mint), de 24/09 05:46Z a 25/09 23:06Z (41,3 h). Lidas
na VPS só com SELECT (`.claude/state/r79/q_h017.sql`, cache `r79/cache/h017.csv`). Relatório em
`.claude/state/notes-R79.md` §4, saída em `r79/h017.txt`, KB em [[KB-0159-a-desaceleracao-nao-avisa-o-topo]].

**Desfechos do braço:**
- entrou: 141;
- `pullback_killed`: 16 (holders_below_min 6, participation_above_cap 5, creator_sold_during_wait 4,
  progress_trend_unknown 1);
- `no_pullback`: 9;
- `pullback_censored`: 5 (feed_lost 4, no_base_row 1).

Resolvidas: 166.

**Controle (protocolo acima):** a sombra de papel de `operator/5` na mesma `(mint, t0)` existe em **39**
decisões. O `operator/5` teve 39 propostas `filled`, 122 `rejected` pelo `auto_stage1` (`creator_flow_unknown`
38, `below_min_sol` 29, `participation_above_cap` 16, `creator_net_seller` 14, `bundled_share_above_cap` 11,
entre outras), 9 `expired` e 1 armação ficou sem proposta. **A sombra só nasce quando a mesa real aceita.** Este
protocolo assumia uma sombra em toda decisão, e isso não acontece.

**Contra a régua:** 39 < 150 decisões resolvidas emparelhadas → **limite de dado: esperar, não julgar.**

Leitura, que não é julgamento:
- D (braço − op5) **+0,032 [−0,006, +0,082]**, braço −0,022, op5 −0,055;
- contra "nada" nos pares: −0,022 [−0,085, +0,045];
- sem o Megawatt, D +0,014 [−0,013, +0,042];
- 24/09 (n 10): +0,076; 25/09 (n 29): +0,018. Os 24 pares "só com entradas" de 25/09 (recuo −0,053 × op5 −0,034
  SOL) deixavam de fora as 5 não-entradas, que eram todas perdas do op5.

**Verificação do mecanismo:**
- item 1: 141 blocos `entry_pullback`, **0** com `trigger_price > armed_max_price × 0,97`;
- item 2: 4 mortes por `creator_sold_during_wait` registradas; não foi refeito na fita;
- item 4, **divergência de fill**: a sombra do op5 preencheu 0,8–16 s depois de `t0` (mediana 9,6 s, a foto
  seguinte). O gatilho veio em mediana 5,5 s. Em **22 dos 34 pares que entraram, os dois braços preencheram na
  mesma foto**, com retorno idêntico: o papel não mede a diferença de preço quando o gatilho vem antes da foto
  seguinte. O D decompõe-se assim: mesma foto 0,000; foto posterior (12) +0,013; não-entradas (5) +0,020;
- em 59 de 141 gatilhos, o preço do gatilho estava acima do preço de `t0`.

**Papel × real** (mesma proposta do op5, n 38): real − papel +0,002 [−0,087, +0,086].

**Próximo passo:**
- a regra congelada volta a ser lida com 150 pares, cerca de 29–30/09 a ~29 pares/dia, **só com a mesa real
  ligada e a aceitar**;
- guardar a trilha antes da poda de 7 d; a de 24/09 some por volta de 01/10;
- um controle que não dependa da mesa real (braço `research_only` de entrada imediata com os mesmos `params`) e
  o preço medido no gatilho seriam **EXP nova ou emenda declarada**, com decisão do coordenador e do Everton.
  Nada foi mudado aqui.

Astra indisponível (401).
