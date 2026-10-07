---
tags: [knowledge, cripto, custo, lab, mean-reversion, spread, binance, instrumento, medicao, h-036]
tema: "instrumento de custo: quanto custaria de verdade uma ida-e-volta na Binance USDⓈ-M nos instantes em que o Lab entra e sai — spread cotado do market_snapshots (1/min, bookTicker) na entrada e na saída + taxa pública; na v14 exposta o custo efetivo é 10,4–11,6 bp contra k* 16,1 bp, mas a decisão depende do bruto, não do custo"
fonte: "h036 (`.claude/state/h036/`): extração somente-leitura da VPS em 2026-10-07 (`q_cost.sql` → `cache/cost.csv`, sha256 `61a8b245…`, só os 3 969 signal_ids já expostos no lab-cost-sweep), inventário cego (`q_survey.sql` → `survey.txt`), instrumento `cost_instrument.py` (testes), medição `measure.py` → `measure.txt`, ensaio do pipeline `ensaio.txt`; manifesto `manifest.txt`"
fonte_url: —
lido_em: 2026-10-07
evidencia: "medição própria, descritiva, sobre a coorte EXPOSTA (desfechos já lidos pela KB-0192); spread de 100 % das pernas da v14 lido no minuto exato; taxas da tabela pública (suposição VIP 0); impacto, deslizamento do stop e latência não medidos"
hipotese_testavel: sim
astra: "duas rodadas na revisão do pré-registro H-036 que usa este instrumento: primário trocado para todo a mercado, 'B estrito' rebaixado a sensibilidade condicionada, 15,7 bp fora da regra de decisão, entrada passiva 'não demonstrada nesta aproximação' (não refutada), export só de spread"
status: vivo
owner: quant-engineer
updated: 2026-10-07
confiança: "?"
tipo: pesquisa
hipotese: H-036
variavel: "custo de ida-e-volta medido por trade (bp e R do Lab): taxa taker/maker + meio spread cotado no minuto da entrada e da saída"
populacao: "desfechos terminais long, Binance perpétuo, coorte prospectiva EXPOSTA (até 2026-10-07 06:07Z): mean_reversion v1–v14 e momentum v3; principal mean_reversion v14 (213 trades, 25 dias, 53 mercados)"
efeito: "v14: custo efetivo 11,57 bp todo a mercado, 10,40 bp com alvo em repouso, 15,65 bp no estresse; R médio ao custo medido +0,023 R (todo a mercado)"
ic: "v14 todo a mercado: R médio IC dia [−0,151; +0,225], IC mercado [−0,117; +0,133]; margem k* − custo +4,5 bp [−30,0; +41,8]"
veredito: —
proximo_passo: "H-036 (coorte futura da v14 a este custo; Fila de Hipoteses) e a proposta de coleta mínima abaixo para medir impacto — decisão do Everton"
classe_de_perda: —
mercado: cripto
---

# KB-0193 — O custo Binance medido nos instantes do Lab

> **Descritivo, sobre a coorte EXPOSTA.** Os desfechos aqui são os mesmos que a
> [[KB-0192-o-custo-do-lab-explica-a-perda-mas-nao-o-sinal]] já leu: nada desta nota é evidência de vantagem. O que
> ela entrega é o **instrumento** — e o instrumento é o que a [[Fila de Hipoteses#H-036 — `mean_reversion v14` em coorte futura, ao custo Binance medido (a v14 tem vantagem fora da amostra?)|H-036]]
> usa na coorte futura.

## O que afirma

1. **O livro que temos é o topo, uma vez por minuto, por 30–60 dias.** `market_snapshots` guarda, por mercado e
   minuto, `bid`, `ask` e `spread_pct` do último `bookTicker` lido do Redis na virada do minuto (anulados se o ticker
   tem mais de 10 s), em partições mensais podadas 30 dias depois da borda superior: na VPS em 07/10, 8 632 635 linhas
   de 2026-09-05 22:42Z a hoje, 481 mercados, 1 321 MB em setembro. **Não** são persistidos: as quantidades do topo
   (`bid_qty`/`ask_qty`), a profundidade (`depth20`, só no Redis com TTL de 10 s) e os trades brutos
   ([[Market Collector]]; `docs/DATABASE.md` §4). Velas 1 m retêm 90 dias.
2. **Nos instantes da v14 o spread cotado é pequeno.** Entrada: p50 **1,31 bp**, p90 4,00, p99 8,41; saída: p50 1,23,
   p90 4,03, p99 9,27; nos stops o p90 sobe a 4,70. Mercados de preço baixo ficam presos a um passo de preço (ex.:
   0,0000100 sobre 0,031 = 3,2 bp). O spread entra pela metade em cada perna.
3. **O custo efetivo medido (régua `Σ h·k / Σ h`) fica abaixo do k* da v14, mas a margem é ruído.**

| política (v14, 213 trades) | custo efetivo bp | custo médio R | margem k* − custo bp [IC dia] | R médio [IC dia] |
|---|---|---|---|---|
| custo assumido do Lab (10 bp/perna) | 20,00 | 0,103 | −3,9 [−38,4; +33,0] | −0,020 [−0,193; +0,177] |
| só taxa taker | 10,00 | 0,051 | +6,1 | +0,031 |
| **todo a mercado (taker + meio spread medido)** — primário da H-036 | **11,57** | 0,060 | **+4,5** [−30,0; +41,8] | **+0,023** [−0,151; +0,225] |
| alvo como limite em repouso (maker só se atravessa o passo) | 10,40 | 0,054 | +5,7 | +0,029 |
| estresse (pior spread de saída, +2 bp/perna de impacto não medido) | 15,65 | 0,081 | +0,5 | +0,002 |

   O k* da v14 é **+16,1 bp [−18,4; +53,0]**: o IC do ponto de equilíbrio tem ~70 bp de largura, o custo medido ~1 bp
   de incerteza. **A decisão sobre a v14 depende do bruto, não do custo.** Na família `mean_reversion` (2 253 trades
   com entradas repetidas) o todo a mercado fica em 11,69 bp e R −0,006; na `momentum v3`, 11,61 bp e **−0,145 R**
   [−0,188; −0,096] — o custo real não salva a `momentum` (confirma a KB-0192).
4. **A entrada passiva não foi demonstrada nesta aproximação** (não refutada). Uma compra limite no bid do minuto
   "executa" (a mínima atravessa o bid) em 85 % dos sinais da v14 em 1 min, e a perna custa a taxa maker (a abertura
   estava no bid: melhora de preço mediana 0). Mas os não executados são os que ganham: bruto **+0,341** contra
   **+0,037** dos executados; por sinal, +0,006 R contra +0,029 do alvo em repouso. Limites: OHLC não ordena alvo e
   preenchimento na mesma vela, o bruto dos executados é o do trade que entrou na abertura, e o snapshot é o da virada
   do minuto (Astra, rodada 1, must-fix 7). Leitura correta: **seleção adversa forte nesta aproximação**, não prova de
   que maker não paga.
5. **Concentração.** Na coorte exposta, sem o maior mercado (UNIUSDT) o R médio todo a mercado da v14 vai de +0,023 a
   **−0,004** (`ensaio.txt`). Toda consulta da H-036 publica esse número.

## Onde foi mostrado

`BEGIN READ ONLY` com `default_transaction_read_only=on` (`q.sh`). Insumos só dos signal_ids já expostos
(`gen_q_cost.py` lê a lista do `lab-cost-sweep/cache/out.csv.gz`): spread no minuto `entry_ts` (o Lab entra na
abertura dessa vela, `walker.py`), em ±1 min, no minuto `exit_bar_open` e no seguinte; velas 1 m da entrada. Unidade
de risco `U = entry_c − stop` (a do Lab, `sweep.py`); custo por perna sobre o próprio preço; `cost_r = (c_in·O +
c_out·B)/U`. Taxas: tabela pública da Binance USDⓈ-M, VIP 0 sem BNB — **taker 5 bp, maker 2 bp por perna**
(suposição; nenhuma conta foi lida). Testes: `test_cost_instrument.py` (10). O ensaio do pipeline da H-036
(`look.py`, export só de spread) reproduz o mesmo +0,0234 R por outro caminho.

## Por que pode falhar (e o que não concluir)

- **Spread cotado não é custo pago.** Falta o impacto além do topo (não guardamos quantidades nem profundidade), o
  deslizamento do stop-mercado dentro do minuto e a latência entre a abertura e a ordem; o "estresse" põe 2 bp por perna
  de impacto como **suposição**. A abertura do Lab é um preço de negócio, não o mid: em média o meio spread é a
  aproximação certa, trade a trade não.
- **Amostra da virada do minuto.** O `bookTicker` é por evento; o snapshot pega o último valor, não o spread médio do
  minuto, e os campos são anulados com o ticker velho (há minutos sem linha: a mediana de 7 d de um mercado tinha
  8 320 de 10 080 snapshots).
- **Reprecificação condicionada.** A admissão do Lab depende dos 6 bp assumidos; outro custo admitiria outras
  entradas. O R reprecificado não é contrafactual de execução.
- **Retenção.** O `market_snapshots` some em 30–60 dias: a H-036 só funciona com o export cego semanal (só spread) e o
  export complementar obrigatório da semana de cada consulta. Spread ausente: minuto → ±1 min → mediana de 7 d com
  ≥ 50 % da janela → p90 das pernas medidas; o minuto seguinte à saída (estresse): +1 → +2 min → p90 (emenda 2).

## Proposta de coleta mínima (para `exchange-integration-specialist` e `database-architect`; NÃO implementada)

O que falta para medir o custo **pago** e não só o cotado, em ordem de valor:

1. **Carimbo do livro no instante do sinal** (o `EXEC-B` da [[KB-0037-o-spread-assumido-contra-o-spread-medido]]):
   ao emitir, gravar no envelope do sinal `bid`, `ask`, `bid_qty`, `ask_qty` e o nocional do `depth20` a 10 e a 25 bp
   de cada lado, com o próprio `ts`. Custo de disco desprezível (dezenas de sinais por dia); responde o impacto na
   entrada.
2. **Quantidades e profundidade no snapshot de minuto:** seis colunas em `market_snapshots` (`bid_qty`, `ask_qty`,
   profundidade a 10/25 bp por lado) lidas do `depth20` do Redis na mesma virada. Ordem de grandeza, **estimada**, não
   medida (1 321 MB em setembro sobre ~6,9 M linhas supondo ritmo uniforme das 8,63 M ⇒ ~190 B por linha; seis
   `NUMERIC` ≈ +60–70 B): **+30–40 %**, ~+0,5 GB/mês, ~0,5–0,9 GB em regime com a retenção de 30 d (a VPS tinha
   207 GB livres em 30/09, [[Diario/2026-09-30]]). Responde o impacto na saída para qualquer tamanho.
3. **Fita de trades só nos minutos de stop do Lab** (aggTrade do mercado no minuto da saída por stop): mede o
   deslizamento real do stop-mercado. Pequeno (dezenas de minutos por dia), mas exige gatilho no `strategy-worker`.
4. **Retenção:** não precisa crescer se o export semanal da H-036 rodar; estender o `market_snapshots` para 90 d custaria
   ~2,6–4 GB a mais.

Nada disto muda estratégia nem parâmetro; é decisão do Everton e precisa de revisão do `database-architect` (item 2).

## Relacionados

[[KB-0192-o-custo-do-lab-explica-a-perda-mas-nao-o-sinal]] (a régua `Σ h·k / Σ h` e o k*) ·
[[KB-0037-o-spread-assumido-contra-o-spread-medido]] (o spread cotado de 24 h e o `EXEC-B`) ·
[[KB-0149-o-que-a-mesa-real-ensinou]] (item 23 e §7) · [[KB-0172-perdas-da-spot-1]] (a v14 na Jupiter, outro custo) ·
[[KB-0171-custo-real-da-spot-1]] · [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] · [[Market Collector]] ·
[[Fila de Hipoteses]] · [[Mapa de Estrategias]] · [[06-DECISIONS/Revisoes-Astra/H-036-prereg|revisão da Astra]] ·
[[11-KNOWLEDGE/Index|Conhecimento]]
