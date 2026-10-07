---
tags: [revisao-astra, meme, mayhem, simulador, papel, bug, teto]
date: 2026-10-07
updated: 2026-10-07
status: registro
owner: quant-engineer
decided_on: 2026-10-07
by: astra
tarefa: conserto do teto da venda de papel em moeda Mayhem (bug do R89/H-032)
veredito: "desenho: concorda com real observado + curve_cost_sol, com 4 must-fix absorvidos; diff: APPROVE_WITH_NITS, nenhum must-fix novo, 2 nice-to-have absorvidos"
---

# Revisão da Astra: teto da venda de papel em moeda Mayhem

Duas consultas, as duas em modo opinião. As transcrições estão em `.claude/state/astra-review-paper-mayhem-cap.md` (desenho) e `.claude/state/astra-review-paper-mayhem-cap-diff.md` (diff).

O defeito está em [[KB-0189-o-papel-nao-sabe-medir-a-moeda-mayhem]]. A correção está em [[Resolved Bugs]] e os residuais em [[Open Bugs]].

## 1. Desenho, antes de codar

**Pergunta.** Qual é o teto correto da venda para a nossa posição hipotética numa curva Mayhem? A mesma omissão atinge as não-Mayhem? A dupla cobrança de impacto nas reservas virtuais entra agora? Como fica o bug?

**Ela concorda com:**

- **Teto = SOL real observado + `curve_cost_sol`.** Vale para uma aposta isolada, ainda na curva e sem saídas anteriores, desde que os demais fluxos sejam mantidos como observados.
- **A prova algébrica para a curva padrão.** Com `x = 30 + r` e `x·y = k₀`, o máximo de `venda − r` ocorre no piso e fica abaixo de `c`.
- **Usar o aporte, não o gasto total.** As taxas não entram no cofre.
- **Não descontar as compras do agente.** Elas já estão no SOL real observado, e descontar de novo duplicaria a conta.
- **Primeira marca sem mudança.** Ela vende contra as reservas depois da compra, devolve `c` bruto, e `r + c ≥ c`.
- **Dupla cobrança nas virtuais fica para uma tarefa separada.**

**Must-fix, todos absorvidos:**

1. **Declarar a hipótese dos fluxos externos preservados.** Cenário: uma venda de terceiro, reprecificada depois da nossa compra, tira 0,02 a mais e o cofre contrafactual cai para `r + 0,05`.
   - Feito: o docstring de `Snapshot.sell_cap_sol` diz "accounting cap, not a replay".
2. **Não chamar as pernas independentes de conservadoras.** Cenário: com `R = 0,10` e duas pernas de 0,07, cada uma pode receber 0,17, contra 0,24 disponíveis.
   - Feito: o docstring diz que cada perna é limitada pelo próprio aporte, nunca por um cofre compartilhado, e o adjetivo saiu.
3. **Identificar as apostas de transição.** Cenário: uma marca velha disparou `max_loss`, e a saída sai depois do deploy com o teto novo.
   - Feito: `sell_cap_model` vai na entrada nova e na saída. Saída com o carimbo e entrada sem ele indica transição.
4. **Corrigir a justificativa falsa** ("em curva padrão o teto não pode morder") em `executable.sell_cap_sol` e em `curve.quote_sell`.
   - Feito, nos dois docstrings.

**Bug:** fechar só a omissão do aporte e deixar **dois** residuais abertos, a trajetória das virtuais e a semântica da venda Mayhem sem liquidez. Foi feito assim.

## 2. Diff, antes de reportar

**Veredito: APPROVE_WITH_NITS. Nenhum must-fix novo.**

- **(a) Aposta sem `entry.curve_cost_sol`.** Daria `KeyError` no `load_open_bets`. Mas a chave existe desde a criação do Lab (`f7edcfef`, 12/09), que ela conferiu no histórico.
  - Ela não exigiria fallback e rejeita zero silencioso, porque zero reintroduziria o defeito.
- **(b) Foto REST, nula ou zero.** O SOL real nulo é recusado pelo normalizador e a coluna é `NOT NULL`.
  - Em Mayhem incompleta com SOL real zero, o teto passa a ser só o aporte, o que está correto.
  - Um `complete` ou um zero errado vindo da fonte ainda distorce a marca, mas isso não foi introduzido pelo diff.

**Nice-to-have:**

- **Absorvido:** provar que a foto idêntica não dispara mais `max_loss`, além do recebimento. Asserção de `decide_exit` adicionada no teste da foto real.
- **Absorvido:** documentar o alcance do carimbo. Saídas por pool e fechamentos sem foto não têm teto nem carimbo, e o docstring de `SELL_CAP_MODEL` agora diz isso.
- **Primeiro não feito, depois feito por pedido do code-reviewer:** teste de transição com recarga pelo banco (`test_lab_cap_transition.py`).
  - Uma aposta aberta com a entrada sem carimbo é recarregada e vendida: a saída sai carimbada e com `own_curve_sol` igual ao `curve_cost_sol` da linha.
  - Uma linha sem `curve_cost_sol` é recusada com `KeyError`, nunca lida como zero.

## Errata — 07/10, depois da revisão do code-reviewer

- **Corrigido.** A primeira versão desta nota, e o relatório que a acompanhou, diziam que "19 testes de integração passaram" como se cobrissem o conserto. Os 19 eram só `test_lab_persistence`, `test_launch_lane_integration` e `test_lab_e2b_persistence`.
- **O teste que fixava o teto velho ficou fora.** `test_lab_mayhem.py` (integração) ainda esperava `0,88425` e falhava com o teto novo. O code-reviewer pegou: 1 falha e 34 aprovações.
- **O que mudou:**
  - O teste passou a esperar cofre + aporte (`0,9325300983`).
  - Ele confere `sell_cap_model`, `sell_cap_sol` e `own_curve_sol` na linha do banco. É a prova de ponta a ponta do caminho de carga.
- **O que entrou junto:**
  - O teste de transição acima.
  - Uma grade de 144 casos em curva padrão (`r0 × aporte × r1`, `k` constante) que prova `venda ≤ r1 + c`.
  - As asserções de carimbo na pista de lançamento.
- **Rodada final:** os números estão no relatório da tarefa, com a saída real.

## O que não se pode afirmar (dela, adotado)

- Que a trajetória contrafactual está validada.
- Que a venda Mayhem on-chain está validada.
- Que a H-032 muda de rótulo. Ela continua `NÃO CONFIRMA — instrumento`, porque corrigir o código não refaz os gatilhos.

## Relacionados

[[H-032-mayhem-prereg]] · [[H-032-mayhem-resultado]] · [[KB-0189-o-papel-nao-sabe-medir-a-moeda-mayhem]] · [[EXP-M23-desfecho-das-recusadas]] · [[Open Bugs]] · [[Resolved Bugs]] · [[Revisoes-Astra/Index|índice das revisões]]
