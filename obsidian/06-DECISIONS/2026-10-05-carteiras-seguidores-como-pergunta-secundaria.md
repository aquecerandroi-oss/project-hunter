---
tags: [decisao, meme, carteiras, pesquisa, pre-registro]
status: decidida
owner: sexta-feira
updated: 2026-10-05
decided_on: 2026-10-05
by: Everton
---

# Seguidores entram no H-030 como pergunta secundária, não como critério de escolha (05/10/2026)

**Pedido do Everton:** escolher as carteiras a seguir pelos seguidores ("a maioria que tem bastante seguidor significa que muita gente segue ele").

**O que foi apresentado:**
- Seguidor mede popularidade, não o lucro de quem copia.
- Evidência própria: a lista KOL do site aparece no minuto do pico. Comprar 20 s depois deu R −0,071, acerto 15 %, n 3 486, negativo em toda célula ([[KB-0142-kol-e-call-antecipam-ou-confirmam]]).
- Mecanismos contra:
  - os seguidores compram antes da nossa ordem;
  - o dono da carteira pode vender na alta que os seguidores criam;
  - todos correm na saída.

**Decisão do Everton:** "pode colocar desse jeito". O critério principal do ranking continua sendo o **C-PnL** (o que nós ganharíamos copiando, [[2026-10-05-seguir-carteiras-lucrativas-aprovado]]). O número de seguidores entra como **pergunta secundária pré-registrada**, ao lado do C-PnL de cada entidade.

## Como entra no pré-registro do H-030 (antes de congelar)

- **Fonte:** `GET /users/{address}` do frontend da pump.fun devolve `followers` e `following` (catálogo em `docs/PUMPFUN.md`, endpoint 11). Leitura pública, sem chave.
- **Ponto no tempo (anti-olhar-o-futuro):** os seguidores crescem *depois* do sucesso, então o valor atual não pode ser usado. Guardar uma foto datada (`known_at`) por carteira candidata, lida no mesmo corte noturno do ranking, e usar só a foto anterior ao instante da aposta. Carteira sem foto anterior fica "seguidores desconhecidos". Ela não vira 0.
- **Pergunta secundária:** dentro das entidades ranqueadas, o C-PnL do braço `follow` difere entre faixas de seguidores (terços fixados antes de ver o resultado: 0, 1–99, ≥ 100, a reconferir com a distribuição do aquecimento sem olhar o C-PnL)? A hipótese registrada é de efeito **negativo ou nulo**: mais seguidores, pior para quem copia.
- **Não muda o critério de sucesso primário**, que segue o §4 do desenho. Rodar a pergunta secundária não abre um segundo caminho para declarar CONFIRMA (sem garfo de análise).
- **Custo:** uma leitura HTTP por carteira candidata por noite. O desenho do armazenamento precisa reservar uma tabela pequena de fotos de perfil.

## Relacionado

[[EXP-M15-carteiras-vencedoras]] · [[KB-0182-quem-ganha-dinheiro-de-verdade-nos-memes]] · [[KB-0136-carteiras-vencedoras-nao-sao-gatilho]] · [[2026-10-05]]
