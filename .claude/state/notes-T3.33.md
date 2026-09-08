# T3.33 — quatro estratégias novas para o Lab: descoberta, escolha e contrato

**Autor:** quant-engineer. **Data:** 2026-09-08. **Base:** `main` @ `c699d48`. **Sem código, sem commit.**
Escopo de escrita desta tarefa: este arquivo, `brief-T3.33{a,b,c,d}-*.md` e `exp-drafts/EXP-000{8,9,10,11}-*.md`.

> **Pedido do Everton (2026-09-08):** "acha mais 4 estratégias no mercado e valide". "Validar" aqui é
> o que D14/D15 e `docs/plans/REPLICATION.md` já definem — replay de 31 dias no dia um, coorte
> prospectiva depois, 100 desfechos avaliáveis **E** 30 dias distintos para sair de `inconclusivo`.
> Nada nesta tarefa chega à carteira; nada nesta tarefa é ativado.

---

## 1. O que o motor deixa uma estratégia ver — medido, não suposto

Antes de escolher candidatas eu li o contrato e **medi** os limites. Estes seis fatos derrubaram
metade da lista sugerida no brief, e nenhum deles é opinião.

### 1.1 O fecho do `code_ref` é a restrição dominante

`hunter_strategy_worker.code_ref.version_code_ref` congela cada versão com o digest do módulo dela
**mais o fecho transitivo dos irmãos que ela importa**. Medido neste build:

```
momentum_v1        ('aggregate','base','canonical','envelope','indicators','momentum_v1','numeric','schema')
                   hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c
volume_anomaly_v1  ('aggregate','base','canonical','envelope','indicators','numeric','schema','volume_anomaly_v1')
                   hunter_core.strategies.volume_anomaly_v1@sha256:9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22
```

Prova de isolamento (cópia da pasta em `%TEMP%\ph33b`, módulo novo `session_orb_v1.py` acrescentado,
`registry.py` e `constraints.py` editados):

```
momentum_v1       hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c
volume_anomaly_v1 hunter_core.strategies.volume_anomaly_v1@sha256:9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22
```

— **byte a byte iguais aos de produção.** Prova do contrário (mesma cópia, um comentário
acrescentado a `base.py`):

```
momentum_v1       hunter_core.strategies.momentum_v1@sha256:31a11c1bc468e3c19eec792377e7a2c6b32e5ac4fbcde7cff58b87a755173703
volume_anomaly_v1 hunter_core.strategies.volume_anomaly_v1@sha256:3a129cf30c7d9e5624d67b24a40b04c325bb24c9667a40028cee0d766f8613aa
```

**Consequência, e ela é a regra de projeto de toda esta tarefa:** um módulo novo pode **importar**
`aggregate`, `base`, `indicators`, `schema`, `envelope`, `canonical`, `numeric` à vontade, e **não
pode editar nenhum deles**. Editar qualquer um re-congela as duas versões vivas (inclusive a linha
`paper`) e o Lab inteiro emudece atrás de um `/ready` verde. `registry.py` e `constraints.py` estão
**fora** do fecho e podem receber linhas novas.

Toda função auxiliar nova (razão de contração, z-score, resolução de sessão) mora **dentro do
módulo da estratégia**, nunca em `indicators.py`.

### 1.2 O que `StrategyContext` carrega, e só

`candles_1m` (1 min, finais, cortadas em `source_bar_close`), `funding: NormalizedFunding | None`
(**uma** observação, não série), `open_interest: NormalizedOpenInterest | None`, `eligible`,
`eligibility_reason`, `exchange`, `symbol`, `source_bar_close`. **Mais nada.**

Não há: livro, trades, `taker_buy_volume` (o `Bar` de `aggregate.py` tem só OHLCV), liquidações,
preço spot, outro mercado, regime, β, score de oportunidade, histórico de funding, histórico de OI.

### 1.3 No replay — que é a evidência do dia um — `open_interest` é sempre `None`

`ReplayHotState.hgetall` devolve `{}` e `_resolve_open_interest` só confia no `oi_ts` do hot state
(o `ts` durável é um balde de rodada de poll e nunca prova `<= cut`). Logo, num replay, **toda**
leitura de OI é `timestamp_unprovable`. Qualquer candidata que dependa de OI não tem evidência de
dia um — só coleta prospectiva, meses.

### 1.4 `funding` existe no replay, mas é a liquidada, e sem `index_price`

No replay o funding vem de `funding_rates` (liquidação, `funding_kind = "realized"`, `ts` = instante
da liquidação), até ~8 h de idade. **`index_price` nunca é preenchido** — nem o caminho durável nem o
do hot state passam o campo ao construir `NormalizedFunding`. Portanto `mark − index` (o prêmio
contra o índice, candidata #13 do [[Strategy Backlog]]) **não é alcançável a partir do contexto**,
mesmo tendo coluna no banco.

### 1.5 Spot não entra no contexto, e forçá-lo custa as duas versões vivas

O caminho spot (PIPELINE §1d) persiste velas com `market_type = SPOT`, mas `StrategyContext` tem um
único par `(exchange, symbol)` e o validador recusa vela de outro símbolo — e o spot da Binance usa
`exchange = "binance"` e `symbol = "BTCUSDT"`, **os mesmos**, então velas spot passariam a checagem
de identidade e colidiriam por `open_time` com as perpétuas. Um campo `spot_candles_1m` é a única
forma correta, e ele mora em `base.py` → §1.1 → re-congela `momentum_v1` e `volume_anomaly_v1`.

### 1.6 A janela de contexto é de 26 horas

`ShadowConfig.context_minutes = 1560` (env `SHADOW_CONTEXT_MINUTES`). É um botão **do worker**,
compartilhado por todas as versões, e subi-lo encarece cada barra de todo mundo (inclusive do
replay). Toda janela das quatro candidatas cabe em 1560 min **sem tocar no botão** — é requisito de
aceite dos quatro briefs. Consequência: baseline sazonal de 7 dias, efeito de dia da semana e
qualquer média longa de 1 h estão fora por construção.

E `aggregate()` exige **todos** os minutos da janela: um minuto faltando torna a janela inteira
`gap`. Janela maior = menos cobertura, não só mais aquecimento.

---

## 2. Shortlist — as 8 do brief, mais duas que apareceram na leitura

Custo assumido do Lab (SHADOW-LAB §3): spread 2 bps total + slippage 5 bps/lado dentro dos preços
(`a = 6 bps/lado`) e taxa 4 bps/lado fora deles. "Sensibilidade a custo" abaixo usa a taxa de acerto
de equilíbrio calculada em §4.

| # | Candidata | Fonte citada | Edge alegado e por que poderia existir | Dado exigido (temos?) | Long-only? | Freq./mercado-dia | Falha principal | Sens. a custo (KB-0008) | Veredito |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **Reversão em funding extremo** (comprar o lado do funding negativo) | Material de corretora/newsletter (Kraken Learn, Bitsgap, Nexo); doc. Binance de teto/piso e cadência — [[KB-0023]] | Estrutural: quem paga funding está alavancado; funding negativo forte = vendidos aglomerados, e uma alta pequena começa a liquidá-los | `ctx.funding.funding_rate` ✔ (liquidada, ≤ 8 h de idade, disponível no replay). **Não** precisa de histórico se o limiar for absoluto | **sim** — a metade negativa é exatamente a metade comprada; a metade positiva ("vender") é descartada por decisão do Everton (SPOT, long-only) | baixa (~0,05–0,3) | funding é variável **limitada** (satura no teto/piso) e a cadência muda para 1 h ao saturar — quem lê só a taxa não vê o regime; amostra dependente entre mercados | média (stop largo dilui o custo: equilíbrio 46,7 % a ATR% 0,6 %) | **ESCOLHIDA (d)** |
| 2 | **Divergência de base spot–perp** (prêmio) | Literatura de cash-and-carry; [[KB-0021]], [[KB-0022]] | Estrutural: o prêmio do perpétuo sobre o spot/índice mede posicionamento e tem de convergir na liquidação | `index_price` ✘ (**nunca preenchido**, §1.4) · velas spot ✘ (**não estão no contexto**, §1.5) | sim | — | — | — | **REJEITADA** — exige campo novo em `base.py`, que re-congela as duas versões vivas (§1.1). Vira brief próprio: coletor + extensão de contexto + `--supersede` das duas |
| 3 | **Rompimento após compressão de volatilidade** (squeeze + RVOL) | Weinstein / O'Neil (CANSLIM) / Minervini (VCP), via [[KB-0053]]; Bollinger squeeze e Donchian como formalizações públicas | Comportamental/estrutural: a base comprime porque a oferta secou; a expansão que a segue é o desequilíbrio resolvendo-se | velas 1 m ✔ (janela 510 min) | sim | ~0,3–1 | a apresentação clássica é **retrospectiva sobre ações que subiram** — viés de seleção puro; e o piso absoluto `atr_pct_min` pode brigar com a medida relativa ([[KB-0035]]) | baixa se o alvo for assimétrico (equilíbrio 44,0 % em 1,25/2,5 a ATR% 0,5 %) | **ESCOLHIDA (a)** |
| 4 | **Reversão curta em tendência de 1 h** (z-score do fechamento; RSI(2)) | Connors & Alvarez (RSI(2)); [[KB-0002]] (reversão intradiária em cripto) | Comportamental: fluxo impaciente empurra o preço além do valor em minutos e ele volta; a tendência de 1 h dá a direção | velas 1 m ✔ (alcance 1 305 min) | **sim** por construção (só a ponta comprada) | ~0,5–2 | a geometria natural (alvo < stop) é **inviável a custo nosso**: equilíbrio 86,7 % a ATR% 0,3 % (§4) | **alta** — é a candidata mais sensível a custo das quatro | **ESCOLHIDA (b)** |
| 5 | **Rompimento da faixa de abertura por sessão** (Ásia/Europa/EUA em horário de Brasília) | Crabel (ORB); Zarattini & Aziz (2023), estratégia intradiária de momentum no S&P; [[KB-0009]], [[KB-0032]] | Estrutural: participação e informação chegam em blocos horários; a primeira hora fixa a faixa que o resto da sessão testa | velas 1 m ✔ + `ctx.source_bar_close` (o relógio **está** no contexto, então a regra continua pura) ✔ | sim | ~0,3–1 | cripto é 24/7: "sessão" é convenção nossa, e [[KB-0032]] já mostrou que o relógio está dentro dos nossos limiares sem ninguém ter decidido isso | média; depende do tamanho da faixa — por isso o alvo é em R, não em ATR (§4) | **ESCOLHIDA (c)** |
| 6 | **Momentum transversal** (decil de topo do retorno 24 h, ajustado por β) | Jegadeesh & Titman; [[KB-0001]], [[KB-0034]]; parte transversal da Presto ([[KB-0022]]) | Comparativo: o vencedor relativo continua vencendo dentro do universo | **impossível hoje**: `Strategy.evaluate(ctx, params)` vê **um** mercado; não há ranking, carteira, nem β no contexto | sim | — | — | — | **REJEITADA** — não é falta de dado, é falta de **protocolo**: exigiria uma segunda interface (`evaluate_universe`) e um Lab com carteira |
| 7 | **Efeito overnight / fim de semana** | Literatura de sazonalidade em ações; adaptações em cripto | Comportamental: liquidez fina fora do horário comercial | dia da semana e hora ✔, mas a **baseline** por dia/hora exige > 26 h de contexto ✘ (§1.6) | sim | ~0,1 | em cripto não há "overnight": o que sobra é hora do dia, que é a #5 com outro nome | — | **REJEITADA** — absorvida pela #5, e a versão com baseline não cabe em `context_minutes` |
| 8 | **Repique de cascata de liquidação** | [[KB-0017]] (nosso coletor por amostragem); folclore de praticante | Estrutural: venda forçada empurra o preço abaixo do valor e ele repica | `liquidations` ✘ — **não existe campo nenhum** em `StrategyContext`, e a série é amostrada e com semântica `q`/`z` ainda por corrigir | sim | ~0,05 | mede-se o coletor, não o mercado | — | **REJEITADA** — precisa de campo novo em `base.py` (§1.1) **e** do conserto do coletor. Brief separado |
| 9 | *(acréscimo meu)* **Perda falsa de suporte / recuperação** (sweep + reclaim) | Wyckoff (spring); Cartea, Jaimungal & Wang sobre caça a stops | Estrutural: stops abaixo do suporte são liquidez; quem os varre precisa recomprar | velas 1 m ✔ | sim | ~0,3 | é a mesma família de reversão da #4 — duas tentativas no mesmo eixo | alta | **REJEITADA** — sobrepõe o eixo da #4; fica como primeira suplente |
| 10 | *(acréscimo meu)* **Família de lookback Donchian 10/20/40** | [[KB-0003]] (data snooping em rompimento de canal) | Trend-following clássico | velas 1 m ✔ | sim | ~1–3 | é **reparametrização** do núcleo do `momentum_v1`; três braços sobre a mesma população, que é exatamente o que [[KB-0010]] proíbe gastar | igual ao pai | **REJEITADA** — já está na fila do backlog (#5) como variante de parâmetro, não é estratégia nova |

---

## 3. As quatro escolhidas

Diversidade de eixo, com a honestidade de dizer que **o eixo transversal ficou vazio** porque o
protocolo não o admite (§2, #6).

| Brief | Família (`strategies.key`) | Módulo | Eixo | Invalidação | Geometria |
|---|---|---|---|---|---|
| **T3.33a** | `breakout` (já semeada) | `breakout_v1.py` | tendência / regime de volatilidade | `close_below(base_low)`, **estritamente acima do stop** | 1,25 ATR / 2,5 ATR |
| **T3.33b** | `mean_reversion` (já semeada) | `mean_reversion_v1.py` | reversão à média | **nenhuma** (só stop, alvo, horizonte) | 1,0 ATR / 1,5 ATR |
| **T3.33c** | `session_orb` (**nova** em `seed_reference.py`) | `session_orb_v1.py` | calendário / estrutura intradiária | **nenhuma** (o stop é a mínima da faixa) | stop = mínima da faixa; alvo = 2 R |
| **T3.33d** | `derivatives` (já semeada) | `derivatives_v1.py` | carry / posicionamento estrutural | **nenhuma** | 2,0 ATR / 3,0 ATR |

**Três das quatro não precisam de linha nova no catálogo de referência** — `breakout`,
`mean_reversion` e `derivatives` já existem em `infra/scripts/seed_reference.py` como `draft`, e
`catalogue.registry_key(key, version)` resolve `("breakout","v1") -> "breakout_v1"`. Só
`session_orb` é família nova.

### Por que estas quatro, uma frase cada

- **a `breakout_v1`** — é o único jeito de perguntar "a contração **antes** do rompimento seleciona
  alguma coisa?" com o dado que já temos, e [[KB-0053]] já deixou as três decisões de instrumento
  fechadas (estimador declarado, janelas terminando em `t−1`, barra do rompimento fora).
- **b `mean_reversion_v1`** — o Lab só sabe comprar força; sem uma versão que compre fraqueza, toda
  perda medida é confundida com "o mercado caiu". É o contraste que falta.
- **c `session_orb_v1`** — [[KB-0032]] e [[KB-0035]] já mostraram que **o relógio está dentro dos
  nossos limiares sem ninguém ter decidido isso**; esta versão põe o relógio na regra, declarado,
  onde ele pode ser refutado.
- **d `derivatives_v1`** — é a afirmação mais repetida do mercado e a menos testada ([[KB-0023]]:
  nenhum teste com método foi localizado), e é a única do conjunto que não é preço puro.

### A divergência que eu preciso declarar contra a nossa própria base

[[KB-0022]] recomenda **não gastar braço de sombra com funding**. Eu escolhi a (d) mesmo assim, e o
motivo é que a recomendação dela é sobre **funding como filtro direcional acoplado ao momentum**,
com prior desfavorável vinda de um estudo que mede a **variação** semanal da taxa no BTC. A (d) é
outra pergunta: **nível negativo** da taxa liquidada como estado de posicionamento, com gatilho de
preço próprio e grupo de controle no próprio replay. [[KB-0023]] diz textualmente que a versão
implementável do folclore ("comprar quando o funding está extremamente negativo") **nunca foi
testada com método** nas fontes consultadas. Se o replay de dia um devolver menos de 20 decisões nos
quatro mercados, a candidata morre ali, e terá custado uma corrida de replay. É o teste mais barato
da lista.

---

## 4. Geometria — a aritmética que escolheu os alvos, não o gosto

Com `a = 6 bps/lado` dentro dos preços e `f = 4 bps/lado` fora, referência `C`, `ATR = v·C`,
`stop = C − s·ATR`, `alvo = C + t·ATR`, entrada na abertura igual à referência (melhor caso):

```
R_net   = (P_exit − P_entry − f(P_entry + P_exit)) / (P_entry − stop)
P_entry = C(1+a)      P_exit = base(1−a)          (SHADOW-LAB §3)
```

Saída de `uv run python` (§8):

| geometria | ATR% | R_net no alvo | R_net no stop | acerto de equilíbrio |
|---|---:|---:|---:|---:|
| `momentum_v1` 1,5/1,5 | 0,003 | 0,4893 | −1,2736 | **0,7224** |
| `momentum_v1` 1,5/1,5 | 0,010 | 0,8324 | −1,0888 | 0,5667 |
| **(b) 1,5/1,0** (a geometria "natural" de reversão) | 0,003 | 0,1955 | −1,2736 | **0,8669** |
| **(b) 1,5/1,0** | 0,010 | 0,5122 | −1,0888 | 0,6801 |
| **(b) escolhida 1,0/1,5** | 0,006 | 1,0592 | −1,2112 | **0,5335** |
| **(b) escolhida 1,0/1,5** | 0,008 | 1,1614 | −1,1619 | 0,5001 |
| **(a) escolhida 1,25/2,5** | 0,005 | 1,5310 | −1,2035 | **0,4401** |
| **(a) escolhida 1,25/2,5** | 0,010 | 1,7538 | −1,1059 | 0,3867 |
| **(d) escolhida 2,0/3,0** | 0,006 | 1,2684 | −1,1102 | **0,4667** |
| **(d) escolhida 2,0/3,0** | 0,010 | 1,3578 | −1,0670 | 0,4400 |

Três conclusões que viraram regra de projeto:

1. **Alvo simétrico é uma aposta cara.** A 1,5/1,5 no piso de ATR% de hoje (0,003) o equilíbrio é
   **72,2 %** de acerto. Nenhuma das quatro repete essa geometria.
2. **A geometria natural da reversão à média é inviável no nosso custo.** Alvo menor que o stop
   (1,5/1,0) pede **86,7 %** de acerto no piso e 68,0 % a 1 % de ATR. A (b) inverte: risco 1 ATR,
   alvo 1,5 ATR, e sobe o piso de ATR% para 0,6 %.
3. **Com stop dado pelo dado (a mínima da faixa, na (c)), o alvo tem de ser em R, não em ATR.**
   Com alvo fixo de 2 ATR o equilíbrio varia de 28,0 % (faixa de 0,5 ATR) a 62,5 % (faixa de 2 ATR)
   — duas estratégias com um nome só. Com alvo em **2 R constantes**:

| risco da faixa (ATR) | ATR% | R_net no alvo | R_net no stop | equilíbrio |
|---:|---:|---:|---:|---:|
| 0,4 | 0,004 | 0,5440 | −1,6356 | 0,7504 |
| 1,0 | 0,006 | 1,5133 | −1,2112 | **0,4446** |
| 1,5 | 0,010 | 1,7929 | −1,0888 | 0,3778 |

   — e é essa tabela que fixa `range_risk_atr_min = 1,0` na (c): abaixo disso o custo come a operação
   antes de o mercado opinar.

### E a evidência de MFE/MAE que o brief pediu (T3.32 ainda não existe)

`.claude/state/notes-T3.32.md` **não existia** quando escrevi isto. Usei no lugar a única
decomposição pareada que temos, o replay de 31 dias de `momentum v2` em
[[EXP-0006-momentum-piso-de-custo]] (4 mercados, `as_of = 2026-09-08T13:09:41Z`):

```
224 sinais · 222 avaliáveis · expectancy −0,1717 R · PF 0,6454
target 91 (+0,7599 R médio) · stop 45 (−1,1883 R) · invalidated 82 (−0,6462 R) · expired 6
```

Aritmética minha sobre esses números, e ela é o achado que desenhou as quatro invalidações:

- só os **toques resolvidos** (91 alvos + 45 stops) dão
  `0,669 × 0,7599 + 0,331 × (−1,1883) = +0,115 R` por toque — o par entrada/stop/alvo do
  `momentum` é **positivo** nessa janela;
- os **82 invalidados** (36,6 % das 224 decisões, média −0,6462 R) somam **≈ −53 R**, e é onde a
  expectancy inteira vai embora.

É exatamente a fronteira que [[KB-0006]] mandou não atravessar: aquele número é **atribuição
contábil, não efeito** — sem as invalidações, aqueles 82 acompanhamentos continuariam até stop,
alvo ou expiração, com resultado desconhecido. Mas é evidência suficiente para uma decisão de
**projeto** (não de conclusão): **nenhuma das quatro novas repete a invalidação do `momentum`**
(fechar abaixo do nível de rompimento, isto é, poucos ticks abaixo da própria entrada). Duas não
têm invalidação nenhuma; a (a) tem uma invalidação **estrutural** (a mínima da base de compressão)
com guarda de geometria obrigando `stop < base_low < referência`, para que ela nunca seja código
morto nem um stop disfarçado; a (c) transforma a estrutura em **stop**, que é o que
`volume_anomaly_v1` já faz com a mínima da barra do pico.

**Isto não substitui o experimento pareado `INV-A/B/C/E`** de [[KB-0006]] / `brief-T3.27`: quatro
estratégias diferentes com políticas de saída diferentes são um contraste **observacional e
confundido** (populações diferentes, entradas diferentes, slots diferentes). Está dito nos quatro
EXP e é a ressalva mais importante desta tarefa.

---

## 5. Plano de validação comum às quatro

Idêntico nos quatro briefs; escrito uma vez aqui.

### 5.1 Dia um — replay de 31 dias, e o que já mata a candidata

Depois da ativação como `research_only`, na VPS, **sem tocar em carteira**:

```bash
docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.run \
  --version <key>:v1 --from 2026-08-08 --to 2026-08-23 \
  --markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT --workers 3 \
  --cohort replay:<uuid> --ledger /tmp/replay-<key>-v1.jsonl
# e a segunda fatia 2026-08-23 -> 2026-09-08 com a MESMA coorte
```

Fatiar em duas metades contíguas com a mesma coorte é o que a EXP-0006 fez e é o formato que o
recibo do livro-razão espera. Referência de custo medida: 11 904 barras (= 31 × 96 × 4) a ~65
barras/s com 3 workers ≈ 183 s por versão; **as quatro juntas ≈ 12 min**.

**Critérios de morte no dia um** (congelados antes de rodar, e a ordem importa):

| # | Leitura no replay de 31 dias × 4 mercados | Decisão |
|---|---|---|
| K1 | **< 20 decisões** | a regra não dispara: **deprecar**. Não é "amostra pequena", é ausência de população, e mais 30 dias não a criam |
| K2 | **> 1 500 decisões** (> ~1,2/mercado-dia) | a regra dispara em quase toda barra: não é uma condição, é um relógio. Deprecar ou re-especificar como versão nova |
| K3 | **≥ 100 desfechos avaliáveis E ≥ 30 dias distintos E expectancy bruta (`r_ex_funding`) < 0** | **deprecar**: com a régua editorial cumprida no próprio replay e o resultado negativo **antes de funding**, não há custo a corrigir |
| K4 | `unavailable` > 40 % das barras | problema de janela/gap, não de estratégia: corrigir a janela é **versão nova**, não ajuste |
| K5 | cobertura de `R_net` < 70 % (funding não apurável) | reportar por `r_ex_funding` e **declarar**; não mata, mas rebaixa toda leitura futura |

K3 é o único que usa expectancy, e usa a **bruta**: uma candidata que perde antes dos custos não é
salva por nenhum piso. Uma que perde só depois dos custos é candidata a variante de geometria, e
isso é experimento novo, não conserto.

Rótulo obrigatório em todo número do dia um: **REPLAY, não coleta prospectiva**. Ele não confirma
nada — é a mesma janela que gerou a hipótese ([[KB-0010]]).

### 5.2 Prospectivo

Coorte `prospective`, universo inteiro, ao lado das versões existentes. Régua do placar (T3.18,
`SHADOW-LAB.md` §9 e `REPLICATION.md` §2):

```
madura   = avaliáveis >= 100 E dias_distintos >= 30
validada = madura E expectancy_r > 0 E profit_factor > 1     (desigualdades estritas)
```

Antes de madura, o `Result` é **`inconclusivo`**, quaisquer que sejam os números.

### 5.3 Maturidade e replicação

`validada` pela primeira vez = **`promissora`**, que é o começo do protocolo, não a conclusão
(`REPLICATION.md` §2). Aí correm os quatro blocos: fora da amostra no tempo (só `prospective`),
irmãs de parâmetro (podem amadurecer por replay pela meia-régua, **rotuladas**, D15), metades de
mercado e bootstrap. `real` exige os quatro concordando; um bloco maduro que falha = `refutada`.

### 5.4 O que o conjunto das quatro **não** prova

- **Não é um experimento sobre política de saída.** Duas sem invalidação, uma com invalidação
  estrutural e uma com stop estrutural são quatro populações diferentes. O contraste pareado é o
  `brief-T3.27` (`INV-A/B/C/E` sobre as mesmas entradas).
- **Multiplicidade.** Quatro versões novas de uma vez são quatro tentativas ([[KB-0010]]). Cada uma
  entra em `Registro de Tentativas` com data de início **antes** da primeira barra, e o veredito de
  cada uma é lido sabendo que houve quatro.
- **Elegibilidade histórica.** O replay lê `markets.is_monitored` **de hoje**; o conjunto replayado
  não é o da janela (`provenance.eligibility_observed_at`).
- **Mistura de slot.** Toda versão nova compete pelo mesmo espaço de "um acompanhamento por
  (versão, mercado, coorte)". A EXP-0006 mostrou que 100 % da diferença de expectancy entre pai e
  variante veio de **6 decisões que o pai nunca tomou** porque o slot estava ocupado. Comparações
  entre as quatro têm de dizer isso.

---

## 6. Ativação — só o operador, e só na VPS

Nenhum dos quatro briefs ativa nada. A sequência, quando o operador quiser:

```bash
# 1. semear o catálogo (só a (c) precisa: 'session_orb' é família nova)
docker exec -i hunter-api-1 python - < infra/scripts/seed.py
# 2. ativar a versão (congela code_ref, parameters_schema, default_parameters — irreversível)
docker exec -i hunter-api-1 python - <key> v1 \
  --changelog 'T3.33<x>: coorte de pesquisa aberta (research_only, sem carteira)' \
  < infra/scripts/activate_strategy_version.py
```

`--dry-run` primeiro, sempre. `purpose` nasce `research_only`; a ponte de execução recusa por nome.
**Nenhuma das quatro pede `--paper-line`.**

---

## 7. Arquivos escritos por esta tarefa

```
.claude/state/notes-T3.33.md                                  (este)
.claude/state/brief-T3.33a-breakout_v1.md
.claude/state/brief-T3.33b-mean_reversion_v1.md
.claude/state/brief-T3.33c-session_orb_v1.md
.claude/state/brief-T3.33d-derivatives_v1.md
.claude/state/exp-drafts/EXP-0008-breakout-compressao-de-volatilidade.md
.claude/state/exp-drafts/EXP-0009-mean-reversion-pullback-em-tendencia.md
.claude/state/exp-drafts/EXP-0010-session-orb-faixa-de-abertura.md
.claude/state/exp-drafts/EXP-0011-derivatives-reversao-de-funding.md
```

`EXP-0007` fica **reservado** para o experimento de invalidação do `brief-T3.27` (`momentum v2`),
que estava na fila antes desta tarefa.

---

## 8. Comandos rodados nesta tarefa (leitura e aritmética; nada escrito no repo)

```
$ uv run python -c "from hunter_strategy_worker.code_ref import module_closure, version_code_ref; ..."
momentum_v1 ('aggregate','base','canonical','envelope','indicators','momentum_v1','numeric','schema')
   hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c
volume_anomaly_v1 ('aggregate','base','canonical','envelope','indicators','numeric','schema','volume_anomaly_v1')
   hunter_core.strategies.volume_anomaly_v1@sha256:9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22

$ # cópia em %TEMP%\ph33b + session_orb_v1.py novo + registry.py e constraints.py editados
momentum_v1 hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c
volume_anomaly_v1 hunter_core.strategies.volume_anomaly_v1@sha256:9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22

$ # cópia em %TEMP%\ph33 com um comentário acrescentado a base.py
momentum_v1 hunter_core.strategies.momentum_v1@sha256:31a11c1bc468e3c19eec792377e7a2c6b32e5ac4fbcde7cff58b87a755173703
volume_anomaly_v1 hunter_core.strategies.volume_anomaly_v1@sha256:3a129cf30c7d9e5624d67b24a40b04c325bb24c9667a40028cee0d766f8613aa

$ uv run python -c "... Timeframe / align_open_time ..."
Timeframe: ['1m', '5m', '15m', '1h', '4h', '1d']
align H1 2026-09-08 13:00:00+00:00 secs 3600
```

As três tabelas de geometria de §4 vêm de `geom.py`/`geom2.py`/`geom3.py`/`geom4.py` em
`%TEMP%\ph33` (aritmética em `Decimal`, `prec = 28`), reproduzidas nos quatro EXP.

**Nota de contrato:** o brief da tarefa cita `packages/core/hunter_core/strategies/seed.py`. Esse
arquivo **não existe**; o registro de uma chave de estratégia acontece em
`infra/scripts/seed_reference.py` (tupla `STRATEGIES`) + `infra/scripts/seed.py`
(`seed_strategies`), e a resolução DB→código em
`services/strategy-worker/hunter_strategy_worker/catalogue.py` (`registry_key`). Os quatro briefs
apontam para os arquivos reais.
