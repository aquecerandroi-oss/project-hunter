---
tags: [knowledge, nota, risk-engine, dimensionamento, meta, dinheiro, m3]
tema: a meta de R$ 9.000/dia traduzida em dinheiro real por mercado e hora, com os limites de risco de hoje — o teto do universo executável é 23–57× menor que a meta, com o sinal trocado, e a trava dura não é só a participação de mercado
fonte: dado próprio da VPS (30 dias de volume por perpétuo, 4 dias por SPOT, 3 dias de coorte prospectiva da família mean_reversion) — `.claude/state/notes-D-P19.md`
fonte_url: —
lido_em: 2026-09-11
as_of: "2026-09-11T08:19:00Z"
read_at: "2026-09-11T08:19:00Z"
evidencia: "?"
hipotese_testavel: "não — é aritmética de dinheiro sobre limites e giro medidos, não candidata de estratégia"
astra: pendente
status: arquivada
owner: sexta-feira
updated: 2026-09-11
confiança: "?"
---

# A meta em dinheiro: quanto R$ 9.000/dia pede, mercado por mercado, hora por hora

> **Arquivada pela Sexta-feira em 2026-09-11 (plantão de arquivamento)** a partir de
> `.claude/state/notes-D-P19.md` (T3.64, plantão run 7, lane 3, item 2 — origem em
> `sentinel-trader-research`, Hacker News: "direcional +0,035 R bruto → −0,243 R líquido, só carry
> com participação 5 % sobrevive"). Não editei nenhum número abaixo além de organizar a nota nesta
> forma; toda proveniência está no arquivo de origem. Nada aqui é dinheiro real
> (`ENABLE_LIVE_TRADING=false`) — é simulação sobre sinais do Lab e velas reais, `packages/
> risk-core` não recebeu uma linha, `limits.py` não foi tocado.
>
> **Veredito em uma linha:** com o universo de 16 mercados (T3.82), a família `mean_reversion` e os
> limites de risco de hoje, o **teto** (toda aposta fechando +1 R) é **R$ 393,60/dia** no perpétuo e
> **R$ 157,41/dia** no SPOT — a meta é **23×** e **57×** isso, e o **esperado** com a expectancy
> medida é negativo em ambos. A meta é decisão de capital, universo e expectancy, nessa ordem — mais
> versões da mesma ideia não é alavanca.

## O que afirma

1. **1 R em dinheiro varia 640× entre os mercados do universo executável.** Um lance isolado numa
   carteira vazia (participação 1 % do minuto, R$ 100 mil, referência = mediana da hora agregada de
   30 dias) autoriza notional entre 7 e 1.953 USDT por entrada — 1 R entre **R$ 0,33** (SAHARA) e
   **R$ 211** (BTC/ETH/SOL), mediano **R$ 53,57** no perpétuo. Em **5 dos 16** mercados (BTC, ETH,
   SOL, ZEC, XRP) quem já limita é o `max_asset_exposure_pct` (10 % do patrimônio), não a
   participação de mercado — nesses cinco, mais capital compra mais tamanho; nos outros onze, não
   compra nada.
2. **A carteira compra no SPOT, e o SPOT é uma fração do perpétuo.** O minuto SPOT vai de 10,5 %
   (ETH) a 19,2 % (ZEC) do minuto perpétuo equivalente; só BTC e ETH chegam a ter o teto de
   patrimônio como limitante no SPOT. O 1 R mediano cai de R$ 53,57 (perpétuo) para **R$ 18,14**
   (SPOT). Um mercado dos 13 com vela SPOT (ARB, 45,6 M/dia medidos) fica abaixo do piso de 50 M/24 h
   e nem chega ao sizing; DASH, LINK e TAO não têm vela SPOT nenhuma no banco.
3. **O teto do dia (cenário impossível: toda aposta fechando +1 R) é R$ 393,60/dia no perpétuo e
   R$ 157,41/dia no SPOT** (16 mercados, participação 1 %, R$ 100 mil, giro medido de 6,33 apostas
   únicas/dia na família nos 3 dias de coorte prospectiva). **O esperado com o R̄ medido da família
   (−0,0994/aposta) é −R$ 310,58/dia e −R$ 137,56/dia** — a meta de R$ 9.000/dia é **23×** e **57×**
   o teto, com o sinal trocado.
4. **O teto que ninguém tinha colocado na conta antes desta nota: as vagas.**
   `max_concurrent_positions = 5` com o horizonte de 4 h da família (`meta.horizon_s = 14400`) limita
   a carteira a **30 entradas por dia, no máximo, não importa quantos sinais existam**. Invertendo a
   meta contra esse teto (participação 1 %, `d_stop` mediano de 2,114 %): R$ 9.000/dia com
   R̄ hipotético = +0,05 pede 1 R = R$ 6.000 e R$ 2,84 milhões de patrimônio (0 dos 16 mercados
   comportam o minuto); com R̄ = +0,20 (cenário generoso), 1 R = R$ 1.500, notional de 13.858 USDT,
   minuto de **1,39 milhão de USDT** (só BTC e ETH têm) e **R$ 709 mil de patrimônio**. Nenhuma linha
   da inversão existe com R̄ ≤ 0 — com expectancy negativa não há tamanho positivo que resolva, só
   prejuízo maior.
5. **Subir a participação de 1 % para 2 % ou 5 % não resolve, e piora o esperado.** Quintuplicar a
   participação multiplica o teto por só 1,87 (os cinco mercados fundos já limitam pelo patrimônio,
   não pela participação); com expectancy negativa, tamanho maior é prejuízo maior (−R$ 310,58/dia →
   −R$ 434,76/dia a 5 %). Quadruplicar o capital com participação 1 % multiplica o teto por 1,78 —
   mesmo mecanismo da T3.60, agora nomeado (só os cinco mercados `asset_exposure` escalam com
   capital).
6. **O modelo de impacto raiz-quadrada (`k·√(notional/ADV)`) entra como sensibilidade rotulada, não
   como custo.** Nos tamanhos que os limites de hoje autorizam (118–1.953 USDT) o impacto fica em
   0,4–5 bps com `k=0,3` — não é o que impede o Lab de ganhar. Ele morde só no tamanho que a **meta**
   exigiria (13.858 USDT), e só nos mercados finos — nos dois que comportam o minuto necessário
   (BTC, ETH) o impacto continua em 3–4 bps.
7. **Um achado de risco lateral, fora do escopo original da nota:** o volume de 24 h que a D-P19
   soma das velas de 1 min diverge até 7× de `markets.volume_24h_usd` (a coluna do ticker) em alguns
   pares (PROM: 106 M contra 14,4 M). Abriu a T3.86, que corrigiu o check de liquidez do Risk Engine
   para somar velas em vez de ler a coluna (`RISK_ENGINE.md` v2.5).

## Onde foi mostrado

VPS de produção (`hunter-vps`), consultas somente leitura dentro de transações `repeatable read read
only`, cortes entre 05:05 e 05:19 BRT de 2026-09-11. 30 dias de volume por perpétuo (43.199 minutos),
4 dias por SPOT (as velas começam em 07/09; SAHARA em 10/09), 3 dias de coorte prospectiva da família
`mean_reversion` (08–10/09 BRT, 191 apostas únicas no total, 22 dentro dos 16 mercados executáveis).
Câmbio USDT/BRL = 5,1198, observado 05:05:35 BRT.

## Como mediríamos aqui (já sabemos o quê; falta ampliar a janela)

`infra/scripts/sql/research/2026-09-11-dp19-q0{0..5}-*.sql` (catálogo, volume por minuto, stop por
mercado, apostas por dia, CSV consolidado, apostas por hora). Reler com mais dias de coorte
prospectiva (hoje só 3) e com o SPOT cobrindo mais de 4 dias reduziria os dois maiores CONCERNs desta
nota — nenhum dos dois é veredito sobre a estratégia, é limite da janela observável hoje.

## Hipótese testável no Lab

Não é candidata de estratégia; é aritmética de dinheiro sobre limites e giro medidos. O que a nota
responde: quanto do R medido pela família vira dinheiro, por mercado e por hora, com os limites de
risco de hoje — e o que precisaria mudar (capital, universo, expectancy) para a meta caber.

## Por que pode falhar

- **3 dias de coorte, 22 apostas nos 16 mercados executáveis** — 8 dos 16 herdam o `d_stop` da
  família e 9 herdam o R̄ (nunca tiveram uma aposta própria); se a família passar a entrar em
  BTC/ETH/SOL, os números desses mercados mudam, e são justamente os que mais dinheiro comportam.
- **O SPOT tem 4 dias de série contra 30 do perpétuo** — a sazonalidade semanal não está lá; os
  números SPOT são ordem de grandeza, não distribuição.
- **Três tetos do motor ficaram de fora da conta** (`aggregate_risk`, `book_depth`, `beta_exposure`)
  — os três só **reduzem** tamanho, então todo número desta nota é teto superior, nunca subestimado.
- **`k` do impacto raiz-quadrada não é medido por nós** — entra só como coluna rotulada.
- **As 30 entradas/dia supõem o horizonte declarado da família (4 h), não o tempo em posição
  medido** — se a família sair antes (stop rápido) o giro real pode ser maior.
- **Dois volumes de 24 h convivem** (item 7 acima) — o teto de liquidez usa um, esta nota usava o
  outro antes da T3.86; reportar os dois, nunca escolher em silêncio.

## Segunda opinião (Astra)

Não registrada na nota de origem além da correção de linguagem já incorporada acima ("cenário, não
impossibilidade estrutural" — ganhos > 1 R existem; as 30 entradas/dia supõem o horizonte, não o
tempo em posição medido). Fica como lacuna declarada para o resto do raciocínio.

## Relacionados

[[KB-0069-capacidade-e-impacto-o-teto-que-o-livro-impoe]] ·
[[KB-0088-o-teto-de-participacao-nos-motores-de-backtest]] ·
[[06-DECISIONS/2026-09-10-universo-de-pesquisa-90-dias]] · [[Diario/2026-09-11]] ·
[[00-INBOX/Hipoteses-do-plantao|Hipoteses do plantao]] · `docs/RISK_ENGINE.md` §4 (sizing e `CAP_ORDER`)

## Fontes

`.claude/state/notes-D-P19.md` · `.claude/state/proposta-carteira-2026-09-09.md` (seção "D-P19: a
meta em dinheiro") · `.claude/state/notes-T3.60.md` (o 1 R = R$ 34,48 que esta nota estende)
