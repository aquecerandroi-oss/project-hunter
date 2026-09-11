---
tags: [proposta, risco, carteira, sizing, m3]
titulo: A carteira simulada — o que R$ 9.000 por dia exigiria, e o que a família mean_reversion entrega hoje
data: 2026-09-09
owner: risk-engine-guardian
origem: T3.60
status: aguardando decisão de Everton (universo / participação)
---

# Carteira simulada: quanto vale 1 R, quantos R por dia sobram, e o que R$ 9.000/dia exigiria

**Para:** Everton. **De:** risk-engine-guardian. **Data:** 2026-09-09, 16:15 (Brasília; 19:15 UTC).
**Estado:** nada foi alterado. Nenhum limite mudou, nenhum código de produção mudou, nada foi
commitado. **Leituras (`as_of`):** VPS, transação somente-leitura, 15:44 e 16:15 Brasília
(18:44 e 19:15 UTC). **Patrimônio de referência:** 19.333,0111 USDT = R$100.000 (câmbio implícito do
seed, R$5,1725/USDT).

**Como isto foi medido:** peguei todos os desfechos da família `mean_reversion` e passei cada um pelo
**motor de risco de verdade** (`packages/risk-core/hunter_risk`), em ordem de tempo, como **uma única
carteira**: mesma vaga, mesmo caixa, mesmo orçamento agregado, mesmo teto de participação calculado
com o **volume real de cada minuto** de cada mercado, mesmo kill switch. Nenhum limite foi
redigitado — as configurações são o `PAPER_V1` com um campo trocado.

---

## 1. A resposta em cinco linhas

1. **Oito versões não são oito estratégias: hoje elas fizeram 168 operações em 38 apostas
   distintas.** Fator de repetição **4,42×**. Os +43,45 R do dia viram **+13,17 R únicos**.
2. **O motor executa 27 das 91 apostas** (coorte prospectiva, 08–09/09) e entrega **+2,42 R por
   dia** — com **1 R valendo R$34,48**, não os R$250 do rótulo. Isso é **R$107 por dia** numa
   carteira de R$100 mil.
3. **Subir `risk_per_trade_pct` de 0,25 % para 0,50 % ou 1,00 % não muda um centavo.** Nem subir o
   risco agregado de 1 % para 2 % ou 4 %. Medi as 27 combinações: **as 27 dão o mesmo número**. Quem
   decide o tamanho é o **teto de participação** (1 % de um minuto de volume) em 24 das 27 entradas.
   É o mesmo achado da T3.48, agora medido no nível da carteira inteira.
4. **Abrir mais vagas (5 → 10 → 20) piora.** Sobem 1,5 operações por dia e o resultado **cai** de
   +2,42 para +1,82 R/dia (R$107 → R$50/dia): as apostas que a sexta vaga admite são as piores.
5. **R$ 9.000/dia não existe neste desenho.** Exigiria 1 R = **R$3.719**, isto é, um notional de
   **43 a 56 mil USDT por operação** — que o teto de 10 % por moeda só permite com um patrimônio de
   **R$2,2 a 2,9 milhões**, e que o teto de participação só permite num mercado com **4,3 a 5,6
   milhões de USDT num único minuto**. **Zero mercados** do universo de 253 têm isso.

---

## 2. A tabela que você pediu: R$/dia = R únicos × valor de 1 R

R únicos/dia medido no motor: **+2,42** (prospectiva 08–09/09, perfil `paper_v1`).

| capital | risco/op | 1 R **rótulo** | 1 R **real** (mediana) | R$/dia se o rótulo valesse | **R$/dia real (medido)** | quanto do rótulo sobra |
|---|---|---|---|---|---|---|
| R$100 k | 0,25 % | R$216,11 | **R$34,48** | R$522 | **R$107** | 16,0 % |
| R$100 k | 0,50 % | R$432,22 | R$34,48 | R$1.044 | **R$107** | 8,0 % |
| R$100 k | 1,00 % | R$864,44 | R$34,48 | R$2.088 | **R$107** | 4,0 % |
| R$400 k | 0,25 % | R$865,02 | R$34,48 | R$2.090 | **R$261** | 4,0 % |
| R$400 k | 0,50 % | R$1.730,04 | R$34,48 | R$4.180 | **R$261** | 2,0 % |
| R$400 k | 1,00 % | R$3.460,09 | R$34,48 | R$8.359 | **R$261** | 1,0 % |

Leitura: **a coluna "R$/dia real" não se move com o risco por operação** e **quadruplicar o capital
multiplica o resultado por 2,4, não por 4**. O rótulo é um teto; quem chega antes é a liquidez do
minuto, e ela não sabe quanto dinheiro você tem.

**O "1 R rótulo" acima não é conta minha:** é o teto `risk_per_trade` que o próprio motor calculou
para cada entrada, antes de perder para outro teto, publicado em `sizing.caps`.

---

## 3. O que cada configuração entrega (prospectiva, R$100 k, 2 dias)

| risco/op | agregado | vagas | ops/dia | R/dia | **R$/dia** | pior dia (R$) | drawdown máx. (R$) | travou? |
|---|---|---|---|---|---|---|---|---|
| 0,25 % | 1 % | 5 | 13,5 | +2,42 | **+107** | +39 | 143 (0,14 %) | não |
| 0,25 % | 1 % | 10 | 15,0 | +1,82 | +51 | −2 | 256 (0,26 %) | não |
| 0,25 % | 1 % | 20 | 15,0 | +1,82 | +51 | −2 | 256 (0,26 %) | não |
| 0,50 % | 2 % | 5 | 13,5 | +2,42 | +107 | +39 | 143 | não |
| 1,00 % | 4 % | 20 | 15,0 | +1,82 | +51 | −2 | 256 | não |

As 27 linhas completas estão em `.claude/state/exp-drafts/t360/configuracoes.csv`. **Só a coluna
"vagas" move alguma coisa** — e move para pior.

No replay de 31 dias (13 dias com sinal; **massa, não veredito**, o replay herda o universo de hoje):
+0,70 R/dia, 1 R = R$105,78, **pior dia −4,62 R = −R$489 (−0,49 % do patrimônio)**, drawdown máximo
0,61 %. **O kill switch nunca travou em nenhuma das duas populações** — nem no cenário de estresse em
que marquei toda posição aberta no seu pior ponto (MAE), que levou o drawdown de 0,14 % para 0,19 %.
Com estes tamanhos, os degraus de 1 %, 2 %, 4 % e 8 % ficam muito longe.

---

## 4. Por que 60 % das apostas nem chegam a virar ordem

Das 91 apostas da coorte prospectiva, o motor recusou 64. Os motivos, medidos:

| motivo (check do contrato) | apostas | o que significa |
|---|---|---|
| `liquidity_24h` | **55 (60,4 %)** | o par negociou menos de **50 M USD em 24 h** — piso do perfil |
| `stop_distance` | 5 (5,5 %) | stop fora da banda [0,3 %; 3 %] |
| `concurrent_positions` | 4 (4,4 %) | as cinco vagas estavam ocupadas |

**O gargalo número um não é o risco: é o universo.** Do universo monitorado de 253 mercados, **só 69
(27,3 %)** passam o piso de 50 M/24 h. Dos 33 mercados em que a família entrou hoje, **11**.

E entre os que passam, o tamanho ainda é o do minuto:

| se 1 R tiver de valer… | notional por operação | minuto de volume exigido | mercados que comportam |
|---|---|---|---|
| R$34 (hoje) | 519 USDT | 52 k USDT | **37** |
| R$100 | 1.506 USDT | 151 k USDT | 15 |
| R$250 (o rótulo de 0,25 %) | 3.764 USDT | 376 k USDT | **7** |
| R$1.000 | 15.057 USDT | 1,5 M USDT | 2 |
| R$3.719 (o que R$9 mil/dia pede) | 55.996 USDT | 5,6 M USDT | **0** |

---

## 5. O roster: das oito versões, uma faz quase tudo

Escolha gulosa por R único acumulado (a versão mais antiga fica com a aposta quando duas coincidem):

| passo | versão | apostas | R único total | ganho do passo |
|---|---|---|---|---|
| 1 | **mean_reversion v1** | 82 | +17,78 | +17,78 |
| 2 | **mean_reversion v2** | 84 | +19,53 | +1,75 |
| 3 | mean_reversion v4 | 85 | +20,19 | +0,66 |
| 4–7 | v3, v5, v8, v11 | 85 | +20,19 | **0,00** |
| 8 | mean_reversion v10 | 90 | +20,03 | **−0,17** |
| 9 | mean_reversion v7 | 91 | +19,65 | **−0,37** |
| 10 | mean_reversion v6 | 91 | +19,54 | **−0,11** |

Passado pelo motor, o roster reduzido dá **o mesmo dinheiro com menos peças**: com só `v1` (ou até
`v1..v7`, que produzem as mesmas 22 entradas) são **+3,46 R/dia e R$107,75/dia**, contra **+2,42
R/dia e R$107,19/dia** da família inteira. As oito versões acrescentam cinco entradas por dia que
diluem o R e não trazem dinheiro.

**Recomendação de roster para a carteira: `v1` e `v2`.** As demais não adicionam aposta nova nenhuma
(v3, v5, v8, v11) ou adicionam apostas que perdem dinheiro (v10, v7, v6). Elas continuam no Lab —
isto é o roster **da carteira**, não uma decisão de matar versão. O intervalo de 95 % por bloco de dia
do ganho de um roster reduzido contra a família inteira é **[+0,001; +0,058] R por decisão** com dois
blocos: **não é evidência**, é aritmética de dois dias, e está aqui declarado como tal.

---

## 6. O que R$ 9.000/dia exigiria, pelos dois caminhos

- **Pelo tamanho:** 1 R = R$3.719 → notional de **43–56 mil USDT** por operação (a faixa vem de dois
  stops medianos: 1,68 % da família inteira, 1,28 % das operações executadas). O teto de 10 % por
  moeda exige patrimônio de **R$2,2 a 2,9 milhões**; o teto de participação exige um minuto de
  **4,3 a 5,6 milhões de USDT** — **nenhum** mercado do universo tem isso hoje; o mais fundo
  (BTCUSDT) comporta 42.952 USDT por minuto, e ainda assim só num único par.
- **Pelo número:** manter o tamanho de hoje e fazer **261 R únicos por dia** — **108× o fluxo de R da
  família inteira**, que hoje é 2,42.
- **Nenhum dos dois é uma mudança de limite.** É mudança de **universo** (mercados fundos), de
  **capital** (uma ordem de grandeza acima) e de **borda** (uma expectância que hoje tem dois dias
  de vida). Mudar `risk_per_trade_pct` não move a agulha em nenhum dos dois.

---

## 7. Os campos exatos que mudariam, se você decidir mudar

**Nada foi aplicado.** Se decidir, é isto e só isto:

| # | campo | onde | valor hoje | efeito medido de mudar |
|---|---|---|---|---|
| 1 | `risk_per_trade_pct` | `packages/risk-core/hunter_risk/limits.py` (objeto `PAPER_V1`) | `0.0025` | **nenhum** (0,50 % e 1,00 % dão o mesmo resultado) |
| 2 | `max_aggregate_planned_risk_pct` | idem | `0.01` | **nenhum** (2 % e 4 % dão o mesmo resultado) |
| 3 | `max_concurrent_positions` | idem | `5` | 10 ou 20: +1,5 op/dia e **R$107 → R$50/dia** |
| 4 | `max_participation_pct` | idem | `0.01` | **é este que decide o tamanho** — e é a regra 3 da sua diretiva; não proponho tocar |
| 5 | `min_liquidity_usd_24h` | idem | `50_000_000` | recusa 60 % das apostas da família; baixá-lo abre mercados finos, onde a participação aperta ainda mais |

Cada uma dessas mudanças arrasta o teste que fixa o valor
(`packages/risk-core/tests/unit/test_limits.py`), a fronteira do banco
(`packages/core/tests/integration/test_schema_paper.py`), a API
(`apps/api/tests/integration/test_risk_limits_api.py`) e uma linha nova em `docs/RISK_ENGINE.md`
§2/§9 — o mesmo roteiro da T3.48. **Minha recomendação é não mexer em nenhum:** os três primeiros são
inertes ou negativos, e os dois últimos são a sua própria regra de não engolir o livro.

---

## 8. O que eu preciso declarar, porque muda o peso de tudo acima

1. **A carteira paper nunca executou nada.** `trade_proposals = 0`, `orders = 0`, `positions = 0`,
   `risk_events = 0` (lido 15:44 BRT). Tudo acima é **simulação** com o motor real sobre sinais do
   Lab — é honesto como ordem de grandeza, **não é extrato**.
2. **Dois dias de população prospectiva** (08 e 09/09), 91 apostas, e **nenhum dia perdedor na
   amostra**. Um p10 calculado sobre dois dias não é um p10. A régua de 100 desfechos / 30 dias que
   você mandou construir só fecha por volta de **08/10** — antes disso nada disto é veredito.
3. **Três insumos que a história não tem** foram neutralizados e cada um empurra o tamanho **para
   cima**: livro (profundidade não é histórica), spread (usei a hipótese de custo do Lab, 2 bps) e
   β contra o BTC (não existe em código). Ou seja: **os tamanhos desta nota são um teto superior** do
   que o motor aprovaria com o livro real.
4. **A decisão de universo/participação está aberta.** Enquanto ela não for tomada, o tamanho da
   carteira é decidido pelo minuto de volume do mercado mais fino em que a estratégia entra — e
   nenhuma escolha de limite de risco muda isso.
5. **A população cresce entre leituras.** A família fechou 168 operações até 15:44 BRT hoje; às 15:35
   eram 164. Todos os números vêm dos snapshots declarados.

---

## D-P19: a meta em dinheiro — 2026-09-11 (05:05–05:23 BRT)

**Para:** Everton. **De:** risk-engine-guardian. **Origem:** D-P19, primeiro da fila da Astra no
plantão run 7. **Estado:** nada alterado, nada commitado, nenhum limite tocado, VPS somente leitura.
**Nota completa:** `.claude/state/notes-D-P19.md`. **Câmbio:** USDTBRL 5,1198 (observado 05:05 BRT).

Na T3.60 (09/09) a conta foi feita sobre o universo de 253 mercados e dois dias. Desde a T3.82 o Lab
só observa **16 mercados** (os com 90 dias de histórico), e a carteira compra no **SPOT**. Refiz a
conta nesse recorte, com **30 dias de velas de 1 min**, hora a hora de Brasília. A conclusão não
mudou de direção; ficou mais precisa, e apareceu um teto que ninguém tinha colocado na conta.

### 1. Quanto vale 1 R hoje, mercado a mercado

Com R$ 100 mil, participação 1 %, no minuto mediano de cada mercado:

| onde | 1 R mediano | quem limita |
|---|---|---|
| 16 perpétuos | **R$ 53,57** | participação em 11 deles; **teto de 10 % por moeda** em BTC, ETH, SOL, ZEC e XRP |
| 16 SPOT (onde a carteira compra) | **R$ 18,14** | participação em 11 de 13; o minuto SPOT é 10–19 % do perpétuo |

O intervalo vai de **R$ 0,33** (SAHARA) a **R$ 211** (BTC, ETH, SOL). A novidade em relação à T3.60:
nos cinco mercados fundos **não é mais a participação que segura, é o seu próprio patrimônio** — e
nesses cinco, capital compra tamanho.

### 2. O dinheiro por dia — teto e esperado, nunca um no lugar do outro

A família fez **6,33 apostas únicas por dia** nesses 16 mercados (3 dias: 08–10/09). Nove dos
dezesseis não receberam nenhuma.

| universo | teto R$/dia (**toda** aposta fechando +1 R) | esperado R$/dia (com o R medido, −0,0994) |
|---|---|---|
| 16 perpétuos | **+393,60** | **−310,58** |
| 16 SPOT executando o sinal do perpétuo | **+157,41** | **−137,56** |

A meta de R$ 9.000 é **23×** o teto do perpétuo e **57×** o do SPOT. E o esperado tem o sinal
trocado: hoje a família **perde** dinheiro por dia, em qualquer tamanho.

### 3. O teto que faltava: as vagas

`max_concurrent_positions = 5` com o horizonte de 4 h da família = **no máximo 30 entradas por dia**,
haja quantos sinais houver. Invertendo a meta contra esse teto:

| se o R médio por aposta fosse | 1 R precisaria valer | notional | minuto de volume necessário | quantos dos 16 têm | patrimônio necessário |
|---|---|---|---|---|---|
| +0,05 | R$ 6.000 | 55.431 USDT | 5,54 M USDT | **0** | R$ 2,84 mi |
| +0,10 | R$ 3.000 | 27.716 USDT | 2,77 M USDT | **0** | R$ 1,42 mi |
| +0,20 | R$ 1.500 | 13.858 USDT | 1,39 M USDT | **2** (BTC, ETH) | **R$ 709 mil** |
| +0,40 | R$ 750 | 6.929 USDT | 693 k USDT | 2 | R$ 355 mil |

(O "1 R = R$ 3.719" da T3.60 é o ponto R̄ ≈ +0,08 desta tabela — as duas contas batem.)

### 4. Se eu afrouxasse a participação (cenário; **não mexi em nada**)

| participação | patrimônio | teto R$/dia | esperado R$/dia |
|---|---|---|---|
| 1 % | R$ 100 k | +393,60 | −310,58 |
| 2 % | R$ 100 k | +485,17 | −346,06 |
| 5 % | R$ 100 k | +734,91 | −434,76 |
| 5 % | R$ 400 k | +1.666,00 | **−1.277,78** |

**Quintuplicar a participação multiplica o teto por 1,87, não por 5**, e **piora** o esperado —
porque com expectancy negativa tamanho maior é prejuízo maior. A célula mais agressiva da tabela
entrega 18,5 % da meta, e só se **todas** as apostas ganharem.

### 5. A hora do dia importa, e estamos na hora errada

O minuto mediano das **11 h BRT** vale 4,8× o das **18 h**; 1 R mediano vai de **R$ 87,95** (11 h)
para **R$ 37,21** (18 h). **14 das 22 apostas da família nos 16 mercados caem entre 16 h e 18 h** —
a janela de menor capacidade. Com 22 apostas isso não vira regra; vira pergunta.

### 6. O que decide a meta, em ordem

1. **Expectancy.** Enquanto o R médio por aposta for ≤ 0, **não existe tamanho positivo que
   resolva** — a frase é da Astra e a conta confirma: todo cenário maior perde mais.
2. **Capital.** Para R$ 9.000/dia com um R médio generoso (+0,20), o teto de 10 % por moeda exige
   **R$ 709 mil**; com +0,10, R$ 1,42 milhão.
3. **Universo.** Só **BTC e ETH** têm o minuto de volume que esse tamanho pede, e a família não
   entrou em nenhum dos dois em três dias. O universo executável precisa incluir os mercados fundos
   **e** a estratégia precisa de fato operar neles.
4. **O que NÃO é alavanca:** mais versões da mesma ideia. O dedupe já mostra que 859 desfechos são
   191 apostas; versões novas multiplicam decisões e não movem nenhum dos três itens acima.
