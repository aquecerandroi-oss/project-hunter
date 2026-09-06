---
tags: [knowledge, backlog, estrategias]
updated: 2026-09-06
---

# Backlog de estratégias (candidatas ao Shadow Lab)

Fila ordenada de ideias que o conhecimento externo e as falhas observadas no Lab sugerem. **Nada aqui está ativo.** Uma candidata só vira experimento pelo caminho normal: brief → código de `Strategy` → revisão (quant cruzado, code-reviewer, Astra) → ativação auditada → `EXP-xxxx`. Dinheiro real não entra nesta página.

Status: `ideia` → `especificada` (parâmetros e regra fechados) → `sombra` (EXP aberto) → `avaliada` (100 outcomes E 30 dias) → `descartada` ou `promovida ao M4`.

**Antes de rodar qualquer linha desta tabela, ela entra em [[Registro de Tentativas]] com data de
início e fim.** Todas as candidatas abaixo nasceram da inspeção da coorte de 2026-09-06, então
**nenhuma pode ser confirmada nessa mesma população** — a confirmação exige janela futura reservada
([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]).

## Features do M2 disponíveis (verificado em 2026-09-06)

`return_1m/5m/15m/1h/4h` (+ `_live` de 1m/5m/15m/1h) · `distance_from_24h_high` ·
`distance_from_24h_low` · `atr_14_pct` · `momentum_15m` · `momentum_acceleration` ·
`breakout_strength_20` · `relative_volume_5m/15m/1h` · `volume_acceleration` · `funding_rate` ·
`funding_change_8h` · `open_interest_change_1h/4h` · `spread_pct` · `orderbook_imbalance_*` ·
`buy/sell_pressure_*` · `trade_velocity_*`. Nas velas: `volume` e `taker_buy_volume`.
**`return_24h` não existe.**

> **Correção de 2026-09-06 (terceira rodada), e ela invalida parte da lista acima:**
> `funding_change_8h`, `open_interest_change_1h` e `open_interest_change_4h` **estão registradas mas
> não computam em produção** — `load_deriv_history` não tem chamada, então `Scanner.deriv_history`
> fica sempre vazio e as três retornam `missing_input` em toda barra
> ([[KB-0020-funding-change-8h-nunca-calcula]]). `funding_rate`, `mark_price` e `index_price`
> **computam** (dependem só do snapshot do hash `deriv`). O detector `OPEN_INTEREST_SPIKE` está
> **armado e mudo**; o `FUNDING_ANOMALY` mede **distância da mediana**, não extremo absoluto.

**Acréscimos verificados em 2026-09-06 (segunda rodada de conhecimento):**
`taker_buy_volume` tem **cobertura de 100%** no banco (519.422 velas de 1 min, 222 mercados) mas é
**descartado na agregação 1m→5m** (`aggregate.py:40,77`) — usá-lo exige carregar o campo no `Bar`.
`buy/sell_pressure_*` e `trade_velocity_*` deixaram de estar bloqueados por `covered_until` (o
publicador e o consumidor existem: `market-worker/coverage.py:153`, `scanner-worker/context.py:96`),
mas a **disponibilidade operacional não foi medida**. A tabela `liquidations` **já tem dados**
(8421 linhas, 197 mercados) e o notional dela tem defeito de semântica ([[Open Bugs]]). O **ranking
do mercado no instante da decisão não está no envelope** de nenhum sinal.

## Fila

| # | Candidata | Notas-fonte | Dado necessário (temos?) | Esforço | Edge esperado e evidência | Status |
|---|---|---|---|---|---|---|
| 1 | **Valor incremental da invalidação** — braços `INV-A/B/C/E` (atual · sem invalidação · dois fechamentos · buffer de 0,25 ATR) | [[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]] · [[KB-0005-stops-quando-eles-param-perdas]] | velas 1m/15m (sim) · ATR₀ congelado (sim) | médio (4 braços + replay) | **desconhecido.** Os −13,8430 R dos 24 invalidados são atribuição contábil, não efeito; o ganho exige contrafactual pós-saída | especificada |
| 2 | **Piso de custo** — `atr_pct_min = 0,0089` | [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] | `atr_pct_15m` da decisão (sim) | baixo | pressão de custo é **aritmética**: no piso atual 20 bps consomem 39,2% de 1 R efetivo. Que o piso maior melhore expectancy é hipótese | especificada, exige janela futura |
| 3 | **Diagnóstico por decil de ATR%** (análise, não variante) | [[KB-0007-atr-e-escala-por-volatilidade]] | `atr_pct_15m` persistido (sim) | baixo | nenhum edge prometido; descobre se a estratégia depende de faixa de volatilidade | especificada |
| 4 | **H1 timing + H2 atraso de execução** (`baseline + 60 s`) | [[KB-0009-o-efeito-do-quarto-de-hora]] | velas 1m com `taker_buy_volume` (existe; **cobertura a conferir**) | baixo (H1) / médio (H2) | artigo mede ~0,5 bps brutos em 10 s — serve para execução, não como estratégia | ideia |
| 5 | **Família de lookback 10/20/40** | [[KB-0003-rompimento-de-canal-e-data-snooping]] | velas 15m (sim) · 3 `strategy_version_id` | médio | canal breakout tem evidência histórica, muito enfraquecida por data snooping e custos | ideia |
| 6 | **Gate de tendência** `return_4h > 0` | [[KB-0001-momentum-academico-e-o-que-nao-se-transfere]] | `return_4h` (sim) | baixo | transferência de horizonte **não demonstrada**; risco alto de só encolher amostra | ideia |
| 7 | **Impulso recente excessivo** `momentum_15m ≤ 2,0` | [[KB-0002-momentum-e-reversao-em-cripto]] | `momentum_15m` (sim) | baixo | reversão intradiária em cripto existe na literatura, mas não neste recorte; `K=2` é escolha experimental | ideia |
| 8 | **Proximidade da máxima de 24 h** `distance_from_24h_high ≥ −0,005` | [[KB-0004-proximidade-da-maxima-e-confirmacao-por-volume]] | `distance_from_24h_high` (existe, mas **não está no envelope da v1**) | baixo + medição prévia | George & Hwang é mensal e transversal em ações; extrapolação declarada | bloqueada pela medição de redundância |
| 9 | **Valor incremental do stop** — braços `STOP-A/B/C` | [[KB-0005-stops-quando-eles-param-perdas]] | velas 1m (sim) | médio | prêmio de parada depende do processo; passeio aleatório sozinho não implica que o stop custe | ideia |
| 10 | **Alvo assimétrico** (alvo > stop) | [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] | — | médio | separada de propósito: muda acertos, exposição, invalidações e funding ao mesmo tempo | ideia |
| 11 | **Desequilíbrio agressor na barra do sinal** (`taker_imbalance_5m ≥ θ`) — precedido de **observar sem decidir** | [[KB-0014-taker-buy-volume-o-que-temos-medido]] | `taker_buy_volume` nas velas de 1 min (**sim**, cobertura de 100% medida); exige carregar o campo no `Bar` de `aggregate.py` | baixo (observação) / médio (braço) | evidência **direcional observada**, não inferida — é o que os dois filtros de preço da `volume_anomaly_v1` não conseguem ver. Utilidade **não demonstrada** | ideia — o θ sai da distribuição **condicionada a pico**, ainda não medida |
| 12 | **Teto de volume** (`volume_mult_max`, além do piso de 4) | [[KB-0015-volume-relativo-e-o-pico-como-exaustao]] | `volume_ratio_5m` no envelope (sim) | médio | **nenhum edge prometido.** Exaustão é explicação compatível, não identificada; o valor 12 é exploratório e sem sustentação | ideia, dependente do diagnóstico H-KB0015a |
| 13 | **Prêmio contra o índice** — `last_index_basis_fraction` e `mark−index` como medidas **distintas**, primeiro só observadas | [[KB-0021-funding-como-preco-de-posicionamento-nao-como-previsao]] | `price`, `mark_price`, `index_price` (sim, no `deriv` e em `market_snapshots`; `index_price` é *nullable*) | baixo (observação) | **nenhum edge prometido.** O carry tem evidência revisada em horizonte de dias a meses; a 4 h, nada | ideia — bloqueada pelo recorte estritamente anterior (chave por minuto) |
| 14 | **OI em nível como profundidade** (não a variação) | [[KB-0024-open-interest-como-posicionamento-evidencia-e-folclore]] | `open_interest` / `open_interest_value` (sim) | médio (exige normalização entre mercados) | Bessembinder & Seguin: OI grande **associado** a menos volatilidade por unidade de volume, em futuros tradicionais dos anos 1980 | ideia |
| — | ~~**Filtro de book** `orderbook_imbalance_20 ≥ 0`~~ | [[KB-0012-ofi-nao-e-o-nosso-orderbook-imbalance]] | — | — | **retirada na própria nota**: a feature é uma razão invariante a escala e **não mede profundidade**, que era a propriedade invocada | **descartada em 2026-09-06** |
| — | ~~**Funding como filtro direcional de entrada**~~ | [[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]] | — | — | **não proposta como braço de sombra**: a melhor evidência direta (Binance USDⓈ-M, 2021–2024) mostra poder preditivo à frente ~zero por ativo; a versão transversal exige carteira e giro que o Lab não tem | **não entra na fila em 2026-09-06** — só diagnóstico |

## Diagnósticos e auditorias abertos pela segunda rodada

Nenhum destes é variante de estratégia, mas **todos contam como inspeção da amostra** e entram em
[[Registro de Tentativas]]:

| Item | Nota | O que responde | Pré-requisito |
|---|---|---|---|
| Associação `volume_ratio_5m` × resultado, com todos os modos de saída | [[KB-0015-volume-relativo-e-o-pico-como-exaustao]] | se a magnitude do pico está associada ao resultado sob a regra atual | nenhum |
| Retorno de preço a horizonte fixo, com o grupo `not_triggered` | [[KB-0011-volume-magnitude-e-a-ponte-para-direcao]] | se o volume prevê magnitude **futura**, incrementalmente aos filtros de preço | registrar as barras `volume_below_threshold`, que hoje não guardamos |
| Composição e escala do denominador de 288 barras | [[KB-0013-vpin-e-a-disputa-sobre-toxicidade]] | zeros, volumes pequenos, mediana absoluta e razão, separados | `quote_volume` para comparar mercados (é *nullable*) |
| Cobertura de `orderbook_imbalance_20` até a decisão | [[KB-0012-ofi-nao-e-o-nosso-orderbook-imbalance]] | se o book está disponível na hora certa, com a idade do snapshot | separar `insufficient_sample`/`corrupt_input`/`missing_input` |
| Cobertura e distribuição de `spread_pct` anterior à decisão | [[KB-0016-quando-o-fluxo-importa-dependencia-de-estado]] | caudas e proporção acima de 2 bps, não só mediana | bucket **inteiramente anterior** — o sampler arredonda ao minuto |
| Observabilidade da série de liquidações | [[KB-0017-liquidacoes-o-fluxo-forcado-que-observamos-por-amostragem]] | qualidade do coletor e intensidade da amostra recebida | corrigir a semântica `q`/`z`, `p`/`ap` antes de somar |
| Gaps abertos × janela do denominador | [[KB-0018-volume-relatado-e-o-denominador-que-usamos]] | se algum sinal foi emitido com gap **aberto** na janela | separar gaps abertos de recuperados |

## Diagnósticos e auditorias abertos pela terceira rodada (funding, OI, posicionamento)

**Antes de qualquer um deles, um bloqueio de instrumento que torna três features e um detector
inúteis** — e que não é diagnóstico, é conserto ou desarme honesto
([[KB-0020-funding-change-8h-nunca-calcula]]):

> `load_deriv_history` não tem chamada em produção → `Scanner.deriv_history` sempre vazio →
> `funding_change_8h`, `open_interest_change_1h` e `open_interest_change_4h` são `missing_input` em
> toda barra → `OPEN_INTEREST_SPIKE` está **armado e mudo**. Vai para [[Open Bugs]].

| Item | Nota | O que responde | Pré-requisito |
|---|---|---|---|
| Motivos de indisponibilidade das três features de derivativos, com denominador (chave ausente · valor presente · `missing_input` · `warmup` · sem vetor) | [[KB-0020-funding-change-8h-nunca-calcula]] | confirma ou refuta o bloqueio, e distingue os dois mecanismos | nenhum além do acesso ao banco |
| Contagem de disparos de `OPEN_INTEREST_SPIKE` desde o armamento | [[KB-0020-funding-change-8h-nunca-calcula]] | teste mais barato do bloqueio (previsão: zero) | nenhum |
| Mistura de `funding_kind` no instante das decisões, idade da leitura e fase do ciclo | [[KB-0019-o-que-a-nossa-funding-rate-mede-de-fato]] | se as nossas leituras de funding são estimativa em formação ou taxa liquidada | persistir os três campos no envelope |
| Cobertura de `index_price` e distribuição do prêmio contra o índice | [[KB-0021-funding-como-preco-de-posicionamento-nao-como-previsao]] | se há dispersão real ou só ruído de arredondamento | recorte **estritamente anterior** — a chave de `market_snapshots` é o minuto alinhado |
| Associação de `funding_rate` (nível, condicionado ao sinal) com o resultado | [[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]] | se o nosso recorte contraria a evidência externa | funding persistido no envelope |
| Taxa base do `FUNDING_ANOMALY` e retorno subsequente, **com grupo não disparado** | [[KB-0023-funding-extremo-como-contrarian-a-afirmacao-mais-repetida]] | se o desvio de funding tem associação, separando nível, desvio, sinal, limite e cadência | nenhum |
| Quadrantes OI × preço nos outcomes existentes, contra controle por volume agressor | [[KB-0024-open-interest-como-posicionamento-evidencia-e-folclore]] | se a leitura direcional do folclore sobrevive a quem cruzou o spread | `open_interest_history` com folga efetiva registrada |
| Disparos de um detector de OI **bilateral** e coincidência de queda de OI com `liquidations` | [[KB-0025-o-nosso-detector-de-open-interest-so-olha-para-cima]] | se a nossa amostragem de 5 min enxerga o desmonte | destravar o histórico; corrigir a semântica do `notional` |
| Duração dos acompanhamentos (`exit_ts − entry_ts`) e taxa de atravessamento explícita | [[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]] | quanto tempo ficamos expostos e quantos outcomes cruzam liquidação de verdade | separar atravessamento confirmado, inferido e indeterminado |

**Requisito de proveniência (bloqueia análise por liquidez):** gravar no envelope de cada sinal o
**ranking do mercado**, o **tamanho e a regra do universo** e o **timestamp do refresh** — hoje nada
disso está lá, e sem isso nenhuma estratificação por liquidez é defensável
([[KB-0016-quando-o-fluxo-importa-dependencia-de-estado]]).

**Observação sem decisão (não é variante, e é o passo mais barato da rodada):** persistir
`taker_imbalance_5m` no envelope imutável de todo sinal, sem alterar a decisão. Em poucos dias dá a
distribuição **condicionada a pico de volume**, que é a população que decide o θ da candidata #11.

## Ordem em que eu testaria, e por quê

1. **#3 e #4-H1 primeiro** — são diagnósticos, custam quase nada, não gastam tentativa de estratégia
   e podem tornar várias candidatas desnecessárias. #4-H1 também audita o timing real das entradas.
2. **#1 (invalidação)** — é a única candidata cuja pergunta o dado já existente consegue atacar por
   **replay** sobre as mesmas entradas, sem esperar 30 dias, e é onde o Lab mostra o maior bloco de
   perda atribuída a uma regra nossa.
3. **#2 (piso de custo)** — a pressão é aritmética e não depende de amostra; o que depende de amostra
   é o efeito da correção, e por isso ela precisa de janela futura reservada.
4. **#8 (proximidade da máxima)** só depois da medição de redundância; se a retenção for ~100%, morre
   sem gastar dia de sombra.
5. **#5, #6, #7, #9, #10** por último: cada uma é uma tentativa a mais sobre a mesma população, e
   #5 sozinha já são três braços.

### Onde a segunda rodada entra nessa ordem (2026-09-06)

0. **Antes de tudo, o que não custa tentativa de estratégia e destrava o resto:** a **observação sem
   decisão** do `taker_imbalance_5m` no envelope, e o **requisito de proveniência** do ranking do
   universo. O primeiro é o único caminho para escolher o θ da #11 sem calibrar em cima de outcomes;
   o segundo é pré-condição de qualquer leitura por liquidez, hoje impossível.
1. **Depois, os diagnósticos da tabela acima**, na ordem: associação `volume_ratio_5m` × resultado →
   composição do denominador → coberturas (book, spread, liquidações, gaps). São baratos e podem
   matar candidatas antes de gastá-las.
2. **#11 (desequilíbrio agressor)** vem antes de **#12 (teto de volume)**: a #11 acrescenta
   informação que nenhum filtro atual enxerga (quem cruzou o spread), enquanto a #12 só reparametriza
   o que já existe — e o seu valor exploratório de 12 ainda não tem sustentação.
3. **#12** só se o diagnóstico de associação apontar concentração de perdas nos picos extremos, e com
   o valor saindo da distribuição condicionada, não do meu chute.

**Lembrete de multiplicidade:** os diagnósticos do item 1 são inspeção da mesma população que gerou
as suspeitas, e portanto **exploração**. Nenhuma candidata desta rodada pode ser confirmada nessa
população ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]).

### Onde a terceira rodada entra nessa ordem (2026-09-06)

**Antes de tudo, e antes até dos diagnósticos da segunda rodada:** o bloqueio de
[[KB-0020-funding-change-8h-nunca-calcula]]. Enquanto `deriv_history` não for alimentado, três
features do M2 e um detector armado são decoração — e qualquer página que os liste como disponíveis
está errada. Consertar ou desarmar é decisão de contrato, não faxina, e não é diagnóstico: é bug.

Depois disso, na ordem, e **nenhum deles é braço de estratégia**:

1. **Os dois diagnósticos que confirmam o bloqueio** (motivos com denominador; disparos do
   `OPEN_INTEREST_SPIKE`). Custam uma consulta cada e decidem entre o caminho A e o B.
2. **Duração e atravessamento** ([[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]]).
   É a medição que impede que "0 de 173" continue sendo lido como frequência de mercado, e
   `exit_ts − entry_ts` é a consulta mais barata desta lista inteira.
3. **Observar sem decidir o funding** (`funding_kind`, idade, fase do ciclo) — mesmo padrão do
   `taker_imbalance_5m` da segunda rodada, e pré-requisito dos itens 4 e 5.
4. **Taxa base do `FUNDING_ANOMALY` com grupo de controle.** O detector já existe e nunca foi lido.
5. **Quadrantes de OI contra o controle por volume agressor.** Depende do item 1 estar resolvido.
6. **Prêmio contra o índice** (#13) e **OI em nível como profundidade** (#14) por último: são as
   duas ideias novas da rodada e as duas mais distantes de evidência aplicável ao nosso horizonte.

**O que a rodada explicitamente NÃO propõe:** funding como filtro direcional de entrada. A evidência
direta no nosso mercado aponta para poder preditivo à frente ~zero por ativo, e gastar uma tentativa
contra uma prior desfavorável é o oposto do que a
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] pede.

## Acréscimo da quarta rodada (2026-09-06) — regime de mercado e volatilidade

**Antes de qualquer coisa desta rodada, três fatos que mudam o que a página acima promete:**

> 1. **Nenhuma candidata da fila pode ser avaliada por regime.** `agent_signals.regime_id` existe e
>    nunca é escrito pelo `strategy-worker`; medido no banco local, **197 sinais, 0 com regime_id**
>    ([[KB-0030-o-regime-nao-chega-ao-sinal]]).
> 2. **E não haveria o que carimbar.** O classificador está em warm-up por construção — 480 amostras
>    horárias e 20 dias distintos contra **47 horas em 3 dias**; `market_regimes` tem **uma linha**,
>    `global`/`UNKNOWN` ([[KB-0031-o-classificador-de-regime-esta-mudo-por-warm-up]]).
> 3. **E o `global` não é global:** é o BTCUSDT. `RegimeScope.BTC` existe no enum e nunca é usado
>    ([[KB-0034-btc-como-fator-e-o-regime-global-que-e-so-o-btc]]).

**Correção que atinge uma candidata já na fila.** A #3 (diagnóstico por decil de ATR) e a #2 (piso
de custo) precisam usar o ATR que a `momentum_v1` **de fato consome** — `rolling_window_v1` sobre
15m com `atr_bars=97`, recalculado a cada avaliação — e **não** o `atr_14_pct` do
`feature_snapshots`, que é o checkpoint ancorado do M2. São dois instrumentos com o mesmo apelido
([[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]], achado da Astra).

### Novas na fila

| # | Candidata | Notas-fonte | Dado necessário (temos?) | Esforço | Edge esperado e evidência | Status |
|---|---|---|---|---|---|---|
| 15 | **Carimbo de regime no envelope** (par, `confidence`, versão, idade, `volatility_ratio`, `breadth.fraction`) — observação sem decisão | [[KB-0030-o-regime-nao-chega-ao-sinal]] | `regime:current` no Redis (sim) · coluna `regime_id` (existe) | baixo | **nenhum edge prometido.** É proveniência: sem ele, nenhuma pergunta desta rodada é respondível | especificada |
| 16 | **Fração de avanços incondicional** publicada ao lado da conjunta | [[KB-0033-amplitude-de-mercado-a-nossa-e-condicionada-a-volume]] | `return_4h`, `relative_volume_1h` (existem; **cobertura zero na instância local**) | baixo | corrige uma incoerência interna (amplitude que confunde "sem volume" com "discordando"), não promete retorno | especificada |
| 17 | **Tendência por mercado** gravada no envelope (`classify_market_trend`, que já existe e não é chamada) | [[KB-0034-btc-como-fator-e-o-regime-global-que-e-so-o-btc]] | `return_4h`, `return_1d`, `atr_pct` por mercado | baixo | permite perguntar se discordar do BTC é informativo; **nada demonstrado** | ideia |
| 18 | **Referência de volatilidade por hora UTC** | [[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]] | 20× mais história do que temos | alto | seria `regime_v1`; a alternativa barata é gravar a hora e corrigir na análise | **bloqueada por amostra** |
| — | ~~**Escalar exposição pelo inverso da volatilidade**~~ (Barroso & Santa-Clara) | [[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]] | — | — | evidência revisada em ações mensais (Sharpe 0,53 → 0,97, número de segunda mão); **mas o Lab de sombra não dimensiona posição** e `PnL de carteira` é *não aplicável* | **adiada para o M4 em 2026-09-06**, sem gastar dia de sombra |

### Diagnósticos e auditorias abertos pela quarta rodada

| Item | Nota | O que responde | Pré-requisito |
|---|---|---|---|
| Curva do warm-up (`samples`/`distinct_days` por dia; horas rejeitadas por motivo) | [[KB-0031-o-classificador-de-regime-esta-mudo-por-warm-up]] | quando o regime acorda, e quantas horas perdemos por gap | nenhum — **o mais barato e o mais urgente** |
| Ciclo de trabalho do piso `[atr_pct_min, atr_pct_max]` por hora UTC | [[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]] | se o piso de custo é, na prática, um filtro de horário/regime | usar o ATR da estratégia, não o do M2 |
| Mediana do estimador por hora UTC e taxa de troca de faixa | [[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]] | quanto do rótulo `HIGH`/`LOW` é relógio | ≥ 20 dias, para separar hora de dia |
| Discordância de rótulo entre o nosso estimador, Parkinson e Garman-Klass | [[KB-0028-o-nosso-estimador-de-volatilidade-e-o-mais-ineficiente]] | quanto o veredito depende de uma escolha nossa (**sensibilidade**, não precisão) | OHLC de 1 min (temos) |
| Persistência do estimador horário, com poder declarado | [[KB-0027-aglomeracao-de-volatilidade-o-que-ela-licencia]] | se o `volatility_ratio` descreve estado ou ruído | ≥ 20 dias |
| Duração e transições do par `{trend, volatility}` | [[KB-0029-hamilton-e-o-que-um-limiar-com-histerese-nao-e]] | se o rótulo dura o suficiente para condicionar decisão | classificador fora do warm-up |
| Distribuição conjunta das três frações de amplitude | [[KB-0033-amplitude-de-mercado-a-nossa-e-condicionada-a-volume]] | se a assimetria touro/urso é grande na prática | cobertura de 80%, hoje inexistente |
| R² e beta de cada mercado contra o BTCUSDT (5 min e 1 h) | [[KB-0034-btc-como-fator-e-o-regime-global-que-e-so-o-btc]] | se chamar de `global` uma leitura do BTC é defensável | velas de 1 min (temos) |

### Onde a quarta rodada entra na ordem (2026-09-06)

1. **A curva do warm-up, primeiro.** Custa uma consulta, e responde a pergunta que decide todo o
   resto: o regime acorda em 18 dias ou nunca, porque perdemos horas demais por gap? Enquanto isso
   não for sabido, planejar análise por regime é planejar sobre um instrumento cego.
2. **O carimbo de regime (#15) em paralelo**, porque não depende do item 1: mesmo gravando `UNKNOWN`
   ele distingue "não sabíamos" de "não gravamos", e essa distinção é irrecuperável depois.
3. **O ciclo de trabalho do piso**, porque ele **bloqueia** a #2 da fila original. Subir
   `atr_pct_min` de 0,003 para 0,0089 sem saber quanto do universo isso desliga, e em que horas, é
   mudar a população sem saber para qual.
4. **R² contra o BTC**, porque é barato, usa dado que já temos, e pode transformar a #16 e a #17 de
   ideias em perguntas — ou matá-las, se a amplitude for só o BTC medido de novo.
5. **Os demais**, todos bloqueados por amostra, entram quando a história existir.

**O que esta rodada explicitamente NÃO propõe:** nenhum filtro de entrada por regime. Não porque a
ideia seja ruim, mas porque não temos como avaliá-la — nem o regime chega ao sinal, nem o
classificador classifica. Propor um filtro agora seria propor algo cuja refutação é impossível, que
é exatamente o que a [[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] proíbe.

## Já em sombra
- `momentum_v1` → [[EXP-0001-momentum-v1]] (coortes `v1` e `v2`; `v2` difere só pelo `code_ref`)
- `volume_anomaly_v1` → [[EXP-0002-volume-anomaly-v1]]

## Relacionados

[[Index]] · [[Registro de Tentativas]] · [[Experiments Index]] · [[Strategy Performance]] ·
[[Features]] · [[Momentum Agent]]

---

## Quinta rodada (2026-09-06) — execução e microestrutura do preenchimento

**A rodada não produziu nenhuma candidata de estratégia, e isso é o resultado.** Produziu nove
diagnósticos e **duas** correções de contrato, porque a pergunta "quanto custa executar" não pode ser
respondida com o que está gravado hoje ([[KB-0044-o-que-morre-em-dez-segundos]]).

**O que a medição mostrou sobre os custos assumidos** (`spread_bps=2`, `slippage_bps=5`,
`fee_bps=4`, ou 6 bps por perna dentro do preço mais 4 bps de taxa fora dele):

| Componente | Assumido | Medido | Veredito |
|---|---|---|---|
| Spread | 2 bps totais | mediana 2,30 bps; p95 7,97; decil 10 = 0,97, decil 1 = 4,93 | **acerta a mediana**; erro de ida e volta de 0,30 bps ([[KB-0037-o-spread-assumido-contra-o-spread-medido]]) |
| Slippage | 5 bps por lado, **sem** o meio spread | o que medi é **outra grandeza**: custo de atravessar o ask contra o **mid**, que **já inclui** o meio spread — 500 USDT → 2,53 bps; 5.000 → 6,85 | **não comparável termo a termo**, e não é falsificável hoje porque o tamanho não existe no contrato ([[KB-0036-o-tamanho-que-a-sombra-nunca-declara]]) |
| Taxa | 4 bps por lado | maker 2 / taker 5 no exemplo do FAQ da Binance; 4,5 com BNB | 1 a 2 bps de ida e volta a menos ([[KB-0038-a-taxa-de-4-bps-nao-e-nem-maker-nem-taker]]) |
| Referência (`open`) | tratado como preço | é o primeiro **negócio** do minuto; erro de sinal desconhecido | o custo contra o mid oscila ±meio spread ([[KB-0042-o-open-nao-e-preco-executavel]]) |
| Espera até a entrada | imposta pela arquitetura; o deslocamento **já entra** em `P_entry` e no R | \|deslocamento\| mediano **14,4 bps**, p90 44,1 | não é custo a somar — é **dispersão** nunca quantificada ([[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]]) |

### Nova na fila — e é de contrato, não de estratégia

| # | Item | Notas-fonte | Dado necessário (temos?) | Esforço | Edge esperado | Status |
|---|---|---|---|---|---|---|
| 19 | **`assumed_notional_usd` em `AssumedCosts`**, congelado na versão | [[KB-0036-o-tamanho-que-a-sombra-nunca-declara]] | nenhum — é campo de contrato | baixo | **nenhum edge.** Sem ele, "6 bps por lado" não tem medição que possa contrariá-lo | especificada |
| 20 | **Carimbo de execução associado ao sinal** (bid/ask/mid, `bid_qty`/`ask_qty`, idade do book, custo de atravessar numa grade de tamanhos, cobertura, `quote_volume_24h` do instante) — em **registro separado** do envelope da decisão | [[KB-0044-o-que-morre-em-dez-segundos]] | book do hot state (existe, vive 10 s) | médio | **nenhum edge.** Proveniência: destrava `EXEC-A`, `EXEC-B` e `EXEC-G` | especificada |
| — | ~~**Entrada por post-only (GTX)** para pagar maker~~ | [[KB-0039-tipos-de-ordem-e-o-que-a-sombra-assume-sem-dizer]] | fila e fluxo agressor no nível (**não temos**) | — | trocaria 3 bps de taxa por risco de não executar | **impossível de avaliar em sombra**; volta no M4 |

### Diagnósticos abertos pela quinta rodada

| Item | Nota | O que responde | Pré-requisito |
|---|---|---|---|
| `EXEC-A` — custo de book por tamanho, por sinal, com cobertura | [[KB-0036-o-tamanho-que-a-sombra-nunca-declara]] | se os 6 bps descrevem a perna de entrada no instante da decisão | itens 19 e 20 |
| `EXEC-B` — spread cotado no instante da decisão | [[KB-0037-o-spread-assumido-contra-o-spread-medido]] | quanto o spread real difere dos 2 bps na população dos sinais | item 20 (**o corte por decil exige, além dele, um ranking congelado no instante**) |
| `EXEC-C` — sensibilidade a `fee_bps ∈ {4; 4,5; 5}` sobre população fixa | [[KB-0038-a-taxa-de-4-bps-nao-e-nem-maker-nem-taker]] | se o resultado publicado cabe dentro do erro da hipótese de custo | **nenhum — roda hoje** |
| `EXEC-D` — contexto da barra de saída (amplitude, gap) por `result`, mais sensibilidade a deslocamento assimétrico | [[KB-0039-tipos-de-ordem-e-o-que-a-sombra-assume-sem-dizer]] | descrição; **não** valida simetria de execução | nenhum |
| `EXEC-E` — custo por tamanho com **fração sem cobertura** publicada junto | [[KB-0040-a-lei-da-raiz-quadrada-e-o-regime-que-nao-e-o-nosso]] | capacidade, se o Everton declarar o orçamento | item 20 |
| `EXEC-F` — decomposição por entrada: deslocamento, 6 bps, taxa, funding | [[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]] | quanto do R efetivo vem de cada termo | **nenhum — roda hoje** |
| `EXEC-G` — erro de referência `(open − mid)/mid`, assinado, com média | [[KB-0042-o-open-nao-e-preco-executavel]] | se o `open` é referência enviesada | item 20 |
| `EXEC-H` — retorno entre aberturas após a entrada (não é markout) | [[KB-0043-selecao-adversa-o-custo-que-so-aparece-depois-do-fill]] | para onde o preço vai no minuto seguinte à entrada | **nenhum — roda hoje** |
| `EXEC-I` — cobertura do carimbo | [[KB-0044-o-que-morre-em-dez-segundos]] | se as perguntas acima ficam respondíveis | item 20 |

### Ordem recomendada (2026-09-06)

1. **`EXEC-C` e `EXEC-F`, hoje.** Não exigem coleta nova para a versão descritiva básica: recomputam
   sobre resultado já colhido. O
   `EXEC-C` responde se o vermelho cabe dentro do erro da hipótese de taxa; o `EXEC-F` separa o que
   hoje chamamos de "custo" em quatro termos com nomes distintos.
2. **`EXEC-H` junto**, pelo mesmo motivo — usa `candles` e as entradas já identificadas, e mais nada.
   Ressalva: o **corte por decil** dele tem a mesma dependência de ranking congelado do `EXEC-B`.
3. **Item 19 (`assumed_notional_usd`).** Uma linha de contrato que transforma uma hipótese
   inverificável em hipótese verificável. É a mudança de maior alavancagem da rodada.
4. **Item 20 (carimbo de execução).** Destrava `EXEC-A`, `EXEC-B`, `EXEC-G` e `EXEC-E`. Custa
   latência no caminho da decisão e precisa de desenho — é o item que merece uma decisão conjunta.
5. **`EXEC-D`** também não exige coleta nova; fica por último não por dependência, e sim porque com
   OHLC ele descreve contexto e não mede custo — é o menos informativo sobre execução.

**O que esta rodada explicitamente NÃO propõe:** mexer em `spread_bps`, `slippage_bps` ou `fee_bps`.
Nenhum dos três seria ajustado com dado independente — todos seriam calibrados na amostra que
revelou o problema, que é o erro da [[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]].
E o valor prático de todos os itens acima é **zero em expectancy**: eles só tornam falsificável uma
hipótese que hoje não é.

---

## Sexta rodada (2026-09-06) — livros de estratégia

Onze notas ([[KB-0045-turtles-a-entrada-que-ja-temos-e-a-saida-que-nao]] a
[[KB-0055-douglas-o-livro-que-nao-vira-hipotese]]). **É a primeira rodada desde a primeira que produz
candidatas de estratégia**, e não só diagnósticos — porque livros dão regras objetivas, que é
justamente o que o Everton pediu: coisa para sair validando no virtual.

### Duas correções que atingem candidatas que já estavam na fila

> **1. A #6 (`return_4h > 0`, T-001) é redundante com a própria condição de entrada.** Se
> `close_t > max(C_{t−1} … C_{t−20})` nos fechamentos de 15m, então em particular
> `close_t > C_{t−16}`, e 16 barras de 15 min são 240 minutos — logo `return_4h > 0` já é verdade no
> instante do disparo. O gate não filtraria nada, **exceto** quando a feature do M2 estivesse
> indisponível ou defasada, e alguém publicaria essa redução de amostra como "benefício da
> confirmação de tendência". Achado da Astra, conferido linha a linha
> ([[KB-0048-o-teste-antes-da-regra-e-o-filtro-que-ja-estava-dentro]]). **A #6 sai da fila.**

> **2. A #2 (piso de custo) ganha uma tradução, e perde uma que eu tinha inventado.** O piso passa a
> ser publicado também como `custo_R_nominal_referencia = b / (10.000 · k · atr_pct)`, medido **na
> referência** — o mesmo corte, dito em unidades que sobrevivem à revisão da hipótese de taxa. O que
> **não** vale é o que eu tinha proposto primeiro: um teto sobre o custo em R **efetivo** não
> equivale a um piso de ATR (depende do deslocamento `g = P_entry/C − 1`) e, pior, `P_entry` **não é
> conhecido no instante da decisão**
> ([[KB-0050-previsao-continua-e-o-limite-de-velocidade-de-custo]]).

### Fila para a sombra — livros

**Todas atrás da #1 do backlog** (valor incremental da invalidação, T-005), que continua sendo a
primeira — decisão conjunta minha e da Astra, nas duas revisões desta rodada.

| # | Candidata | Regra em uma frase | Parâmetros | Dado (temos?) | Esforço | O que a refutaria |
|---|---|---|---|---|---|---|
| **L1** | **Alvo assimétrico** ([[KB-0054-a-cauda-direita-e-o-alvo-fixo-que-a-corta]] · [[KB-0046-r-multiplos-e-o-r-que-a-simetria-esconde]]) | Manter entrada, stop, invalidação e horizonte, e replicar cada acompanhamento com o alvo a 1,5 / 3,0 / 4,5 ATR₀ da referência | `target_atr ∈ {1.5, 3.0, 4.5}` — 3 e 4,5 são o `target2_atr`/`target3_atr` que a estratégia já calcula e persiste | **sim** — velas de 1 min, entradas registradas, ATR₀ congelado; exige motor de replay | médio (3 braços) | diferença **pareada** de média de `R_net` contra a base sem exceder o efeito mínimo declarado, com Holm e blocos de tempo. Ausência de evidência **não** é refutação |
| **L2** | **Saída sem alvo e por canal oposto** ([[KB-0045-turtles-a-entrada-que-ja-temos-e-a-saida-que-nao]]) | Mesma entrada e stop; um braço sem alvo; outro sem alvo e saindo quando o fechamento de 15m fica abaixo do mínimo dos 10 fechamentos anteriores | `exit_lookback = 10`; `target = null`; stop, invalidação e horizonte inalterados | **sim** — mesmas velas | médio (2 braços + saída móvel) | `CHAN − NOTGT` ≤ 0 no efeito declarado. **Poucas saídas por canal não refutam**: poucas saídas podem ter efeito grande |
| **L3** | **Razão de eficiência de Kaufman** ([[KB-0047-razao-de-eficiencia-de-kaufman]]) | Só aceitar o sinal quando a `ER(20)` sobre os 21 fechamentos de 15m — deslocamento líquido dividido pela soma dos deslocamentos barra a barra — ficar ≥ θ | `efficiency_window = 20`; `efficiency_min = θ`, de um quantil da distribuição condicionada, **congelado antes** | **sim** para o cálculo; o grupo de comparação retrospectivo é **replay reconstruído** (as barras `not_triggered` não são gravadas individualmente) | baixo (diagnóstico `D-ER`) / médio (braço) | nem `delta_por_aceito` nem `delta_por_oportunidade` positivos (convenção `C-META`) |
| **L4** | **Contração de volatilidade antes do rompimento** ([[KB-0053-contracao-de-volatilidade-o-unico-pedaco-formalizavel]]) | Só aceitar quando `ATR(8 barras de 15m) / ATR(32 barras)` — **as duas janelas terminando em `t−1`** — ficar ≤ θ | estimador declarado (Wilder exige `period + 2` barras), janelas 8/32, `θ` de quantil congelado antes | **sim** para o cálculo; mesma ressalva de replay reconstruído | médio | os dois denominadores do `C-META` não positivos; ou correlação alta com `ER`/`atr_pct`, que a tira por parcimônia |
| **L5** | **Benchmark aleatório condicionado** ([[KB-0049-walk-forward-que-nao-temos-e-o-nulo-que-nunca-calculamos]]) | Para cada sinal, sortear entradas alternativas **na mesma elegibilidade, mercado, hora UTC e bloco de calendário**, e rodar o mesmo acompanhamento | `K` declarado **depois** da especificação de estatística, ponderação e blocos | velas: sim. Controles são **replay reconstruído**, com cobertura publicada | alto | não é braço e não tem refutação — é referência. O quantil de leitura é declarado antes |

Sobre a L5, duas coisas que a revisão obrigou a escrever: **não é teste de permutação validado** —
sortear não demonstra a intercambialidade que um p-valor exigiria —, e **o zero continua sendo** a
referência de "isto é lucrativo?". Ganhar de um controle de −0,30 R com −0,08 R não demonstra
rentabilidade nenhuma.

### O bloco de políticas de saída — T-005, L1 e L2 são a mesma busca

Compartilhar entradas não determina, sozinho, a família estatística. Mas aqui a finalidade é
**procurar uma política de saída melhor dentro do mesmo conjunto de alternativas**, e para essa
finalidade os três são um bloco só (desenho da Astra):

| Pergunta | Contrastes primários |
|---|---|
| T-005 (invalidação) | `INV-B − base` · `INV-C − base` · `INV-E − base` |
| L1 (alvo) | `alvo 3 − base` · `alvo 4,5 − base` |
| L2 (saída móvel) | `NOTGT − base` · `CHAN − NOTGT` |

**Oito políticas únicas** (incluindo a base compartilhada) e **sete contrastes**, sem cruzar todas as
combinações. **Holm a 5% sobre os sete**, com p-valores válidos para a dependência temporal — Holm
aceita dependência entre testes, mas **não conserta** p-valores calculados tratando entradas
correlacionadas como independentes.

`INV-B` **não** duplica `EXIT-NOTGT`: o primeiro remove a invalidação e conserva o alvo; o segundo
remove o alvo e conserva a invalidação. E o bloco **não autoriza** combinar o vencedor de T-005 com o
vencedor de L1 — isso seria uma comparação adicional, e uma tentativa a mais.

**Ressalva de pareamento que quase passou:** aumentar o alvo mexe na validação
`stop < entrada < alvo` (`walker.py:45`), então um alvo maior pode admitir entradas que a base
recusaria. As entradas só continuam pareadas se essa checagem ficar congelada na base. E rodar
qualquer braço como estratégia **independente**, em vez de replay, muda ocupação e rearme de slots
(`episodes.py:57`) — nesse regime não há pareamento nenhum.

### O menor conjunto para o Everton começar a validar mais rápido

1. **Reproduzir a base** a partir dos registros persistidos, conferindo saída, preço e R. Sem isso
   nenhum contraste tem chão.
2. **Piloto técnico `INV-A` contra `INV-B`** sobre as entradas efetivas da base — o menor contraste
   que responde se a invalidação acrescenta valor.
3. **Completar a T-005** (`INV-C` e `INV-E`): são quatro braços, não dois. Reduzir o escopo para A/B
   é legítimo, mas tem de ser declarado **antes** da janela — não se eliminam C e E depois de olhar
   resultado.
4. **L1 em seguida**; `D-ER` e `D-CONTR` rodando como **observação**, sem filtro ativo.

O primeiro replay produz aprendizado operacional rápido. **Confirmação continua exigindo janela
futura reservada, maturação e cobertura**, sem converter funding desconhecido em zero — e o piso de
100 outcomes e 30 dias **não substitui cálculo de potência**.

### Diagnósticos e convenções abertos pela sexta rodada

| Item | Nota | O que responde | Pré-requisito |
|---|---|---|---|
| `D-VT` — distribuição do payoff nominal `(target1 − P_entry)/(P_entry − stop)` e do desvio referência→`P_entry` | [[KB-0046-r-multiplos-e-o-r-que-a-simetria-esconde]] | quanto o relógio desloca a razão ganho/risco que todo mundo lê como 1:1 | **nenhum — roda hoje** (usar `P_entry`, não o `open` bruto) |
| `D-ER` — distribuição de `ER(20)` condicionada a sinal | [[KB-0047-razao-de-eficiencia-de-kaufman]] | de onde sai o θ, sem calibrar em cima de outcomes | grupo de comparação é replay reconstruído |
| `D-CHAN-a` — correlação de postos entre `ER(20)`, `VR(2)` e `VR(4)` | [[KB-0048-o-teste-antes-da-regra-e-o-filtro-que-ja-estava-dentro]] | se vale gastar duas tentativas em duas medidas de caminho | estimador de `VR` declarado antes |
| `D-CHAN-b` — mercados com sinal que não estão mais monitorados, separando outcomes encerrados, censurados e abertos | [[KB-0048-o-teste-antes-da-regra-e-o-filtro-que-ja-estava-dentro]] | viés de sobrevivência, no escopo estreito | **nenhum** |
| `D-CHAN-c` — fração de sinais com `return_4h > 0`, **por reconstrução com velas** | [[KB-0048-o-teste-antes-da-regra-e-o-filtro-que-ja-estava-dentro]] | confirma ou derruba a redundância da T-001 | `return_4h` **não está** no envelope da `momentum_v1` |
| `D-CONC` — concentração temporal: acompanhamentos abertos por minuto, mercados por minuto e por hora, blocos e outcomes por bloco | [[KB-0051-tres-barreiras-mais-uma-e-a-amostra-que-nao-e-independente]] | quão concentrada está a população, antes de o limiar editorial ser atingido | **nenhum — roda hoje** |
| `D-CONTR` — distribuição da razão de contração e correlação com `atr_pct` e `ER` | [[KB-0053-contracao-de-volatilidade-o-unico-pedaco-formalizavel]] | se a contração é medida distinta na nossa população | estimador e janelas congelados |
| `C-META` — convenção de relatório de filtros: estratégia-base, população avaliável, cobertura, e `q`, `μ_A − μ_B`, `q·μ_A − μ_B`, precisão positiva | [[KB-0052-meta-rotulagem-o-formato-de-todo-filtro-que-propusemos]] | impede o filtro que "melhora a média" cortando 90% da amostra | **nenhum — é convenção** |
| `C-COST` — publicar `custo_R_nominal_referencia` ao lado de `atr_pct_min` | [[KB-0050-previsao-continua-e-o-limite-de-velocidade-de-custo]] | o piso em unidades que sobrevivem à revisão da taxa | **nenhum — é tradução, não muda população** |
| `C-FCAST` — score contínuo não vinculante, com faixas e alvo declarados **antes** | [[KB-0050-previsao-continua-e-o-limite-de-velocidade-de-custo]] | se um score ordena `R_net` — pergunta prospectiva, **não** adiada para o M4 | nome de método próprio; nunca reusar `confidence_method` |

### O que esta rodada explicitamente NÃO propõe

- **Nenhum braço em nome de Mark Douglas.** Não há humano no laço; atribuir resultado de algoritmo a
  psicologia sem observar decisão humana é o erro que a nota registra
  ([[KB-0055-douglas-o-livro-que-nao-vira-hipotese]]).
- **Nenhum braço de dimensionamento, volatilidade-alvo ou carteira** (Carver, Van Tharp, Turtles,
  Clenow): o Lab de sombra não dimensiona posição, e `PnL de carteira` é *não aplicável*.
- **Nenhuma troca do relógio de amostragem** (barras de volume ou de dólar): não é reparametrização,
  é outra estratégia — muda a janela do rompimento, a do ATR, a do volume relativo, a cadência das
  decisões e o rearme. Registrada como ideia **bloqueada**
  ([[KB-0052-meta-rotulagem-o-formato-de-todo-filtro-que-propusemos]]).
- **Nenhum alongamento do horizonte** neste primeiro lote. Que as 4 h sejam a trava é hipótese que
  exige outro contraste; variar só o alvo já mede o efeito do alvo **condicionado** ao horizonte
  atual.
- **Nenhum classificador de meta-rotulagem.** O formato entra como convenção; o modelo exigiria
  amostra rotulada que não temos.

---

## Sétima rodada (2026-09-06) — meme coins

Dez notas ([[KB-0056-meme-coin-como-ativo-e-o-rotulo-que-nao-e-medida]] a
[[KB-0065-a-coorte-de-memes-nao-se-distingue-do-resto]]). É a rodada com **mais medição própria** de
todas: ATR%, spread, profundidade de 20 níveis, funding, beta contra o BTC, quedas, sinais e
outcomes — tudo na **VPS**, com 45 h de dados reais, 200 mercados monitorados e 581 mil velas de
1 min.

### A restrição estrutural que organiza toda esta fila

**O `StrategyContext` carrega `candles_1m`, `funding`, `open_interest`, `eligible` e
`eligibility_reason` — e nada mais** (`packages/core/hunter_core/strategies/base.py:109` em diante),
e ele é validado para **recusar velas de outro símbolo**. Consequências que decidem o que pode
entrar na fila:

> 1. Toda candidata testável hoje tem de ser calculável a partir de **velas, funding e open
>    interest** do próprio mercado. Spread, livro e volume de 24 h **não estão lá** — filtros que os
>    usem exigem mudança de contrato, do mesmo peso dos itens 19 e 20.
> 2. **Filtro entre mercados é estruturalmente impossível hoje.** Nenhuma regra pode olhar o BTC,
>    ou a coorte, ou o mercado vizinho, porque o contexto é de um símbolo só e rejeita o resto.

### O que a medição derrubou do folclore de meme

| Afirmação corrente | O que medi (VPS, 42 h, 2026-09-05 00:00 a 2026-09-06 18:00 UTC) |
|---|---|
| "Meme é o ativo mais volátil" | Medianas de ATR%(14) por barra de 15 min **próximas** entre memes (0,84%) e resto (0,83%). O contraste grande é BTC (0,127%) e majors (0,50%) contra tudo mais ([[KB-0057-a-volatilidade-das-memes-e-o-piso-que-bane-o-btc]]) |
| "As memes azuis são as mais voláteis" | DOGE 0,56%, PEPE 0,53%, SHIB 0,45% — na faixa das majors. As listagens recentes de símbolo não-ASCII vão de 1,57% a 5,87% |
| "Meme tem funding extremo" | Por liquidação, **menos** extremo que o resto (\|média\| 1,07 contra 2,32 bps); e metade da diferença entre coortes é **cadência**, não sentimento ([[KB-0059-funding-em-memes-a-cadencia-antes-do-sentimento]]) |
| "Memes descolam do mercado" | São **mais** acopladas ao BTC que a altcoin média: inclinação mediana 2,80 e R² 0,152, contra 1,44 e 0,021 ([[KB-0060-correlacao-com-o-btc-e-a-meme-season]]) |
| "Meme é onde estão as quedas de 80%" | A maior queda **observada** ficou fora das memes (−58,67% contra −29,75%) — mas 19 contra 133 mercados **não decide cauda** ([[KB-0064-a-cauda-de-queda-e-o-que-o-risk-engine-vai-precisar]]) |
| "Meme dá mais sinal" | 4,00 sinais por mercado contra 5,43 do resto; e dentro de cada estratégia as taxas de alvo não se distinguem ([[KB-0065-a-coorte-de-memes-nao-se-distingue-do-resto]]) |

**O achado que mais importa não é sobre meme, é sobre nós:** o estimador de ATR ficou **abaixo do
piso `atr_pct_min = 0,003` em 100% das 154 observações do BTCUSDT**, e a `momentum_v1` emitiu **zero
sinais** para o BTC. Se confirmado pelo `D-MEME-ATR`, quer dizer que **ninguém decidiu** que o Lab
seria um laboratório de altcoin: o piso de custo decidiu, e nunca foi lido assim.

### Duas medições que mudam contratos existentes

| Componente | Assumido pelo Lab | Medido nas memes (coorte A) | Medido nas majors |
|---|---|---|---|
| Spread total | 2 bps | **3,12 bps** (p99 12,10) | 1,23 bps |
| Travessia de 5.000 USDT contra o mid | não existe no contrato | **7,07 bps** | 1,34 bps |
| Cabe 20.000 USDT em 20 níveis? | não perguntado | **18 de 21** | 23 de 23 |

Para 5.000 USDT, o custo estático da perna de entrada numa meme mediana **já supera os 6 bps** que o
Lab assume para spread mais slippage somados, antes de qualquer taxa
([[KB-0058-spread-e-profundidade-o-custo-de-sair-de-uma-meme]]). Isso reforça o item 19
(`assumed_notional_usd`) da quinta rodada; **não** autoriza recalibrar custo na amostra que revelou
o problema.

### Marcação de universo — `meme_universe_v1`, congelada antes de qualquer consulta

Toda candidata desta rodada declara a que universo se aplica usando esta lista, que é **julgamento
meu** e está datada por isso ([[KB-0056-meme-coin-como-ativo-e-o-rotulo-que-nao-e-medida]]):

- **Coorte A (21):** `DOGEUSDT, 1000SHIBUSDT, 1000PEPEUSDT, 1000BONKUSDT, 1000FLOKIUSDT, WIFUSDT,
  BOMEUSDT, FARTCOINUSDT, PENGUUSDT, TRUMPUSDT, MOODENGUSDT, CHILLGUYUSDT, PNUTUSDT, NEIROUSDT,
  1000CATUSDT, 1000000BOBUSDT, SPXUSDT, USELESSUSDT, MUBARAKUSDT, BROCCOLI714USDT, TSTUSDT`
- **Coorte B (regra sintática):** símbolo que não casa `^[A-Za-z0-9]+$` — hoje 牛来USDT, 哈基米USDT,
  龙虾USDT, 币安人生USDT, 我踏马来了USDT. **Confunde meme com listagem recente**, e a regra identifica
  caracteres, não natureza econômica.
- **Zona cinzenta, fora das duas:** PEOPLE, CATI, GIGGLE, 4, DOOD, PUMP, MARSCOIN, BULLA, RAYSOL,
  GRAM, TRADOOR, SKYAI.

A lista é `default_parameters` de **relatório**, nunca de decisão: **nenhuma candidata abaixo muda de
comportamento por coorte** — porque, pela restrição estrutural acima, nenhuma regra consegue saber em
que coorte está.

### Fila para a sombra — meme coins

**Todas atrás da #1 do backlog** (valor incremental da invalidação, T-005) e do bloco de saídas da
sexta rodada. Nenhuma é ativada por mim.

| # | Candidata | Regra em uma frase | Parâmetros | Dado (temos?) | Marcação de universo | O que a refutaria |
|---|---|---|---|---|---|---|
| **M-A** | **Teto de ATR% mais apertado** ([[KB-0057-a-volatilidade-das-memes-e-o-piso-que-bane-o-btc]] · [[KB-0058-spread-e-profundidade-o-custo-de-sair-de-uma-meme]]) | Manter tudo da `momentum_v1` e baixar só o teto de volatilidade admitida | `atr_pct_max ∈ {0,05 (base), 0,03, 0,02}`; θ de quantil **congelado antes** da janela | **sim** — Wilder(14) sobre 15m com `atr_bars=97`, já calculado no contexto | universo inteiro; **relatório estratificado** por `meme_universe_v1` | diferença **pareada** de média de `R_net` contra a base sem exceder o efeito mínimo declarado, com Holm e blocos de tempo, e os quatro números da `C-META`. **Bloqueada até `D-MEME-ATR` e `D-MEME-LIQ` rodarem** (exigência da Astra) |
| **M-E** | **Teto de funding absoluto como custo** ([[KB-0059-funding-em-memes-a-cadencia-antes-do-sentimento]]) | Recusar o sinal quando \|`funding_rate`\| na decisão passar de θ — **filtro de custo, simétrico, não direcional** | `abs_funding_max = θ`, de quantil congelado antes; um braço | **sim** — `funding` está no `StrategyContext` | universo inteiro; relatório por coorte | os dois denominadores da `C-META` não positivos. **Não é a T-016**: aquela era direcional e foi retirada por prior desfavorável ([[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]]); esta é simétrica e não promete previsão. **Ressalva:** `funding_rate` é a estimativa em formação, e sem `next_funding_time` não sabemos a fase do ciclo ([[KB-0019-o-que-a-nossa-funding-rate-mede-de-fato]]) |
| **M-G** | **Teto de amplitude da barra de referência** ([[KB-0064-a-cauda-de-queda-e-o-que-o-risk-engine-vai-precisar]]) | Recusar quando a amplitude da própria barra de 15 min do sinal passar de K × ATR₀ | `bar_range_atr_max = K`, de quantil congelado antes; um braço | **sim** — só velas | universo inteiro; relatório por coorte | os dois denominadores da `C-META`. **É distinta do `atr_pct_max`**: aquele mede o nível ambiente de volatilidade, este mede **aquela barra**. E é distinta do `return_max_atr = 2` da `volume_anomaly_v1`, que limita o **retorno** e não a amplitude, e não existe na `momentum_v1` |
| ~~**M-B**~~ | ~~**Piso de liquidez** (`quote_volume_24h` mínimo)~~ | — | — | **não** | — | **BLOQUEADA em 2026-09-06.** Dois motivos: o `StrategyContext` **não carrega** volume de 24 h (`base.py:109`), então é mudança de contrato; e o `ts` do hash `ticker` é compartilhado entre REST e WS (`hot_state.py:61`, `sampling.py:55`), então volume velho pode aparecer preenchido e "fresco". Achado da Astra. Classificação: *especificada; diagnóstico de cobertura liberado; avaliação bloqueada até validar disponibilidade e frescor* |

### Diagnósticos abertos pela sétima rodada

| Item | Nota | O que responde | Pré-requisito |
|---|---|---|---|
| `D-MEME-ATR` | [[KB-0057-a-volatilidade-das-memes-e-o-piso-que-bane-o-btc]] | ciclo de trabalho de `atr_pct_min`/`atr_pct_max` **no ATR que a estratégia consome**, por coorte e hora UTC, com três números: gate de ATR isolado nas janelas válidas, exclusões após os demais critérios, emissões efetivas | **nenhum — roda hoje**; **bloqueia a M-A** |
| `D-MEME-LIQ` | [[KB-0058-spread-e-profundidade-o-custo-de-sair-de-uma-meme]] | ATR contra **spread** (não profundidade), com spread de snapshots comprovadamente anteriores, condicionado aos sinais; associação refeita sem BTC, por coorte, removendo um mercado por vez | **nenhum**; **bloqueia a M-A** |
| `D-MEME-CUSTO` | [[KB-0058-spread-e-profundidade-o-custo-de-sair-de-uma-meme]] | `EXEC-C` estratificado por coorte, mais recomputar `R_net` com o spread **medido** de cada coorte | **nenhum — roda hoje** |
| `D-MEME-FUND` | [[KB-0059-funding-em-memes-a-cadencia-antes-do-sentimento]] | funding em **bps por hora de exposição** (intervalo real medido, não cadência modal), com cadência publicada junto; e custo de funding realizado por acompanhamento | intervalo medido; `next_funding_time` continua com **zero linhas** |
| `D-MEME-BETA` | [[KB-0060-correlacao-com-o-btc-e-a-meme-season]] | `D-023` estratificado, publicando **distribuição** de β e R² por coorte, com sensibilidade à retirada de mercados **e** de blocos de tempo | nenhum |
| `D-MEME-PICO` | [[KB-0061-pump-and-dump-o-detector-que-precisa-de-25-segundos]] | de que lado do máximo entramos, em **janela fixa** (barra de referência → entrada + 2 h), independente da saída | desenho declarado antes: empates, cobertura, maturação, dependência |
| `D-MEME-SAIDA` | [[KB-0062-o-primeiro-dia-que-nao-conseguimos-ver]] | tamanho do viés de sobrevivência: os **27 sinais em 14 mercados** que saíram do universo, contra os 982 que ficaram | **nenhum — roda hoje** |
| `D-MEME-GAP` | [[KB-0064-a-cauda-de-queda-e-o-que-o-risk-engine-vai-precisar]] | saída contra barreira nos stops, **decomposta** em `exit_at_open`, `exit_base`, barreira e custos — é **gap na resolução do modelo**, não custo de execução real | **nenhum — roda hoje** |
| `D-MEME-POP` | [[KB-0065-a-coorte-de-memes-nao-se-distingue-do-resto]] | retrato por **estratégia/versão × coorte** com todos os denominadores, mercados desmonitorados incluídos, `count(r_multiple)` ao lado de cada média e corte temporal declarado | **nenhum — roda hoje** |
| `D-MEME-ATRPAR` | [[KB-0065-a-coorte-de-memes-nao-se-distingue-do-resto]] | taxa de alvo pareada por decil de `atr_pct`, dentro de cada estratégia. **Ausência de diferença não demonstra redundância** | `D-MEME-POP` |

### Proveniência — três itens que não são estratégia e destravam o resto

| Item | Nota | Por quê |
|---|---|---|
| `H-KB0056` — carimbar `monitor_rank` do instante, tamanho e regra do universo, e a versão da lista de marcação, no envelope | [[KB-0056-meme-coin-como-ativo-e-o-rotulo-que-nao-e-medida]] | a **classificação** é reconstruível pela identidade do mercado; o **ranking e a composição históricos** não são |
| `H-KB0062a` — persistir a data de listagem (`onboardDate`) | [[KB-0062-o-primeiro-dia-que-nao-conseguimos-ver]] | são **duas** mudanças, não uma: `binance/normalize.py:137` guarda só `contractType`, e `universe_repo.py:64` **não transfere `metadata`** no upsert |
| `H-KB0062b` — persistir o diff de universo em tabela própria | [[KB-0062-o-primeiro-dia-que-nao-conseguimos-ver]] | hoje ele existe no stream do Redis (46 eventos, 20 h) mas a retenção é por **número de entradas**; com 52 trocas em 20 h, isso é da ordem de semanas |

### O que esta rodada explicitamente NÃO propõe

- **Nenhuma estratégia de listagem nova.** É a ideia mais citada do mercado de meme e a sua refutação
  é **impossível de construir** hoje: a `momentum_v1` precisa de 24 h 15 min de histórico contínuo e
  a `volume_anomaly_v1` de 24 h, o backfill não inventa história que a Binance não tem, e não
  gravamos a data de listagem ([[KB-0062-o-primeiro-dia-que-nao-conseguimos-ver]]).
- **Nenhum braço "só memes" nem "sem memes".** Duas razões: dentro de cada estratégia as coortes não
  se distinguem na amostra atual, e — decisivo — **nenhuma regra consegue saber em que coorte está**,
  porque o contexto é de um símbolo só.
- **Nenhum braço de detecção de pump.** A literatura opera em blocos de 25 s; nós decidimos sobre
  barras de 5 e 15 min. Não é parâmetro, é outra arquitetura.
- **Nada de social nem on-chain.** `enable_social_intelligence` é flag sem consumidor funcional e
  `intelligence_events` é tabela sem escritor ([[KB-0063-social-e-on-chain-a-linha-que-nao-atravessamos]]).
- **Nenhuma recalibração de `spread_bps`, `slippage_bps` ou `fee_bps` por coorte.** Seria calibrar na
  amostra que revelou o problema ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]).
- **Nenhuma mudança de limite de risco.** Os cinco requisitos da
  [[KB-0064-a-cauda-de-queda-e-o-que-o-risk-engine-vai-precisar]] são **propostas** para o Risk
  Engine do M3/M4, nascidas de 42 h sem nenhum evento de stress.
