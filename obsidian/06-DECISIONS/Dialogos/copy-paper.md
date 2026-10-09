---
tags: [dialogo, astra, carteiras, copia, nats, papel, h-037]
date: 2026-10-09
updated: 2026-10-09
status: registro
owner: sexta-feira
decided_on: 2026-10-09
by: sexta-feira + astra
tarefa: desenho do piloto de copiar ~20 carteiras no papel (H-037, EXP-M28) e da pista de cópia no meme-worker
veredito: "4 rodadas. R1 REQUEST_CHANGES com 8 must-fix; R2 REQUEST_CHANGES com 5 (R2-1 a R2-5); R3 com 1 residual (colisão do UNIQUE do funil); R4 DECISÃO CONJUNTA, sem discordância de desenho. O fechamento não aprova código nem autoriza T0"
---

# Copiar carteiras no papel: o desenho até a decisão conjunta

**Pedido:** o piloto que o Everton aprovou em [[2026-10-09-piloto-copiar-carteiras-no-papel]]. Os documentos são o
desenho `docs/design/copiar-carteiras-papel.md` e o pré-registro H-037 da [[Fila de Hipoteses]]. O experimento é o
[[EXP-M28-copiar-carteiras-no-papel]], e a transcrição bruta está em `.claude/state/dialogue-copy-paper.md`.

## Rodada 1: 8 must-fix

| MF | Achado | O que mudou |
|---|---|---|
| MF1 | Uma página de `/user-trades` não detecta um robô de 900 trades/dia nem episódios completos. "Realizado ≥ não realizado" deixa passar +10 realizado com −100 não realizado. O KB-0186 não sustenta "100 % das pernas" | Paginação até 7 dias com teto de 10 páginas (falha fechada). Episódio definido. `pnlSol > 0` exigido. Citação corrigida para 415/415 e 1 315/1 317 |
| MF2 | Excluir as cópias invalidadas do primário apaga perdas que a política rápida assumiu | As invalidadas ficam no primário. A invalidação vira intenção de saída no instante em que soubemos |
| MF3 | O contrato proíbe agir em evento provisório, exige `sol_delta` inteiro e não tem confirmação separada. Token que sobe com SOL que desce não prova swap | Emenda 0b do contrato. Evidência mínima de entrada. Cinco estados de confirmação |
| MF4 | 1,65 s não é "conservador". O seletor do Lab não serve. Faltam prazos e ordem causal | Chamado de cenário nominal. Seletor próprio (estado observado ≥ decisão + 1,65 s, slot ≥ líder + 1, `confirmed`). Prazos de 30 s e 60 s. A PumpSwap só entra com aceite próprio |
| MF5 | Depois de um reinício, a elegibilidade muda: o stream Redis é aparado e as compras recusadas não ficam guardadas | Funil durável em `meme_proposals` e reconstrução na partida |
| MF6 | A dispensa do risk-engine-guardian estava mal provada. O executor seleciona por `mode = 'live'` sem filtrar o `kind` (`repo.py:111`), e `decide_proposal` muda o `mode` de qualquer linha `proposed` | A cópia nasce já `approved`/`paper`. O guardião volta numa revisão limitada à fronteira (R4) |
| MF7 | O Lab lê toda proposta `approved` e toda aposta `open`; ele tomaria as linhas da cópia | Tarefa I: dono único das linhas da cópia, com teste de coexistência |
| MF8 | T0 ambíguo e parada dependente da velocidade de fechamento | T0 é o fim da lacuna inicial. Horizonte fixo de 28 dias. Tarefa X congela a análise antes da coleta |

Os achados de MF6 e MF7 foram conferidos no código antes de absorvidos: `repo.py:111`, `approval.py:57`,
`lab_repo.py:120`, `lab_repo_bets.py:107` e `lab_bets.py:101–106`/`:228`.

## Rodada 2: 5 must-fix

- **R2-1, portão de censura.** M (primário) e U (o restante de F) particionam as cópias preenchidas. S1 imputa
  r = −1 em U; S2 põe U no percentil 90 de M. Se \|U\|/\|F\| > 10 %, o portão bloqueia o veredito. O REFUTA vale só
  para as cópias medidas e precisa valer em M e em S2.
- **R2-2, piso de slot da venda.** O piso depende do gatilho da saída, o slot nunca regride e a leitura de resgate
  obedece aos mesmos cortes.
- **R2-3, fatos de elegibilidade.** Toda primeira observação de aumento de saldo do par (líder, mint) é guardada.
  Depois de uma lacuna, a pista recompõe os pares pelo histórico da carteira, ou o líder fica sem novas entradas.
- **R2-4, recursos.** Dois conjuntos (`copy_v0/1` e `copy_everton_v0/1`), cada um com recursos próprios, e
  prioridade protegida para o estrato da regra.
- **R2-5, interrupção.** Parar antes dos 28 dias dá NÃO CONFIRMA. A régua editorial de 30 dias deixa o `result` da
  EXP `inconclusivo`.

A revisão do pré-registro ([[Revisoes-Astra/H-037-prereg|H-037-prereg]]) correu em paralelo e entrou na **emenda 1**.

## Rodadas 3 e 4

**Residual da rodada 3.** "Colisão no índice único implica mint consumido" era falso. O contraexemplo da Astra: dois
líderes recusados com o mesmo carimbo, o fato do segundo perdido, um reinício, e a recompra dele passando como
primeira. **Solução:** "par já observado" e "mint consumido por admissão" são fatos distintos. O fato do segundo
líder entra como `co_observacao` no `reasons` da linha existente, e o segundo líder não é admitido
(`colisao_nao_admitida`). Registrado na **emenda 2**.

**DECISÃO CONJUNTA (rodada 4).** Pontos acordados:

- piloto só em papel;
- seleção prospectiva congelada;
- decisão provisória, com confirmação independente;
- execução simulada causal, com custos explícitos;
- primeira observação do par distinta do consumo do mint;
- colisões preservadas por `co_observacao`;
- recuperação que falha fechada;
- dois conjuntos, com recursos separados;
- dono exclusivo das linhas da cópia;
- T0 durável, depois da readiness;
- horizonte de 28 dias, com maturação limitada;
- análise e portões congelados;
- `result` editorial `inconclusivo`;
- nenhuma autorização de dinheiro real.

**Aceites de implementação, antes de T0** (não são discordâncias de desenho):

- emenda 0b do contrato;
- cortes de slot e prazos com resgate;
- os três casos de colisão, reinício e duplicata;
- reserva de vagas e o teste com o estrato secundário saturado;
- isolamento do Lab e a fronteira com o executor (R4);
- tarefa X;
- o ensaio E2E;
- as revisões R1–R4.

**Rastreabilidade (registrada pela Astra na rodada 4).** O sha256 da emenda 1 que ela leu na rodada 3 (`6a9fe21b…`)
difere do atual (`776c134c…`). A causa é conhecida e foi minha: depois da rodada 3 eu corrigi o carimbo do cabeçalho
da emenda 1 de "05:00Z" para "04:58Z" e o da emenda 2 de "05:20Z" para "05:09Z", para coincidir com o relógio real
da máquina. Os horários antigos tinham sido escritos à mão, adiantados. Nenhuma outra palavra mudou. A correção foi
feita antes de existir conjunto, carteira ou dado.

## Relacionado

[[EXP-M28-copiar-carteiras-no-papel]] · [[EXP-M15-carteiras-vencedoras]] ·
[[KB-0185-o-que-a-pumpfun-publica-sobre-carteiras-lucrativas]] ·
[[KB-0186-o-tempo-real-da-pumpfun-chega-uns-0-1-s-antes-das-outras-fontes]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]] · [[Dialogos/Index|índice dos diálogos]]
