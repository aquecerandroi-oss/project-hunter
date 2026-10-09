---
tags: [revisao-astra, meme, copiar-carteiras, h-037, exp-m28, papel, pista, caminho-quente]
date: 2026-10-09
updated: 2026-10-09
status: registro
owner: backend-specialist
decided_on: 2026-10-09
by: astra
tarefa: pista de cópia no meme-worker (tarefa C do desenho de H-037) — duas rodadas de revisão do diff
veredito: "rodada 1: REQUEST_CHANGES (14 must-fix) · rodada 2: REQUEST_CHANGES (resíduos + 7 novos) — absorvidos os que a pista pode fechar sozinha; os demais estão listados como aberto no fim"
---

# Revisão da Astra: a pista de cópia (C) do H-037

Pista de papel que copia as carteiras congeladas: decide em memória, preço e escrita fora do caminho
quente. Código em `services/meme-worker/hunter_meme_worker/copy_*.py`. Desenho e pré-registro:
[[2026-10-09-piloto-copiar-carteiras-no-papel]] · [[EXP-M28-copiar-carteiras-no-papel]] ·
[[Fila de Hipoteses]] (H-037, emendas 1–4) · diálogo [[Dialogos/copy-paper|copy-paper]] ·
revisão do pré-registro [[Revisoes-Astra/H-037-prereg|H-037-prereg]].

## O que foi lido antes (e o que mudou no plano)

- [[KB-0189-o-papel-nao-sabe-medir-a-moeda-mayhem]] e [[paper-mayhem-cap]]: o teto da venda (SOL real
  observado **mais** o custo da nossa compra) e o carimbo `sell_cap_model` vêm de `paper_engine.close_bet`.
  A pista não calcula a venda: chama `close_bet`. Por isso uma cópia Mayhem herda o teto consertado, e o
  teste do ciclo de vida confere `sell_cap_sol = real + curve_cost_sol` na linha do banco.
- [[KB-0184-o-buyevent-da-pumpswap-e-as-armadilhas-de-ler-eventos-do-programa-inteiro]]: pool com WSOL na
  base e reservas virtuais; não existe cotação de **compra** na pool no motor de papel. Resultado: a compra
  de um mint já na pool não é precificada; vira linha `rejected` com `venue_fora_do_escopo` (emenda 4 b).
  A venda após migração só existe se `venues` tiver `pumpswap`; senão `indeterminate/migrou_fora_de_praca`.
- [[KB-0186-o-tempo-real-da-pumpfun-chega-uns-0-1-s-antes-das-outras-fontes]]: a NATS chega ~0,1 s antes, mas
  "chegou antes não é operamos antes". O caminho quente mede o **nosso** trecho (`first_seen_at →
  decided_at`), não promete o slot do líder.
- O desenho (`docs/design/copiar-carteiras-papel.md`, commit `c1a171d2`) tinha ido além do briefing da tarefa:
  nomes de parâmetro congelados, funil durável, duas pistas, seletor de estado com piso de slot. Quando li
  isso, metade do primeiro código estava com nomes errados (`ticket_sol`, `exit_peak_drop_pct`); foi refeito
  contra a EXP-M28. **Lição:** o briefing do orquestrador era um resumo; a fonte é o desenho.

## Rodada 1 (14 must-fix) e o que foi feito

Transcrição: `.claude/state/astra-review-copy-lane.md`.

| # | Achado | Estado |
|---|---|---|
| 1 | fila limitada virava tarefas ilimitadas | fechado: semáforo `MAX_INFLIGHT` (32 primário, 8 secundário) tomado **antes** de retirar o job; a fila enche e o `put_nowait` recusa |
| 2 | `QueueFull` perdia saída/confirmação | fechado: outbox em memória reentregue pelo sweep, em ordem; só uma entrada é devolvida (`sobrecarga`) |
| 3 | funil/pendências não eram recuperados | fechado: `load_funnel` (pares, chaves, tentativas) + `restore_pending` com o prazo **original** |
| 4 | tarefas sobrevivem ao cancelamento | fechado: `executor.shutdown()`; a fonte que termina abre lacuna global |
| 5 | contaminação não chegava às saídas próprias | fechado: `CloseIntent.contaminated`, relido depois de precificar |
| 6 | invalidação apagava o resultado econômico | fechado: a aberta vende a mercado (`invalidated`), a fechada só ganha diagnóstico |
| 7 | "mesma assinatura" não prova o fato | fechado: identidade (assinatura, carteira, mint, lado), `LeaderConfirmation`, números e slot comparados |
| 8 | seletor sem piso de slot nem prazo | fechado: `slot ≥ slot do líder + 1`, `observed_at ≤ prazo`, `asyncio.timeout` na leitura |
| 9 | seletor da pool vendia antes do instante | fechado: piso arredondado para cima, `until=min(now, prazo)` |
| 10 | o Lab continua escritor das apostas | tarefa I (outro agente) já exclui `clock='copy'`; a pista tem leitura **própria** de recuperação e prova que o `close` dela pousou (`closed_elsewhere`) |
| 11 | stop sem efeito após a migração | fechado: a marca segue `venues`; curva esvaziada (`curve_emptied`) conta como migração |
| 12 | admissão diferente do pré-registro | fechado: primeira compra, piso 0,1 SOL, chave (estrato, mint) consumida, tetos por dia e por estrato |
| 13 | parâmetros, custos, T0 | fechado: nomes da EXP-M28, `fee_pct` 1,25 e prioridade 0,00005 por perna, T0 durável (fim da lacuna `lane_not_started`), horizonte 30 d, T0 pelo `fields_complete_at` |
| 14 | o caminho quente ainda podia esperar IO | fechado: nenhum `logger` em `on_item` nem em `dispatch`; contadores no heartbeat |

## Rodada 2 e o que foi feito

Transcrição: `.claude/state/astra-review-copy-lane-2.md`. Resíduos e novos achados que a pista fecha
sozinha, **fechados**: barreira de recuperação antes de abrir a fonte (`CopyFleet.run`); conjunto secundário
vazio sem derrubar o primário (`stratum` explícito); conjunto aposentado com posições abertas continua em
manutenção (só sai/marca/teto); saída decidida antes do fill espera `max(intenção, entry_at) + latência`;
falha de escrita reentrega a intenção original (até 5 vezes) e declara `funil_indisponivel` se um fato do
funil se perde; slot comparado na reconfirmação; `curve_emptied` tratada como migração; compra num mint já
na pool vira `rejected/venue_fora_do_escopo` sem gastar tentativa; prazo de confirmação do restart não se
estende.

## Aberto (não construído; o orquestrador decide)

1. **Recomposição depois de lacuna** (desenho §4.1): sem ela, um líder que compra e zera um mint durante a
   desconexão recompra como "primeira". A pista não tem como ler o histórico da carteira; o gancho certo é
   da fonte (tarefa A). Até lá, a falha fechada do desenho (sem novas entradas do líder) **não** está ligada.
2. **Sensibilidades `ideal` e `p90`** (desenho §3.3): `PostReserves` da confirmação não alimentam um preço
   `ideal`; e não há leitura do estado a `decided_at + 3,9 s`. Precisa ser feito antes de T0 ou virar emenda.
3. **Prioridade protegida de recursos compartilhados**: o secundário tem teto próprio de tarefas e fila
   própria, mas `chain` e o pool do banco são compartilhados e não há reserva por estrato.
4. **`co_observacao`** do funil (dois líderes, mesmo mint, mesmo microssegundo): a colisão é contada
   (`funnel_collisions`) e o par continua conhecido na memória, mas o segundo fato não é durável.
5. Heartbeat em `hb:meme:radar` com prefixo `copy_` (briefing); o desenho pede `hb:meme:copy`, o stream
   Redis por líder e o hash `copy:pos:<bet_id>` (o pico do líder reinicia no valor do gatilho).

## Onde discordo da Astra

- "Função síncrona não prova ausência de IO": certo, por isso o teste usa colaboradores que explodem se
  tocados e um logger que explode; a prova é por construção **e** por contraexemplo.
- `-stake` como imputação: a Astra pede que apareça como imputação adversa à parte; mantive o
  `indeterminate` do motor (as somas já o deixam de fora) e o rótulo vai em `outcome_quality_reason`.

## Relacionados

[[Revisoes-Astra/Index|índice das revisões]] · [[EXP-M15-carteiras-vencedoras]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]] · [[Open Bugs]]
