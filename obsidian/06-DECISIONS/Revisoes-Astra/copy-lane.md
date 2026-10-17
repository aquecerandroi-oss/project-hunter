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

## Revisão R2 integrada (09/10/2026)

A R2 integrada do piloto (pista + fonte + combinação) deu REQUEST_CHANGES com 8 must-fix. As decisões que vieram dela estão na emenda 5 do H-037, que segue em rascunho. Síntese, aceites e os quatro deltas levados à Sexta-feira: [[cr-copy-pilot]].

Revisão de fronteira do guardião (R4, 09/10): [[guardian-copy-boundary]] — nenhum caminho de ordem real; F1/F2 (pedigree e pinos) abertos, F3 corrigido.

## Correção da R2 (09/10/2026): rodadas 3 e 4 com a Astra

Contexto: a revisão de código do commit `0736023a` deu REQUEST_CHANGES (B1 a B6, F7 a F9, sensibilidades,
F4); a síntese dela está em [[cr-copy-pilot]]. A correção foi feita com teste que falha antes, e a Astra
revisou o diff duas vezes (`.claude/state/astra-review-copy-lane-fix-r2.md` e `...-fix-r2b.md`), as duas
com REQUEST_CHANGES, a segunda mais estreita.

**Rodada 3 (8 achados), todos corrigidos em código e teste:** a saída que passava na frente de uma
entrada estacionada (agora espera a linha da entrada: `NotYet`); o desligamento que perdia o job em
andamento (o executor devolve o job cancelado e `stop()` o escreve); a lacuna fechada cuja janela não foi
lida e que o reinício esquecia (`owed_gaps` mais o marcador `recomposed`); a lacuna de saúde promovida a
downtime global no reinício (agora cada buraco mantém escopo e tipo, e o downtime começa no último
marcador); o `unverified` ressuscitado como pendência após reinício; o buraco do funil que começava
depois do fato perdido (`funnel_failed(since)`); a posição sobrevivente censurada antes de tentar reler
(`mint_trace` antes de manter a censura); e T0 sem prontidão da fonte (`wait_ready`).

**Rodada 4 (5 achados):**

| # | Achado da Astra | O que foi feito |
|---|---|---|
| 1 | entrada perdida no estouro do outbox deixava posição sem linha | `_defer` abandona a entrada (`mark_closed`) e abre o buraco desde `decided_at`; a espera esgotada de uma saída vira `_give_up` (volta a aberta e abre buraco), não só `annotation_lost` |
| 2 | `stop()` ainda perdia obrigações | o executor guarda a tarefa de cada job antes de ela começar (cancelada antes do primeiro passo não se perde); job tirado da fila durante o fechamento volta à fila; nota terminal (`unverified`/`invalidated`) que o `stop()` não escreve vira buraco declarado |
| 3 | `recomposed` gravado sem o par cuja escrita se perdeu | o livro separa "observado em memória" de "linha gravada" (`_unlanded`, `landed(job)`): a janela reemite o par que só está em memória e não reemite o que já está no banco |
| 4 | `copy_alive` avançava além do recuperável | o downtime do reinício e o fechamento dos buracos abertos são gravados na mesma transação que o primeiro marcador, antes dele; em operação o marcador para no fato mais antigo ainda não durável (`oldest_unlanded`) |
| 5 | prontidão da fonte opcional mantém o achado 8 aberto | não feito, decisão do orquestrador (ver abaixo) |

**Onde discordo da Astra:**

- Item 2, `CloseIntent` já precificado e perdido no `stop()`: a Astra pede registrar a saída como
  obrigação durável. Mantive a posição aberta no banco; no reinício ela volta marcada `worker_restart_gap`,
  relida na cadeia (`mint_trace`) e só é censurada, com nome, se a posição do líder não puder ser lida.
  Uma saída de stop interna cujo preço se recuperou antes do reinício, porém, se perde: o resultado fica
  sinalizado `contaminated`, não corrigido. É escolha de custo (reconstruir o gatilho exigiria guardar o
  estado do stop), não prova de que é inofensivo.
- Item 5, prontidão obrigatória: sem `wait_ready` a pista ainda arma quando o stream inicia (T0 pode
  cair até cerca de 20 s antes de a rede responder; `CopyFleet.ready_signal = False` mostra isso). Tornar
  o método obrigatório deixa o piloto sem armar até a tarefa A e o `copy_main` (o wrapper
  `_RenewedLeaderSource` só expõe `stream`) o entregarem; isso é decisão de prontidão do T0, não minha.

**Aberto, para o orquestrador:** (a) o gancho `LeaderHistory` (`window`, `mint_trace`) e `wait_ready` na
fonte da tarefa A, e o `copy_main` passar `history=` à pista (hoje não passa: sem histórico toda
recomposição falha fechada e o líder fica bloqueado); (b) a tabela `meme_ingest_gaps` é append-only, então
abertura e fechamento são duas linhas com `gap_id` determinístico e o marcador `copy_alive:<rule_set_id>`
é outra linha a cada 30 s: se isso incomodar, o `database-architect` decide se vira tabela própria;
(c) a reconciliação de multi-mint por confirmação (achado 6 do CR) segue sem fazer porque
`LeaderConfirmation` não traz o dado.

Aprendizado: o checkpoint de vida (`copy_alive`) só vale se for limitado pelo fato mais antigo ainda sem
representação durável; separar três estados (conhecido, durável, concluído) explica cinco dos oito achados
da rodada 3. Prova das correções: 37 mutações (21 de unidade e 16 da rodada 4) rodadas no código final,
todas mortas pelos testes.
