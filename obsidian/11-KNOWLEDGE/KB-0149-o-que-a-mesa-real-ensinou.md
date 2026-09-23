---
tags: [knowledge, meme, mesa-real, consolidado, custo, entrada, saida, infra, metodo, m4]
tema: tudo o que sete dias de dinheiro real na mesa de memes ensinaram — o que está provado, o que foi refutado e o que ainda não sabemos
fonte: R58, R60, R61, R62, R63, R64, R65, R66, R67 + diários 16–23/09/2026 + 88 posições reais
fonte_url:
lido_em: 2026-09-23
evidencia: medição própria — 88 posições reais (16–23/09/2026), ~1 500 apostas de papel, 178 mil negócios pós-graduação, fita e fotos reconstruídas trade a trade
hipotese_testavel: sim
astra: concorda
status: vivo
owner: sexta-feira
updated: 2026-09-23
confiança: "replicado"
---

# KB-0149 — O que a mesa real ensinou (16–23/09/2026)

> Consolidado para construir em cima. Cada linha tem número e origem; o que não tem, está marcado como **não sabemos**.
> Regra de leitura: só entra aqui o que foi medido com dinheiro real ou com população independente. Opinião não entra.

## 0. O placar honesto

88 posições reais, **−0,347 SOL** acumulado, 0 de 6 dias verdes até 22/09; 23/09 abriu positivo (`RIGBY` +0,0112). Carteira: 0,92 → 0,56 SOL. Acerto global **26 %** (23/87 no corte do R65).

## 1. O custo é o inimigo, não o mercado

1. **72 % do prejuízo é custo.** O preço tirou −0,0952 SOL; taxas e aluguel tiraram −0,2492 (R65).
2. **Composição por operação: 4,09 % do tamanho** — pump.fun 1,59 % + criador 0,50 % + rede 0,13 % + **aluguel de ATA 1,86 %**. Sem o aluguel: **2,23 %** (R65).
3. **O aluguel é 33 % de todo o prejuízo** (−0,1135 SOL): 75 contas abertas, **0 das 87 vendas** pediu reembolso porque a flag nasceu desligada por cautela em 16/09 (T4.46) e ninguém a ligou por 7 dias. **Cautela também tem preço.**
4. **Ponto de equilíbrio com alvo +15 %: 27 % de acerto com aluguel, 19 % sem.** A mesa faz 26 % — ou seja, **o vazamento é a diferença entre perder e empatar** (R65).
5. **Sair da pump.fun não resolve o custo.** Pós-graduação (PumpSwap) cobra **1,20 %/perna** na mediana — a faixa de 0,30 % só começa em 98 240 SOL de market cap e um recém-graduado tem 708 SOL (só 5,8 % chegam lá). Ida e volta **2,40 %**, pior que a curva (R66/[[KB-0148-a-graduacao-nao-e-a-saida-barata|KB-0148]]).

## 2. A saída já está certa — o problema é a entrada

6. **A regra atual (alvo 1,15× · recuo 10 % armado na entrada · 5 min) foi a 1.ª de 52 variantes** testadas nas 24 operações de 19/09 (R64/[[KB-0146-trailing-apertado-e-rent-de-ata|KB-0146]]).
7. **Recuo mais largo perde**: 15 % −0,176 · 20 % −0,188 · 30 % −0,148; armar só depois de +10 %/+20 % também perde. Motivo: **5 posições drenaram ≥ 70 % num único bloco** — nenhum stop largo pousa antes disso.
8. **"Segurar 5 minutos" daria −0,40 SOL** nas mesmas 24: 12 moedas ≤ −40 %, 8 ≤ −70 % (R64).
9. **A venda grande é o gatilho, não o aviso**: a saída por evento dispara 0,9–1,5 s depois do bloco da venda grande; "vender na primeira venda grande" não melhora nem nas 8 reais nem em 82 de papel (R62/[[KB-0143-o-que-antecede-o-dump|KB-0143]]).
10. **Mas o dinheiro ficou lá**: XCrypto, NARKY#1 e FЕРЕ foram a +139 %, +139 % e +55 % **depois** de o recuo nos tirar a −2…−14 %. Tensão não resolvida: o recuo apertado protege das drenagens e custa as explosões. **Não sabemos** separar as duas antes do fato.

## 3. Nada do que medimos na entrada separa vencedora de perdedora

11. **13 variáveis de decisão testadas** (snipers, dev share, compradores únicos, progresso, fluxo do criador, idade, volume 1 m, sells/buys, holders, top10, retenção, carteiras novas, flip rápido) com bucket + bootstrap por cluster de mint + permutação + Benjamini-Hochberg: **nenhuma sobrevive**. p mais baixo 0,046 contra limiar 0,0077. Snipers p = 0,52; dev share p = 0,67 (R65/[[KB-0147-custo-e-o-prejuizo-e-buys-1m-e-a-unica-pista|KB-0147]]).
12. **`buys_1m` parecia a exceção e não é**: ≤ 25 compras/min dava 34 % de alvos e MFE +28,1 % contra 20 % e +8,2 % nas 87 — mas em **473 moedas independentes** o efeito é D = +0,036 por SOL, IC 95 % **[−0,058, +0,136]**, p = **0,43**; a mediana inverte o sinal e a curva de limiares é **pico, não patamar** (R67). *Não confirmado ≠ refutado*: faltariam ~1 300 mints sob a saída real para decidir.
13. **Rajada de compradores é negativa** em 54 células (R58/[[KB-0138-rajada-de-compradores|KB-0138]]).
14. **Sniper de lançamento: descartado** — 18/18 células negativas, e não era latência (R60/[[KB-0141-sniper-de-lancamento|KB-0141]]).
15. **KOL/call confirma, não antecipa**: o bum começa 16 s *depois* do sinal; R −0,07, acerto 15 % (R61/[[KB-0142-kol-e-call-antecipam-ou-confirmam|KB-0142]]).
16. **Seguir carteira vencedora não é gatilho** (R57/KB-0136).
17. **O segundo de entrada decide a aposta**: 8 moedas compradas duas vezes com 19–190 s de diferença tiveram **uma saída por alvo e outra por recuo** (R65). A entrada move a distribuição inteira.
18. **Recompra do mesmo mint depois de uma perda**: 19 recompras em papel, **0 acertos, −0,338 SOL** (R64). Aplicada na mesa real em 20/09 como pausa de 300 s (T4.78), com o contraexemplo registrado (NARKY#2 +0,0142 teria sido bloqueado).
19. **Horário**: manhã 02–11 h com 45 % de acerto (+0,003) contra tarde 14–20 h com 31 % (−0,044) — mas é **um dia**; não restringir (R64 + Astra).

## 4. A infra é estratégia

20. **RPC gratuito mata a mesa em silêncio**: com o Helius no limite, a pista rápida parou e a mesa ficou **2 dias e 1 hora sem operar** sem nenhum alarme (21/09 12:08 → 23/09 10:47). Plano pago: 0 erros/hora, 815 moedas avaliadas por tique (eram 385), 310 rastreadas (eram 126).
21. **O `.env` não chega ao robô sem recriar o contêiner.** Quatro tentativas de 19 a 23/09 falharam por isso; `compose.sh update` recria porque o commit muda, mas mudança só de `.env` exige `up --force-recreate`.
22. **A Binance lidera a Solana por menos de 15 s** e a Jupiter cota +9 bp acima do mid: em cripto normal a vantagem tem de vir do sinal, não da velocidade (R63/[[KB-0145-binance-como-sinal-solana-como-execucao|KB-0145]]).
23. **Custo por praça, medido:** pump.fun 4,09 % (2,23 % sem aluguel) · pós-graduação 2,40 % · Solana à vista pela Jupiter **0,14 %** · Binance 0,02–0,10 %. Praça barata tem movimento pequeno — a vantagem não é de graça.

## 5. Método: o que nos salvou de perder mais

24. **Antecipação (look-ahead) mente com convicção.** A 1.ª volta do R66 dizia "9 de 11 variáveis sobrevivem, p = 0,0001" — vendia na última leitura da série. Com censura, o sinal **sumiu inteiro** e o prejuízo caiu à metade.
25. **Escolher limiar olhando o resultado vale zero.** O corte 25 do R65 morreu fora da amostra; o "melhor" limiar mudava com a janela de ajuste.
26. **Patamar × pico**: efeito real sobrevive a limiares vizinhos; artefato é um pico isolado. Virou teste padrão.
27. **A revisão adversária pagou-se** em achados que teriam custado dinheiro: verificador de swap aceitando transferência estranha (T4.54b), invariante de simulação que não lia a simulação (T4.73), tesouraria contando 10,4 M de "SOL" de entrada e desarmando o teto diário (T4.73c), refutação que se desfazia com um ganho (T4.74-5), `--i-know` sem teto absoluto (T4.73b).
28. **Ligar critério novo na mesa real não é "sombra"**: a proposta não nasce e não há contrafactual. Sombra é braço `research_only` ou portão em modo sombra (T4.80/Astra).

## 6. O que fazer com isto (ordem de valor esperado)

1. **Fechar a ATA em toda venda** — única mudança com evidência forte e efeito imediato: −1,86 pp por operação e +0,1135 SOL parados de volta.
2. **Medir coisa nova, não girar botão velho**: as 13 variáveis estão esgotadas. Em curso: **EXP-M22 absorção de venda** (venda ≥ 5 % → preço recupera em 30 s → segura 10 s), **EXP-M19 retenção dos primeiros compradores**, **EXP-M21 pausa por mint**.
3. **Segunda praça em paralelo, não em substituição**: `spot/1` (Jupiter, 0,14 %) ligada em 23/09 com 1 posição e refutação automática em 20 operações.
4. **Não mexer**: saída, tamanho da ficha, `creator_dump`, filtros de sniper e dev share, horário. Todos sem evidência a favor de mudança.

## 7. O que continuamos sem saber

- Como separar, **antes** da compra, a moeda que drena 70 % num bloco da que faz +139 %.
- Se a `operator/6` (entrada do Lab) é pior que a `operator/5` ou é ruído: 22 contra 50 operações, diferença dentro do erro.
- Se existe vantagem em qualquer horizonte maior que 5 minutos (nunca medimos; a mesa nasceu com 300 s).
- Se o sinal do Lab (`mean_reversion v14`) tem vantagem fora da amostra: 23 sinais, agora em teste com dinheiro real na `spot/1`.

## Relacionado

[[KB-0143-o-que-antecede-o-dump]] · [[KB-0146-trailing-apertado-e-rent-de-ata]] · [[KB-0147-custo-e-o-prejuizo-e-buys-1m-e-a-unica-pista]] · [[KB-0148-a-graduacao-nao-e-a-saida-barata]] · [[KB-0145-binance-como-sinal-solana-como-execucao]] · [[2026-09-12-teste-pequeno-meme-real]] · [[Mesa-operator-6]] · [[Registro de Tentativas]]
