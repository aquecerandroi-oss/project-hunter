---
tags: [knowledge, meme, mesa-real, concentracao, criador, fita, antecipacao, cobertura, hipotese, m4]
tema: a concentração do maior comprador não pode ser medida com o arquivo de trocas que temos — ele chega ~44 s atrasado por polling, a fita que decide (WS) não é persistida, e o teto que parecia óbvio mataria o SENTHOS e deixaria passar o AIRAA
fonte: R73 (`.claude/state/notes-R73.md`) — H-010 da Fila de Hipóteses, origem na perda real do AIRAA (23/09/2026)
fonte_url:
lido_em: 2026-09-23
evidencia: medição própria — 91 posições reais + 1 475 apostas de papel (694 mints), fita `meme_trades` de 144 859 trocas; guarda de chegada da T4.80 testada (15 testes); moinho `run_hypothesis`
hipotese_testavel: sim (com medida nova)
astra: concorda (duas rondas; 3 + 6 achados corrigidos)
status: vivo
owner: sexta-feira
updated: 2026-09-23
---

# KB-0153 — O maior comprador não estava no arquivo

## Em uma frase

A tese "não comprar onde um único dono concentra a curva" **não pôde ser testada**. O arquivo de trocas
(`meme_trades`) vem de *polling* do `swap_api` com ~44 s de atraso mediano, e cobre a vida inteira da moeda em
menos de 60 % das decisões. **Onde se consegue medir, o teto de concentração mata ganhos tão facilmente quanto
evita perdas.**

## O que se mediu (R73)

- **Cobertura desde o nascimento** (a fita começa ≤ 5 s do `created_at` **e** reconstrói a foto da curva a ±2 %):
  **53,8 %** das posições reais e **47,7 %** dos mints. Isso fica abaixo da barra de 60 % que a própria hipótese
  pré-registou, e é **limite de dado**.
- **Com a guarda de chegada** (só conta a troca que já estava no arquivo na hora da decisão): **1 de 91**. Em 60
  das 91 posições reais o arquivo **não tinha nenhuma troca** do mint quando decidimos.
- **`AIRAA`**: as 87 trocas anteriores à decisão, incluindo os 8,89 SOL do criador, entraram no arquivo **num só
  poll, 6 s depois da nossa compra**. A mesa decidiu por outro caminho, a fita WS em memória do
  `meme_event_gate_v1`, que via trocas (`buys_1m=31`). Se via a compra do criador, **não sabemos**: essa fita não
  é gravada troca a troca.
- **`SENTHOS` (+19,6 %)**: o criador tinha **68 %** da curva na hora da decisão. Qualquer teto de 20–50 % o
  bloqueava.
- **Contrafactual nas 91 reais:**
  - com a variável que existia, o teto de 20 % bloqueia 11 posições, **mata 2 vencedoras** e **não pega o
    `AIRAA`**;
  - com a fita perfeita de hoje, bloqueia 24, **10 delas vencedoras**, e ganha +0,006 SOL;
  - a 30 % o resultado **piora**.
- **Cauda (perda ≥ 50 %) por tercil**, sempre na fita retrospetiva:
  - SOL líquido: 11,8 / 11,2 / 14,9 %;
  - SOL bruto: 12,3 / 12,8 / 12,8 %;
  - estoque de tokens: 10,9 / 9,8 / 17,8 %, com BH 0,128.
  
  Nenhuma sobrevive à correção.
- **Moinho** (tercil baixo × alto): D = +0,0139 SOL/SOL, IC [−0,073, +0,099], p = 0,80, curva em pico →
  **NÃO CONFIRMA**. Não é refutação.

## Por que importa

1. **`meme_trades` não é "o que a mesa sabia".** É uma cópia atrasada. Qualquer estudo que reconstrua features de
   fita a partir dele e aplique a guarda de chegada fica quase sem população. Sem a guarda, mede uma fita que a
   mesa não tinha. Isso vale para R62–R72.
2. **Dono concentrado é o criador subindo a própria moeda tanto quanto despejando.** O `SENTHOS` e o `AIRAA` têm o
   criador como maior comprador, e só um deles afundou.
3. **Ligar `max_top10_share` na mesa não é a lição.** Ele lê fotos de holders, que é outra medida, e o contrafactual
   da medida próxima é desfavorável.

## Para reabrir (medida nova)

- Persistir por troca a fita WS usada na decisão, ou gravar em `reasons` o maior comprador e o seu **estoque de
  tokens** no instante da decisão.
- Depois, pré-registar a variável de **estoque** (capacidade de despejo), e não fluxo de SOL. É a única que
  apontou na direção da tese pela cauda.

Ver: [[Fila de Hipoteses]] (H-010) · [[KB-0149-o-que-a-mesa-real-ensinou]] · [[KB-0143-o-que-antecede-o-dump]]
