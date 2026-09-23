---
tags: [knowledge, meme, mesa-real, rede, financiador, despejo, criador, hipotese, m4]
tema: o despejo de dezenas de carteiras num só slot (SIMFTR, CITIZEN, WAVECOREE, RHOS) não vem de uma rede com o mesmo financiador; a medida "primeiro financiador comum" não sustentou a H-014 e não vale a pena construí-la
fonte: R76 (`.claude/state/notes-R76.md`) — H-014 da Fila de Hipóteses, origem na perda real do SIMFTR (23/09/2026)
fonte_url:
lido_em: 2026-09-23
evidencia: medição própria — 591 mints (84 reais + 507 de papel `fluxo_e_holders`), 291 com fita desde o nascimento; financiador de 10 274 carteiras resolvido na Helius (98,1 %), validado contra o `funded-by` (50 de 51); moinho `run_hypothesis`
hipotese_testavel: sim
astra: concorda (duas rondas; 5 + 3 achados corrigidos)
status: vivo
owner: sexta-feira
updated: 2026-09-23
confiança: "?"
---

# KB-0156 — O despejo em bloco não é uma rede de financiamento

## O que afirma

A tese da H-014 era que as dezenas de carteiras que despejam uma moeda no mesmo slot formam uma rede montada por uma única
carteira financiadora, que ainda fabrica a "demanda" que a porta lê. **A tese não se sustentou.**

- Nos quatro casos de origem, a fração de compradoras com o mesmo financiador é de **0 a 1,4 %**: SIMFTR 0, CITIZEN 0,6 %,
  WAVECOREE 0, RHOS 1,4 %.
- As vendedoras dos grandes despejos (73, 76, 154, 224, 262 num slot) têm **financiadores distintos**.
- Na população, o tercil com mais "rede" tem **menos** despejos coordenados que o tercil sem rede (0,67×).

## Onde foi mostrado

- **Mesa de memes, 12 a 23/09/2026.**
  - 95 posições reais: 84 mints, 29 vencedoras, PnL de −0,387 SOL.
  - 1 223 apostas de papel da porta `fluxo_e_holders`: 507 mints.
- **População principal:** as 291 moedas com fita desde o nascimento (critério do R73). A cobertura de financiadores é de
  **98 %** das compradoras pré-decisão.
- **Desfecho:** a regra atual (1,15× / recuo 10 % / 300 s), com custo de 2,23 % e pouso 1,6 s depois do gatilho.
- **Financiador:** o remetente da primeira transferência de SOL que a carteira recebeu, lido da instrução do System Program.
  Casas de câmbio (identidade Helius, ou mais de 1 000 destinatários) não contam como rede.

## O que se mediu

| peça | resultado |
|---|---|
| retorno, tercil baixo − alto (previsão: ≥ +0,05 com IC > 0) | **+0,054** por SOL, IC [−0,005, +0,116], p 0,083, Holm 0,166. O braço baixo **perde em nível** (−0,043) |
| despejo coordenado, alto ÷ baixo (previsão: ≥ 2×) | **0,67×** (8,8 % contra 13,2 %) |
| patamar | três partições (os empates colapsam a grelha); D de +0,041 / +0,050 / +0,031, nenhum com IC acima de zero |
| financiadores "desconhecidos" tratados como serviço (s1) | o sinal **inverte**: −0,024 |
| teto nas 95 reais | nenhum bloqueia mais de **1 das 6 piores** (o AIRAA); com rede > 10 %, mata ANT, WEENY e RESERVED |
| teto "financiado pelo criador" | bloqueia 2 das 6 piores e **mata 31 % a 48 % das vencedoras**, incluindo SENTHOS e MMKT |

**Veredito: `NÃO CONFIRMA`.** A cláusula (a) literal dispara, mas pela errata escrita antes do contraste isso só não-confirma. A
cobertura passa: 98 %.

## Por que importa

1. **O despejo em bloco é real e frequente, mas não é "a rede do criador".**
   - Das 272 decisões com desfecho, 36 tiveram 10 ou mais vendedoras num só slot, nos primeiros 300 s.
   - O criador vende no mesmo slot em cerca de 1/3 dos casos.
   - Uma **vencedora** (KODA) teve 224 vendedoras num slot.
   - A leitura mais simples, e **não medida**: muitas carteiras independentes (utilizadores de bots e apps) reagem no mesmo
     bloco. Como o **R62** e o **KB-0143** já tinham mostrado, a venda grande é o gatilho, não o aviso.
2. **O "primeiro financiador" não vê rede sibila financiada por casa de câmbio.**
   - No YOU (uma das 6 piores), 20 das 34 compradoras foram financiadas direto pela mesma carteira quente da OKX.
   - A medida exclui isso por construção, e com razão: essa carteira quente também financia milhões de utilizadores legítimos.
3. **O que a medida apanha é frota ou app, não anel.**
   - O tercil alto é dominado por um financiador sem rótulo que aparece em 29 moedas diferentes.
   - Outras 11 moedas vêm do **FOMO Co-signer**, a carteira de autoridade de um app de trading.
   - Bloquear "rede > 10 %" é bloquear utilizadores do mesmo app.

## Como mediríamos aqui

- **Nada a construir para esta medida.** A Helius paga resolve o financiador por cerca de 10 créditos por carteira (o R76 gastou
  cerca de 132 mil créditos, sem nenhum 429), mas o sinal não justifica uma dependência de RPC no caminho da decisão.
- **Proxy barato ao vivo:** nenhum proxy tirado da fita WS concorda com a medida de financiador (|Spearman| ≤ 0,13).
- **Pista exploratória, fora do veredito:** o **SOL comprado no slot de criação**.
  - Previu o despejo com AUC 0,675 [0,58, 0,76] e as perdas ≥ 50 % com AUC 0,74 [0,56, 0,89], mas estas são só 12 em 272.
  - É vizinho de dev share e de snipers, variáveis já esgotadas: pela regra 1 da fila, só volta como medida nova, numa população
    nova e com ganho sobre essas duas.
  - A fita `0062` sozinha **não** mede isto: a fatia gravada não tem `slot` e perde a criação quando a decisão vem depois de
    60 s. É preciso instrumentar antes: gravar no derivado o agregado do slot de criação, com o instante em que ficou conhecido.

## Por que pode falhar (limites desta nota)

- As compradoras vêm de `meme_trades` por `block_time`. É um **oráculo retrospetivo**: a fita WS vê essas compras, o arquivo por
  polling não (R73).
- A identidade Helius e a contagem de destinatários foram lidas hoje. A contagem respeita o corte da decisão; a identidade é
  retrospetiva.
- Com os empates, o patamar só teve 3 partições. O diagnóstico do moinho rotula "pico" por construção; não é um pico
  demonstrado.
- As reais sozinhas (44 com desfecho) não têm potência.

## Segunda opinião (Astra)

- **Antes de correr**, a Astra levantou 5 correções de desenho, e todas foram aplicadas antes de resolver a população:
  - financiador lido pela instrução, não pela maior queda de saldo;
  - casa de câmbio com corte por decisão e estado "desconhecido";
  - desfecho censurado quando há buraco de fita até ao pouso;
  - errata da cláusula (a), que literalmente só não-confirma;
  - empates tratados como partições distintas.
- **No veredito**, reproduziu a primária ao dígito e apontou 3 pontos:
  - tercis cortados **antes** da censura do desfecho: mudou a secundária para D +0,048;
  - separar o "pico" mecânico da interpretação feita depois de correr;
  - a `0062` não mede o bundle de criação.
- Concorda com não construir. Pediu a redação "não sustentou" em vez de "não existe".

## Relacionados

[[Fila de Hipoteses]] (H-014) · [[KB-0149-o-que-a-mesa-real-ensinou]] · [[KB-0153-o-maior-comprador-nao-estava-no-arquivo]] ·
[[KB-0143-o-que-antecede-o-dump]] · [[KB-0155-o-equilibrio-quase-nao-passa-na-porta]] · [[Strategy Backlog]]
