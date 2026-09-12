---
tags: [trading, meme, pumpfun, estudo, estrategia, pre-registro, m4]
status: vivo
owner: sexta-feira
updated: 2026-09-12
---

# Estudo — as 21 apostas de papel de 12/09 (1 acerto) e o que o vault diz sobre o que fazer

**Pedido do Everton (14:2x BRT):** "de 21 só 1 acerto; use o Obsidian para isso e trace estratégias". Este estudo cruza
as 21 apostas fechadas até 14:00 BRT (banco da VPS, `infra/scripts/sql/research/2026-09-12-t416-caso-das-21-apostas.sql`
e a consulta de filtros do orquestrador) com o que o vault já mediu hoje ([[02-MARKET/Meme/2026-09-12|nota do dia]],
[[00-INBOX/Hipoteses-do-plantao|fila]], [[11-KNOWLEDGE/README-meme|conhecimento]]). **Aviso de método:** tudo abaixo é
**dentro da amostra** (21 apostas, um dia). Serve para gerar hipóteses; nenhuma vira regra viva sem pré-registro e
medição fora da amostra ([[06-DECISIONS/2026-09-10-validacao-em-um-dia-e-lucro-real|a régua]]).

## 1. O que as 21 têm em comum (fatos)

| Fato | Número | Fonte |
|---|---|---|
| Saídas por "sem fotografia" fecharam a −1 R sem a moeda ter morrido (artefato do simulador antes das 12:14) | **5 de 21** (−5 R dos −7,67 R) | `q_case`: mcap 30 min depois = mcap da entrada |
| A moeda **nunca subiu** depois da entrada (mcap na entrada = máximo dos 30 min seguintes) | **17 de 21** | `q_case` |
| Entrada com a moeda parada no valor inicial (~28 SOL de mcap) e 1–7 holders | 12 de 21 | `q_case` |
| Sondas de hype: compras ≈ vendas no minuto (giro, não demanda) | 8 de 8 sondas (vendas/compras 0,63–1,36) | `q_filters` |
| Idade na entrada (decisão em minuto fechado + fill na fotografia seguinte) | 99–289 s; decisão→fill mediana 27 s (5–148) | `q_case` |
| Criador em série (≥ 2 moedas do mesmo criador na hora anterior) | **6 de 21**, todas perdedoras (DOJO 18, LARPEPE 35, Bupa 15, Dick 4, Traders 3, DIAPER 2) | `q_filters` |
| Clone de ticker (≥ 3 moedas com o mesmo símbolo em 24 h) | **6 de 21**, todas perdedoras (Chaotic 32, CATECOIN 29, DIAPER 27, 67 % 23, Bupa 19, RISE 9) | `q_filters` |
| Snipers > 2 no minuto da proposta | 10 de 21 (só no conjunto original; a sonda já exige ≤ 2) | `q_filters` |
| Holders ≤ 5 no minuto da proposta | 12 de 21; **a única vencedora tinha 8** | `q_filters` |
| Graduação no mesmo slot da criação | 0 de 21 (as regras já não compram essas) | `q_filters` |
| A vencedora (The Tied Pajeet, +0,16 R): 8 holders, 1 sniper, criador sem outra moeda na hora, sem clone, subiu 20 % e saiu por "criador vendeu" | 1 de 21 | `q_case`/`q_filters` |

**Leitura:** o problema não é a saída; é **o que se compra e quando**. Compramos moedas sem demanda, de criadores em
série, clones e giro de robô, 2 a 5 minutos depois de nascerem, quando o dev já vendeu (5 das 8 sondas).

## 2. O que o vault já sabia e confirma

- [[11-KNOWLEDGE/KB-0091-pump-fun-as-taxas-base-e-seus-denominadores|KB-0091]]: ~1 % gradua; a maioria morre em minutos.
- [[11-KNOWLEDGE/KB-0092-o-modelo-pre-registrado-que-morreu-no-holdout|KB-0092]]: um modelo que parecia bom (AUROC 0,86) caiu a 0,46 fora da amostra — **este estudo é exatamente o tipo de coisa que precisa de holdout**.
- Plantão run 3/5/9/13 (nota do dia): ~75 % das graduações acontecem **no mesmo segundo** da criação; as lentas (organicamente compradas) têm `bo` > 0 e top-10 alto; moedas cujo `twitter` é um **post** (não perfil) associam-se às células lentas (18/19) e perfil ao mesmo slot (42/47) — M-P17/M-P33.
- Plantão run 7/9/11: os campos `dh`/`t10` do board **mudam em minutos** para o mesmo mint (M-D5): não decidir no primeiro minuto por eles.
- Plantão run 10/13: criador em série e clones (M-P3, M-P5, M-P26, M-P29) — hoje confirmados como marcadores de perda nas 21.
- Plantão run 12 (pesquisa): o único deploy publicado em memes é negativo sem os 3 maiores trades (Kamat) — **a cauda paga**, o que sustenta os braços moonshot ([[05-EXPERIMENTS/EXP-M4-moonshot|EXP-M4]]) desde que a entrada não seja lixo.
- [[03-TRADING/Meme/Terminal-do-pumpfun|Terminal]]: a fita do site rotula o dev; no caso RISE o dev despejou 14,25 SOL aos 55 min — a fita do `swap-api` estava limitada; T4.2f/T4.2g corrigem a cobertura.

## 3. Estratégias a pré-registrar (cada uma vira uma página EXP-M* antes de rodar; previsão padrão: `descartar`)

### E1 — "Fluxo e holders" (EXP-M5, já no brief T4.16)
Porta: idade 30–300 s; fluxo líquido de SOL > 0 no minuto; ≥ 10 compradores únicos; vendas/compras ≤ 0,6;
holders subindo em duas leituras seguidas; progresso ≥ 5 % e subindo; snipers ≤ 2; dev ≤ 10 %; criador não vendedor
líquido (desconhecido recusa); participação ≤ 1 %. Saídas: alvo 3×, trailing 35 % após 1,5×, 30 min, `creator_dump`,
`line_broken`, piso 50 %. **Relógio de 15 s** nos primeiros 5 min (decisão por fotografia, fill na seguinte).
*Na amostra:* teria excluído 18 das 20 perdedoras pelos critérios de holders/snipers/criador/clone (mantendo a
vencedora e duas perdedoras: 100k or Rug? e Roblox) — dentro da amostra, sem valor confirmatório.

### E2 — "Exclusões de pedigree" (filtro transversal, EXP-M6)
Recusa nomeada em **qualquer** conjunto quando: `creator_prior_mints_1h ≥ 2` (M-P26), `symbol_dup_24h ≥ 3` (M-P3),
`post_sibling_rank_at_create > 1` (M-P33: não é a primeira moeda daquele post), `twitter` ausente **e** `desc` vazia
(sem identidade). *Na amostra:* 11 de 20 perdedoras cairiam só por criador-em-série ou clone; a vencedora passa.
É a mais barata de medir: só features que o radar já grava ou grava a partir de T4.2g/T4.12.

*Medido fora da amostra (banco da VPS, 17:0x BRT, 1 893 moedas criadas na última hora ≈ 31/min):* criador em série
(≥ 2 outras moedas do mesmo criador na hora anterior) **1 150 (61 %)**; clone de ticker (≥ 3 outras com o mesmo símbolo
em 24 h) **1 053 (56 %)**; uma ou outra **1 412 (75 %)**; primeira moeda do criador na hora 522 (28 %). Os tickers mais
clonados em 24 h: HODL ×283, ASD ×216, BALL ×125, "." ×110. Ou seja: E2 não é um filtro fino — descarta três quartos do
que nasce, e é o que a porta `flow_v2/1` mostra no heartbeat (`creator_serial` 64 e `symbol_clone` 65 de ~110 moedas
jovens por tique). O que sobra (~25 %) é a população onde E1/E3/E5 têm de provar valor.

### E3 — "Orgânica lenta" (EXP-M7)
Alvo explícito das moedas que **não** graduam no slot da criação e cujo `twitter` é um post (célula lenta do plantão):
entrada quando o progresso cruza 10–30 % com inclinação positiva de 3 fotografias, holders ≥ 20 e subindo, top-10 ≤
30 % (lido ≥ 3 min após a criação, por M-D5), snipers ≤ 2; alvo 5×, trailing 40 % após 2×, 60 min, segurar através da
migração (T4.11). Hipótese: é aqui que mora a cauda de Kamat.

### E4 — "Continuação pós-migração" (EXP-M8)
Comprar **depois** da graduação, na pool, quando o DEX Screener já lista (+70 s a +8 min), com holders ≥ 100 e subindo,
compras > 2 × vendas por 3 minutos, dev ≤ 5 %, top-10 ≤ 25 %; alvo 5×, trailing 40 %, `dead` e `creator_dump`.
Contra: 105 de 150 graduadas do run 1 estavam abaixo de 10 % do topo horas depois — a régua tem de ser dura e a amostra
grande. Depende de T4.11 (marca pela pool) e T4.2g (fita por lote).

### E5 — "Moonshot" (EXP-M4, T4.11, já pré-registrado)
Alvo 10×/25×, trailing 50 % só após 3×, 2 h, segurar através da migração, 0,02 SOL. Sem E1/E2 na frente ele compra o
mesmo lixo; **E2 vira pré-condição de E5**.

## 4. Ordem de teste (o que roda primeiro e por quê)
1. **E2** (exclusões) sobre os conjuntos vivos — custo zero, feature já existe, mede-se amanhã.
2. **E1** com o relógio de 15 s (T4.16) — ataca os dois defeitos medidos (entrada e latência).
3. **E5** só atrás de E2; **E3/E4** depois de T4.2g (fita por lote) e T4.11 (pool) estarem no ar.
Régua para todas: ≥ 100 apostas e 30 dias, IC 95 % por blocos de dia, leave-top-out, retenção sem seleção por sucesso;
o fechamento diário (T4.15) escreve o placar de cada uma sozinho.

## 5. O que NÃO fazer
- Subir tamanho ou ligar dinheiro real em regra que perde 20 de 21 em papel.
- Ajustar limiar olhando estas 21 e chamar de "aprendizado": é curva ajustada ao ruído de um dia (KB-0092).
- Ler `dh`/`t10` do board no primeiro minuto como verdade (M-D5).

## Ligações
[[02-MARKET/Meme/2026-09-12]] · [[05-EXPERIMENTS/EXP-M1-comprar-cedo-na-curva]] · [[05-EXPERIMENTS/EXP-M2-a-linha-manda]] · [[05-EXPERIMENTS/EXP-M3-sonda-de-hype]] · [[05-EXPERIMENTS/EXP-M4-moonshot]] · [[00-INBOX/Hipoteses-do-plantao]] · [[03-TRADING/Meme/Terminal-do-pumpfun]] · [[11-KNOWLEDGE/README-meme]]
