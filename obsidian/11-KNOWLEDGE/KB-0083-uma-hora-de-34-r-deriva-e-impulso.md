---
tags: [knowledge, nota, shadow-lab, diagnostico, mean-reversion, regime, custos, m3]
tema: a hora de −34 R de 09/09 (21:00Z / 18:00 BRT) decomposta — deriva, impulso de amplitude do universo, e dois achados de instrumento (spot duplicado, denominador escondido de `late:delay`)
fonte: dado próprio da VPS — `signal_outcomes`, `agent_signals`, `strategy_versions`, `markets`, `candles_1m`, `market_regimes` (`regime_hourly_v1`/`regime_v0`), lido em transações `repeatable read read only`
fonte_url: —
lido_em: 2026-09-10
as_of: "2026-09-10T03:47:00Z"
read_at: "2026-09-10T03:47:00Z"
evidencia: "9 consultas SQL somente leitura (`infra/scripts/sql/research/2026-09-10-dp9-q0{0..8}-*.sql`) sobre as 39 decisões pooled da hora 21:00Z de 09/09 + o dia 08/09 inteiro para contraste + candles de 1 min das 5 piores apostas em unidades de ATR"
hipotese_testavel: "sim — H-P7 (correlação de barra: R por aposta única vs. pooled) e H-P8 (amplitude do universo em tercis fixados como estado), pré-registradas, ainda não testadas"
astra: pendente
status: arquivada
owner: sexta-feira
updated: 2026-09-10
confiança: "?"
---

# Uma hora de −34 R: 9 apostas × 4,3 versões, deriva + impulso de amplitude

> **Arquivada pela Sexta-feira em 2026-09-10 (plantão de arquivamento)** a partir de
> `.claude/state/notes-D-P9.md` (diagnóstico somente-leitura sobre a VPS, plantão de mercado T3.64).
> Não editei nenhum número abaixo além de organizar a nota nesta forma; toda proveniência está no
> arquivo de origem. Nada foi escrito na VPS, nenhuma versão foi mudada, nada foi commitado. Nada
> aqui é dinheiro real (`ENABLE_LIVE_TRADING=false`).
>
> **Veredito em uma linha:** os −34,02 R que fecharam a hora das 18:00 BRT de 09/09 são **9 apostas
> econômicas**, não 39 decisões — a família `mean_reversion` decidiu a mesma aposta em média 4,33
> vezes (até 8), e o R pooled escala com o número de versões vivas, não com o número de decisões
> reais. O preço fez duas coisas em sequência (deriva, depois um impulso de amplitude do universo), e
> nenhuma delas é explicada pelo BTC. Dois achados de **instrumento** (não de estratégia) aparecem no
> caminho e contaminam qualquer contagem de "aposta única" feita por `market_id`.

## O que afirma

1. **A soma pooled de R por hora superestima o dano/ganho quando várias versões decidem a mesma
   aposta na mesma barra.** As 39 decisões das 21:00Z de 09/09 são, na chave (mercado, barra de
   15 min de `observation_ts`), **9 apostas únicas** em 7 mercados e 2 barras (21:00Z e 21:30Z), com
   **4,33 versões por aposta** em média (uma, `ZKUSDT` 21:30Z, foi tomada por **8** versões e sozinha
   soma −8,69 R pooled — que é **uma** decisão econômica de −1,09 R repetida oito vezes). Somando uma
   vez cada aposta, a hora vale **−7,53 R**, não −34,02 R.
2. **A perda teve dois mecanismos em sequência, não um evento só.** Primeiro uma **deriva**: dezenas
   de velas de 1 min pequenas (corpo 0,03–0,3 ATR, nenhuma > 1 ATR) entre 18:22 e 18:49 BRT que já
   levam o preço a −1/−1,5 ATR e matam os stops apertados (`stop_atr = 1`, versões `v1`/`v2`/`v3`).
   Depois um **impulso de amplitude**: às **19:08 BRT (22:08Z)**, **194 dos 200 perpétuos monitorados
   caíram no mesmo minuto** (média −3,71 %, mediana −1,76 %, casos extremos como LABUSDT −35,8 % e
   ESPORTSUSDT −30,6 %) com repique imediato no minuto seguinte (36/200 caindo, +1,53 % de média) — a
   assinatura de uma **cascata de liquidação em alts ilíquidas**, não de um choque macro. Ali saíram
   15 das 39 decisões, −14,77 R (43 % da hora), e ali está a única vela de 1 min do dia com corpo
   maior que 1 ATR (XVGUSDT, −1,54 ATR).
3. **O BTC não caiu.** No minuto do estouro (22:08Z) o BTC caiu apenas −0,204 % (amplitude 0,246 %),
   e na hora inteira −0,22 %. O regime `regime_hourly_v1` (escopo BTC) marcou `BTC_BEAR`, confiança
   1,0000, em **todas** as horas de 09/09 16:00Z a 10/09 01:00Z — inclusive a própria hora 21:00Z e a
   hora fechada anterior. A família só emite `LONG`
   (`packages/core/hunter_core/strategies/mean_reversion_v1.py:315`) e emitiu 39 LONGs numa hora
   rotulada de baixa, com 58–76 % do universo já caindo quando as primeiras 5 apostas entraram — mas
   o rótulo de regime **não separa** a hora 21Z das outras horas do mesmo dia (todas `BTC_BEAR`), só
   mostra que a família comprou fraqueza dentro de um regime de baixa.
4. **Não é o relógio, ainda.** A mesma hora 21Z em 08/09 deu **+1,32 R**, 50 % de acerto — o oposto do
   dia seguinte. Com só dois dias de série prospectiva isto é **painel, não teste**: uma hipótese de
   relógio (H-P4) não pode ser confirmada pelo próprio dia que a inspirou.
5. **ZEC concentra metade da perda do dia, mas removê-lo não vira o dia positivo.** Leave-one-out
   sobre o dia inteiro (não só a hora 21Z): tirar ZEC (−18,04 R, 5 apostas únicas) deixa o dia em
   −16,47 R; tirar os dois maiores vencedores do dia (TRUTH +16,67, FF +15,05) piora muito mais.
   Banir mercado pela manchete continua proibido (revisão da Astra sobre o mesmo plantão).

## Onde foi mostrado

Perpétuos USDT da Binance, família `mean_reversion` (8 versões vivas + `mean_reversion_h1 v1`),
timeframe de decisão 15 min (a maioria) e 1 h (`v10`/`h1 v1`), universo de 200 mercados monitorados,
coorte `prospective`, dia 09/09/2026 (comparado com 08/09/2026, único outro dia com série
prospectiva completa). Custos assumidos do Lab (2/5/4 bps). `r_multiple` é nulo em 21 dos 423
desfechos do dia (funding não estabelecido); toda soma "com R" tem denominador explícito menor que o
n de decisões.

## Como mediríamos aqui — já medido, é o que esta nota é

`observation_ts` truncado à barra de 15 min como chave de aposta única; `candles_1m` do perpétuo (só
`is_final`) em unidades do próprio ATR usado pela decisão (`supporting_features.atr.value`); amplitude
do universo = fração de 200 perpétuos monitorados com vela de 1 min negativa, minuto a minuto;
`regime_hourly_v1`/`regime_v0` para o rótulo de regime da hora fechada anterior e da própria hora.

## Hipótese testável no Lab

Duas, pré-registradas nesta nota, nenhuma testada ainda:

- **H-P7 (correlação de barra):** a família concentra 4–8 versões e vários mercados na mesma barra de
  15 min; medir a exposição por barra (apostas × versões) e testar se o R por **aposta única** difere
  do R pooled, com bootstrap de blocos de dia. Se diferir, o problema é de dimensionamento/contagem,
  não de horário.
- **H-P8 (amplitude do universo como estado):** fração de perpétuos monitorados caindo nos 5 min
  antes da decisão, em tercis fixados numa janela anterior; a pergunta é se comprar reversão com
  ~70 % do universo caindo tem expectancy diferente de comprar com o universo estável. Célula de
  regime candidata, não filtro.

## Dois achados de instrumento, sem edge (o motivo de esta nota também servir de alerta de dado)

1. **O Lab aposta em spot e perpétuo do mesmo símbolo como se fossem mercados independentes.**
   `markets` tem duas linhas por símbolo (a família apostou nas duas de `NEARUSDT` no mesmo minuto,
   09/09 21:30Z). As linhas de **spot** das 21Z saem com `r_multiple = NULL` e
   `r_net_reason = funding_schedule_unknown` — funding não resolvido num mercado que não tem funding,
   por construção. Os −34,02 R vêm **inteiramente** das 35 linhas perpétuas; as 4 linhas spot ficam
   fora de qualquer soma com R. Isso contamina qualquer contagem de "aposta única" feita só por
   `market_id`, e é a mesma linha de instrumento que a T3.73 fechou no consumidor
   (`hunter_strategy_worker/consumer.py` passou a recusar vela não-perpétua antes de resolver o
   mercado — [[07-BUGS/Open Bugs|Open Bugs]], T3.73).
2. **O denominador de "sinais que não entraram" é maior do que parece e cresce com o custo do
   roster.** 513 sinais do dia 09/09 não viraram entrada (`no_entry`), 512 deles por `late:delay` — o
   atraso decisão-menos-barra, não o preço fugindo da zona (a T3.73/T3.74 mediram a causa exata:
   `plan.py::plan_entry` mede o tempo que o próprio worker levou para persistir a decisão, e a
   mediana desse atraso saiu de 2,0 s no início do mês para 107,9 s em 09/09 e 125,1 s em 10/09 —
   [[07-BUGS/Open Bugs|Open Bugs]], T3.73/T3.74). Sem contar isso, qualquer leitura de "quantas vezes
   a família tentou operar" subestima o denominador verdadeiro.

## Por que pode falhar

- **Dois dias de série prospectiva não são dois testes independentes** — 09/09 é descoberta, não
  confirmação, e H-P4 (relógio) precisa de janela reservada antes de qualquer conclusão.
- **As oito versões da família não são independentes entre si** (compartilham parâmetros e mercado),
  então "39 decisões" nunca foi um n de 39 eventos econômicos — é exatamente o que H-P7 formaliza.
- **A definição de "aposta única" usada aqui é uma escolha declarada, não a única possível**: agrupar
  por barra de 15 min separa mais apostas do que agrupar por hora, e é conservadora nesse sentido —
  mas versões de 1 h (`v10`, `h1 v1`) leem barra de 1 h e foram agrupadas na grade de 15 min mesmo
  assim.
- **A causa raiz do impulso de amplitude (22:08Z) não foi investigada aqui** — fica descrita como
  cascata de liquidação em alts ilíquidas pela assinatura (queda concentrada em símbolos de baixa
  liquidez com repique imediato e volume 30–40× o normal), não confirmada contra um feed de
  liquidações.

## Segunda opinião (Astra)

Ordenou o diagnóstico D-P9 antes de qualquer teste formal, com H-P4 como primeiro teste formal e H-P2
(volatilidade agendada) instrumentada em paralelo; corrigiu que a `mean_reversion_v1` só emite `LONG`
(então "dividir por direção" não separa nada) e que H-P5 (ZEC parabólico) tem o mecanismo presumido
errado — a regra exige tendência de alta de 1 h, então comprar recuo numa alta parabólica não perde
por construção; o perigo seria comprar durante a reversão, não durante a alta. Vetou banir ZEC pela
manchete. Transcrição completa em `.claude/state/astra-review-plantao-20260910-0045.md` (referenciada
por `.claude/state/plantao/2026-09-10-0045-lane2.md`).

## Relacionadas

[[KB-0076-por-que-perdemos-2026-09-08]] · [[KB-0079-onde-ganha-e-perde]] ·
[[EXP-0025-mean-reversion-90-dias]] · [[mean_reversion]] · [[Diario/2026-09-10]] ·
[[07-BUGS/Open Bugs|Open Bugs]] · [[00-INBOX/Hipoteses-do-plantao|Hipoteses do plantao]]

## Fontes

`.claude/state/notes-D-P9.md` · `infra/scripts/sql/research/2026-09-10-dp9-q0{0..8}-*.sql` ·
`.claude/state/notes-T3.73.md` · `.claude/state/notes-T3.74.md` ·
`.claude/state/plantao/2026-09-10-0045-lane2.md` ·
`packages/core/hunter_core/strategies/mean_reversion_v1.py:315`

## Adendo 2026-09-12 (Astra)

- **Foi retirada a explicação "N² de Aldridge explica esta hora":** a revisão distingue duplicação de exposição, variância e impacto — N cópias idênticas de uma aposta somam NR e têm variância N²·Var(R), mesmo sem impacto adicional; isso não demonstra a perda superlinear do corolário, que exige outras hipóteses de correlação, equilíbrio e impacto (procedência: `.claude/state/astra-review-plantao-20260910-0730.md`, "MUST-FIX"; retirada aceita em `.claude/state/plantao/2026-09-10-0730-lane1.md`, item 2).
- **A D-P9 permanece diagnóstico de população e trajetória:** seus 39 registros, agrupados em nove apostas pela chave declarada, não são 39 eventos independentes; o fator médio 4,33 daquela hora não deve virar divisor geral, pois versões com stops distintos podem produzir R distintos (procedência: `.claude/state/notes-D-P9.md`, consultas q02–q03; `.claude/state/plantao/2026-09-10-0435-lane3.md`, seção "Astra", agregação por aposta).
- **H-P18, dispersão BTC × alts, é hipótese exploratória, não previsão:** a especificação revisada usa, em cada decisão t, retornos móveis de 24 h calculados só com fechamentos finais disponíveis, com mediana dos 16 mercados < −3% e BTC > −2%, congelando o rótulo por aposta; o snapshot das 19:10Z não pode classificar uma entrada das 13:00Z (procedência: `.claude/state/astra-review-plantao-20260910-1608.md`, "MUST-FIX" 1).
- **O contraste primário proposto é discordância menos controle com BTC também > −2% e mediana ≥ −3%:** afirmar informação incremental requer comparar BTC-only com BTC+amplitude em período reservado, com métrica fixada antes; os cortes vieram da descoberta, os 90 dias explorados continuam exploração e H-P18 pertence à família H-P8/H-P10 (procedência: `.claude/state/astra-review-plantao-20260910-1608.md`, "MUST-FIX" 2).
- **A evidência externa discutida no plantão não valida H-P18:** volatilidade futura de cinco dias por canal macro não equivale ao retorno direcional de 24 h desta célula, e a discordância observada não comprova antecipação de cascata (procedência: `.claude/state/plantao/2026-09-11-0935-lane3.md`, resposta curta e item 4; `.claude/state/notes-D-P9.md`, diagnóstico de preço e regime).
