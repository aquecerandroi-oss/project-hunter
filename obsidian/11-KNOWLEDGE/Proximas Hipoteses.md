---
tags: [knowledge, indice, hipoteses, moinho]
tipo: consolidado
mercado: meme
status: vivo
owner: sexta-feira
updated: 2026-09-28
---

# Próximas Hipóteses — como montar a próxima

Página de partida para quem vai escrever o próximo bloco em [[Fila de Hipoteses]]. Não mede nada
sozinha — junta o que já existe em três lugares (o que nunca foi olhado, o que ficou pela metade, o
que já morreu) para a próxima hipótese nascer informada, não repetida. Ver
[[Dicionario de Variaveis]] (toda variável, testada ou não), [[Mapa de Estrategias]]
(Vivas/Pistas/Cemitério, por Dataview) e `docs/RESEARCH.md` (o vocabulário de veredito e o moinho).

## (a) Variáveis nunca testadas

Copiado à mão da seção "O que nunca foi testado" de [[Dicionario de Variaveis]] — **não é
Dataview**: essa página lê uma tabela de variáveis dentro de uma nota só, sem frontmatter por linha,
que o Dataview não indexa. Se esta lista divergir da fonte, a fonte é [[Dicionario de Variaveis]];
atualize lá primeiro, depois aqui. Das 53 linhas do dicionário, **30 nunca foram testadas de forma
independente**; as oito abaixo (das dez "mais prontas" da fonte) ainda não viraram hipótese — as
outras duas já viraram (H-021, H-020) e saíram da lista.

Classe de perda é **candidata, não medida** — é só a hipótese de qual dos [[Perdas/Index|cinco
vazamentos da mesa de memes]] a variável poderia atacar, para orientar quem for escrever a
`variável`/`previsão` do próximo bloco. Cripto não tem classe de perda (o classificador de
`meme_daily_ficha_classify.py` é só da mesa de memes).

| variável | onde vive | mercado | classe de perda candidata (especulativo) |
|---|---|---|---|
| `distance_from_24h_high` / `_low` | `features/price.py:106` | cripto | não se aplica — bloqueada só por uma medição de redundância nunca feita ([[Strategy Backlog]] item 8) |
| `open_interest` **em nível** (não a variação) | `features/deriv.py:94` (mesmo bloqueio de `missing_input` de `funding_change_8h`, [[KB-0020-funding-change-8h-nunca-calcula]]) | cripto | não se aplica — item 14 do [[Strategy Backlog]], nunca rodado |
| `{buy,sell}_pressure_{Nm}` e `trade_velocity_{Nm}` | `features/micro.py:179,221` | cripto | não se aplica — disponibilidade operacional nunca medida desde que o bloqueio de `covered_until` caiu |
| `is_mayhem` | bloco `mayhem` em `meme_proposals.reasons` (T4.27, só quando `declares_mayhem`) | meme | `comprou_no_topo`? — mecânica do agente (SOL virtual da curva) é diferente da curva normal; nunca medido se excluir por padrão paga |
| `top_buyer_share` / `fill_seconds` | bloco `pedigree_e2b` em `meme_proposals.reasons` (T4.31, EXP-M9) | meme | `golpe_do_criador`? — concentração de um comprador único no preenchimento é parente da concentração que gera despejo em bloco (H-014); a família E2-b morreu como "seguir carteira" (R57/KB-0136), nunca como o **preenchimento** em si |
| `market_betas` (β vs. BTC) | tabela `market_betas` (pacote `beta_v1`) | cripto | não se aplica — tabela existe, **0 linhas na VPS**, nunca populada o suficiente para medir |
| `holders_rising` / `progress_rising` isolados | `meme_features_15s` | meme | `comprou_no_topo`? — hoje só medidos **dentro** de `equilibrio` (H-013, que morreu por 1 caso: 1 de 587 decisões com `equilibrio = verdadeiro`) |
| `liquidations` (notional) | tabela `liquidations` (8 421 linhas, 197 mercados) | cripto | não se aplica — defeito de semântica (`q×p` em vez do executado) nunca corrigido, nem a série testada |

## (b) Pistas em aberto — não confirmadas ou limitadas por dado, com próximo passo

Notas com veredito `nao_confirma` ou `limite_de_dado` **têm** algo escrito para reabrir (medida
nova, coorte nova, ou já virou outra hipótese) — diferente do Cemitério em (c), que é para não
repetir.

```dataview
TABLE hipotese AS "hipótese", veredito AS "veredito", proximo_passo AS "próximo passo"
FROM "11-KNOWLEDGE" OR "03-TRADING/Meme/Perdas"
WHERE veredito = "nao_confirma" OR veredito = "limite_de_dado"
SORT hipotese ASC
```

A consulta só alcança hipóteses com nota `KB-00xx` dedicada (frontmatter `hipotese`/`veredito`/
`proximo_passo`) — seis hoje: H-009 (KB-0152), H-010 (KB-0153), H-013 (KB-0155), H-014 (KB-0156),
H-020 (KB-0160), H-021 (KB-0161). H-017 e H-018 não têm KB própria (a nota que as cita,
[[KB-0159-a-desaceleracao-nao-avisa-o-topo]]/[[KB-0158-recompra-sem-amostra-e-bundle-sem-filtro]],
tem `hipotese` apontando para a irmã que fechou primeiro) e as hipóteses de cripto (H-003 a H-008)
nunca tiveram KB própria — só relatório em `.claude/state/`. A tabela estática abaixo cobre
**H-001 a H-022** por isso; se divergir da consulta, a nota é a fonte (nunca esta tabela) e o
`veredito`/`proximo_passo` dela é o que se corrige.

| hipótese | veredito | próximo passo |
|---|---|---|
| [[Fila de Hipoteses#H-003 — Horizontes de 1 a 4 h no lado à vista\|H-003]] | nao_confirma | nenhum declarado; pista descritiva `P3_vol_surge` (h=120): IC de cluster estreito, mas cai na permutação (p=0,1478) — [[Mapa de Estrategias]] §Pistas |
| [[Fila de Hipoteses#H-004 — Percentil de sells/buys dentro da coorte viva\|H-004]] | nao_confirma | nenhum declarado; curva é **pico**, não planalto (1 de 7 limiares exclui zero) — reabrir só com medida ou população que não caia no mesmo pico |
| [[Fila de Hipoteses#H-005 — Piso de impulso recente (momentum_15m ≤ 2,0)\|H-005]] | nao_confirma (no desenho executado; população verbatim vazia) | pôr `momentum_15m` no envelope imutável do sinal e voltar em ~2 semanas |
| [[Fila de Hipoteses#H-006 — Desequilíbrio agressor na barra do sinal\|H-006]] | nao_confirma | nenhum declarado; o contraste pré-registado (tercil alto × tercil baixo) nunca foi refeito com IC — o moinho só sabe medir selecionados × resto |
| [[Fila de Hipoteses#H-008 — Portão de tendência de 4 h\|H-008]] | estudo inválido por censura (51,4 % > 20 %; fica `aberta`, não é um dos cinco rótulos) | pôr `return_4h` no envelope imutável do sinal (sem mudar a decisão) e voltar em ~2 semanas |
| [[Fila de Hipoteses#H-009 — Giro rápido na oscilação (comprar a queda, vender o repique, repetir)\|H-009]] | nao_confirma | já executado: o único pedaço com sinal virou H-011, que **refutou** ([[KB-0154-subir-o-alvo-nao-paga]]) — nada mais a reabrir aqui |
| [[Fila de Hipoteses#H-010 — Concentração do maior comprador (o dono que pode afundar)\|H-010]] | limite_de_dado | reabrir só com a fita WS da decisão persistida por troca (a T4.89 já resolveu isso) e pré-registrar a variável de **estoque** de tokens |
| [[Fila de Hipoteses#H-013 — Moeda em equilíbrio, não em subida (fluxo fraco + vendas ≈ compras + curva rasa)\|H-013]] | limite_de_dado | reabrir com coorte prospectiva do `operator/5` (teto 1,0, série WS) julgando com 20 equilíbrios — meses ao ritmo de 23/09 |
| [[Fila de Hipoteses#H-014 — Rede coordenada de compradores (o golpe em um bloco só)\|H-014]] | nao_confirma | já executado: a pista (SOL no slot de criação) virou H-015, que **refutou** ([[KB-0158-recompra-sem-amostra-e-bundle-sem-filtro]]) — nada mais a reabrir aqui |
| [[Fila de Hipoteses#H-017 — Recuo pequeno como melhora de preço (coorte nova, braço de papel)\|H-017]] | limite_de_dado (R79; braço `recuo_v1/1` continua rodando em papel) | ETA ~29 pares/dia → ~29–30/09, só com a mesa real ligada e aceitando |
| [[Fila de Hipoteses#H-018 — Recompra do mesmo mint logo depois de um ganho\|H-018]] | limite_de_dado | ETA para 20 recompras reais: 4–9 dias ao ritmo de 25/09 |
| [[Fila de Hipoteses#H-020 — Identidade social reciclada (o mesmo X/Twitter em várias moedas)\|H-020]] | nao_confirma | reparar a coleta do link social (parada desde 25/09 17:13:16Z) e capturá-lo na criação, com instante próprio; só então coorte nova pré-registrada |
| [[Fila de Hipoteses#H-021 — Estrutura do gráfico na hora da compra (distância do suporte, fundos mais altos, rompimento)\|H-021]] | limite_de_dado (estrutural) | gravar a estrutura do preço **marginal** na fita da decisão; já virou [[Fila de Hipoteses#H-022 — Estrutura do gráfico em moedas maduras (15–120 min, ainda na curva)\|H-022]] (em curso, [[EXP-M26-grafico-em-moedas-maduras]]) |

Fora da tabela: H-001 e H-002 estão `em_curso` (amostra insuficiente ainda, sem veredito — ver
[[Mapa de Estrategias]] §Vivas); H-022 está `aberta`/em construção, ainda sem veredito.

### Pistas novas do R83 (28/09/2026) — só em coorte nova

| pista | número (exploratório) | por que ainda não vale | próximo passo |
|---|---|---|---|
| **Longe da mínima de 24 h** nos sinais de continuação do Lab de cripto | +0,207 R [+0,121, +0,284], Holm 0,0004, patamar nos 7 cortes ([[KB-0163-perto-da-maxima-de-24h-nao-separa-os-sinais-do-lab]]) | secundária de uma hipótese que não confirmou; anda com ATR% (ρ 0,77); o melhor tercil ainda perde −0,097 R | pré-registrar em coorte prospectiva, com ATR% controlado e a comparação contra "não operar" |
| **`mean_reversion v14`** (a da `spot/1`) | +0,228 R [−0,099, +0,597] no contraste da máxima, 183 sinais | amostra pequena, IC largo, só descritivo | seguir acumulando na `spot/1` (limite pequeno) até ter amostra para pré-registrar |

### Segunda frente — H-024 concluída (R84, 28/09/2026)

- **H-024 — momentum semanal de série temporal em cripto grande (à vista, só compra): `nao_confirma`.** D_ts +0,14
  p.p./sem [−0,50; +0,86] em 395 semanas; a secundária transversal D_cs (+0,35, Holm 0,04) é **pico** na grade 7/14/28 d
  e não vira pista ([[KB-0166-evitar-as-moedas-em-queda-nao-bate-a-cesta]]). **Não reabrir** com outro lookback, só
  pós-2022, outro N ou outro universo: seriam escolhas depois de ver. O que sobra de útil é **ferramenta**, não
  sinal: o painel diário de 750 pares USDT à vista com deslistados (`.claude/state/r84/cache/`, sobrevivência auditada
  contra 153 cópias históricas de cadastro) e o código de universo ponto-no-tempo (`.claude/state/r84/engine.py`) —
  qualquer hipótese semanal nova de cripto pode nascer sobre eles, pré-registrada, com poder declarado (dp de d_t
  medido aqui: 6,7 p.p./semana → só efeitos de ~1 p.p./semana têm 80 % de poder em ~400 semanas).

### Figuras do Everton — H-025 e H-026 concluídas (R85, 28/09/2026)

- **H-025 — primeira retração de 50–61,8 % no diário (top-20 à vista): `nao_confirma`.** D +0,69 p.p. por 10 d
  [−1,43; +2,95] contra as moedas do mesmo dia sem recuo; as faixas vizinhas de 45 % e 55 % deram negativo (pico, não
  patamar) e a faixa de Fibonacci não bate as vizinhas de forma confirmável; o alvo 1,618 com stop abaixo do fundo rende
  o mesmo que segurar 10 d (+0,009 p.p. nas mesmas entradas). **Não reabrir** com outro k, outra faixa, outro H ou outra
  amplitude: seriam escolhas depois de ver ([[KB-0169-fibonacci-e-lta-diaria-no-dado]]).
- **H-026 A — retorno na LTA diária: `refuta`** (−1,09 p.p. [−2,08; −0,02], negativo em todas as tolerâncias, períodos,
  horizontes e blocos). Não volta como compra; o mesmo repique já tinha perdido no 15 min ([[EXP-0016-trendline-breakout]]).
- **H-026 B — rompimento do topo depois do teste da LTA: `nao_confirma`**, pista descritiva (+1,09 p.p. [−0,76; +2,89],
  Holm 0,22; patamar e corte passam). Só volta em **coorte prospectiva** com H = 10 d (não 20) e contraste
  incremental contra um rompimento de topo **sem** LTA no mesmo dia; e, antes de qualquer ideia de `spot/1`, a taxa fixa
  real por perna em ficha de 0,05 SOL tem de ser medida.
- **Elliott:** sem hipótese — nenhuma operacionalização causal publicada que eu tenha conseguido ler
  ([[KB-0168-fibonacci-elliott-e-lta-diaria]]).

### Tendência diária — H-027 concluída (R86, 01/10/2026)

- **H-027 — razão à média de 20 dias como estado dos sinais de continuação do Lab: `nao_confirma` (análise retrospectiva pré-especificada).** Na `momentum` (874 unidades, 23 dias, 16 mercados) β −0,026 R por desvio [−0,083; +0,029] por dia e [−0,072; +0,014] por mercado: o tamanho previsto (+0,05) fica fora dos dois — **refuta o tamanho** pelo protocolo; os dois grupos perdem −0,19 R. A `volume_anomaly` ficou em limite de dado. Como afirmação geral fica só **não confirmada**: com efeito fixo de dia o IC superior chega a +0,058 e o grupo razão ≤ 0 é, na prática, a semana de 11–18/09 (13 datas). **Não reabrir** com outra janela (50/200 d), outro corte ou outras covariáveis nestes dados. A coorte futura da C1 não foi feita e **não é prioridade** só para repetir este filtro. A `mean_reversion v14` com razão ≤ 0 (16 unidades, +0,25 R, 6 no mesmo dia) não é pista; se virar ideia, é hipótese nova de reversão com população própria ([[KB-0170-tendencia-diaria-nao-separa-os-sinais-do-lab]]).

### Carry de funding — H-029 concluída (R87, 05/10/2026)

- **H-029 — carry de funding protegido (à vista + perpétuo vendido, top-20 Binance): `nao_confirma`** (A2 limite de dado). O A1 (entra com funding de 7 d ≥ 0,125 %, sai com ≤ 0) rendeu +5,3 a +5,9 % a.a. sobre o capital total, mas Holm 0,15–0,175, e quase tudo veio de 2020–2021; **desde 2023 recebeu +3,1 % a.a. de funding e ficou com +0,6 % líquido**; o sempre-ligado perdeu −4,4 % a.a. desde 2023 ([[KB-0181-carry-de-funding-no-dado]], [[KB-0180-carry-de-funding]]). **Não reabrir** com outro limiar, janela, bloco, universo ou só pós-2023 nestes dados. O que sobra de útil: o painel de perpétuos com deslistados (velas, marca e funding de 481 contratos, `.claude/state/r87/cache/`) e o motor de duas pernas com liquidação pela marca (`sim87.py`). Perpétuo real é proibido até a Fase 4: qualquer volta é **coorte prospectiva** pré-registrada (a partir de 2026-09-21, a primeira semana não usada aqui), papel/Lab, com família de tentativas = 2 — decisão do orquestrador depois do advogado e do defensor.

### Candidatas de análise gráfica (28/09/2026) — não registradas

Da leitura [[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]] (literatura aberta, nenhum preço nem desfecho
nosso consultado; revisão da Astra em [[06-DECISIONS/Revisoes-Astra/KB-analise-grafica|KB-analise-grafica]]). Na
ordem abaixo; **nenhuma é bloco da [[Fila de Hipoteses]]** — quem registra é o orquestrador, com MRE e refutação
declarados antes de qualquer desfecho. Nenhuma é variável esgotada por definição; o risco de repetir uma com outro
nome é empírico e tem de ser afastado no registro (regras 1 e 2 da Fila).

| # | candidata | variável | onde vive o dado | mercado / tempo | classe de perda | por que não é esgotada | portão antes de registrar |
|---|---|---|---|---|---|---|---|
| C1 | tendência diária como estado dos sinais de continuação do Lab | `razao_mm20d` = último fechamento diário UTC completo ÷ média dos 20 últimos − 1 (dias com os 1.440 min presentes; dia incompleto = indisponível; secundária: só o sinal) | reconstruída de `candles` 1 min `is_final` (não existe como feature; 20 dias > teto de contexto de 6.000 min do Lab) | perpétuos Binance no Lab, **por estratégia** (`momentum` 15 min, `volume_anomaly` 5 min); `spot/1` descritiva | — (cripto) | horizonte de 20 dias; as testadas são 15 min (H-005), 4 h (H-008, aberta) e 24 h (H-023) | teste incremental **conjunto** com `distance_from_24h_low` (pista do R83), ATR% e `return_4h`; coorte futura; grupo favorável lucrativo em nível — **rodada em 01/10 como [[Fila de Hipoteses#H-027 — Tendência diária (razão à média de 20 dias) como estado dos sinais de continuação do Lab de cripto\|H-027]] (retrospectiva): NÃO CONFIRMA; `momentum` refuta o tamanho; coorte futura não feita** ([[KB-0170-tendencia-diaria-nao-separa-os-sinais-do-lab]]) |
| C2 | fundos mais altos **sem** rompimento de 15 min | `higher_lows ∧ ¬breakout_15m` × `higher_lows ∧ breakout_15m` na 1.ª oportunidade de `grafico_ctrl_v1/1`, linha coberta | `meme_features_1m` (`lines.py` v1) + registro R1 `meme_mature_opportunities` do [[EXP-M26-grafico-em-moedas-maduras]] | memes de 15–120 min na curva, via de 1 min | `comprou_no_topo` | o bloco `line` nunca foi isolado; H-021 = limite de dado; H-022 testa só a conjunção | só depois do veredito da H-022, em coorte que não seja a dela; bloqueada se a H-022 fechar por instrumento; herda cobertura, controle de progresso e cláusula de `mcap_slope_15m` |
| C3 | geometria do nível antes do rompimento (exploratória) | `rejeicoes_nivel` (visitas distintas a ≤ 0,25·ATR do nível, sem fechar acima) e `barras_perto_nivel`, nas 20 barras de 15 min antes do rompimento da `momentum_v1`; 0,25 = convenção | reconstruída de `candles` 1 min; nível e ATR no envelope da `momentum_v1` | perpétuos Binance no Lab, 15 min | — (cripto) | `breakout_strength_20` mede quanto passou do nível, não a história dele | previsão bicaudal e extrapolada (não vem dos artigos); antes, rever a prontidão da `sweep_reclaim_v1` ([[EXP-0017-sweep-reclaim]]), que já existe para o mesmo mecanismo |

**Não recomendados agora** (detalhe na KB-0167): confirmação por volume do rompimento (três resultados nossos
contra e evidência externa fraca), distância à VWAP (nenhum estudo revisado achado), cruzamento de número redondo
(BTC sem padrão de retorno depois), canal diário como estratégia própria na `spot/1` (mesmo objeto da H-024) e o
momento intradiário de primeira/última janela (custo de equilíbrio publicado de 3–10 bps por operação).


### Rompimento do topo depois do teste da LTA diária (H-026 B) — coorte futura arquivada (01/10/2026)

Instrumento e rascunho de pré-registro prontos ([[H-028-forward-prereg]], `.claude/state/h026b-forward/`, congelado; 3 rodadas da Astra). Contagem cega do painel do R85: o contraste incremental honesto (B contra rompimento sem LTA no mesmo dia) teve **90 eventos em 7,56 anos (~12/ano)** — até a parada dura de 2030 esperam-se ~48 contra o piso de 150, ou seja, **LIMITE DE DADO** como desfecho esperado. **Decisão da Sexta-feira (pesquisa, sem dinheiro):** não montar a coorte em produção (tabelas + job) agora; o bloco não entra na Fila como hipótese aberta. Reabre só se aparecer um universo muito maior (ex.: todos os pares USDT líquidos) com poder calculado antes.

## (c) Cemitério — não repetir

Uma linha, o porquê. Lista completa e o número exato de cada uma: [[Mapa de Estrategias]] §Cemitério.
Regra da casa (Fila de Hipoteses.md, regra 2): **hipótese que morreu não volta com outro nome.**

| hipótese | veredito | por que não repetir |
|---|---|---|
| [[Fila de Hipoteses#H-007 — Teto de volume relativo (exaustão)\|H-007]] | refuta | teto em 12 não sustenta +0,10 R; quanto a +0,02 R, o resultado depende de ruído de Monte Carlo — não decide |
| [[Fila de Hipoteses#H-011 — Onde deve ficar o alvo (vender o primeiro repique e não voltar)\|H-011]] | refuta | melhor alvo (1,08×) é a **borda** da grade e o ganho concentra em 5 moedas, invertendo com a cobertura da fita |
| [[Fila de Hipoteses#H-012 — Tempo máximo curto ("o que não sobe logo não sobe mais")\|H-012]] | refuta | maior IC inferior −1,16 pp; a 30 s cortam-se 14 de 23 vitórias reais |
| [[Fila de Hipoteses#H-015 — Compra no slot de criação (o "bundle" do lançamento)\|H-015]] | refuta | teto no tercil alto mataria 36,5 % das vencedoras (limite 30 %) |
| [[Fila de Hipoteses#H-016 — Entrar no recuo, não no pico (esperar a primeira correção depois do sinal)\|H-016]] | refuta | as moedas que não recuam são as vencedoras; esperar recuo grande custa mais do que compra no topo |
| [[Fila de Hipoteses#H-019 — Fluxo desacelerando na hora da compra (o topo local visto pela fita de 10 s)\|H-019]] | refuta | piso no tercil baixo mataria 34,7 % das vencedoras; sinal saiu ao contrário da tese |
| 13 variáveis de decisão (R65) | nao_confirma (todas) | nenhuma sobrevive Benjamini-Hochberg; girar o botão de novo sem população/medida nova é proibido pela regra 1 da Fila |
| Sniper de lançamento | nao_confirma (descartada) | 18/18 células negativas, não era latência |
| Rajada de compradores | nao_confirma (descartada) | negativa em 54 células |
| Seguir carteira vencedora | nao_confirma (descartada) | não é gatilho |
| `momentum v2/v4/v6/v10`, `volume_anomaly v2`, `session_orb v1`, `trendline_breakout v1` (Shadow Lab) | aposentadas | negativas em toda coorte que tiveram (T3.56) |
| H-003 a H-006 (cripto) | nao_confirma | ver (b) — ignorância, não repetir sem envelope/medida nova |
| `return_4h > 0` como gate de tendência | descartada antes de testar | redundância lógica com a própria entrada |
| `orderbook_imbalance_20 ≥ 0` como filtro de book | descartada antes de testar | razão invariante a escala, não mede profundidade |
| Funding como filtro direcional de entrada | nunca entrou na fila | evidência direta aponta poder preditivo ~zero por ativo |
| `derivatives_v1` (reversão de funding) | morreu na pré-checagem | 5 liquidações negativas em 31 d × 4 mercados |

## (d) Como transformar isto numa hipótese

1. **Escolha uma linha de (a)**, ou uma pista de (b) com próximo passo declarado — nunca uma linha
   de (c) com o mesmo desenho (regra 2 da Fila).
2. **Insira o modelo Templater** — `obsidian/_templates/Nova hipotese.md` (`_templates/LEIA-ME.md`
   explica como) — no fim de [[Fila de Hipoteses]] e preencha os seis campos obrigatórios: `origem`,
   `variável`, `população`, `previsão`, `refutação`, `status`. O carregador
   (`infra.research.queue.load_queue()`) recusa a fila inteira se faltar um.
3. **Exporte a população** (SQL somente-leitura na VPS → CSV local, sem tocar a base nem a rede) e
   escreva o spec do moinho (`infra/research/`, `docs/RESEARCH.md`) — pré-registro antes de olhar
   qualquer resultado, do contrário `run_hypothesis` recusa (`PreRegistrationError`).
4. **Cole o veredito** na nota do estudo (`KB-00xx` nova ou existente, frontmatter completo —
   `hipotese`, `variavel`, `populacao`, `efeito`, `ic`, `veredito`, `proximo_passo`, `mercado`,
   `classe_de_perda` se for meme) e atualize o `status` do bloco na Fila. Vocabulário de veredito:
   `docs/RESEARCH.md`.
5. **Antes de qualquer mudança chegar à mesa** (parâmetro, ativação, braço de papel), a regra
   Obsidian-first (`.claude/rules/obsidian-first.md`) exige a nota citada em `--note`: sem ela as
   ferramentas auditadas (`meme_rule_set.py`, `activate_strategy_version.py`,
   `spot_desk_markets.py`) recusam aplicar.

## Relacionado

[[Dicionario de Variaveis]] · [[Mapa de Estrategias]] · [[Fila de Hipoteses]] · [[Ideias do Everton]] ·
[[Perdas/Index|Perdas]] · [[KB-0149-o-que-a-mesa-real-ensinou]] · [[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]] ·
[[KB-0168-fibonacci-elliott-e-lta-diaria]] · [[KB-0169-fibonacci-e-lta-diaria-no-dado]] ·
[[KB-0170-tendencia-diaria-nao-separa-os-sinais-do-lab]] · `docs/RESEARCH.md` · `.claude/rules/obsidian-first.md`
