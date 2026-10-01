---
tags: [knowledge, cripto, fibonacci, linha-de-tendencia, lta, diario, segunda-frente, hipotese, pesquisa, sobrevivencia]
tema: "no diário do top-20 da Binance à vista (2019–2026, com deslistados), comprar a primeira retração de 50–61,8 % não bate as moedas do mesmo dia sem recuo de forma confirmável e a faixa de Fibonacci não se mostra especial (H-025 não confirma); comprar o toque numa LTA confirmada rende MENOS que as moedas do mesmo dia longe da linha (H-026 A refuta, IC inteiro abaixo de zero); comprar o rompimento do topo depois do teste tem estimativa +1,09 p.p. por 10 d mas o IC cruza zero (H-026 B não confirma)"
fonte: R85 (`.claude/state/notes-R85.md`) — H-025 e H-026 da Fila de Hipóteses
fonte_url: https://data.binance.vision · https://api.binance.com/api/v3/exchangeInfo · https://www.infomoney.com.br/guias/o-que-e-uma-linha-de-tendencia-na-analise-grafica/
lido_em: 2026-09-28
evidencia: "medição própria — painel diário do R84 (843 542 velas finais de 750 pares USDT à vista, com deslistados, sobrevivência auditada contra 153 cópias históricas de cadastro), 2 762 dias de sinal (2019-02-24 → 2026-09-16), universo ponto-no-tempo dos 20 de maior volume; contraste contra controles do mesmo dia; bootstrap de blocos móveis de 28 d (120 d na estrutural), 10 000 réplicas; 26 testes, fumaça sintética com nulo e controle positivo, antecipação conferida no dado real (25 dias reconstruídos só com velas anteriores: 0 divergências)"
hipotese_testavel: sim
astra: "desenho: 6 must-fix aceitos numa emenda datada antes de qualquer evento; resultado: concorda com os quatro vereditos, 4 must-fix de código aceitos e corrigidos (a expiração da LTA mudou os números da H-026 sem mudar rótulo; os outros três sem impacto neste painel) e números reproduzidos por ela"
status: vivo
owner: sexta-feira
updated: 2026-09-28
confiança: "?"
tipo: pesquisa
hipotese: H-025, H-026
variavel: "H-025 fib_50_618 (1.º fechamento na retração 50–61,8 % da última perna de alta confirmada, pivô k = 5); H-026 LTA por dois fundos ascendentes confirmados, 3.º toque confirma — A retorno na linha, B rompimento do topo anterior em até 20 d"
populacao: "2 762 dias de sinal 2019-02-24 → 2026-09-16, top-20 USDT à vista da Binance ponto-no-tempo com deslistados; eventos com controle no mesmo dia: 360 (Fibonacci), 1 529 (A), 323 (B)"
efeito: "H-025 D +0,691 p.p. por 10 d (nao_confirma); H-026 A D -1,085 (refuta o tamanho, IC inteiro < 0); H-026 B D +1,089 (nao_confirma)"
ic: "H-025 [-1,429, +2,946]; A [-2,079, -0,021]; B [-0,755, +2,891]"
veredito: nao_confirma
proximo_passo: "nenhuma regra à mesa; não recalibrar k, faixa, tolerância, H ou MRE depois de ver; o B (rompimento do topo depois do teste da LTA) só volta em coorte prospectiva pré-registrada e com teste incremental contra um rompimento de topo sem LTA; o A não volta como compra"
classe_de_perda: —
mercado: cripto
---

# KB-0169 — Fibonacci e LTA diária no dado: o recuo não é especial e o toque na linha perde

> **H-025 `NÃO CONFIRMA` · H-026 A `REFUTA` · H-026 B `NÃO CONFIRMA`.** No diário do top-20 da Binance à vista
> (2019–2026, com deslistados, 0,15 % por perna, compra na abertura seguinte ao sinal), contra as moedas do **mesmo
> universo, no mesmo dia, na mesma estrutura sem o gatilho**:
>
> - comprar a **primeira retração de 50–61,8 %** rendeu **+0,69 p.p.** por operação de 10 d, IC 95 % **[−1,43; +2,95]**;
>   as faixas vizinhas 45 % e 55 % deram **negativo** (pico, não patamar) e a faixa de Fibonacci não bateu as vizinhas
>   de forma confirmável;
> - comprar o **toque numa LTA confirmada** (3.º toque ou depois) rendeu **−1,09 p.p.**, IC **[−2,08; −0,02]** — o
>   tamanho previsto (+1 p.p.) fica excluído e o intervalo inteiro está abaixo de zero;
> - comprar o **rompimento do topo** depois do teste da LTA rendeu **+1,09 p.p.**, IC **[−0,76; +2,89]**, Holm 0,22 —
>   patamar e corte de período passam, a precisão não.
>
> Pré-registro e emenda em [[Fila de Hipoteses]] § H-025/H-026 · literatura e o artigo em
> [[KB-0168-fibonacci-elliott-e-lta-diaria]] · estudo em `.claude/state/notes-R85.md` · código e saídas em
> `.claude/state/r85/` (resultado final `h025_h026.txt`, sha256 `f04f7bde…`; a primeira corrida, antes das correções da
> Astra, fica em `h025_h026_v1_antes_da_revisao.txt`).

## O que afirma

1. **O recuo até a "zona de ouro" não é um lugar especial para comprar**, pelo menos não de um jeito que 360 eventos
   em 7,5 anos consigam distinguir de zero. A faixa 50–61,8 % foi melhor que a média das quatro vizinhas por
   +1,28 p.p., IC [−0,11; +2,63] — não é especial pela regra escrita antes — e as duas vizinhas que se sobrepõem a ela
   (45 % e 55 %) deram negativo. Isso bate com a tese do Ramyar: as viradas não se agrupam nos números de Fibonacci.
2. **O alvo 1,618 com stop abaixo do fundo não muda nada em média:** nas mesmas 443 entradas, a saída estrutural rendeu
   **+0,009 p.p.** a mais que segurar 10 dias (mediana de 31 dias segurando). Contra os controles segurados o mesmo
   tempo: +0,18 p.p., IC [−3,17; +3,59].
3. **O "retorno na LTA" do artigo, no diário, é o braço que perde** — em todas as leituras: nas três tolerâncias
   (−0,95/−1,09/−0,95 p.p.), antes e depois de 2022 (−0,90/−1,21), com 5 e 20 dias (−1,25/−0,61), com blocos de 1, 14
   e 56 dias e com cluster por moeda (todos os IC abaixo de zero), e sem nenhuma moeda dominando (a maior, BNB, tem
   5,9 % dos eventos; tirar qualquer moeda deixa D entre −1,30 e −0,99). Repete, no diário e à vista, o que a
   [[EXP-0016-trendline-breakout]] viu no 15 min: o repique no suporte ascendente não paga.
4. **O rompimento do topo depois do teste (B) é a única leitura que aponta para cima**, e não confirma: IC cruza zero,
   Holm 0,22. É **pista descritiva**, não resultado.

## Onde foi mostrado

| braço | D por 10 d (otimista = pessimista) | IC 95 % (blocos 28 d) | p / Holm | nível do evento | n (cobertura) | veredito |
|---|---|---|---|---|---|---|
| **H-025** 50–61,8 % | **+0,691** p.p. | [−1,429; +2,946] | 0,274 / 0,547 | +2,73 % | 360 (85) | **NÃO CONFIRMA** |
| H-025 saída estrutural (blocos 120 d) | +0,176 | [−3,173; +3,591] | 0,408 / 0,547 | +2,05 % | 355 (23) | **NÃO CONFIRMA** |
| **H-026 A** retorno na LTA | **−1,085** | [−2,079; −0,021] | 0,983 / 0,983 | −0,51 % | 1 529 (96) | **REFUTA** |
| **H-026 B** rompimento do topo | **+1,089** | [−0,755; +2,891] | 0,112 / 0,223 | +4,37 % | 323 (77) | **NÃO CONFIRMA** |

p.p. por operação; D = retorno líquido do evento − média dos controles do mesmo dia; "nível" = retorno líquido médio
do evento (a média dos controles é nível − D: +2,04 % na H-025, +0,58 % em A, +3,28 % em B). Otimista e pessimista
iguais em 3 casas: só uma operação terminou em fim de série (LUNA, sinal de 06/05/2022, em A: −99,99994 % × −100 %).

**Cláusula a cláusula.**

- **H-025 primária:** D ≥ +1,0 não (+0,69); IC inferior > 0 não; Holm < 0,05 não; nível > 0 sim; **patamar não**
  (0,45: −0,22; 0,55: −0,68); corte sim (+0,70 antes de 2022, n 151; +0,69 depois, n 209). IC superior +2,95 ≥ +1,0 →
  não refuta. Faixas: 0,40 +1,06 (n 248) · 0,45 −0,22 (331) · **0,50 +0,69 (360)** · 0,55 −0,68 (343) · 0,70 −2,51 (259).
- **H-025 estrutural:** D +0,18; IC cruza zero; Holm 0,55; cobertura 23 ≥ 15; blocos de 60 e 180 d também cruzam zero.
- **H-026 A:** IC superior −0,021 < +1,0 → **REFUTA o tamanho previsto**. O intervalo inteiro abaixo de zero é leitura
  **descritiva** de efeito oposto neste contraste; o Holm publicado testa superioridade, não descobre o inverso.
- **H-026 B:** D ≥ +1,0 sim (+1,09); IC inferior > 0 **não**; Holm **não** (0,22); nível sim; patamar sim (0,15: +0,50,
  n 238; 0,35: +0,29, n 407); corte sim (+1,54 antes, n 140; +0,74 depois, n 183); K6 não (ETH 7,1 %). Falha só na
  precisão — e o patamar é o 0,25 no pico de vizinhos pequenos.

**Sensibilidade (não decide):** H-025 com H = 5 d −0,28 e H = 20 d +1,05; blocos de 1/14/56 d e cluster por moeda,
todos cruzando zero. B com H = 5 d +0,43 e **H = 20 d +3,72** — **não** autoriza trocar o horizonte depois de ver;
blocos de 1/14/56 d e cluster por moeda cruzam zero.

**Contagem antes de qualquer retorno** (`r85/counts.txt`, 13:21Z): 448 eventos brutos na faixa principal, 1 632 A,
336 B; 88, 102 e 13 ficaram sem controle no dia e saíram contados. Venda: 23 381 saídas na abertura de e + 10, 3 com
atraso de 1–2 dias (primeira abertura real).

## Como mediríamos aqui

- **Sem antecipação:** pivô conhecido 5 velas depois; a perna e a linha só existem a partir da confirmação; o
  resultado na vela t não muda quando velas futuras ou a vela em formação mudam (testes em 3 sementes × Fibonacci e 3
  tolerâncias); **uma estratégia trapaceira que usa o pivô na própria barra é pega pela guarda**; no dado real, 25 dias
  sorteados reconstruídos só com velas de abertura ≤ d deram o mesmo universo, as mesmas bandeiras e os mesmos
  controles (0 divergências).
- **Sobrevivência:** o painel do R84 ([[KB-0166-evitar-as-moedas-em-queda-nao-bate-a-cesta]]), com as 5 continuidades
  de ticker levando máxima e mínima; fim de série nos dois limites.
- **Fumaça sintética** (`r85/smoke_synth.txt`, rotulada SINTÉTICA): nulo sem nenhum CONFIRMA; com +3 p.p. somados ao
  evento, primária, A e B confirmam. Num nulo o A deu +0,87 p.p. (p 0,03, Holm 0,06); seis sementes a mais deram de
  −0,68 a +0,40 — acaso, não viés do encanamento.

## Por que pode falhar (e o que não concluir)

- **O controle mede "esta regra contra este controle", não a geometria** (emenda da Astra). O controle de A são moedas
  com LTA confirmada **longe** da linha — as que continuaram fortes. A perder para elas pode ser **momentum
  transversal** (quem recua rende menos que quem não recua), não "a LTA faz mal". **Não concluir:** que a LTA causa
  perda, que vender o toque a descoberto pagaria, ou que B acrescenta algo a um rompimento de topo qualquer.
- **Poder:** com ~360 eventos dependentes, o meio-IC da H-025 ficou em ~±2,2 p.p. (o a priori era ±1,5); só um efeito
  de ~3 p.p. teria boa chance de aparecer. `NÃO CONFIRMA` é ignorância, não prova de ausência.
- **Transferência:** preço da Binance à vista, 20 maiores por volume; nada disso é a Jupiter em ficha de 0,05 SOL
  ([[KB-0145-binance-como-sinal-solana-como-execucao]]).
- **Uma regra de traçado, entre muitas:** k = 5, amplitude ≥ 3 ATR, tolerância 0,25 ATR, 1 ATR de afastamento, 180 velas
  de vida — escolhas congeladas antes, não medidas ([[KB-0077-linhas-de-tendencia]] §7 lista o que um humano faria
  diferente).

## Porta para papel (parte D do pedido)

**Nada sobreviveu, então não há braço de papel a descrever.** Registro o que faltaria para o B chegar a ser
candidato, sem abrir nada: (1) coorte **prospectiva** a partir de 28/09/2026, pré-registrada com H = 10 d (não 20);
(2) contraste incremental contra **rompimento do topo sem teste de LTA** no mesmo dia, para separar a linha do momentum;
(3) antes de qualquer ideia de `spot/1`: medir a taxa fixa real por perna — a premissa de papel da
[[KB-0145-binance-como-sinal-solana-como-execucao]] é 0,001 SOL por perna, o que em ficha de 0,05 SOL daria 2 % por
perna, maior que o próprio D pontual do B; a ida e volta variável medida em 0,05 SOL é 0,14 % na mediana
([[KB-0149-o-que-a-mesa-real-ensinou]] item 23). Sem as três, o B fica no [[Mapa de Estrategias]] como pista.

## Segunda opinião (Astra)

**Desenho** ([[06-DECISIONS/Revisoes-Astra/H-025-H-026-prereg|H-025-H-026-prereg]]): seis must-fix aceitos numa emenda
datada antes de qualquer evento. **Resultado e código** ([[06-DECISIONS/Revisoes-Astra/H-025-H-026-resultado|H-025-H-026-resultado]]):
concorda com os quatro vereditos pela letra; achou **quatro defeitos de código**, todos com teste que falhou antes e
passa depois: a LTA vivia até b + 181 (em vez de morrer em b + 180) — corrigido, mudou A de −1,079 para **−1,085** e B de
+1,060 para **+1,089** sem mudar rótulo, exatamente os números que ela recalculou em memória; a abertura além do alvo
tem de vencer a mínima da mesma vela; K6 tem de bloquear também o REFUTA; a estrutural não pode depender de a saída fixa
existir (os três últimos sem impacto neste painel). Aceitas também as leituras: "efeito oposto" em A é descritivo; B é
pista descritiva, não um quarto veredito, e não autoriza trocar H depois de ver.

## Relacionados

[[KB-0168-fibonacci-elliott-e-lta-diaria]] · [[Fila de Hipoteses]] · [[Mapa de Estrategias]] · [[Proximas Hipoteses]] ·
[[EXP-0016-trendline-breakout]] · [[KB-0077-linhas-de-tendencia]] · [[KB-0166-evitar-as-moedas-em-queda-nao-bate-a-cesta]] ·
[[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]] · [[KB-0149-o-que-a-mesa-real-ensinou]] ·
[[KB-0145-binance-como-sinal-solana-como-execucao]]

**Atualização (01/10/2026):** a taxa fixa real por perna da `spot/1` foi medida — média 0,00005 SOL (0,10 % da ficha de 0,05 SOL), não 0,001 SOL (2 %); o custo total medido é ~0,25 %/perna (0,49 % ida-e-volta, IC [0,32; 0,67]), acima dos 0,15 %/perna usados aqui. Com isso o pré-requisito (3) da parte D está cumprido. Como D = evento líquido − controles líquidos do mesmo dia (os dois pagam o mesmo custo), o custo maior **não muda D** (+1,09 p.p.) nem o rótulo NÃO CONFIRMA; muda o **nível** do B, de +4,37 % para ~+4,18 % (−0,19 p.p. de custo extra por ida-e-volta na ficha de 0,05 SOL). Ver [[KB-0171-custo-real-da-spot-1]].
