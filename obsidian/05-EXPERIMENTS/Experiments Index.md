---
tags: [experimentos, indice]
updated: 2026-09-11
status: em-andamento
owner: sexta-feira
---

# Experiments Index

## Status honesto

**Quatro experimentos abertos: `EXP-0001` e `EXP-0002` (coortes prospectivas do Shadow Lab, desde
2026-09-06), `EXP-0004` (replay de políticas de saída, 2026-09-06) e `EXP-0003` (o instrumento de
baselines do M2, 2026-09-07).** Os dois primeiros: S0 (migração `0002_shadow_lab`), S1
(estratégias) e S2 (`strategy-worker` em modo sombra) foram entregues e provados
(`.claude/state/s2-proof.md`), as duas versões foram ativadas pelo script auditado e o worker está
no ar emitindo sinais sobre o mercado real da Binance. Continua valendo o que o Shadow Lab **não**
é: não há carteira, ordem, posição nem PnL de portfolio — todo número é hipotético, com custos
assumidos declarados, e todo sinal carrega `purpose = research_only`.

Na primeira avaliação datada (`as_of = 2026-09-06T02:55:00Z`) os dois experimentos estão
**inconclusivos** pelo limiar editorial: **57** outcomes avaliáveis no `EXP-0001` (48 na coorte v1 +
9 na v2) e **72** no `EXP-0002` (66 + 6), todos em **1** dia distinto, contra os 100 outcomes **E**
30 dias exigidos. E há um segundo motivo, achado nessa mesma leitura: **nenhum** dos 57 do
`EXP-0001` teve o horizonte de 4 h maturado — a população avaliável é inteiramente composta de
acompanhamentos que resolveram cedo.

**Segunda avaliação datada, 2026-09-06 à tarde — agora sobre a coorte da VPS**
(`as_of = 13:00:00Z`, `read_at = 13:26:35Z`). É **outra população, em outro banco**: a VPS tem uma só
versão ativada por estratégia (ativadas lá às 03:36 UTC, com `code_ref` de digest diferente do local
pelo motivo já registrado em [[Open Bugs]]), então esta leitura **não continua** a série local.

| Experimento | Coorte | Emitidos | Avaliáveis c/ `R_net` | Taxa de alvo | Expectancy (R) | PF | Dias | Result |
|---|---|---|---|---|---|---|---|---|
| `EXP-0001` momentum | v1 (VPS, active) | 208 | 91 | 0,5333 | **−0,2102** | 0,6084 | 1 | **inconclusivo** |
| `EXP-0002` volume | v1 (VPS, active) | 459 | 316 | 0,5000 | **−0,2304** | 0,6539 | 1 | **inconclusivo** |

Duas coisas mudaram de verdade nesta leitura. **Primeira: o horizonte maturou.** Na avaliação da
madrugada nenhum dos 57 acompanhamentos do momentum tinha as 4 h completas, e a expectancy aparecia
em +0,3053 R; com o gate cumprido ela é **−0,2102 R**. O alerta escrito naquela página estava certo —
os números de então descreviam "os que resolveram cedo". **Segunda: o `EXP-0002` passou dos 100
outcomes** (316) e continua `inconclusivo` assim mesmo, porque o limiar é 100 **E** 30 dias, e há
**1**. Trezentos e dezesseis outcomes de um único dia são 316 leituras do mesmo dia de mercado.

Abertas nas duas páginas as seções **"Hipóteses de falha"** — pesquisa datada e acrescentada, que não
toca Hipótese nem Protocolo e não ativa nada. A primeira rodada cobre a invalidação (35% dos
acompanhamentos resolvidos, nenhum lucrativo, e um contrafactual que o dado **não** decide) e o
funding não apurável (69 de 73 casos são falha de identificação temporal, com efeito medido de no
máximo 0,028 R). Revisão em [[S4-hipoteses]].

**Terceiro experimento aberto em 2026-09-06 à noite: [[EXP-0004-politicas-de-saida]]**, e ele é de
outro tipo. Não é uma coorte nova coletando: é um **replay** das oito políticas de saída sobre as
**mesmas entradas** que o Lab já registrou (`as_of = 2026-09-06T20:55Z`, commit `2c6bb2d`), unindo
num bloco só o T-005 (invalidação), o L1 (alvo assimétrico) e o L2 (sem alvo / canal oposto) do
[[Registro de Tentativas]] — 7 contrastes com Holm a 5% e efeito mínimo declarado de 0,05 R. O
replay **não escreve nada** (transação `REPEATABLE READ, READ ONLY`) e **não cria coorte
`replay:<run_id>`**; a população é a mesma dos experimentos acima, lida no banco **local**. O portão
de reprodução passou (**trajetória 1,0000 em 339 linhas comparáveis**, com 14 divergências isoladas
na liquidação), e o resultado é **inconclusivo por `B = 1`**: todas as entradas caem num único dia
UTC, então IC é indisponível (`single_block`) e `p = 1` sai **por construção** — ausência de
replicação, não evidência de equivalência. Os sete contrastes daquela página são **exploratórios**.

**Quarto experimento aberto em 2026-09-07: [[EXP-0003-baselines-v1]]**, e ele é de um terceiro
tipo. Não é coorte prospectiva nem replay: mede um **instrumento** — o arquivo de baselines por
(mercado, feature, hora UTC) do M2 — e o que ele destrava rio abaixo. Por isso as métricas em R e
de carteira do [[_TEMPLATE-EXP|template]] estão marcadas **não aplicáveis** ali, em vez de
preenchidas com número sem significado. Primeira avaliação (`as_of = 2026-09-07T03:30Z`,
`read_at = 03:24:49Z`, população da VPS): **4.944 buckets utilizáveis de 88.746 revisões vigentes
(5,57 %)**, **12 de 27** features com ao menos um bucket utilizável, **29 de 200** mercados no
melhor caso. `Result` **inconclusivo** — 1 dia distinto de série viva contra os 3 do portão. Duas
coisas já decididas por aritmética e não por opinião: as 15 features mudas são exatamente as de
tape, livro, derivativos e `_live` (o `historical_source_unavailable` da T2.3, confirmado em
produção), e com 3 componentes disponíveis somando peso 0,25 **o score não passa de 25,00 contra a
linha de 40 do WATCHING** — nenhum mercado pode ser HOT hoje. Detalhe e parecer do milestone em
`docs/reports/M2.md`.

**Acréscimo de 2026-09-08 — são seis, não quatro.** Os parágrafos acima ficam como estão (são
datados); o que mudou é a contagem. Entraram **[[EXP-0005-momentum-paper]]** (a linha
`purpose = paper` do `momentum`, decisão delegada D10 — mede a mesma decisão pela carteira, e na
primeira avaliação a carteira estava intocada porque `ENABLE_PAPER_AUTONOMY=false`) e
**[[EXP-0006-momentum-piso-de-custo]]** (`momentum v4`, a primeira **variante de parâmetro** do Lab:
mesmo `code_ref` do pai, um único valor diferente). O `EXP-0006` traz um tipo de leitura que ainda
não existia aqui — **replay de abertura da própria variante**, sobre a mesma janela que gerou a
hipótese —, e por isso ele nasce com dois motivos de `inconclusivo` escritos lado a lado: o limiar
editorial e a construção. O achado que sobrevive aos dois é operacional: **o piso corta 86% das
decisões**.

**Acréscimo de 2026-09-08 (noite, T3.32b) — são onze, e cinco entraram no mesmo dia.** Os parágrafos
acima ficam como estão. O que mudou:

- **[[EXP-0007-momentum-invalidacao-bracos-INV]] nasceu já avaliado**, e é o primeiro experimento do
  Lab que **fecha uma linha do backlog em vez de abrir uma**: os braços `INV-B/C/E` sobre as mesmas
  entradas congeladas ficam entre −0,070 R e +0,032 R em quatro populações, nenhum passa o efeito
  mínimo de 0,05 R e o **sinal muda** entre elas. A invalidação **adianta** a perda, não a cria — e a
  versão de código `momentum_v2` com `invalidation_mode` **não se justifica**. O maior contraste do
  conjunto (`EXIT-NOTGT`, +0,163 R no replay) **troca de sinal** nas populações prospectivas
  (−0,226 R e −0,102 R): a [[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] em estado
  puro.
- **[[EXP-0008-breakout-compressao-de-volatilidade]], [[EXP-0009-mean-reversion-pullback-em-tendencia]],
  [[EXP-0010-session-orb-faixa-de-abertura]] e [[EXP-0011-derivatives-reversao-de-funding]] entraram
  `nao-iniciado`** — Hipótese e Protocolo congelados, **nenhuma linha de código escrita, nenhuma
  versão ativada, nenhuma coorte aberta**. Quatro de uma vez são **quatro tentativas**
  ([[Registro de Tentativas]], T-035 a T-038), e o veredito de cada uma será lido sabendo que houve
  quatro.
- **As quatro nasceram de uma pergunta, não de quatro ideias soltas.** A
  [[KB-0076-por-que-perdemos-2026-09-08]] mostrou que a expectancy **bruta** de tudo que o Lab mede
  hoje fica entre −0,04 e +0,09 R (cara ou coroa) enquanto o custo assumido vale 0,11 a 0,62 R por
  operação. Nenhuma política de saída conserta isso; a única saída é uma **família de entrada** com
  bruto acima do custo típico. As quatro páginas são quatro tentativas de responder isso, com
  geometria escolhida por aritmética de custo em vez de gosto.
- **A escolha das quatro teve divergência entre os dois motores**, e ela está registrada em
  [[Dialogos/2026-09-08-quatro-estrategias]]: a Astra queria spot–perp e força relativa transversal
  no lugar de `session_orb` e `derivatives`; as duas dela ficaram no [[Strategy Backlog]] com o que
  cada uma exige (campo novo em `base.py` + `--supersede` das versões vivas; protocolo
  `evaluate_universe`).
- **O portão de desenho C1–C8 existe como método, não como seção do template** (tarefa T3.36; o
  método está em `.claude/skills/edge-strategy-reviewer/references/review_criteria.md`). As quatro
  páginas trazem a seção **"pendente"**, para que ninguém leia a ausência do veredito como aprovação.
  A **T3.33b está em voo** e já aplicou o portão ao rascunho da `EXP-0009`; o veredito entra na
  página quando aquela tarefa fechar, e não antes — arquivar número de rascunho em movimento é
  arquivar número que pode mudar.

**Acréscimo de 2026-09-08 (tarde, T3.33h) — o dia um das quatro, e o portão deixou de estar
pendente.** As linhas das tabelas abaixo foram atualizadas (este é um **índice**, não uma página de
experimento: as avaliações datadas, essas sim append-only, estão nas páginas). O que mudou:

- **duas foram ativadas e replayadas** (`breakout v1` às 16:23:39Z, `mean_reversion v1` às 16:32:33Z,
  31 dias × 4 mercados, coorte `replay:` própria por versão). A primeira fez **0 decisões** e a
  segunda **37**, com o primeiro resultado líquido positivo que este Lab mede — e **as duas saem
  `inconclusivo`**, uma por ausência de população e a outra pela régua de maturidade;
- **uma morreu antes do código**: a `derivatives v1` foi reprovada pela pré-checagem congelada
  (5 liquidações negativas em 31 d × 4 mercados) e **o módulo não foi escrito**. É o caso mais barato
  possível de uma candidata morrer, e é para isso que a pré-checagem existia;
- **o portão C1–C8 foi preenchido nas quatro**, com o veredito `REVISE` em todas (66,0 · 65,5 · 62,5 ·
  63,5) e as divergências declaradas em vez de consertadas. **Ele foi autoavaliação do
  `quant-engineer`**, não revisão viva da Astra — está escrito em cada página, porque ausência de
  revisor externo não é aprovação. A tarefa T3.36 (a seção no [[_TEMPLATE-EXP]]) continua aberta;
- **o portão errou o essencial na `derivatives`**: C3 devolveu "amostra adequada" (80) por uma fórmula
  de barra diária em ações, e a consulta ao dado mostrou o oposto. O portão pontua a **forma** do
  rascunho e **não substitui a consulta**.

**Acréscimo de 2026-09-08 (noite, T3.41) — o dia fecha com seis ativações, três aposentadorias e dois
experimentos novos.** As linhas das tabelas abaixo foram atualizadas de novo (este é um **índice**;
as avaliações datadas, essas sim append-only, estão nas páginas e nenhuma foi tocada). O que mudou:

- **`EXP-0010` deixou de ser `nao-iniciado`.** A `session_orb v1` foi ativada às **19:42:56Z** e
  replayada: 20 decisões, 9 dias, líquida −0,1928 R. **K1 não disparou por uma decisão**, e a única
  condição de K3 que depende do mercado (bruta negativa) **já está cumprida**. O achado da página é
  duplo e vale ser lido inteiro: a amostra se dividiu 30/35/35 % entre as três sessões — a regra dos
  70 % **não** dispara, o que refuta o medo de "isto é só uma hora específica" —, e **as três
  perderam com expectancy indistinguível**, o que esvazia a hipótese pelo outro critério da mesma
  página. A passada de estresse devolveu **`amostra_insuficiente`** (20 de 30) e é descritiva;
- **`EXP-0008` foi testado até o fim e as duas versões estão aposentadas.** A `v2` por parâmetro
  tornou a hipótese da compressão **testável** (a `v1` não deixava) e a resposta foi bruta ≈ 0 com
  pedágio de 0,0912 R — líquida negativa **por custo**;
- **`EXP-0009` ganhou a primeira passada de estresse do Lab**, e ela **qualifica** o único resultado
  positivo que este Lab produziu: `frágil a custos`, com o IC do Δ inteiramente negativo;
- **`EXP-0012` e `EXP-0013` são novos** — as duas variantes de `momentum` que o [[Strategy Backlog]]
  listava desde a T3.32 saíram do papel. A do teto de pedágio **morreu no dia** (0 decisões, aposentada
  19:39:00Z); a do alvo de 3 ATR **continua viva** em pesquisa, com janela prospectiva até ~2026-10-08;
- **aposentar deixou de ser impossível.** A T3.39 abriu a via auditada (`--deprecate`), que faltava
  desde a T3.33f: `--supersede` recusa, de propósito, uma sucessora que compartilha o mesmo
  `code_ref` — exatamente o caso de toda variante por parâmetro.

**Acréscimo de 2026-09-08 (arquivamento da Sexta-feira, T3.34c–T3.47c) — dezenove experimentos, quatro
famílias de estratégia novas.** Os parágrafos acima ficam como estão. O que mudou:

- **[[EXP-0016-trendline-breakout]]** (`trendline_breakout v1`, família nova) — ativada
  **22:29:52Z** e replayada 31 d × 4 mercados: 47 decisões, bruta +0,1045 R, líquida **−0,0382 R**,
  PF 0,922, 14 dias distintos. **A regra dos 60 % dispara**: 89,4 % das decisões são **repique em
  suporte ascendente**, não o rompimento que deu nome ao experimento (5 rompimentos em 31 dias,
  perdeu os 5). Veredito: **manter em pesquisa, com a hipótese REENUNCIADA** como repique — não
  como rompimento. O contraste pareado da invalidação (braço `INV-B`, método do [[EXP-0007-momentum-invalidacao-bracos-INV]])
  repete o achado da [[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]]: Δ +0,0922 R com IC
  contendo zero — a invalidação estrutural **não** corta a cauda esquerda melhor que a de
  `momentum_v1`, ela adianta a perda;
- **[[EXP-0017-sweep-reclaim]]** (`sweep_reclaim v1`, família nova) — pré-checagem por margem
  estreita (57 eventos em 31 d × 4 mercados, 17 dias distintos, cobertura 99,5 %; portão C1–C8 =
  70,5 `REVISE`, C8 `fail` por desenho declarado — sem invalidação). O módulo **foi implementado**
  no mesmo dia (commit `a9bacc6`, T3.45b, 46 testes), mas **nenhuma coorte foi ativada e nenhum
  replay rodou** até o fechamento do dia: `sweep_reclaim: implemented, replay pending`;
- **[[EXP-0018-stop-largo]]** (seis braços: `momentum v7`/`v8`, `mean_reversion v4`/`v5`/`v6`/`v7`) —
  a identidade do pedágio se confirma nos seis (o custo cai pelo fator pedido, ÷1,48 a ÷2,08), mas
  **os seis intervalos de confiança contêm zero** e só **12 %** da economia de pedágio sobrevive no
  braço com população julgável (`momentum v8`). Com `risk_per_trade_pct` fixo, dobrar o stop **corta
  a posição pela metade** — o eixo é alavanca de variância, não de sinal. Recomendações por braço:
  descartar `momentum v7` e `mean_reversion v4`/`v5`; manter em pesquisa `momentum v8` e
  `mean_reversion v6`/`v7`;
- **[[EXP-0019-piso-atr]]** (`mean_reversion v8`, mais a irmã por identidade `v1`) — baixar o piso de
  ATR% de volta a 0,006 (pagando o pedágio com o stop largo do [[EXP-0018-stop-largo]]) dobra a
  população (15 → 33 decisões) e **destrói a expectância** (+0,2861 → +0,0855 R); os quatro dias que
  só existem com o piso baixo são os quatro negativos. **Veredito formal `negativo`** no corpo do
  EXP — corrigido para `inconclusivo` só no campo de vocabulário controlado do frontmatter (33/37
  avaliáveis < 100, 11 dias < 30; ver a nota na própria página). Fecham-se três eixos de geometria
  medidos no dia (alvo, stop, piso) e nenhum fabricou vantagem: falta vantagem na entrada;
- **Aposentadas pela via auditada em 2026-09-08T23:34:42Z–23:34:59Z:** `momentum v7` (sucessora
  `momentum v8`), `mean_reversion v4` e `mean_reversion v5` (sem sucessora) — roster de 16 para 14
  versões vivas. `--deprecate` passou a **acrescentar** ao `changelog` em vez de sobrescrevê-lo
  (T3.47c, commit `803f648`): o prefixo de linhagem (`derived_from`/`overrides`/`params_hash`) da
  variante sobrevive à aposentadoria;
- **Duas famílias novas entram no catálogo de referência no mesmo dia**
  (`trendline_breakout`, `sweep_reclaim`), com páginas em
  [[Strategies|03-TRADING/Estrategias]] — ver [[Estrategias/trendline_breakout-v1|trendline_breakout-v1]] e [[sweep_reclaim-v1]].

**Acréscimo de 2026-09-09 (T3.52–T3.56) — dois experimentos novos, e o roster do Lab passa de 16
para 9 versões vivas.** Os parágrafos acima ficam como estão. O que mudou:

- **[[EXP-0020-regime-gate]]** (portão de elegibilidade por regime horário, um braço por família:
  `mean_reversion` só decide em `SIDEWAYS`, `momentum` só em `BTC_BULL`) nasce direto de
  [[KB-0079-onde-ganha-e-perde]] (T3.53, o mapa de onde cada versão ganha e perde). O portão foi
  **implementado e entrou em produção** (migração `0017`, commit `d21a11d`, T3.52/b/c) — **nenhum dos
  dois braços foi derivado, ativado ou replayado ainda**. `status: implementado, replay pendente`;
- **[[EXP-0021-timeframe]]** (mover a referência de ATR de 15 m para 1 h) mede que ATR%(1h)/ATR%(15m)
  = **2,21×** nos 16 mercados com 31 dias de histórico — não os 3–4× do brief —, e que **nas decisões**
  o ganho de pedágio encolhe para **1,4× (momentum) e 1,04× (mean_reversion)**, porque o piso de ATR%
  já selecionava a cauda de volatilidade. `mean_reversion v10` vira a **primeira coorte julgável da
  família** (54 decisões, 16 dias, estresse `robusto`, +0,2013 R líquido); `momentum v10` fura o teto
  de stop do `paper_v1` em 37,3 % das decisões (C5 `REJECT`) e foi **aposentada no mesmo dia** pelo
  T3.56. A irmã que decide em barras de 1 h de verdade (`mean_reversion_h1_v1`, código pronto, 35
  testes) segue **bloqueada por contexto** até o mesmo commit `d21a11d` subir o teto — o que já
  aconteceu; falta ativar e replayar;
- **T3.56 (roster 16 → 9):** pelo veredito medido de cada versão (Everton, 2026-09-09 11:50 BRT,
  "as que estão dando ruim pode matar"), sete versões foram aposentadas pela via auditada —
  `volume_anomaly v2`, `momentum v2`, `momentum v4`, `momentum v6` (sucessora `momentum v8`),
  `momentum v10`, `session_orb v1`, `trendline_breakout v1` — todas negativas em toda coorte que
  tinham. `momentum v3` (a linha `paper`) foi **poupada por um portão que o brief não previu**: o
  script recusa aposentar a linha paper enquanto ela tiver acompanhamento aberto (5–6 *shadow slots*
  em voo, e ela continua ativa abrindo novos). Roster final: `mean_reversion v1/v2/v3/v6/v7/v8/v10` +
  `momentum v3` (paper) + `momentum v8` — nove versões, nenhuma nova ativada.

Cada experimento significativo (uma hipótese testada sobre uma estratégia, um conjunto de parâmetros, um mercado ou período) ganha seu próprio arquivo `EXP-NNNN-<slug>.md` nesta mesma pasta, numerado sequencialmente a partir de `EXP-0001`.

## Registro de IDs (decisão conjunta SHADOW, 2026-09-05)

| ID | Experimento | Origem | Estado |
|---|---|---|---|
| `EXP-0001` | [[EXP-0001-momentum-v1\|momentum em modo sombra]] (15 min, stop e alvo a 1,5 ATR da referência, horizonte 4 h) | Shadow Lab v0 — tarefa S4 | **aberto em 2026-09-06**; coortes locais `v1` (deprecated) e `v2` (active), e a coorte da **VPS** `v1` (active, `code_ref` `…6ccbe8b6…`) |
| `EXP-0002` | [[EXP-0002-volume-anomaly-v1\|volume_anomaly em modo sombra]] (5 min, ATR de 15 min, stop na mínima da barra do sinal, horizonte 2 h) | Shadow Lab v0 — tarefa S4 | **aberto em 2026-09-06**; coortes locais `v1` (deprecated) e `v2` (active), e a coorte da **VPS** `v1` (active, `code_ref` `…a03d18fe…`) |
| `EXP-0003` | [[EXP-0003-baselines-v1\|baselines por ativo e hora do M2, e o que elas destravam]] (instrumento, não estratégia: maturidade das baselines → anomalias, estágio, regime, score) | `docs/plans/M2.md` (T2.8) | **aberto em 2026-09-07**; primeira avaliação `as_of = 2026-09-07T03:30Z`, **inconclusivo** (1 dia distinto de série viva) |
| `EXP-0004` | [[EXP-0004-politicas-de-saida\|replay de oito políticas de saída sobre as entradas congeladas]] (bloco T-005 + L1 + L2, 7 contrastes, efeito mínimo 0,05 R) | Rodada 6 de conhecimento → brief R1; commit `2c6bb2d` | **aberto em 2026-09-06**; primeira execução `as_of = 2026-09-06T20:55Z`, **inconclusivo por `B = 1`** |

| `EXP-0005` | [[EXP-0005-momentum-paper\|momentum v3 em carteira paper]] (a linha `purpose = paper` da decisão delegada D10, ao lado da coorte `research_only`) | `docs/plans/M3.md` (D10) | **aberto em 2026-09-08**; primeira avaliação `as_of = 2026-09-08T12:00:00Z`, **inconclusivo** |
| `EXP-0006` | [[EXP-0006-momentum-piso-de-custo\|piso de custo no momentum]] (`atr_pct_min = 0,0089`, mesmo `code_ref` do pai — variante de **parâmetro**, candidata #2 do [[Strategy Backlog]]) | [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] → T3.26 | **aberto em 2026-09-08**; coorte `prospective` desde 13:05 UTC e um **replay de abertura** `as_of = 2026-09-08T13:09:41Z`, **inconclusivo** |

| ID | Experimento | Origem | Estado |
|---|---|---|---|
| `EXP-0007` | [[EXP-0007-momentum-invalidacao-bracos-INV\|os braços de saída (INV/TGT/EXIT) sobre entradas congeladas]] (replay de **política de saída**: 8 braços, 7 contrastes, 4 populações) | `brief-T3.27` → T3.32 | **aberto e avaliado em 2026-09-08**; `read_at = 15:11Z–15:15Z`, **inconclusivo** — e **encerra** o item 1 do [[Strategy Backlog]] |
| `EXP-0008` | [[EXP-0008-breakout-compressao-de-volatilidade\|rompimento após compressão de volatilidade]] (`breakout_v1`, 1,25/2,5 ATR, invalidação estrutural com guarda de geometria) | T3.33a | **aberto em 2026-09-08T16:23:39Z** (ativação `research_only`); replay de abertura `as_of = 2026-09-08T16:36:58Z`, **inconclusivo** — 0 decisões, recomendação `descartar` (não executada) |
| `EXP-0009` | [[EXP-0009-mean-reversion-pullback-em-tendencia\|recuo comprado dentro de tendência de 1 h]] (`mean_reversion_v1`, 1,0/1,5 ATR, **sem** invalidação) | T3.33b | **aberto em 2026-09-08T16:32:33Z** (ativação `research_only`); replay de abertura `as_of = 2026-09-08T16:41:07Z`, **inconclusivo** — 37 decisões, 11 dias; coorte `prospective` em curso |
| `EXP-0010` | [[EXP-0010-session-orb-faixa-de-abertura\|rompimento da faixa de abertura de sessão]] (`session_orb_v1`, stop na mínima da faixa, alvo em 2 R; **família nova** no catálogo) | T3.33c | **aberto em 2026-09-08T19:42:56Z** (ativação `research_only`); replay de 31 d, **20 decisões**, 9 dias, líquida −0,1928 R, **inconclusivo**; portão C1–C8 = REVISE (62,5), teto de pedágio 0,3333 R e pedágio medido 0,1428 R |
| `EXP-0011` | [[EXP-0011-derivatives-reversao-de-funding\|comprar depois de funding liquidado negativo]] (`derivatives_v1`, 2,0/3,0 ATR, horizonte de 8 h) | T3.33d | **bloqueado por pré-checagem em 2026-09-08** — 5 liquidações negativas em 31 d × 4 mercados; **módulo não escrito**, reexecutar ~2026-10-06. Aberto **contra** a recomendação de [[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]], com a divergência declarada na página |
| `EXP-0012` | [[EXP-0012-momentum-teto-de-pedagio\|teto de pedágio no momentum]] (`momentum v5`, `atr_pct_min` 0,003 → 0,020 — variante de **parâmetro**, mesmo `code_ref` do pai `v2`) | T3.40 (V1 do [[Strategy Backlog]]) | **aberto e encerrado em 2026-09-08**: ativado 18:57:05Z, **0 decisões em 11 904 barras**, aposentado 19:39:00Z. `result` `inconclusivo` por população vazia; `status` **descartada-por-construcao** |
| `EXP-0013` | [[EXP-0013-momentum-alvo-3-atr\|alvo de 3 ATR no momentum]] (`momentum v6`, `target_atr` 1,5 → 3,0 com a escada em 3/6/9 — variante de **parâmetro**) | T3.40 (V2 do [[Strategy Backlog]]) | **aberto em 2026-09-08T19:04:56Z**; replay pareado com o pai `v2`, **inconclusivo**, mantido em pesquisa; coorte `prospective` até ~2026-10-08 |

| ID | Experimento | Origem | Estado |
|---|---|---|---|
| `EXP-0016` | [[EXP-0016-trendline-breakout\|rompimento e repique de linha de tendência]] (`trendline_breakout v1`, **família nova**; stop estrutural, alvo em largura de canal ou 2 R) | T3.34b (contrato) / T3.34c (implementação e replay) | **aberto e avaliado em 2026-09-08**; ativada 22:29:52Z, replay de 31 d × 4 mercados: 47 avaliáveis, 14 dias, líquida −0,0382 R; **manter em pesquisa, hipótese REENUNCIADA como repique** (K6 dispara: 89,4 % repique) |
| `EXP-0017` | [[EXP-0017-sweep-reclaim\|comprar a perda falsa de um suporte]] (`sweep_reclaim v1`, **família nova**; stop estrutural, porta de custo por `risk_pct_min`) | T3.45 (contrato) / T3.45b (implementação) | **pré-checagem passou em 2026-09-08** (57 eventos, 17 dias distintos); módulo implementado (commit `a9bacc6`); **nenhuma coorte ativa, replay pendente** |
| `EXP-0018` | [[EXP-0018-stop-largo\|stop largo: dividir o pedágio pela largura do stop]] (seis braços — `momentum v7`/`v8`, `mean_reversion v4`/`v5`/`v6`/`v7` — variantes de **parâmetro**) | T3.47 | **aberto e avaliado em 2026-09-08**; replay retrospectivo nos seis, seis coortes `prospective` abertas 22:29–22:38Z; **inconclusivo nos seis** (nenhum IC exclui zero); `momentum v7` e `mean_reversion v4`/`v5` **aposentadas** 23:34:42–23:34:59Z |
| `EXP-0019` | [[EXP-0019-piso-atr\|o piso de ATR%: comprar população de volta e pagar o pedágio com o stop]] (`mean_reversion v8`, mais a irmã por identidade `v1` — variante de **parâmetro**) | T3.47b | **aberto e avaliado em 2026-09-08**; replay retrospectivo, coorte `prospective` da `v8` aberta 23:37:33Z; **inconclusivo pelo limiar editorial (sinal `negativo` no corpo do EXP)** — os quatro dias que só existem com o piso baixo são os quatro negativos |

| ID | Experimento | Origem | Estado |
|---|---|---|---|
| `EXP-0020` | [[EXP-0020-regime-gate\|o regime da hora como porteiro]] (`mean_reversion v9` de `v6` só em `SIDEWAYS`, `momentum v9` de `v8` só em `BTC_BULL` — portão por `eligibility_policy`, não por parâmetro) | KB-0079 (T3.53) → brief T3.52 | **implementado em 2026-09-09** (migração `0017`, commit `d21a11d`); **nenhum braço derivado, ativado ou replayado** — `status: implementado, replay pendente` |
| `EXP-0021` | [[EXP-0021-timeframe\|o eixo de timeframe: ATR de referência em 1 h em vez de 15 m]] (`mean_reversion v10`/`momentum v10` — variantes de **parâmetro**; `mean_reversion_h1_v1` — módulo novo, bloqueado por contexto) | T3.54 | **aberto e avaliado em 2026-09-09**; `mean_reversion v10` **robusto** (54 decisões, 16 dias, +0,2013 R líq.) e viva no roster do T3.56; `momentum v10` `REJECT`/`sem_vantagem_na_base` e **aposentada** no mesmo dia (T3.56); `mean_reversion_h1_v1` código pronto, contexto destravado no mesmo commit que fechou o EXP-0020, replay ainda não rodado |
| `EXP-0025` | [[EXP-0025-mean-reversion-90-dias\|90 dias, 16 mercados: agosto era a história inteira]] (`mean_reversion v1`/`v2`/`v10` — replay de 90 d, mesmo desenho da T3.62/EXP-0021 sobre janela maior) | T3.62b | **aberto e avaliado em 2026-09-10**; **reprovada nas três** — K3 dispara, população suficiente pela primeira vez (798/89 d, 542/83 d, 302/68 d no eixo `r_ex_funding`); a vantagem medida antes é só a janela de agosto–setembro |
| `EXP-0026` | [[EXP-0026-regime-como-estrategia\|a vantagem é um regime, não uma estratégia?]] (`mean_reversion v15`/`v16`/`v17` de `v10` + `momentum v11` de `v8` — quatro braços de **portão de elegibilidade**, nenhum parâmetro muda) | T3.76 | **pré-registrado e avaliado em 2026-09-10**; **descartada nos quatro braços** — o portão funciona (Δ pareado por mercado-barra = **0,0000 R**) e move o ponto de −0,0293 R para +0,036…+0,061 R, mas **nenhum IC de blocos de dia exclui zero**: ele compra expectativa pagando em **dias** (21 a 35 blocos). O braço de **falseamento** (`HIGH_VOLATILITY`, +0,0613 R/PF 1,223) venceu os dois de consolidação — hipótese refutada, e o vencedor é o mais suspeito de calendário. `momentum v11`: −0,0595 R em 1 167 desfechos/47 dias, K3 dispara, `sem_vantagem_na_base`. Bloqueio tirado antes: `market_regimes` de **784 linhas (36,3 %)** para **2 161/2 161 (100 %)** |
| `EXP-0028` | [[EXP-0028-mean-reversion-5-min\|a reversão à média decidida em 5 minutos]] (`mean_reversion_m5 v1` — **módulo novo**, `code_ref` próprio, o eixo de timeframe da EXP-0021 percorrido para **baixo**; três parâmetros mudam, os mesmos três da irmã de 1 h) | T3.84 | **pré-registrado em 2026-09-11, antes de qualquer replay**; nenhuma medição ainda. Portão de desenho `REVISE` (C5: o stop mediano de 1 ATR a 5 min cai em cima do piso de 0,3 % do `paper_v1`, e quem o salva é o `atr_pct_min = 0,006` herdado — logo o piso **define** a versão em vez de filtrá-la). Priors contrários pré-registrados com número: KB-0076 (pedágio p50 previsto 0,267–0,333 R contra os 0,2169 R da mãe), KB-0086 (460/460 células de custo negativas a 5 min no perp do BTC), EXP-0025 (a família de 15 m já é −0,0910 R em 90 d). Previsão registrada: **ex-funding −0,25 a −0,09 R, veredito `descartar`** |

A reserva está consolidada nos três lugares que a decisão exige: aqui, em `docs/plans/SHADOW-LAB.md` (item 11) e em `docs/plans/M2.md` (T2.8).

**As duas linhas acima entraram em 2026-09-08 (T3.26b), e a de `EXP-0005` estava faltando desde o
dia anterior** — a página existia e o registro de IDs não a tinha. Fica dito, porque um registro de
IDs incompleto é pior que nenhum: quem procura o próximo número livre precisa poder confiar nele.

## Protocolo — o que fica congelado e o que é acrescentado

A regra que vale para todo `EXP-NNNN` a partir daqui:

1. **Hipótese e protocolo são escritos uma vez e não mudam.** Estratégia, versão, `code_ref`, parâmetros completos, `params_hash`, timeframes, agregação, seed/âncora do ATR, política de reentrada, perfil de entrada/saída/custos, modelo de outcome e coorte (`prospective` | `replay:<run_id>`). Conteúdo diferente = **experimento novo**, linkado ao anterior. Nunca sobrescreva um `EXP-NNNN` existente.
2. **Avaliações são acrescentadas, datadas e rastreáveis.** Cada avaliação traz o SQL usado, os parâmetros da consulta, o `as_of`, a versão da métrica e a proveniência. A conclusão de ontem não é reescrita — ganha uma linha nova abaixo.
3. **Limiar editorial.** Abaixo de **100 outcomes avaliáveis E 30 dias distintos**, o campo `Result` só pode ser `inconclusivo`. Acima disso continua sendo pesquisa, nunca promessa: incerteza por reamostragem em blocos de tempo (mercados simultâneos são dependentes), sensibilidade a custos, variantes tentadas e avaliação futura reservada.
4. **Nada é ativado automaticamente.** A variante vencedora de um experimento nunca é promovida sozinha; ativar uma `strategy_version` é ato auditado, com pré-requisitos provados.
5. **Carteira não se aplica.** No Shadow Lab não há capital: `PnL de carteira` e `Max Drawdown de carteira` são **não aplicáveis**, e a soma de R hipotéticos, quando aparecer, vem com nome e ordenação explícitos.

## Template — `EXP-NNNN`

Ver [[_TEMPLATE-EXP]] para o arquivo pronto para copiar. Os campos e a distinção entre as métricas estão lá; o resumo do que cada uma significa:

| Campo | O que registra |
|---|---|
| Date / As of | Data de abertura do experimento e `as_of` de cada avaliação acrescentada |
| Hypothesis | O que se esperava provar ou refutar, em uma frase — **congelado** |
| Strategy / Version / code_ref / params_hash | Identidade exata do que está sendo medido — **congelada** |
| Cohort | `prospective` ou `replay:<run_id>` — replay nunca vira sinal prospectivo |
| Custos assumidos | Spread total, slippage por lado, taxa por lado — hipóteses declaradas, não tarifas verificadas |
| Cobertura | Emitidos, pendentes, entradas, não entradas por motivo, ativos, target, stop, expired, invalidated, censurados, funding indisponível |
| Taxa de alvo entre toques resolvidos | `target / (target + stop)` — **não** é taxa de lucro |
| Taxa de lucro líquido | Encerrados avaliáveis com `R_net > 0` / encerrados avaliáveis |
| Expectancy líquida hipotética em R | Média de `R_net` na mesma população |
| Profit Factor | Σ `R_net` positivos / \|Σ negativos\| — **nulo com motivo** se não houver perdas |
| PnL / Max Drawdown de carteira | **Não aplicável** (não há carteira no Shadow Lab) |
| Result | confirmou \| refutou \| inconclusivo (com o limiar editorial acima) |
| Conclusion / Next Action | Acrescentados por avaliação, nunca reescritos |

Todos os números vêm de `agent_signals` / `signal_outcomes` reais, com o SQL colado — nunca estimados ou inventados. Um experimento sem dado suficiente registra isso explicitamente em vez de preencher os campos com aproximação.

## Experimentos registrados

| Arquivo | Estratégia | Aberto em | Última avaliação (`as_of`) | Result |
|---|---|---|---|---|
| [[EXP-0001-momentum-v1]] | `momentum` v1 (deprecated) + v2 (active) | 2026-09-06 | `2026-09-06T02:55:00Z` | **inconclusivo** — 57 avaliáveis (48 + 9), 1 dia, **0 com horizonte maturado** |
| [[EXP-0002-volume-anomaly-v1]] | `volume_anomaly` v1 (deprecated) + v2 (active) | 2026-09-06 | `2026-09-06T02:55:00Z` | **inconclusivo** — 72 avaliáveis (66 + 6), 1 dia, 35 com horizonte maturado |
| [[EXP-0004-politicas-de-saida]] | replay: `momentum` v1+v2 e `volume_anomaly` v1+v2 (4 versões congeladas), 8 políticas de saída | 2026-09-06 | `2026-09-06T20:55:00Z` | **inconclusivo** — 275 maturados, **1** dia (`B = 1`); reprodução de trajetória 1,0000 em 339 comparáveis |
| [[EXP-0003-baselines-v1]] | baselines por (mercado, feature, hora UTC) do M2 — instrumento, não estratégia | 2026-09-07 | `2026-09-07T03:30:00Z` | **inconclusivo** — 1 dia distinto de série viva; **4.944 buckets utilizáveis de 88.746 (5,57 %)**, 12 de 27 features com algum bucket utilizável, **teto de score 25,00 de 100** |
| [[EXP-0005-momentum-paper]] | `momentum` v3 (`purpose = paper`, D10) — a mesma decisão medida pela carteira | 2026-09-08 | `2026-09-08T12:00:00Z` | **inconclusivo** — 30 avaliáveis maturados (31 antes do gate), **1** dia; e a carteira **não foi tocada**: `ENABLE_PAPER_AUTONOMY=false`, 0 propostas / 0 posições / 0 trades |
| [[EXP-0006-momentum-piso-de-custo]] | `momentum` v4 — variante de **parâmetro** (`atr_pct_min` 0,003 → 0,0089), mesmo `code_ref` do pai `v2` | 2026-09-08 | `2026-09-08T13:09:41Z` (**replay** de abertura) | **inconclusivo** — 30 avaliáveis, **9** dias; **o piso corta 86% das decisões** (31 contra 224 do pai) e toda a diferença de expectancy vem de **6 decisões sem par**, 5 avaliáveis |
| [[EXP-0007-momentum-invalidacao-bracos-INV]] | replay de **política de saída** sobre entradas congeladas: `momentum` v1/v2 e `volume_anomaly` v2, 8 braços | 2026-09-08 | `2026-09-08T04:00Z` (replay) e `15:00Z` (prospectivas), `read_at = 15:11–15:15Z` | **inconclusivo** — 4 populações (222 · 337 · 189 · 933 avaliáveis; 24 · 29 · 1 · 3 dias), **nenhum dos 7 contrastes rejeita em nenhuma**; a invalidação **adianta** a perda, não a cria |
| [[EXP-0008-breakout-compressao-de-volatilidade]] | `breakout` v1 e v2 — compressão de TR (8/32) antes do rompimento de 20 barras | 2026-09-08 | `2026-09-08T16:36:58Z` (v1) e **17:46Z** (v2, coorte `replay:0def121f…`) | **inconclusivo nas duas** — a `v1` fez **0 decisões** (14/14 `geometry_invalidation`); a `v2` (`stop_atr` 1,25 → 3,5) fez **8 decisões**, bruta +0,0120 R, pedágio 0,0912 R, líquida **−0,0810 R**, PF 0,798, acerto 50 % contra os 65 % de equilíbrio. K1 dispara nas duas → **ambas aposentadas** pela via auditada em 19:35:34Z e 19:35:36Z. Portão C1–C8 = **REVISE** (66,0) |
| [[EXP-0009-mean-reversion-pullback-em-tendencia]] | `mean_reversion` v1 — z ≤ −1 dentro de tendência de 1 h, sem invalidação | 2026-09-08 | `2026-09-08T16:41:07Z` (replay) e **19:13:53Z** (passada de estresse sobre a mesma coorte) | **inconclusivo** — 37 avaliáveis (< 100), **11** dias (< 30); bruta +0,3210 R, líquida **+0,0938 R**, PF 1,186, cobertura 100 %; o saldo inteiro está em 6 saídas por horizonte e 2 dias. **Estresse: `frágil a custos`** (`custos_x2` → −0,1213 R, IC do Δ inteiro negativo) **e dependente de metade** (2ª metade: 7 operações, −0,5568 R). Portão C1–C8 = **REVISE** (65,5) |
| [[EXP-0010-session-orb-faixa-de-abertura]] | `session_orb` v1 — faixa da 1ª hora de Ásia/Europa/EUA, stop no dado, alvo em 2 R | 2026-09-08 | `2026-09-08` (**replay** do dia um, coorte `replay:3fb9dda2…`, `read_at` 19:44–19:57Z) | **inconclusivo** — 20 avaliáveis (< 100), **9** dias (< 30); bruta −0,0501 R, líquida **−0,1928 R**, PF 0,662, cobertura 100 %. **K1 não dispara por uma decisão** e a condição de mercado de K3 já está cumprida; as três sessões perderam com expectancy **indistinguível** (30/35/35 %) — o rótulo de sessão não fez trabalho. Estresse: **amostra insuficiente** (20 de 30) |
| [[EXP-0011-derivatives-reversao-de-funding]] | `derivatives` v1 — funding liquidado ≤ −0,01 % em 8 h, depois de queda, com estabilização | 2026-09-08 | `2026-09-08` (**pré-checagem**, sem replay) | **inconclusivo / `bloqueado-por-precheck`** — 5 liquidações negativas em 31 d × 4 mercados (ETH e DOGE: 0), teto medido de 158 barras (1,33 %); **módulo não escrito de propósito**; reexecutar ~2026-10-06 |
| [[EXP-0012-momentum-teto-de-pedagio]] | `momentum` v5 — variante de **parâmetro** (`atr_pct_min` 0,003 → 0,020), mesmo `code_ref` do pai `v2` | 2026-09-08 | `2026-09-08` (**replay**, coorte `replay:72cf5671…`, `read_at` 19:11:21Z) | **inconclusivo por população vazia** — **0 decisões em 11 904 barras**, corte de **100 %**; o piso está acima de todo o ATR% observado ao decidir (máx. 1,756 %). **Aposentada 19:39:00Z** pela via auditada |
| [[EXP-0013-momentum-alvo-3-atr]] | `momentum` v6 — variante de **parâmetro** (`target_atr` 1,5 → 3,0, escada 3/6/9), mesmo `code_ref` do pai `v2` | 2026-09-08 | `2026-09-08` (**replay** pareado com o pai, `read_at` 19:11–19:15Z) | **inconclusivo** — 195 avaliáveis (≥ 100), **24** dias (< 30); líquida **−0,0513 R** contra −0,1717 R do pai, PF 0,906; Δ pareado **+0,1341 R** em 191 pares com risco inicial idêntico, e **IC por dia [−0,0939; +0,1866] contém zero**. Reduz a perda em 70 %, **não a inverte** |
| [[EXP-0016-trendline-breakout]] | `trendline_breakout` v1 — **família nova**; rompimento de resistência descendente ou repique em suporte ascendente, stop estrutural | 2026-09-08 | `2026-09-08` (**replay** de dia um, coorte `replay:d78c14d1…`, T3.34c) | **inconclusivo** — 47 avaliáveis (< 100), **14** dias (< 30); bruta +0,1045 R, líquida **−0,0382 R**, PF 0,922; **regra dos 60 % dispara** (89,4 % repique) → hipótese **REENUNCIADA** como repique; manter em pesquisa |
| [[EXP-0017-sweep-reclaim]] | `sweep_reclaim` v1 — **família nova**; varredura de pivô de mínima com recuperação na mesma barra, stop = mínima varrida | 2026-09-08 | `2026-09-08` (**pré-checagem**, sem replay) | **inconclusivo (população, não edge)** — 57 eventos em 31 d × 4 mercados, 17 dias distintos, cobertura 99,5 %; nenhuma regra de morte disparou; módulo implementado (commit `a9bacc6`), **replay pendente** |
| [[EXP-0018-stop-largo]] | `momentum` v7/v8, `mean_reversion` v4/v5/v6/v7 — seis variantes de **parâmetro** (stop e escada multiplicados por 1,5 ou 2×) | 2026-09-08 | `2026-09-08` (**replay** retrospectivo pareado com cada pai) | **inconclusivo nos seis** — pedágio cai pelo fator pedido (÷1,48 a ÷2,08) nos seis, mas **nenhum IC exclui zero**; só 12 % da economia sobrevive na melhor população julgável (`momentum v8`); `momentum v7` e `mean_reversion v4`/`v5` **descartadas e aposentadas** |
| [[EXP-0019-piso-atr]] | `mean_reversion` v8 (mais a irmã por identidade `v1`) — variante de **parâmetro** (`atr_pct_min` 0,008 → 0,006 + stop ×1,5) | 2026-09-08 | `2026-09-08` (**replay** retrospectivo, coorte `prospective` da v8 aberta 23:37:33Z) | **inconclusivo (sinal `negativo` no corpo do EXP)** — 33/37 avaliáveis (< 100), 11 dias (< 30); quatro contrastes pré-registrados negativos; o piso escondia dias ruins, não decisões boas; mantida em pesquisa pela mensurabilidade |
| [[EXP-0020-regime-gate]] | `mean_reversion` v9 (de v6, portão `SIDEWAYS`) + `momentum` v9 (de v8, portão `BTC_BULL`) — portão de elegibilidade por `eligibility_policy`, não variante de parâmetro | 2026-09-09 | — (nenhuma corrida ainda) | **implementado, replay pendente** — migração `0017` em produção (commit `d21a11d`); nenhum braço derivado/ativado/replayado |
| [[EXP-0021-timeframe]] | `mean_reversion` v10 (de v6) + `momentum` v10 (de v8) — variantes de **parâmetro** (`atr_timeframe` 15m → 1h, `atr_bars` 97 → 24); `mean_reversion_h1_v1` — módulo novo (decide em barras de 1 h) | 2026-09-09 | `2026-09-09` (replay 31 d × 4 mercados, coortes `replay:71c76d86…` e `replay:6eff77c0…`) | **inconclusivo pelo limiar editorial** — `mean_reversion v10`: 54 avaliáveis (< 100), 16 dias (< 30), estresse **robusto**, líquida +0,2013 R, viva no roster T3.56; `momentum v10`: 252 avaliáveis, 29 dias (< 30), estresse `sem_vantagem_na_base`, líquida −0,0357 R, **aposentada** no mesmo dia (T3.56); pedágio cai 2,21× no ATR% incondicional mas só ÷1,40/÷1,04 nas decisões (o piso de ATR% já seleciona a cauda) |
| [[EXP-0025-mean-reversion-90-dias]] | `mean_reversion` v1 + v2 + v10 — replay de **90 dias × 16 mercados** (mesmo `code_ref`, três contrastes de parâmetro) | 2026-09-10 | `2026-09-10` (36 corridas, 414 720 barras, 1 644 decisões, 0 erros; coortes `replay:c7d138eb…`/`fa005985…`/`da706026…`) | **reprovada nas três** — primeira vez que a régua tem população (≥ 100 e ≥ 30 dias no eixo `r_ex_funding`, cobertura 100 %) para julgar a família: `v10` −0,0293 R/PF 0,910 (89 d), `v1` −0,0910 R/PF 0,851 (83 d), `v2` −0,0343 R/PF 0,940 (68 d). **K3 dispara nas três.** Por janela: J1 e J2 negativas, J3 (ago–set) positiva nas três, Δ(J3−J1J2) exclui zero nas três — a vantagem da T3.62/EXP-0021 é a janela de agosto, e só ela; os 4 mercados originais caem para +0,0002 R (zero) em 90 dias. C5 (teto de risco 3 %) é 16,8 % em 90 d contra 32,3 % só em J3 — propriedade de versão × regime |
| [[EXP-0026-regime-como-estrategia]] | `mean_reversion` v15/v16/v17 (de v10) + `momentum` v11 (de v8) — **portão de elegibilidade** por regime horário do BTC, conjunto congelado do pai byte a byte | 2026-09-10 | `2026-09-10` (48 corridas, 552 960 barras, 1 767 decisões, 0 erros; coortes `replay:3271f431…`/`309144d2…`/`095d4772…`/`70f55430…`) | **descartada nos quatro** — condição 5 (Δ pareado por mercado-barra) **PASSA com 0,0000 R** nos três braços de `mean_reversion`, provando que o portão é só um portão; condições 3 e 4 passam nos três; **condição 1 falha nos três** (Δ +0,0651/+0,0744/+0,0905 com IC [−0,0832;+0,2024], [−0,1135;+0,2362], [−0,1540;+0,2763]); `v17` também falha a condição 2 (**21 dias**). Estresse: **frágil a custos nos três**, dependente de metade em `v15`/`v17`. `momentum v11` sem controle de 90 d (o pai `v8` está `deprecated` e o replay recusa versão não executável) e negativo por conta própria. K4 lido no pai: **0,93 %** |
| [[EXP-0028-mean-reversion-5-min]] | `mean_reversion_m5` v1 — **módulo novo** (irmã de `mean_reversion_v1` que decide em 5 min; `atr_timeframe` 5m, `trend_timeframe` 15m — o degrau seguinte da grade, porque 4 × 5 min = 20 min não existe em `Timeframe` —, `horizon_s` 4800) | 2026-09-11 | — (pré-registro; nenhum replay rodado) | **não iniciado** — regra de sucesso congelada: ex-funding 90 d > 0 com IC de blocos de dia acima de zero **E** PF > 1 em ≥ 2 de 3 janelas **E** leave-one-market-out nunca negativo **E** estresse não `frágil`; qualquer coisa menos é `descartar` com `--deprecate` na mesma tarefa. Braço de falseamento: a mãe **já medida** (`v1`, coorte `replay:fa005985…`, EXP-0025), que não será re-rodada |

### O que a próxima extração tem de fazer (achados da revisão da Astra, 2026-09-06)

O SQL das páginas já incorpora estes cinco pontos; ficam escritos aqui porque valem para **todo**
`EXP-NNNN` futuro, não só para estes dois:

1. **Coorte e propósito impostos na consulta**, não apenas declarados no protocolo
   (`supporting_features->>'cohort'` e `->>'purpose'`). No dia em que existir `replay:<run_id>`, um
   SQL sem esse filtro mistura prospectivo com retrospectivo em silêncio.
2. **Maturação do horizonte contada à parte** (`expires_at <= read_at`). Sem ela, uma leitura feita
   cedo mede só os acompanhamentos que resolveram rápido e a composição muda sozinha com o tempo.
3. **Motivos exatos**, agrupados pelo valor, nunca por `LIKE 'late%'` — `late:delay`,
   `late:missed_open` e `late:unconfirmed` são populações diferentes.
4. **PF nulo só com motivo verdadeiro:** ausência de **perdas** (denominador vazio) ou ausência de
   população. Ausência de **ganhos** dá PF **zero**, que é um resultado conhecido — chamá-lo de nulo
   esconderia o pior caso.
5. **Snapshot único** (`REPEATABLE READ READ ONLY`) para todas as consultas da mesma avaliação, e a
   ressalva escrita de forma dura: a leitura **não é reconstruível** depois, porque `signal_outcomes`
   avança no lugar e não há histórico de estados preservado.

### Por que existem duas coortes de versão em cada experimento

`v2` não é variante de pesquisa: nas duas estratégias ela nasceu da correção do `code_ref` (o
digest da árvore inteira invalidava toda versão congelada a cada módulo novo — MUST-FIX 1 do
`risk-engine-guardian`). Campo congelado não se corrige no lugar, então a correção obrigou uma
versão nova, e a `v1` foi `--supersede`d para `deprecated` **mantendo a população que já tinha**.
Código, `default_parameters`, `parameters_schema` e `params_hash` são idênticos entre as duas; o que
separa as populações é o `strategy_version_id` dentro do `uuid5` de cada sinal. Comparar `v1` com
`v2` como se fossem hipóteses concorrentes seria erro de leitura — está escrito em cada página.

### A VPS é uma população separada, ainda sem avaliação datada

Desde 2026-09-06 03:36 UTC o Shadow Lab também roda na VPS
(`.claude/state/vps-lab-proof.md`): `momentum v1` e `volume_anomaly v1` ativadas pelo script
auditado, 109 sinais em 1 h 18 min, todos `research_only` e `prospective`, `/ready` 200, outbox
109/109, zero exceção — e **zero `unavailable`**, ao contrário da máquina local.

Mas essas linhas **não** entram nas avaliações acima. São `strategy_version` próprias, com
`activated_at` e `code_ref` diferentes (o digest não é o mesmo entre Windows e Linux — [[Open Bugs]]),
logo são **coortes distintas**, com população própria. Vão virar avaliação datada no próximo
plantão, com o mesmo SQL, e com uma exclusão que a janela local não teve: **19 dos 70
acompanhamentos encerrados na VPS têm `R_net = NULL`** (`funding_missing:2026-09-06T04:00:00+00:00`
em 18, `funding_ambiguous_exit` em 1), com `meta.r_ex_funding` preservado — 27% dos encerrados ficam
fora dos "encerrados avaliáveis". **O motivo desses 18 está sob investigação**, não confirmado: o
cálculo exige timestamp exato numa grade de liquidações e o histórico da VPS tem a liquidação em
`04:00:00.005` (achado da Astra, [[S4-vps-lab]]) — o dado pode estar lá. Fora da conta eles ficam de
qualquer jeito; o que muda é se o rótulo é honesto.

Vale a mesma advertência do [[Workers|worker]]: a prova da VPS mostra que o **fluxo de sombra
funcionou naquela janela**, e nada além. Não é avaliação de experimento.

### Rotina de plantão

A cada turno da [[Mente da Sexta-feira|Sexta-feira]] os experimentos ativos recebem **uma avaliação
nova, datada**, com o SQL colado, o `as_of` do turno e os números de saída real. Avaliação anterior
nunca é reescrita; hipótese e protocolo nunca mudam; a variante "vencedora" nunca é ativada
automaticamente. A rotina está em `.claude/agents/sexta-feira.md`, seção "Plantão permanente".

**Turno sem avaliação — registrado, porque a regra manda registrar.** O plantão da madrugada de
**2026-09-07 (04:20–04:50Z)** **não** acrescentou avaliação datada a nenhum `EXP-NNNN`: foi um turno
de documentação, com escopo de escrita fechado em `obsidian/**` (changelog, bugs, diário, páginas de
trading, home) por instrução do Everton. Fica anotado aqui em vez de o log ficar mudo — silêncio num
registro de pesquisa é indistinguível de instrumento quebrado. Dois fatos medidos naquele turno que
importam para a próxima leitura: o `hb:strategy:shadow` da VPS às **04:33:15Z** trazia
`evaluated_bars = 0`, `open_trackings = 36`, `errors = 0`, `outbox_pending = 0` — número compatível
com um **restart recente** do `strategy-worker` durante o deploy dos 4 shards, não necessariamente
com uma parada; e a **cobertura do tape voltou a andar** (`covered_until` a 0,7–0,9 s do relógio,
sessão contínua desde 04:33:05Z), o que muda a disponibilidade das features de tape rio acima de
[[EXP-0003-baselines-v1]]. A avaliação datada do próximo turno tem de começar por confirmar as duas
coisas com SQL. Ver [[Diario/2026-09-07]].

## Relacionadas

[[Strategies]] · [[Agents Overview]] · [[Momentum Agent]] · [[Volume Agent]] · [[Performance Overview]] · [[Strategy Performance]] · [[Dialogos/SHADOW]] · [[Architecture Decisions]]

## Fontes

`docs/plans/SHADOW-LAB.md` (itens 9 e 11 da decisão conjunta) · `docs/plans/M2.md` (T2.8) · `.claude/state/dialogue-SHADOW.md` · `docs/decisions/0003-base-de-conhecimento-obsidian.md` · `docs/DATABASE.md` §6 e §9
