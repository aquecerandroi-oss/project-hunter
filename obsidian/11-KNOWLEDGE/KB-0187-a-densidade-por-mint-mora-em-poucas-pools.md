---
tags: [knowledge, meme, pumpfun, pumpswap, densidade, carteiras, cpu, h-030]
tema: como os eventos de swap do programa inteiro (pump + PumpSwap) se distribuem por mint/pool numa hora, e o que isso faz com o custo do motor de carteiras (o stop por cópia escaneia a hora do mint)
fonte: sonda de 06/10/2026 desta máquina, só WebSocket do RPC público (infra/scripts/research/2026-10-06-wallet-tape-density-probe.py; leitura em …-density-read.py; saídas em .claude/state/carteiras-lucro/density/run1 com density-read.md); curva de custo sintética em .claude/state/carteiras-lucro/bench/hot-mint-sweep-2026-10-06-step3.txt
lido_em: 2026-10-06
evidencia: medição própria (uma hora contínua, 06/10 18:47:42–19:49:55 UTC, 1 308 464 swaps com chave, 0 recusas/suspensões/desconexões) + cenário de custo sobre a varredura sintética do passo 3
hipotese_testavel: não (é medição de instrumento; serve ao orçamento de CPU do H-030)
astra: concorda (REQUEST_CHANGES na leitura, depois APPROVE: os números centrais conferem no recálculo dela; corrigidos os denominadores, a fatia extrapolada de 50–58 % e a identificação indevida com a cópia típica; os limites do cenário continuam) — ver Revisoes-Astra/wallets-cpu-step3
status: vivo
owner: quant-engineer
updated: 2026-10-06
confiança: "backtest do autor"
tipo: pesquisa
hipotese: —
variavel: eventos de swap na hora mais cheia de cada chave (mint da curva ou pool da PumpSwap), janela deslizante exata de 60 min
populacao: programa pump (6EF8…) e PumpSwap (pAMM…) inteiros, terça-feira 06/10/2026, uma hora
efeito: —
ic: —
veredito: —
proximo_passo: medir entidades distintas por pool quente e repetir em outro dia; decidir entre o stop em O(1) (passo 4 do plano de CPU) e uma mudança de universo (decisão do Everton)
classe_de_perda: —
mercado: meme
---

# KB-0187 — A densidade por mint mora em poucas pools: uma pool teve 124 mil eventos numa hora (06/10/2026)

## O que afirma

Numa hora do programa inteiro (pump + PumpSwap), 352 swaps por segundo se espalharam por **10 619 chaves**: mint da curva ou pool da PumpSwap. A mediana teve **2 eventos**, mas o peso está numa cauda curta:

- **235 chaves** passaram de 1 000 eventos na hora (201 pools e 34 mints da curva), **58** de 4 000 (57 pools e 1 mint) e **5** de 16 000, estas todas pools;
- a maior pool teve **124 069 eventos** (9,6 % de tudo, até 3 140 por minuto); as 10 maiores, 21,6 %;
- nenhum mint da curva passou de 4 512 por hora.

Ponderado pelos eventos, o evento médio vive numa chave com **17 062 eventos por hora** (Σn²/Σn). Isso pesa no custo do motor de carteiras do H-030, porque o stop de cada cópia cota a venda em cada evento da hora seguinte do mint ([[wallets-cpu]]). Mas não é a densidade de uma cópia típica: as cópias nascem de **apostas elegíveis** (primeira compra ≥ 0,1 SOL de cada entidade no mint, sob o teto diário), não de eventos, e as apostas por chave não foram medidas.

## Onde foi mostrado

**A sonda.** É a da onda 0 ([[KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar|KB-0183]]), com um contador a mais: swaps por chave e o instante de cada um.

- `logsSubscribe` em `confirmed`, uma conexão por programa, só WebSocket. O lado HTTP do RPC público passou a responder 413 de cota em 06/10 ([[KB-0186-o-tempo-real-da-pumpfun-chega-uns-0-1-s-antes-das-outras-fontes|KB-0186]]).
- A sonda para na primeira recusa ou na primeira suspensão da máquina; nenhuma das duas aconteceu.
- 3 720 s de recepção, sem desconexão nem descarte de fila.
- A hora mais cheia de cada chave é contada por dois ponteiros sobre os instantes de recepção: janela semiaberta de 3 600 s, não alinhada ao minuto.

| eventos na hora | chaves de curva | chaves de pool | fatia dos eventos (tudo) |
|---|---|---|---|
| 1–9 | 4 690 | 3 036 | 1,4 % |
| 10–99 | 1 303 | 657 | 4,9 % |
| 100–999 | 441 | 257 | 17,0 % |
| 1 000–3 999 | 33 | 144 | 27,9 % |
| 4 000–15 999 | 1 | 52 | 33,1 % |
| ≥ 16 000 | 0 | 5 | 15,8 % |

Σn²/Σn por programa: curva 738, pool 20 904. Da 2.ª à 10.ª chave, todas pools, com 14 141–24 956 eventos na hora.

## O que muda no custo (cenário)

Cada chave-hora foi cotada na curva sintética de um mint só, medida no passo 3 do plano de CPU (de 0,28 s a 1 000/h até 37,4 s a 16 000/h). Além de 16 000/h, a curva foi estendida com o expoente 1,51–1,69.

- **Multiplicador sobre o custo linear: 5,7–6,7×.** Curva 1,31×, pools 6,7–8,0×.
- Uma hora do programa custa 2 070–2 455 s de CPU, e a maior pool sozinha, 819–1 194 s.
- Extrapolado para a janela de 7 dias (≈ 213 M fills): **97–115 h por noite num núcleo** pela projeção direta, ou 41–108 h pela razão sobre o passo 2. Com 2 workers: 55–96 h pela projeção direta e 23–90 h pela razão; envelope das duas bases, 23–96 h.
- Se a maior pool ficasse assim a semana inteira, só ela seria um caminho crítico de 38–56 h, que não se divide entre workers.

A meta de < 2 h com 2 núcleos fica a ≈ 12–48× de distância: workers não resolvem. O que ataca isso é o stop em O(1) por evento (passo 4) ou uma mudança de universo, que é decisão do Everton e versão nova do protocolo. Ver [[wallets-cpu]], seção "Densidade real".

## Limites

- **Uma hora**, numa terça às 18h–19h UTC. Outros dias e horários não foram medidos.
- **A curva de custo é sintética.** As cópias do gerador crescem menos que os eventos. Também não sabemos quantas entidades distintas compram ≥ 0,1 SOL nas pools quentes: a sonda conta eventos, não carteiras nem apostas por chave. Uma pool de 124 mil eventos por hora pode ser um laço de poucos robôs com zero apostas elegíveis. Por isso o cenário **pode errar para os dois lados**.
- **As 5 chaves acima de 16 000/h** ficam fora da faixa medida (até 7,75×) e pesam **50–58 %** do custo do cenário.
- **Chaves de pool:** 39,5 % dos swaps com chave são compras de pool chaveadas pela pool **inferida** (layout do `BuyEvent`, [[KB-0184-o-buyevent-da-pumpswap-e-as-armadilhas-de-ler-eventos-do-programa-inteiro|KB-0184]]).
- **Curva e pool de um mesmo mint são chaves separadas.** Juntá-las acrescenta no máximo os eventos da curva, que são poucos.

## Relacionado

[[wallets-cpu]] · [[wallets-cpu-step3]] · [[KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar]] · [[KB-0184-o-buyevent-da-pumpswap-e-as-armadilhas-de-ler-eventos-do-programa-inteiro]] · [[EXP-M15-carteiras-vencedoras]]
