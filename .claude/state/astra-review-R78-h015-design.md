**RESUMO**

Como `quant-engineer`: concordo com população, desfecho e errata, com as ressalvas abaixo. **Não concordo que slot ausente ≤ máximo prove zero.**

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

Não executados; revisão estática, sem consultar desfechos nem chamar RPC.

**MUST-FIX**

1. **(1) Assinar ao receber o create não garante observar todas as compras daquele slot.** A assinatura WS é solicitada depois do evento de criação ([event_gate_subscriptions.py:74](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_gate_subscriptions.py:74)). Cenário: criação e compra de 5 SOL no slot S; assinatura efetiva depois dessa compra; primeiras compras recebidas em S+1. A regra atribui zero a S, embora tenha havido 5 SOL. `create_signature` resolve **onde** ocorreu a criação, não recupera compras perdidas. Aceitar `not_covered_from_birth` na primária mantém precisamente esse risco ([DATABASE.md:8092](C:/dev/project-hunter/docs/DATABASE.md:8092)).

   Há outra falha: os cinco slots são de **compras, por ordem de chegada**; um sexto slot distinto é descartado. Cenário: chegam S+1…S+5 e depois uma compra atrasada de S; S fica ausente apesar de observado ([event_wallets.py:186](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_wallets.py:186), [event_wallets.py:206](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/event_wallets.py:206)). Portanto, **ausência ambígua → não resolvida**, salvo prova adicional de cobertura e ausência de truncamento. `reason=null` ajuda, mas reconciliação líquida com tolerância de 1% não prova completude de compras brutas. Recontar as 150 após isso.

2. **(5) Colapso da grade não pode virar “pico”.** Se todos os quantis vizinhos produzirem a mesma partição, não existe comparação de vizinhança; declarar pico refutaria por falta de resolução. Manter empates juntos, publicar cortes/tamanhos e contar apenas partições distintas. Se q⅓=q⅔=0, ainda pode haver contraste **zeros versus positivos**, respeitando o mínimo congelado de 20 por extremo; não são três grupos equilibrados. Sem extremo suficiente: **contraste não identificável**. Sem vizinho distinto: **patamar não avaliável**, impedindo confirmação completa, sem acionar refutação por pico ([notes-R78.md:79](C:/dev/project-hunter/.claude/state/notes-R78.md:79)).

**NICE-TO-HAVE**

Publicar composição por porta e real/papel em cada extremo, além das sensibilidades: diferenças de execução e saída podem explicar parte do contraste.

**O QUE EU FARIA DIFERENTE**

Selecionaria a primeira entrada antes de filtrar desfechos fechados. Hoje o SQL filtra fechadas primeiro: uma primeira entrada ainda aberta pode ser substituída por outra já encerrada. Verificaria se isso ocorreu; se ocorreu, corrigiria antes do contraste ([q_h015_pop.sql:8](C:/dev/project-hunter/.claude/state/r78/q_h015_pop.sql:8)).

**CONCORDO COM**

- **(2)** Todas as portas de `meme_event_gate_v1`, incluindo `absorb_v0`, na primária; `fluxo_e_holders` como sensibilidade. É a população literal congelada ([Fila de Hipoteses.md:180](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:180>)).
- **(3)** PnL registrado ÷ SOL gasto é aceitável como retorno observado das políticas existentes. Declarar a diferença para R76 e não interpretar o agregado como retorno sob execução padronizada ([notes-R78.md:78](C:/dev/project-hunter/.claude/state/notes-R78.md:78)).
- **(4)** Aplicar a errata, preservando o texto original e mostrando ambos os julgamentos. Para D=alto−baixo, refutação pelo intervalo exige **limite inferior > −0,01**; limite superior > −0,01 sozinho não basta ([notes-R76.md:123](C:/dev/project-hunter/.claude/state/notes-R76.md:123)).

**OBSIDIAN**

- **Fila de Hipoteses** — acrescentar adendo H-015 sobre cobertura, zeros ambíguos, empates e errata; preservar o bloco congelado.
- **KB-0156 — O despejo em bloco não é uma rede de financiamento** — registrar que resolver o slot não resolve a completude das compras observadas.