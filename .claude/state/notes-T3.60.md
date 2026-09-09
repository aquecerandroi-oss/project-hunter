# notes-T3.60 — a família `mean_reversion` como UMA carteira sob o motor de risco real: 492 desfechos, 155 apostas distintas, 27 execuções e a conta do R$ 9.000/dia

**Data:** 2026-09-09 (Brasília, UTC−3; UTC como detalhe). **Owner:** risk-engine-guardian.
**Base:** `main` — árvore compartilhada, **nada commitado**, nada tocado em `apps/`, `services/`,
`packages/`. **Nenhum limite alterado.** **VPS estritamente somente leitura**: toda consulta dentro
de `begin transaction isolation level repeatable read read only; … commit;` entregue pelo stdin de
`psql`. Nenhum container parado, recriado ou reiniciado. Nenhum `.env*` tocado. Nenhum shell em
segundo plano; todo comando em primeiro plano com `timeout 290`.
**`t342-blocos/blocos.py` reusado sem uma linha alterada** (é o IC por bloco de dia do §7).

---

## STATUS

**DONE_WITH_CONCERNS.**

| # | Entrega do brief | Resultado |
|---|---|---|
| 1 | Simulador de carteira em Python puro/Decimal, com dedupe, vagas, risco agregado, risco por operação, kill switch e participação com volume real, **chamando as funções do `hunter_risk`** | **OK** — `t360/carteira.py`; `evaluate`, `assess`, `resume`, `advance_peak`, `sao_paulo_day_start_utc` e `RiskLimits.model_validate(PAPER_V1…)` são os do motor; nenhum limiar redigitado |
| 2 | Três populações: prospectiva 08–09/09, replay de 31 d, e hoje hora a hora | **OK** — §3, §4, §6 |
| 3 | Saídas por configuração: ops/dia, R/dia com p10/p50/p90, drawdown em R e R$, pior dia, dias até o kill switch, recusas por limite, e a tabela do dinheiro | **OK** — §4, §5, §8; 27 configurações × 2 coortes em `configuracoes.csv` |
| 4 | Correlação entre versões e recomendação de roster (guloso, com o pooling) | **OK** — §7 |
| 5 | O documento para o Everton | **OK** — `.claude/state/proposta-carteira-2026-09-09.md` |
| 6 | ≤ 10 linhas em português | **OK** — §10 |

**Resposta curta:** oito versões da `mean_reversion` são **uma** estratégia com quatro vezes o
barulho — 168 operações hoje em **38 apostas** (4,42×), +43,45 R brutos que viram **+13,17 R
únicos**. Passada pelo motor real, a carteira executa **27 das 91 apostas** da coorte prospectiva e
entrega **+2,42 R/dia com 1 R = R$34,48 → R$107/dia** sobre R$100 mil. **As 27 combinações de
`risk_per_trade_pct` × `max_aggregate_planned_risk_pct` × `max_concurrent_positions` dão exatamente o
mesmo resultado, exceto pelas vagas — e mais vagas dá menos dinheiro** (R$107 → R$50/dia). Quem
decide o tamanho é o **teto de participação** em 24 das 27 entradas; quem recusa é o **piso de
liquidez de 50 M/24 h**, em 60,4 % das apostas. **R$ 9.000/dia exigiria 1 R = R$3.719**, isto é, um
notional de 43–56 mil USDT que **nenhum** dos 253 mercados do universo comporta num minuto.

**As CONCERNs (§9), em uma linha cada:** (1) dois dias de população prospectiva e **nenhum dia
perdedor na amostra** — p10/p50/p90 sobre dois blocos não são distribuição; (2) livro, spread e β
foram neutralizados e os três empurram o tamanho **para cima** (os números são teto superior);
(3) a marca das posições abertas é o custo, então o kill switch enxerga menos intradia do que
enxergaria na carteira real (mitigado, não resolvido, pelo cenário MAE do §8); (4) o replay herda o
universo de hoje e quatro mercados, e não é veredito; (5) a carteira paper **nunca executou nada**
(`orders = 0`), então tudo aqui é simulação sobre sinais do Lab, não extrato.

---

## 0. LEITURA PRÉVIA

`docs/RISK_ENGINE.md` v2.3 inteiro (§1 insumos, §2 o perfil `paper_v1`, §3 a ordem dos checks, §4 o
sizing e os nove tetos, §5 o kill switch e o dia de São Paulo, §7 falhar fechado, §11 escopo de
capital); `docs/PIPELINE.md` §7 (proposal builder) e §8 (execution engine, os seis laços e a
expiração de 30 s); `docs/ARCHITECTURE.md` §6 (`RiskEngine` puro, `ExecutionAdapter`). Do lado da
pesquisa: a decisão de 2026-09-08 `obsidian/06-DECISIONS/2026-09-08-limites-de-risco-teto-inerte.md`
(T3.48 — o teto de 0,25 % é inerte; quem manda é a participação), `notes-T3.53.md` (o pooling da
família, 3,6–3,8×, e o precedente de "amostra insuficiente é o achado") e
`infra/scripts/sql/research/2026-09-08-00-base.sql` (a decomposição do R e a identidade do pedágio).

**O que a T3.48 já tinha provado e esta nota estende:** lá a medida era *por sinal*, com o volume das
últimas 24 h como proxy da referência do minuto. Aqui é *por carteira*, em ordem de tempo, com o
**minuto real** de cada entrada (`min(último minuto completo, mediana das 30 barras completas)`,
calculado das velas de 1 min) e com o estado da carteira mudando a cada evento. A conclusão não
mudou; ela ficou mais dura, porque agora inclui a concorrência entre as versões.

---

## 1. Arquivos

**SQL (somente leitura, cada um executável sozinho):**
- `C:\dev\project-hunter\infra\scripts\sql\research\2026-09-09-t360-q00-catalogo.sql`
- `C:\dev\project-hunter\infra\scripts\sql\research\2026-09-09-t360-q01-populacao-csv.sql`
- `C:\dev\project-hunter\infra\scripts\sql\research\2026-09-09-t360-q02-tetos-e-universo.sql`

**Análise (rascunho, fora de produção):**
- `C:\dev\project-hunter\.claude\state\exp-drafts\t360\carteira.py` — o simulador
- `C:\dev\project-hunter\.claude\state\exp-drafts\t360\test_carteira.py` — 40 testes
- `C:\dev\project-hunter\.claude\state\exp-drafts\t360\roda.py` — a manivela das tabelas
- `C:\dev\project-hunter\.claude\state\exp-drafts\t360\populacao.csv` — 492 desfechos (dump de `q01`)
- `C:\dev\project-hunter\.claude\state\exp-drafts\t360\configuracoes.csv` — 54 linhas (27 configurações × 2 coortes)
- `C:\dev\project-hunter\.claude\state\exp-drafts\t360\q00.out`, `q02.out`, `roda.out`, `pytest.out`

**Entregas de texto:**
- `C:\dev\project-hunter\.claude\state\proposta-carteira-2026-09-09.md` (o documento para o Everton)
- `C:\dev\project-hunter\.claude\state\notes-T3.60.md` (este arquivo)

---

## 2. Corte, snapshots e o que o simulador é

**Cortes declarados:** `q00` lido **2026-09-09 15:44 BRT** (18:44 UTC); `q01` (o CSV que alimenta
tudo) **15:47 BRT**; `q02` **16:15 BRT** (19:15 UTC). A população cresce entre leituras — a família
tinha 164 operações fechadas às 15:35 e 168 às 15:44. Todo número desta nota vem do snapshot do CSV.

**O simulador é o motor mais um relógio.** `hunter_risk.evaluate` é puro (docs/ARCHITECTURE.md §6):
não tem relógio, banco nem rede. O que `t360/carteira.py` faz é exatamente o que falta em volta —
manter caixa, posições, a âncora do dia de São Paulo, a trava do kill switch e o orçamento móvel de
participação de 60 s — e montar, para cada sinal, os insumos que o motor exige. As decisões, os
tetos, o limitante vencedor, a ordem dos checks e a escada do kill switch **são do `hunter_risk`**.

**As configurações não redigitam limiar nenhum:**

```python
def limites(self) -> RiskLimits:
    base = PAPER_V1.model_dump(mode="json")
    base["risk_per_trade_pct"] = str(self.risk_per_trade_pct)
    base["max_aggregate_planned_risk_pct"] = str(self.max_aggregate_planned_risk_pct)
    base["max_concurrent_positions"] = self.max_concurrent_positions
    return RiskLimits.model_validate(base)
```

`test_o_perfil_de_cada_configuracao_e_o_PAPER_V1_com_um_campo_trocado` prova que o resto
(participação, kill switch, banda de stop) continua sendo o do Everton.

**Três neutralizações, todas empurrando o tamanho para cima** (declaradas no cabeçalho do módulo):
livro sintético fundo no preço-limite do `max_slippage_pct` (`book_depth` e `slippage_estimate` nunca
mordem), spread da própria hipótese de custo do Lab (2 bps < 5 bps do teto), e **β = 0 validado** —
sem ele o motor rejeitaria **tudo** por `beta_validity` (o β não existe em código, KB-0071) e a
pergunta ficaria sem resposta. É a única neutralização que muda o veredito de um check.

**O dinheiro.** `r_net` do Lab tem denominador `risk = |entrada − stop|` em preço, **sem** custo.
Então `pnl = qty × risk × r_net = notional × risco_pct × r_net`, e `1 R = notional × risco_pct` — a
mesma identidade da T3.48. `r_net` já é líquido de spread, slippage, fee e funding: o caixa é
debitado do notional na entrada e creditado de `notional + pnl` na saída, para o custo não ser
cobrado duas vezes.

**Dedupe.** A aposta é `(mercado, source_bar_close)`; vence a **versão mais antiga** (menor número),
com desempate por `signal_id`. É o critério que **não olha o resultado** — há teste para isso
(`test_a_escolha_do_dedupe_nao_olha_o_resultado`). Hoje o crédito ficou 33 apostas para a `v1` e 5
para a `v10`.

---

## 3. A população e o pooling — `roda.py` §1 e `q00` §4

```
prospectiva  | n= 279 | apostas=  91 | pooling= 3.07x | dias= 2 | mercados= 69 | versoes=10 | R_bruto_soma=   63.11 | R_unico_soma=   19.54
replay       | n= 213 | apostas=  64 | pooling= 3.33x | dias=13 | mercados=  4 | versoes=12 | R_bruto_soma=   49.50 | R_unico_soma=    8.21
hoje 09/09   | n= 168 | apostas=  38 | pooling= 4.42x | dias= 1 | mercados= 32 | versoes= 8 | R_bruto_soma=   43.45 | R_unico_soma=   13.17
   creditos do dedupe (quem levou a aposta): {'mean_reversion v1': 33, 'mean_reversion v10': 5}
```

Do banco, sem passar por Python (`q00` §4 e §5):

```
| prospective | 2026-09-08 |       111 |            53 |           50 |       45 |       8 |          2.09 |  19.66 |
| prospective | 2026-09-09 |       168 |            38 |           38 |       32 |       8 |          4.42 |  43.45 |
...
|   coorte    | pico_simultaneo | media_simultanea | eventos_acima_de_5 | pct_eventos_acima_de_5 |
| prospective |              51 |            25.81 |                531 |                   95.2 |
| replay      |              27 |             7.17 |                210 |                   49.3 |
```

**Correção a um número do brief:** o pico de posições simultâneas que a família pediria é **51**, não
100 — medido por varredura de eventos entrada/saída sobre desfechos terminais com janela conhecida.
Em **95,2 %** dos instantes ela quer mais de cinco posições ao mesmo tempo. O `max_concurrent_positions
= 5` é, portanto, o filtro mais agressivo da carteira em número de apostas descartadas por
concorrência — mas, como o §5 mostra, não é ele que descarta mais.

---

## 4. A varredura de 27 configurações — `roda.py` §3, §4, §8

Coorte prospectiva (08–09/09, 2 dias, 91 apostas candidatas). As 27 linhas colapsam em **duas**:

| risco/op | agregado | vagas | cand | aprov | ops/dia | R/dia | pior dia R | USDT/R p50 | PnL USDT | DD USDT | DD % | travou |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0,25 / 0,50 / 1,00 % | 1 / 2 / 4 % | 5 | 91 | **27** | 13,5 | **+2,42** | +1,12 | 6,67 | +41,45 | 27,65 | 0,14 | não |
| 0,25 / 0,50 / 1,00 % | 1 / 2 / 4 % | 10 ou 20 | 91 | **30** | 15,0 | **+1,82** | −0,07 | 5,47 | +19,54 | 49,53 | 0,26 | não |

**Nove configurações por linha, centavo por centavo iguais.** Não é arredondamento: `risk_per_trade`
só é o teto vencedor em **0** das 27 entradas aprovadas da coorte prospectiva, e o orçamento
agregado nunca chega perto (as cinco posições da carteira somam risco planejado muito abaixo de 1 %,
porque cada uma é pequena por causa da participação).

Em R$ (capital R$100 k, `roda.py` §8):

| vagas | ops/dia | R/dia | R$/dia | R$ pior dia | R$ drawdown máximo |
|---|---|---|---|---|---|
| 5 | 13,5 | +2,42 | **+107,19** | +38,60 | 143,03 |
| 10 / 20 | 15,0 | +1,82 | **+50,54** | −2,11 | 256,20 |

Replay (13 dias com sinal, 4 mercados — **massa, não veredito**): 61 de 64 apostas aprovadas, 4,7
ops/dia, **+0,70 R/dia**, 1 R = 20,45 USDT (R$105,78), **pior dia −4,62 R = −R$488,75 = −0,489 % do
patrimônio**, drawdown máximo 0,61 %, e **também idêntico nas 27 configurações**.

**Dias até o kill switch: nunca, nas duas populações e em todas as configurações.** Com estes
tamanhos, o degrau de aviso (1 % no dia / 4 % de drawdown) fica a uma ordem de grandeza. O pior dia
medido consome 0,489 % do patrimônio.

---

## 5. Onde as entradas morrem, e qual teto decide o tamanho — `roda.py` §5

```
-- prospectiva: 91 apostas candidatas, 27 aprovadas
     recusa liquidity_24h              55  (60.4%)
     recusa stop_distance               5  (5.5%)
     recusa concurrent_positions        4  (4.4%)
     limitante market_participation    24
     limitante asset_exposure           3
-- replay: 64 apostas candidatas, 61 aprovadas
     recusa duplicate_position          2  (3.1%)
     recusa stop_distance               1  (1.6%)
     limitante asset_exposure          50
     limitante market_participation     8
     limitante risk_per_trade           3
```

Três leituras:

1. **O gargalo não é risco, é universo.** 60,4 % das apostas prospectivas morrem no piso de
   liquidez de 50 M USD/24 h (check 9). Do universo monitorado, **69 de 253 (27,3 %)** passam esse
   piso (`q02` §1); dos 33 mercados em que a família entrou hoje, **11** (`q02` §2).
2. **Quem decide o tamanho no universo vivo é a participação** (24 de 27). No replay, que só tem
   BTC/ETH/XRP/DOGE, quem decide é o **teto por moeda de 10 %** (50 de 61) — em mercado fundo a
   participação para de morder e a carteira encontra o limite do próprio patrimônio.
3. **`risk_per_trade` vence 3 vezes em 88 entradas aprovadas somando as duas coortes** — e as três
   são de replay, em mercados enormes. É a mesma frase da T3.48, agora com a carteira inteira.

O contraste com um cenário de mercado grande está fixado em teste
(`test_quatro_posicoes_cheias_esgotam_a_exposicao_total_de_40_por_cento`): com liquidez infinita, o
que limita não é a vaga nem o risco, é `max_total_exposure_pct = 0,40` dividido por
`max_asset_exposure_pct = 0,10` — **quatro** posições cheias, e a quinta sai com tamanho zero.

---

## 6. Hoje, hora a hora (dia de São Paulo, `roda.py` §6)

```
hora BRT | ops | R | R medio
       0 |   2 |   -0.84 |  -0.419
       1 |   1 |   -1.12 |  -1.115
       2 |   1 |   +0.68 |  +0.678
       5 |   1 |   -1.06 |  -1.064
       7 |   2 |   +1.38 |  +0.688
       8 |   2 |   +0.43 |  +0.217
      10 |   1 |   -1.07 |  -1.071
      12 |   5 |   +5.31 |  +1.063
TOTAL | 15 ops | +3.71 R | PnL +55.54 USDT = R$ +287.26 | USDT/R mediano 7.26
```

**Quinze operações, e uma hora (12 h BRT) explica +5,31 dos +3,71 R do dia.** Sem ela o dia é
negativo. Não é uma hipótese de "hora boa" — é o tamanho da amostra aparecendo: o dia inteiro da
carteira cabe em quinze decisões e uma janela de uma hora.

---

## 7. Roster: das oito (dez, contando o dia 08) versões, uma faz quase tudo — `roda.py` §9

Guloso por R único acumulado:

| passo | versão | apostas | R único total | ganho do passo |
|---|---|---|---|---|
| 1 | **v1** | 82 | +17,78 | +17,78 |
| 2 | **v2** | 84 | +19,53 | +1,75 |
| 3 | v4 | 85 | +20,19 | +0,66 |
| 4–7 | v3, v5, v8, v11 | 85 | +20,19 | 0,00 |
| 8 | v10 | 90 | +20,03 | −0,17 |
| 9 | v7 | 91 | +19,65 | −0,37 |
| 10 | v6 | 91 | +19,54 | −0,11 |

Passado pelo motor, o roster de **uma** versão dá **22 entradas, +3,46 R/dia, R$107,75/dia**; a
família inteira dá **27 entradas, +2,42 R/dia, R$107,19/dia**. As cinco entradas a mais **diluem o R
e não trazem dinheiro**.

**O IC não sustenta a escolha, e isso está declarado.** Reusando `t342-blocos/blocos.py` sem
alteração (bloco = dia, 2.000 reamostragens), o Δ do roster de duas versões contra a família é
**+0,0178 R por decisão, IC95 [+0,0013; +0,0575]** — com **dois blocos**. Um IC de dois dias não é
inferência; é a aritmética dos dois dias que existem. A recomendação de roster se sustenta pelo
mecanismo (a `v1` é quem leva 33 das 38 apostas de hoje no dedupe, então as outras não estão
adicionando aposta), não por esse intervalo.

---

## 8. Estresse e kill switch — `roda.py` §10 e §11

```
marca=custo  | aprovadas=  27 | R/dia=  +2.42 | DD= 0.14% | travou=nao
marca=mae    | aprovadas=  27 | R/dia=  +2.42 | DD= 0.19% | travou=nao
```

A marca a custo (a posição aberta vale o que custou) faz o patrimônio só se mover na saída, e isso
esconde intradia. O cenário `mae` marca cada posição no **pior ponto que ela de fato atingiu**, a
partir da barra de MAE: o drawdown sobe de 0,14 % para 0,19 % e **nada trava**. Não é prova de que a
carteira real não travaria; é a medida de que, **neste tamanho**, o intradia da amostra não chega
perto de 1 %.

O comportamento da trava está fixado em três testes com cenário sintético: uma perda de 4 % do
patrimônio no dia leva a `TRADING_DISABLED`, a trava **não se desfaz sozinha no dia seguinte**, e a
retomada manual passa pelo `hunter_risk.resume` de verdade — que recusaria se a avaliação automática
ainda bloqueasse.

---

## 9. CONCERNs

1. **Dois dias e nenhum dia perdedor.** A coorte prospectiva tem 08 e 09/09. Os p10/p50/p90 de R/dia
   são, literalmente, dois números. O pior dia prospectivo é **+1,12 R** — não existe dia ruim na
   amostra, então a coluna "quanto custa um dia ruim" do documento vem do **replay** (−0,489 % do
   patrimônio) e é a única evidência de dia ruim que temos. Antes da régua 100/30 (≈ 08/10) nada
   disto é veredito.
2. **Três insumos neutralizados, todos na mesma direção.** Livro, spread e β foram entregues em
   configuração benigna porque a história não os tem. Os três empurram o tamanho **para cima**: os
   notionais desta nota são **teto superior**. O efeito é maior nos mercados finos, que são
   justamente os que a família mais usa.
3. **A marca das posições abertas é o custo.** O kill switch da simulação reage a resultado
   realizado; o da carteira real reage à marcação a cada 60 s. O cenário MAE (§8) mede o pior caso e
   não muda a conclusão nesta amostra, mas num tamanho maior mudaria.
4. **O replay não é veredito.** 13 dias com sinal, quatro mercados (BTC/ETH/XRP/DOGE), universo
   herdado de hoje, e a janela que inventou as hipóteses. Ele entra como massa e como a única fonte
   de dia ruim.
5. **A carteira paper nunca executou nada.** `trade_proposals = 0`, `orders = 0`, `positions = 0`,
   `risk_events = 0`, `risk_profile_id` nulo (lido 15:44 BRT). Tudo é simulação sobre sinais do Lab.
   A pendência da T3.48 continua aberta: **não existe linha `paper_v1` em `risk_profiles`**, então a
   tela de limites mostra o código, não um perfil auditável.
6. **Duas medianas de stop convivem na conta do R$ 9.000.** 1,677 % (toda a família, via SQL) e
   1,284 % (só as operações que o motor executou, via simulador) — daí a faixa de 43–56 mil USDT de
   notional. Nenhuma das duas muda a conclusão, porque zero mercados comportam qualquer ponto da
   faixa.
7. **`participation_used_quote` é o consumo da própria simulação.** Como o dedupe deixa uma aposta
   por mercado e barra, o orçamento móvel de 60 s quase nunca morde aqui. Numa carteira com várias
   famílias ele morderia mais, e este simulador subestimaria as recusas.

---

## 10. Veredito em dez linhas

1. Oito versões da `mean_reversion` são uma estratégia repetida 4,42 vezes: 168 operações, 38 apostas.
2. O motor executa 27 das 91 apostas prospectivas e entrega +2,42 R/dia.
3. Um R vale **R$34,48** — 16 % do rótulo de R$216 que 0,25 % promete.
4. São **R$107 por dia** sobre R$100 mil; com R$400 mil viram R$261, não R$429.
5. Subir o risco por operação para 0,50 % ou 1,00 % não muda **nada** — nem o agregado para 2 % ou 4 %.
6. Abrir vagas de 5 para 10 ou 20 **piora**: mais 1,5 operação por dia, R$107 → R$50.
7. Quem decide o tamanho é a participação (24/27); quem recusa é o piso de liquidez (60,4 %).
8. O kill switch nunca travou; o pior dia medido custa 0,489 % do patrimônio (replay).
9. Para o roster da carteira, `v1` + `v2` bastam: as outras seis não trazem aposta nem dinheiro.
10. **R$ 9.000/dia pediria 1 R de R$3.719 — notional de 43–56 mil USDT, que nenhum dos 253 mercados
    do universo comporta num minuto. É decisão de universo e de capital, não de limite de risco.**
