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

## Já em sombra
- `momentum_v1` → [[EXP-0001-momentum-v1]] (coortes `v1` e `v2`; `v2` difere só pelo `code_ref`)
- `volume_anomaly_v1` → [[EXP-0002-volume-anomaly-v1]]

## Relacionados

[[Index]] · [[Registro de Tentativas]] · [[Experiments Index]] · [[Strategy Performance]] ·
[[Features]] · [[Momentum Agent]]
