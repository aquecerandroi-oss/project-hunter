---
tags: [knowledge, protocolo, tentativas]
updated: 2026-09-06
status: aberto
---

# Registro de tentativas (append-only)

Regra vinda de [[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]. Toda variante que
venha a ser rodada no Shadow Lab entra **aqui antes de rodar**. Linhas nunca são editadas nem
apagadas: correção é **linha nova** com a mesma ID e o motivo. Uma variante avaliada antes da data de
fim declarada é uma tentativa inválida, e assim tem de ser reportada.

Cada relatório de variante cita o **total acumulado de tentativas** desta tabela até aquela data.

**Distinção obrigatória:** *candidata proposta* (ideia registrada, ainda sem coleta) ≠ *tentativa
avaliada* (rodou e foi lida). Só a segunda entra na conta de multiplicidade — mas toda candidata
abandonada **depois** de olhar dado também entra, e é por isso que as descartadas ficam registradas.

**Verificabilidade e seu limite.** O compromisso só vale se a linha estiver publicada no remoto
**antes** do início da janela; o que a torna verificável é o SHA vinculado a um evento datado pelo
servidor (PR/CI), com branch protegida contra reescrita. Data local de commit é ajustável e
assinatura sozinha não prova anterioridade. Isto comprova o compromisso publicado, **não** a
inexistência de testes privados omitidos.

## Estado em 2026-09-06

**Tentativas avaliadas: 0.** Nenhuma das candidatas abaixo foi rodada. As duas coortes vivas
(`momentum v1/v2` e `volume_anomaly_v1`) são o experimento base, não variantes de busca — e `v2`
difere de `v1` apenas pelo `code_ref` ([[EXP-0001-momentum-v1]]).

## Candidatas propostas (ainda não rodadas)

| ID | Candidata | Nota de origem | Parâmetros | `δ` | Início/fim UTC | Status |
|---|---|---|---|---|---|---|
| T-001 | gate de tendência (`return_4h > 0`) | [[KB-0001-momentum-academico-e-o-que-nao-se-transfere]] | `trend_gate_feature=return_4h`, `trend_gate_min=0` | a definir | — | proposta |
| T-002 | impulso recente excessivo (`momentum_15m ≤ 2,0`) | [[KB-0002-momentum-e-reversao-em-cripto]] | `impulse_max=2.0` | a definir | — | proposta |
| T-003a/b/c | família de lookback 10 / 20 / 40 | [[KB-0003-rompimento-de-canal-e-data-snooping]] | `lookback_closes ∈ {10,20,40}` | a definir | — | proposta (3 braços) |
| T-004 | proximidade da máxima de 24 h | [[KB-0004-proximidade-da-maxima-e-confirmacao-por-volume]] | `distance_from_24h_high ≥ −0,005` | a definir | — | proposta, **bloqueada** pela medição de redundância |
| T-005 | valor incremental da invalidação | [[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]] | braços `INV-A/B/C/E`; `INV-E` com `L − 0,25·ATR₀` | 0,05 R | — | proposta (4 braços, 3 contrastes, Holm) |
| T-006 | valor incremental do stop | [[KB-0005-stops-quando-eles-param-perdas]] | braços `STOP-A/B/C` | a definir | — | proposta |
| T-007 | piso de custo (`atr_pct_min = 0,0089`) | [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] | `atr_pct_min=0.0089` | a definir | — | proposta, **exige período futuro reservado** |
| T-008 | atraso de execução (`baseline + 60 s`) | [[KB-0009-o-efeito-do-quarto-de-hora]] | entrada uma barra além da elegível, limite de 120 s mantido | a definir | — | proposta |

Análises **diagnósticas** (não são variantes e não contam como tentativa de estratégia, mas contam
como inspeção da amostra): decomposição de expectancy por decil de ATR%
([[KB-0007-atr-e-escala-por-volatilidade]]), decomposição de custos por faixa e H1 de timing
([[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]], [[KB-0009-o-efeito-do-quarto-de-hora]]), e a
medição de redundância da proximidade da máxima.

**Consequência já registrada:** T-001 a T-008 nasceram da inspeção da coorte de 2026-09-06. Nenhuma
delas pode ser confirmada nessa mesma população — a confirmação exige janela futura reservada, e é
por isso que a coluna `Início/fim UTC` está vazia e tem de ser preenchida **antes** de qualquer
coleta.

## Acréscimo de 2026-09-06 (segunda rodada de conhecimento — volume e fluxo de ordens)

Linhas **acrescentadas**, nunca editadas. **Tentativas avaliadas continuam em 0**: nenhuma das
candidatas abaixo foi rodada, e nenhum dos diagnósticos foi executado.

| ID | Candidata | Nota de origem | Parâmetros | `δ` | Início/fim UTC | Status |
|---|---|---|---|---|---|---|
| T-009 | desequilíbrio agressor na barra do sinal | [[KB-0014-taker-buy-volume-o-que-temos-medido]] | `taker_imbalance_min` — valor **a definir pela distribuição condicionada a pico**, não o 0,10 da minha primeira redação | a definir | — | proposta, **bloqueada** pela observação sem decisão |
| T-010 | teto de volume | [[KB-0015-volume-relativo-e-o-pico-como-exaustao]] | `volume_mult_max` — valor **exploratório**, sem sustentação; o 12 que escrevi não tem justificativa | a definir | — | proposta, dependente do diagnóstico D-004 |
| T-011 | filtro de book `orderbook_imbalance_20 ≥ 0` | [[KB-0012-ofi-nao-e-o-nosso-orderbook-imbalance]] | — | — | — | **proposta e retirada em 2026-09-06**, antes de qualquer coleta: a feature é razão invariante a escala e não mede profundidade, que era a propriedade invocada |

**T-011 fica registrada mesmo tendo morrido no mesmo dia.** A regra desta página diz que candidata
abandonada depois de olhar dado entra na conta; esta foi abandonada por argumento sobre a
**definição** da feature, não por resultado, e é por isso que está aqui com o motivo escrito — para
que ninguém a reproponha achando que é ideia nova.

**Diagnósticos registrados** (não são variantes de estratégia; **contam como inspeção da amostra**, e
a KB-0015 corrigiu a minha ideia de que diagnóstico "não gasta tentativa" — um diagnóstico usado para
escolher a próxima hipótese entra no histórico de pesquisa):

| ID | Diagnóstico | Nota | Status |
|---|---|---|---|
| D-001 | retorno de preço a horizonte fixo por quartil de `volume_ratio_5m`, **com** o grupo `not_triggered` | [[KB-0011-volume-magnitude-e-a-ponte-para-direcao]] | proposto; exige registrar as barras `volume_below_threshold` |
| D-002 | cobertura e idade de `orderbook_imbalance_20` até o instante da decisão | [[KB-0012-ofi-nao-e-o-nosso-orderbook-imbalance]] | proposto |
| D-003 | composição e escala do denominador de 288 barras (zeros, volumes pequenos, mediana absoluta, razão — **separados**) | [[KB-0013-vpin-e-a-disputa-sobre-toxicidade]] | proposto |
| D-004 | associação de `volume_ratio_5m` com o resultado, **todos** os modos de saída | [[KB-0015-volume-relativo-e-o-pico-como-exaustao]] | proposto |
| D-005 | cobertura e distribuição de `spread_pct` **anterior** à decisão (caudas e proporção acima de 2 bps) | [[KB-0016-quando-o-fluxo-importa-dependencia-de-estado]] | proposto |
| D-006 | observabilidade da série de `liquidations` já coletada, após corrigir a semântica `q`/`z` e `p`/`ap` | [[KB-0017-liquidacoes-o-fluxo-forcado-que-observamos-por-amostragem]] | proposto |
| D-007 | gaps **abertos** × janela do denominador, separados dos **recuperados** | [[KB-0018-volume-relatado-e-o-denominador-que-usamos]] | proposto |

**Medições e requisitos que não são tentativa nem diagnóstico** (não alteram decisão, não consomem
multiplicidade): persistir `taker_imbalance_5m` no envelope, e gravar no envelope o ranking do
mercado, o tamanho e a regra do universo e o timestamp do refresh.

**Análise retirada por inexecutabilidade:** estratificação retrospectiva de expectancy por faixa de
liquidez. O ranking do instante **não está** no envelope de nenhum sinal, e reconstruí-lo pelo estado
atual de `markets` atribuiria resultados à faixa errada
([[KB-0016-quando-o-fluxo-importa-dependencia-de-estado]]).

**Consequência de multiplicidade, repetida porque vale para estas também:** T-009 a T-011 e D-001 a
D-007 nasceram da inspeção da coorte de 2026-09-06. Nenhuma pode ser confirmada nessa mesma
população; a confirmação exige janela futura reservada, declarada **antes** da coleta.

## Acréscimo de 2026-09-06 (terceira rodada de conhecimento — funding, open interest e posicionamento)

Linhas **acrescentadas**, nunca editadas. **Tentativas avaliadas continuam em 0**: nenhuma candidata
foi rodada e nenhum diagnóstico foi executado — nesta rodada nem SQL houve, porque o portão de
permissão da sessão recusou `psql` na VPS e o Docker local estava fora.

| ID | Candidata | Nota de origem | Parâmetros | `δ` | Início/fim UTC | Status |
|---|---|---|---|---|---|---|
| T-012 | `time_to_funding_s` como feature, para condicionar a linha de base do `FUNDING_ANOMALY` à fase do ciclo | [[KB-0019-o-que-a-nossa-funding-rate-mede-de-fato]] | `next_funding_time − as_of`, em segundos | a definir | — | proposta, **bloqueada** pela observação sem decisão |
| T-013 | prêmio contra o índice — `last_index_basis_fraction` e `mark−index` como medidas **distintas** | [[KB-0021-funding-como-preco-de-posicionamento-nao-como-previsao]] | nenhum parâmetro de decisão; só medição | — | — | proposta, **bloqueada** pelo recorte estritamente anterior |
| T-014 | OI **em nível** como proxy de profundidade | [[KB-0024-open-interest-como-posicionamento-evidencia-e-folclore]] | normalização entre mercados **a definir** (por OI próprio recente ou `open_interest_value`) | a definir | — | proposta |
| T-015 | detector de OI **bilateral** (lado de baixo além do de cima) | [[KB-0025-o-nosso-detector-de-open-interest-so-olha-para-cima]] | `DetectorSide.BOTH` em `open_interest_change_1h`; seria `detector_version` nova | a definir | — | proposta, **bloqueada** pelo bloqueio de `deriv_history` |
| T-016 | funding como filtro direcional de entrada | [[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]] | — | — | — | **proposta e retirada em 2026-09-06**, antes de qualquer coleta: a melhor evidência direta no nosso mercado e corretora (Binance USDⓈ-M, 2021–2024) mostra poder preditivo à frente ~zero por ativo; a versão transversal exige carteira, neutralização e giro que o Lab não tem |

**T-016 fica registrada mesmo tendo morrido no mesmo dia**, pela mesma regra que preservou a T-011:
foi abandonada por argumento sobre evidência externa, **não** por resultado nosso, e está aqui com o
motivo para que ninguém a reproponha como ideia nova. Ressalva obrigatória: a evidência que a matou é
sobre **outra variável** (variação, não nível), **outro universo** e **outro horizonte** — ela é
prior desfavorável, não refutação.

**Diagnósticos registrados** (não são variantes; **contam como inspeção da amostra**):

| ID | Diagnóstico | Nota | Status |
|---|---|---|---|
| D-008 | motivos de indisponibilidade de `funding_change_8h`, `open_interest_change_1h/4h`, com denominador (chave ausente · valor presente · `missing_input` · `warmup` · sem vetor) | [[KB-0020-funding-change-8h-nunca-calcula]] | proposto |
| D-009 | contagem de disparos de `OPEN_INTEREST_SPIKE` desde o armamento (previsão: zero) | [[KB-0020-funding-change-8h-nunca-calcula]] | proposto |
| D-010 | mistura de `funding_kind`, idade da leitura e fase do ciclo no instante das decisões | [[KB-0019-o-que-a-nossa-funding-rate-mede-de-fato]] | proposto |
| D-011 | cobertura de `index_price` e distribuição do prêmio contra o índice, com recorte **estritamente anterior** | [[KB-0021-funding-como-preco-de-posicionamento-nao-como-previsao]] | proposto |
| D-012 | associação de `funding_rate` (nível, condicionada ao **sinal**) com o resultado | [[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]] | proposto |
| D-013 | taxa base do `FUNDING_ANOMALY` e retorno a horizonte fixo, **com grupo não disparado**, separando nível · desvio · sinal · limite vigente · cadência | [[KB-0023-funding-extremo-como-contrarian-a-afirmacao-mais-repetida]] | proposto |
| D-014 | quadrantes OI × preço nos outcomes existentes, com controle por `taker_imbalance_5m` | [[KB-0024-open-interest-como-posicionamento-evidencia-e-folclore]] | proposto |
| D-015 | coincidência entre queda acentuada de OI e eventos de `liquidations` (validação de instrumento) | [[KB-0025-o-nosso-detector-de-open-interest-so-olha-para-cima]] | proposto, depende de corrigir a semântica do `notional` |
| D-016 | duração dos acompanhamentos (`exit_ts − entry_ts`) e taxa de atravessamento explícita, separando atravessamento **confirmado**, **inferido** e **indeterminado** | [[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]] | proposto |

**Não é tentativa nem diagnóstico — é bug de instrumento**, e por isso não consome multiplicidade:
`load_deriv_history` sem chamada em produção, deixando três features `missing_input` e o detector
`OPEN_INTEREST_SPIKE` armado e mudo. Vai para [[Open Bugs]], não para esta contagem.

**Inferências retiradas nesta rodada, registradas para não voltarem:** a taxa de atravessamento de
funding de ~13% e a duração média de acompanhamento de ~1 h derivada dela
([[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]]) — misturavam populações e assumiam
que atravessamento inferido é atravessamento real.

**Consequência de multiplicidade, repetida:** T-012 a T-016 e D-008 a D-016 nasceram da inspeção da
coorte e do código de 2026-09-06. Nenhuma pode ser confirmada nessa mesma população; a confirmação
exige janela futura reservada, declarada **antes** da coleta.

## Acréscimo de 2026-09-06 (quarta rodada de conhecimento — regime de mercado e volatilidade)

Linhas **acrescentadas**, nunca editadas. **Tentativas avaliadas continuam em 0.** Diferença desta
rodada em relação à terceira: **houve SQL**, na instância local (o Docker local subiu; a VPS
continua recusada pelo portão de permissão). Nenhuma candidata foi rodada.

| ID | Candidata | Nota de origem | Parâmetros | `δ` | Início/fim UTC | Status |
|---|---|---|---|---|---|---|
| T-017 | carimbo de regime no envelope do sinal (`regime_id`, par `{trend, volatility}`, `confidence`, `classifier_version`, idade em segundos, `volatility_ratio`, `breadth.fraction`) | [[KB-0030-o-regime-nao-chega-ao-sinal]] | nenhum parâmetro de decisão; **observação sem decisão** | — | — | proposta — pré-requisito de toda estratificação por regime |
| T-018 | referência de volatilidade **por hora UTC** em vez da mediana agrupada | [[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]] | 24 medianas; exigiria 480 amostras **por hora** (20× a história atual) | seria `regime_v1` | — | proposta, **bloqueada por amostra**; a alternativa barata é gravar a hora UTC e corrigir na análise |
| T-019 | publicar a fração de avanços **incondicional** ao lado da conjunta na amplitude | [[KB-0033-amplitude-de-mercado-a-nossa-e-condicionada-a-volume]] | nenhum; só medição adicional em `supporting_features` | — | — | proposta |
| T-020 | tendência **por mercado** gravada junto do sinal (chamar `classify_market_trend`, que já existe e não tem chamada) | [[KB-0034-btc-como-fator-e-o-regime-global-que-e-so-o-btc]] | os mesmos limiares do `regime_v0` | — | — | proposta |
| T-021 | escalar exposição pelo inverso da volatilidade (Barroso & Santa-Clara) | [[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]] | alvo de volatilidade a definir | — | — | **proposta e adiada para o M4 no mesmo dia**: o Lab de sombra não dimensiona posição, e `PnL de carteira` é *não aplicável* — abrir braço de sombra para isso gastaria dia de coleta numa pergunta que o instrumento não responde |

**T-021 fica registrada mesmo tendo sido adiada no mesmo dia**, pela regra que preservou a T-011 e a
T-016: foi barrada por **limite do instrumento**, não por resultado, e está aqui com o motivo.

**Diagnósticos registrados** (não são variantes; **contam como inspeção da amostra**):

| ID | Diagnóstico | Nota | Status |
|---|---|---|---|
| D-017 | persistência do estimador horário: autocorrelação de |retorno| nos atrasos 1–48 h, com **poder declarado**, e a mesma conta no retorno com sinal | [[KB-0027-aglomeracao-de-volatilidade-o-que-ela-licencia]] | proposto, bloqueado por amostra (47 horas) |
| D-018 | discordância de rótulo `LOW`/`NORMAL`/`HIGH` entre o nosso estimador, Parkinson e Garman-Klass sobre as mesmas horas | [[KB-0028-o-nosso-estimador-de-volatilidade-e-o-mais-ineficiente]] | proposto — mede **sensibilidade**, não precisão |
| D-019 | duração e número de transições do par `{trend, volatility}`, e idas-e-voltas em 15 min | [[KB-0029-hamilton-e-o-que-um-limiar-com-histerese-nao-e]] | proposto, bloqueado pelo warm-up |
| D-020 | curva do warm-up: `samples` e `distinct_days` por dia, e horas **rejeitadas** por motivo (< 60 min · sem âncora · não contígua · preço zero) | [[KB-0031-o-classificador-de-regime-esta-mudo-por-warm-up]] | proposto — é o mais barato e o mais urgente |
| D-021 | mediana do estimador **por hora UTC** e taxa de troca de faixa contra a mediana agrupada | [[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]] | proposto, exige ≥ 20 dias para separar hora de dia |
| D-022 | distribuição conjunta das três frações de amplitude (incondicional · com volume · conjunta) e o seu ciclo diário | [[KB-0033-amplitude-de-mercado-a-nossa-e-condicionada-a-volume]] | proposto |
| D-023 | R² e beta de cada mercado contra o BTCUSDT em 5 min e em 1 h, distribuição transversal | [[KB-0034-btc-como-fator-e-o-regime-global-que-e-so-o-btc]] | proposto |
| D-024 | ciclo de trabalho do piso: fração admitida por `[atr_pct_min, atr_pct_max]` por hora UTC, **medida no ATR que a `momentum_v1` de fato consome** (`rolling_window_v1`), nunca no `atr_14_pct` do M2 | [[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]] | proposto — pré-requisito de qualquer mudança no piso |

**Não é tentativa nem diagnóstico — é estado do instrumento**, e por isso não consome
multiplicidade: o classificador em warm-up (47/480 amostras, 3/20 dias), o `regime_id` nunca escrito
nos sinais, e a amplitude nunca utilizável na instância observável. Vão para [[Open Bugs]] ou para a
página do módulo, conforme o caso.

**Inferências retiradas nesta rodada, registradas para não voltarem:**

1. **"A razão de volatilidade percorreu 0,505 a 2,245"** como se fosse leitura do sistema — não é: o
   classificador não calculou razão nenhuma no período, e o número é meu, contra a mediana de 47
   horas ([[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]]).
2. **"O motivo `gap` prova que falta a vela de 240 minutos atrás"** — falso: qualquer minuto ausente
   na janela produz o mesmo motivo ([[KB-0033-amplitude-de-mercado-a-nossa-e-condicionada-a-volume]]).
3. **A primeira versão da H-KB0035a**, que mediria o piso da `momentum_v1` com o ATR do M2 — dois
   instrumentos diferentes com o mesmo apelido.
4. **A razão de variâncias da KB-0027 escrita na escala da soma** em vez da média.

**Consequência de multiplicidade, repetida:** T-017 a T-021 e D-017 a D-024 nasceram da inspeção do
código e do dado de 2026-09-06. Nenhuma pode ser confirmada nessa mesma população; a confirmação
exige janela futura reservada, declarada **antes** da coleta.

## Quinta rodada (2026-09-06) — execução e microestrutura do preenchimento

**Nenhuma variante nova de estratégia.** A rodada não gastou multiplicidade em parâmetros: gastou em
diagnósticos e em duas mudanças de contrato. O que entra aqui, portanto, são **diagnósticos** e
**inferências retiradas**.

| ID | Diagnóstico | Nota | Status |
|---|---|---|---|
| D-025 | custo de atravessar o book por tamanho, por sinal, com a fração sem cobertura publicada junto | [[KB-0036-o-tamanho-que-a-sombra-nunca-declara]] | proposto, bloqueado pelo carimbo de execução |
| D-026 | spread cotado no instante da decisão, por estratégia e por decil | [[KB-0037-o-spread-assumido-contra-o-spread-medido]] | proposto, bloqueado pelo carimbo — e o **corte por decil** exige, além dele, um **ranking congelado no instante**, que o carimbo sozinho não dá |
| D-027 | sensibilidade a taxa de 4 / 4,5 / 5 bps por lado, sobre a mesma população e as mesmas censuras | [[KB-0038-a-taxa-de-4-bps-nao-e-nem-maker-nem-taker]] | proposto — **roda hoje**, sem pré-requisito |
| D-028 | contexto da barra de saída (amplitude e gap) por resultado, mais sensibilidade a deslocamento assimétrico | [[KB-0039-tipos-de-ordem-e-o-que-a-sombra-assume-sem-dizer]] | proposto — descreve contexto, **não** valida simetria de execução |
| D-029 | teto de capacidade por tamanho, condicionado à cobertura, com o orçamento declarado pelo Everton | [[KB-0040-a-lei-da-raiz-quadrada-e-o-regime-que-nao-e-o-nosso]] | proposto, bloqueado pelo carimbo |
| D-030 | decomposição por entrada: deslocamento referência→entrada, os 6 bps assumidos, a taxa e o funding, tudo no mesmo denominador | [[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]] | proposto — **roda hoje** |
| D-031 | erro de referência entre a abertura e o meio do book, assinado, com **média** e não só quantis | [[KB-0042-o-open-nao-e-preco-executavel]] | proposto, bloqueado pelo carimbo |
| D-032 | retorno entre aberturas no minuto seguinte à entrada, medido contra a abertura bruta | [[KB-0043-selecao-adversa-o-custo-que-so-aparece-depois-do-fill]] | proposto — **roda hoje** |
| D-033 | cobertura do carimbo de execução | [[KB-0044-o-que-morre-em-dez-segundos]] | proposto |

**Não é tentativa nem diagnóstico — é estado do instrumento:** o book de 20 níveis e os tamanhos no
topo nunca são gravados; `volume_24h` tem 6 linhas em 55.709, e há um **mecanismo consistente com
essa cobertura**: o refresh REST e o `bookTicker` usam o mesmo `TICKER_FIELDS` e cada escrita apaga
com `HDEL` os campos do outro (**as seis linhas não foram atribuídas individualmente**);
`next_funding_time` tem zero linhas por omissão no dicionário do snapshot. Vão para [[Open Bugs]].

**Inferências retiradas nesta rodada, registradas para não voltarem:**

1. **"A lei da raiz quadrada é sobre metaordens, nós somos ordem única, logo ela não se aplica"** —
   falso: **61% das metaordens** da amostra de Donier & Bonart têm uma única ordem-filha. O que
   separa os regimes é a normalização (volume e volatilidade **diários**) e o objeto medido (impacto
   de **pico**, não permanente, e nenhum dos dois é o preço pago).
2. **A decomposição que "fechava" em 6 bps** (1,15 + 2,3 + 2,3): dois termos se sobrepunham,
   diferença de medianas não é mediana da diferença, e o erro de referência vale ~±**meio** spread.
3. **"O Lab cobra o erro de referência sempre no lado adverso"** — não cobra: aplica acréscimo fixo
   à abertura, e o custo contra o meio do mercado oscila para os dois lados.
4. **"O deslocamento referência→entrada é variância, não viés"** — quantis não determinam média
   (−1, 0, +100 tem mediana 0 e média +33).
5. **"Somos o lado informado, a contraparte é formador de mercado, o spread efetivo é maior"** —
   nada disso demonstrado.
6. **"Falta produtor para `volume_24h`"** — o produtor existe; o defeito é disputa de escritores.
7. **"15% de 1 R dá orçamento de 3,8 bps por lado para o book"** — 15% de 51 bps são 7,65 bps
   **totais**, já consumidos pelos 8 bps de taxa.
8. **"68 dos 200 livros" e "28+41 = 69"** apresentados como a mesma amostra — são **duas leituras**
   do Redis, segundos de diferença.

**Correções por nota, para quem consultar este registro como memória dos erros.** Os oito itens
acima são os de maior alcance; a lista completa por nota está na seção "Segunda opinião (Astra)" de
cada uma, e os pareceres inteiros ficaram em `.claude/state/astra-review-KB-0036-0038-execucao.md`,
`astra-review-KB-0039-0041-execucao.md` e `astra-review-KB-0042-0044-execucao.md`. Resumo:

| Nota | O que foi retirado ou estreitado |
|---|---|
| [[KB-0036-o-tamanho-que-a-sombra-nunca-declara]] | critério de adequação dos 6 bps limitado a **custo estático da perna de entrada no instante da decisão**, com cobertura obrigatória; "acima de 5.000 mais da metade não cabe" (são 34% em 20 mil); "tamanho é o único parâmetro que decide"; "ordem pequena executa no toque"; e as duas leituras do Redis apresentadas como uma amostra só |
| [[KB-0037-o-spread-assumido-contra-o-spread-medido]] | 0,15 → **0,30 bps** de ida e volta; a falsa garantia de "p90 abaixo de 6 implica erro máximo de 2 bps"; "monotônico"; "a dispersão é quase toda entre mercados"; e a causalidade atribuída ao filtro de volume |
| [[KB-0038-a-taxa-de-4-bps-nao-e-nem-maker-nem-taker]] | tarifa de **exemplo** distinguida de tarifa efetiva; "inequivocamente taker nos dois lados"; 51 bps declarado como denominador **de exemplo**; e a comparação com os 14 bps de deslocamento absoluto |
| [[KB-0039-tipos-de-ordem-e-o-que-a-sombra-assume-sem-dizer]] | "é o modelo de uma ordem a mercado" e "sempre preenche"; amplitude de vela validando simetria de execução; e "stop-primeiro mais deslocamento é dupla penalização" |
| [[KB-0040-a-lei-da-raiz-quadrada-e-o-regime-que-nao-e-o-nosso]] | autoria do arXiv 2205.07385 (é **Emilio Said**); a omissão da dependência de velocidade; a tabela que comparava raiz quadrada com custo de book; e o teto de capacidade mal calculado |
| [[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]] | "variância, não viés"; a não linearidade da geometria como prova de deterioração; a perspectiva invertida do stop numa compra; a amostra selecionada não declarada; o "poder plausível" da H2; a comparação causal dos grupos de 60 e 120 s; "500 a 5.000 cabem em um a três níveis"; e a ressalva **errada** sobre o JOIN de 1 minuto |
| [[KB-0042-o-open-nao-e-preco-executavel]] | a decomposição com termos sobrepostos; "o Lab cobra o erro sempre no lado adverso"; mediana e IQR como prova de ausência de viés; abertura fora do intervalo bid-ask como prova de atraso; e a conversão linear de segundos em bps |
| [[KB-0043-selecao-adversa-o-custo-que-so-aparece-depois-do-fill]] | a perspectiva do markout; o transporte de magnitudes de outra venue; o retorno contra `P_entry` como evidência (contaminado pelos 6 bps); os dois critérios sobre stops e sobre mediana zero; e o poder presumido sem cálculo |
| [[KB-0044-o-que-morre-em-dez-segundos]] | "falta produtor para `volume_24h`"; "TTL é janela histórica"; `market_snapshots` como permanente; e a promessa de que o carimbo torna **todas** as perguntas respondíveis — não dá ranking histórico nem mid posterior, e o `EXEC-H` nem depende dele |

**Consequência de multiplicidade:** D-025 a D-033 nasceram da inspeção do código e do dado de
2026-09-06 e **contam como inspeção da amostra**. Nenhum pode ser confirmado nessa mesma população;
a confirmação exige janela futura reservada, declarada **antes** da coleta.

## Sexta rodada (2026-09-06) — livros de estratégia

Linhas **acrescentadas**, nunca editadas. **Tentativas avaliadas continuam em 0.** Esta é a primeira
rodada desde a primeira a propor variantes de estratégia, e por isso é também a que mais precisa
desta página.

**Correção da T-001, com a mesma ID e o motivo, como a regra da página manda.**

| ID | Candidata | Nota de origem | Parâmetros | `δ` | Início/fim UTC | Status |
|---|---|---|---|---|---|---|
| T-001 | gate de tendência (`return_4h > 0`) | [[KB-0048-o-teste-antes-da-regra-e-o-filtro-que-ja-estava-dentro]] | — | — | — | **retirada em 2026-09-06, antes de qualquer coleta:** é **redundante com a condição de entrada**. `close_t > max(C_{t−1} … C_{t−20})` nos fechamentos de 15m implica `close_t > C_{t−16}`, e 16 barras de 15 min são 240 minutos. O gate só recusaria sinais quando a feature estivesse indisponível ou defasada — e isso seria publicado como benefício da confirmação de tendência. Achado da Astra, conferido por mim (`indicators.py:141,147`, `price.py:38`) |

**T-001 fica registrada** pela mesma regra que preservou T-011, T-016 e T-021: foi abandonada por
argumento sobre a **definição** da regra, não por resultado, e está aqui com o motivo para que
ninguém a reproponha como ideia nova. Ressalva: a implicação é exata na **série de 15m da
estratégia**; a feature do M2 é calculada sobre velas de 1 min com âncora própria, e a versão `_live`
não satisfaz automaticamente a equivalência. Por isso o `D-CHAN-c` existe.

### Variantes novas

| ID | Candidata | Nota de origem | Parâmetros | `δ` | Início/fim UTC | Status |
|---|---|---|---|---|---|---|
| T-022a/b | **alvo assimétrico** (L1) | [[KB-0054-a-cauda-direita-e-o-alvo-fixo-que-a-corta]] · [[KB-0046-r-multiplos-e-o-r-que-a-simetria-esconde]] | `target_atr ∈ {3.0, 4.5}` contra a base de 1,5; stop, invalidação e horizonte inalterados | a definir (efeito mínimo relevante, **antes** da janela) | — | proposta (2 contrastes), **dentro do bloco de saídas** |
| T-023a/b | **sem alvo** e **saída por canal oposto** (L2) | [[KB-0045-turtles-a-entrada-que-ja-temos-e-a-saida-que-nao]] | `EXIT-NOTGT` (sem alvo) e `EXIT-CHAN` (sem alvo + mínimo dos 10 fechamentos de 15m) | a definir | — | proposta (2 contrastes: `NOTGT − base` e `CHAN − NOTGT`), **dentro do bloco de saídas** |
| T-024 | **filtro de eficiência de Kaufman** (L3) | [[KB-0047-razao-de-eficiencia-de-kaufman]] | `efficiency_window = 20`; `efficiency_min = θ` — **θ a definir pela distribuição condicionada**, nunca por outcomes | a definir | — | proposta, **bloqueada** pelo `D-ER` |
| T-025 | **contração de volatilidade** (L4) | [[KB-0053-contracao-de-volatilidade-o-unico-pedaco-formalizavel]] | `ATR(8)/ATR(32)`, **as duas janelas terminando em `t−1`**, estimador declarado; `contraction_max = θ` a definir | a definir | — | proposta, **bloqueada** pelo `D-CONTR` e pelo congelamento do estimador |
| T-026 | **relógio de amostragem** (barras de volume ou de dólar) | [[KB-0052-meta-rotulagem-o-formato-de-todo-filtro-que-propusemos]] | — | — | — | **proposta e bloqueada no mesmo dia:** não é reparametrização, é outra estratégia (muda rompimento, ATR, volume relativo, cadência e rearme); e `quote_volume` é *nullable* em parte do universo |
| T-027 | **alongar o horizonte** além de 14.400 s | [[KB-0054-a-cauda-direita-e-o-alvo-fixo-que-a-corta]] | — | — | — | **proposta e adiada no mesmo dia:** exige contraste próprio e muda exposição, atravessamento de funding e ocupação de slots; **não** entra no primeiro lote |

**Família declarada, e é a novidade de método desta rodada.** T-005, T-022 e T-023 procuram a mesma
coisa — uma política de saída melhor sobre as **mesmas entradas congeladas** —, então formam **um
bloco**: 8 políticas únicas (com a base compartilhada) e **7 contrastes**, com **Holm a 5% sobre os
sete**. Holm aceita dependência entre testes, mas **não conserta** p-valores calculados tratando
entradas correlacionadas como independentes; a incerteza sai de reamostragem em blocos de tempo. O
bloco **não autoriza** combinar o vencedor de T-005 com o de T-022 — isso seria comparação adicional,
e tentativa a mais.

### Diagnósticos e convenções registrados

| ID | Diagnóstico | Nota | Status |
|---|---|---|---|
| D-034 | distribuição do payoff nominal `(target1 − P_entry)/(P_entry − stop)` e do desvio referência→`P_entry` | [[KB-0046-r-multiplos-e-o-r-que-a-simetria-esconde]] | proposto — **roda hoje**, usando `P_entry` e não o `open` bruto |
| D-035 | distribuição de `ER(20)` condicionada a sinal disparado | [[KB-0047-razao-de-eficiencia-de-kaufman]] | proposto; grupo de comparação é **replay reconstruído** |
| D-036 | correlação de postos entre `ER(20)`, `VR(2)` e `VR(4)`, com o estimador de `VR` declarado antes | [[KB-0048-o-teste-antes-da-regra-e-o-filtro-que-ja-estava-dentro]] | proposto — regra de priorização, **não** prova de redundância |
| D-037 | mercados com sinal que não estão mais monitorados, separando outcomes encerrados, censurados e abertos | [[KB-0048-o-teste-antes-da-regra-e-o-filtro-que-ja-estava-dentro]] | proposto; não identifica quem saiu e voltou |
| D-038 | fração de sinais com `return_4h > 0`, **por reconstrução com velas** | [[KB-0048-o-teste-antes-da-regra-e-o-filtro-que-ja-estava-dentro]] | proposto — confirma ou derruba a retirada da T-001 |
| D-039 | benchmark aleatório condicionado (L5) | [[KB-0049-walk-forward-que-nao-temos-e-o-nulo-que-nunca-calculamos]] | proposto — **não é** teste de permutação validado; especificar população, estatística, calendário, invalidação e censura **antes** de escolher `K` |
| D-040 | concentração temporal: acompanhamentos abertos por minuto, mercados por minuto e hora, blocos e outcomes por bloco | [[KB-0051-tres-barreiras-mais-uma-e-a-amostra-que-nao-e-independente]] | proposto — **roda hoje**; mede concentração, **não** tamanho efetivo de amostra |
| D-041 | distribuição da razão de contração e correlação com `atr_pct` e `ER` | [[KB-0053-contracao-de-volatilidade-o-unico-pedaco-formalizavel]] | proposto; exige estimador, aquecimento e janelas congelados |

**Convenções que não são tentativa nem diagnóstico** (não consomem multiplicidade): `C-META`
(relatório de filtros com estratégia-base, população avaliável, cobertura e os quatro números),
`C-COST` (publicar `custo_R_nominal_referencia` ao lado de `atr_pct_min`, sem mudar população) e
`C-FCAST` (score contínuo não vinculante, com faixas e alvo declarados antes).

**Inferências retiradas nesta rodada, registradas para não voltarem:**

1. **"O canal oposto raramente decidiria a saída em 4 h"** — o raciocínio estava errado; o que
   restringe o canal é a **concorrência com a invalidação nos 9 primeiros fechamentos**, e a partir
   do décimo ele pode disparar sozinho dentro do horizonte (contraexemplo numérico da Astra).
2. **"Os dois lados do payoff se deslocam na mesma direção"** — é efeito duplo: risco `a + δ`, ganho
   `a − δ`.
3. **"Teto de custo em R equivale a piso de `atr_pct`"** — só nominalmente; depende de `g`, e
   `P_entry` não é conhecido na decisão.
4. **"Zero é o nulo errado"** — zero continua sendo a referência de rentabilidade; o benchmark
   responde outra pergunta.
5. **"`VR` e `ER` medem quase a mesma coisa"** — dois arranjos dos mesmos 20 retornos dão a mesma
   `ER` com `VR(2)` de 0 e de 1,894737.
6. **"Todas as candidatas de filtro são meta-rótulos sobre a `momentum_v1`"** — filtro não é
   meta-rótulo (o meta-rótulo é o alvo do modelo secundário), e a #11 e a #12 são sobre a
   `volume_anomaly_v1`.
7. **"`nº outcomes / nº blocos` é o tamanho efetivo da amostra"** — mede outcomes por bloco, e
   concentrar a população faz a razão **subir**.
8. **"O `rvol_min = 1,5` é o critério de volume do CANSLIM"** — o do IBD é volume diário 40–50% acima
   da **média**; o nosso é 1,5× a **mediana** de 96 barras de 15 min, e numa distribuição assimétrica
   pode ficar abaixo da média.
9. **"MFE é sempre nulo e não ajuda"** — um extremo pode ser conhecido com o outro nulo, e um gap
   favorável pode registrar excursão acima do alvo creditado.
10. **"Qualquer cauda é truncada em 4 horas"** — o horizonte limita **duração**, não magnitude; e
    variar só o alvo mede o efeito do alvo **condicionado** ao horizonte.
11. **"A contribuição do decil superior sobre o `R_net` total" como métrica de cauda** — degenera
    quando a soma total é perto de zero ou negativa.
12. **"Clenow pirâmide"** — as regras publicadas dele rejeitam piramidação explicitamente.
13. **"Avaliação antes do fim da janela é sempre tentativa inválida"** — monitoramento **descritivo**
    continua permitido; o proibido é a inferência antecipada e a parada oportunista.

**Consequência de multiplicidade, repetida:** T-022 a T-027 e D-034 a D-041 nasceram da inspeção do
código e do dado de 2026-09-06, e da leitura de fontes externas. Nenhuma pode ser confirmada nessa
mesma população; a confirmação exige janela futura reservada, declarada **antes** da coleta, e o piso
de 100 outcomes e 30 dias **não substitui cálculo de potência**.

## Sétima rodada (2026-09-06) — meme coins

Linhas **acrescentadas**, nunca editadas. **Tentativas avaliadas continuam em 0.** Diferença desta
rodada: é a que teve **mais medição própria** — VPS, 45 h de dados, 200 mercados monitorados, 581 mil
velas de 1 min, mais 50 livros de 20 níveis do hot state e o stream de universo do Redis. Nenhuma
candidata foi rodada e nenhum diagnóstico foi executado.

**Restrição estrutural que decidiu o formato da fila, e vale registrar aqui porque ela invalida
famílias inteiras de candidatas antes de elas serem propostas:** o `StrategyContext`
(`packages/core/hunter_core/strategies/base.py:109`) carrega apenas `candles_1m`, `funding`,
`open_interest`, `eligible` e `eligibility_reason`, e recusa velas de outro símbolo. Portanto
**nenhum filtro por spread, livro, volume de 24 h ou por outro mercado é implementável hoje** sem
mudança de contrato.

### Variantes novas

| ID | Candidata | Nota de origem | Parâmetros | `δ` | Início/fim UTC | Status |
|---|---|---|---|---|---|---|
| T-028 | **teto de ATR% mais apertado** (M-A) | [[KB-0057-a-volatilidade-das-memes-e-o-piso-que-bane-o-btc]] | `atr_pct_max ∈ {0,03; 0,02}` contra a base de 0,05; θ de quantil congelado **antes** da janela | a definir | — | proposta, **bloqueada** pelos diagnósticos `D-042` e `D-043` (exigência da Astra) |
| T-029 | **teto de funding absoluto como custo** (M-E) | [[KB-0059-funding-em-memes-a-cadencia-antes-do-sentimento]] | `abs_funding_max = θ`, simétrico, **não direcional** | a definir | — | proposta. **Não duplica a T-016**: aquela era filtro direcional retirado por prior desfavorável; esta é simétrica e não promete previsão |
| T-030 | **teto de amplitude da barra de referência** (M-G) | [[KB-0064-a-cauda-de-queda-e-o-que-o-risk-engine-vai-precisar]] | `bar_range_atr_max = K`, quantil congelado antes | a definir | — | proposta |
| T-031 | **piso de liquidez** (`quote_volume_24h` mínimo) (M-B) | [[KB-0058-spread-e-profundidade-o-custo-de-sair-de-uma-meme]] | — | — | — | **proposta e bloqueada no mesmo dia:** o `StrategyContext` não carrega o campo (`base.py:109`), e o `ts` do hash `ticker` é compartilhado entre REST e WS (`hot_state.py:61`, `sampling.py:55`), então volume velho pode aparecer preenchido e "fresco". Achado da Astra |
| T-032 | **braço por coorte de meme** ("só memes" ou "sem memes") | [[KB-0065-a-coorte-de-memes-nao-se-distingue-do-resto]] | — | — | — | **proposta e retirada no mesmo dia, antes de qualquer coleta:** dentro de cada estratégia as coortes não se distinguem na amostra atual **e**, decisivo, nenhuma regra consegue saber em que coorte está — o contexto é de um símbolo só e recusa velas de outro |
| T-033 | **estratégia de listagem** (primeiros N dias de um perpétuo novo) | [[KB-0062-o-primeiro-dia-que-nao-conseguimos-ver]] | — | — | — | **proposta e bloqueada no mesmo dia:** aquecimento de 24 h 15 min (`momentum_v1`) e 24 h (`volume_anomaly_v1`); o backfill de 1499 min não inventa história anterior à listagem; e não gravamos `onboardDate`. A refutação é **inconstruível**, que é o que a [[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] proíbe |
| T-034 | **detecção de pump em tempo real** | [[KB-0061-pump-and-dump-o-detector-que-precisa-de-25-segundos]] | — | — | — | **proposta e bloqueada no mesmo dia:** a literatura opera em blocos de 25 s sobre o tape; nós decidimos sobre barras fechadas de 5 e 15 min. Não é reparametrização, é outra arquitetura |

**T-031 a T-034 ficam registradas mesmo tendo morrido no mesmo dia**, pela mesma regra que preservou
T-011, T-016, T-021, T-026 e T-027 — para que ninguém as reproponha como ideia nova.

### Diagnósticos registrados

| ID | Diagnóstico | Nota | Status |
|---|---|---|---|
| D-042 | `D-MEME-ATR` — ciclo de trabalho de `atr_pct_min`/`atr_pct_max` no ATR **que a estratégia consome**, por coorte e hora UTC, com gate isolado · exclusões posteriores · emissões efetivas separados | [[KB-0057-a-volatilidade-das-memes-e-o-piso-que-bane-o-btc]] | proposto — **roda hoje**; bloqueia a T-028 |
| D-043 | `D-MEME-LIQ` — ATR contra **spread** condicionado a sinal, com snapshots comprovadamente anteriores; sem BTC, por coorte, removendo um mercado por vez | [[KB-0058-spread-e-profundidade-o-custo-de-sair-de-uma-meme]] | proposto; bloqueia a T-028 |
| D-044 | `D-MEME-CUSTO` — `EXEC-C` por coorte, mais `R_net` recomputado com o spread medido de cada coorte | [[KB-0058-spread-e-profundidade-o-custo-de-sair-de-uma-meme]] | proposto — **roda hoje** |
| D-045 | `D-MEME-FUND` — funding em **bps por hora de exposição** (intervalo medido, não cadência modal), cadência publicada junto, e custo por acompanhamento | [[KB-0059-funding-em-memes-a-cadencia-antes-do-sentimento]] | proposto; `next_funding_time` continua com zero linhas |
| D-046 | `D-MEME-BETA` — distribuição de β e R² por coorte, com sensibilidade à retirada de **mercados** e de **blocos de tempo** | [[KB-0060-correlacao-com-o-btc-e-a-meme-season]] | proposto |
| D-047 | `D-MEME-PICO` — lado do máximo em **janela fixa** (barra de referência → entrada + 2 h), independente da saída, com empates, cobertura, maturação e dependência declarados antes | [[KB-0061-pump-and-dump-o-detector-que-precisa-de-25-segundos]] | proposto — **não identifica exaustão**; sem grupo de comparação é descrição |
| D-048 | `D-MEME-SAIDA` — os 27 sinais em 14 mercados que saíram do universo, contra os 982 que ficaram | [[KB-0062-o-primeiro-dia-que-nao-conseguimos-ver]] | proposto — **roda hoje** |
| D-049 | `D-MEME-GAP` — saída contra barreira nos stops, decomposta em `exit_at_open` · `exit_base` · barreira · custos; o resultado se chama **gap na resolução do modelo** | [[KB-0064-a-cauda-de-queda-e-o-que-o-risk-engine-vai-precisar]] | proposto — **roda hoje** |
| D-050 | `D-MEME-POP` — retrato por **estratégia/versão × coorte**, mercados desmonitorados incluídos, `count(r_multiple)` ao lado das médias, corte temporal declarado por consulta | [[KB-0065-a-coorte-de-memes-nao-se-distingue-do-resto]] | proposto — **roda hoje** |
| D-051 | `D-MEME-ATRPAR` — taxa de alvo pareada por decil de `atr_pct` dentro de cada estratégia | [[KB-0065-a-coorte-de-memes-nao-se-distingue-do-resto]] | proposto; **ausência de diferença não demonstra redundância** |

**Não é tentativa nem diagnóstico — é proveniência**, e por isso não consome multiplicidade:
`H-KB0056` (carimbar `monitor_rank`, tamanho e regra do universo e a versão da lista de marcação),
`H-KB0062a` (persistir `onboardDate`, em **duas** camadas: `normalize.py:137` e
`universe_repo.py:64`) e `H-KB0062b` (persistir o diff de universo em tabela própria).

**Não é tentativa nem diagnóstico — é estado do instrumento:** `enable_social_intelligence` e
`enable_onchain` são flags **sem consumidor funcional**, e `intelligence_events` é tabela sem
escritor nem leitor ([[KB-0063-social-e-on-chain-a-linha-que-nao-atravessamos]]). Vai para a página
do módulo, não para esta contagem.

**Inferências retiradas nesta rodada, registradas para não voltarem.** A Astra recusou a primeira
versão das dez notas, em três passagens (`.claude/state/astra-review-KB-0056-0058-memecoins.md`,
`astra-review-KB-0059-0061-memecoins.md`, `astra-review-KB-0062-0065-memecoins.md`):

1. **"Zero sinais de Momentum em BTCUSDT confirma que o piso o exclui"** — é **compatibilidade
   observacional**: o gate de ATR vem depois de rompimento, retorno e `rvol`
   (`momentum_v1.py:180,204`), e o BTC pode estar sendo recusado antes.
2. **"Média simples de TR aproxima Wilder com viés conhecido"** — o viés **não tem direção
   universal**; contraexemplo: TR usual de 0,1%, um choque de 10% e 14 barras normais dá SMA 0,1% e
   Wilder ≈0,3506%.
3. **"As frações abaixo do piso são taxas de recusa operacional"** — a minha consulta atravessa
   lacunas que a `aggregate.py:128` recusa.
4. **"A volatilidade migrou para as listagens novas"** — 42 h sem data de listagem mostram
   heterogeneidade contemporânea, não migração.
5. **"O nosso dado discorda do ME2F porque TRUMP está no meio do pelotão"** — o ME2F mede
   fragilidade combinando volatilidade, concentração e sentimento; ATR de dois dias não refuta isso.
6. **"Meme coin é ativo sem utilidade declarada"** — falso para DOGE e FLOKI, pelas páginas oficiais
   deles. A definição passou a separar origem cultural, utilidade declarada e direito a fluxo de
   caixa.
7. **"Sem carimbo, nenhuma estratificação por meme é possível"** — a **classificação** é
   reconstruível pela identidade do mercado (`record.py:188`); o que se perde é o **denominador**
   (composição e ranking históricos).
8. **"A M-B é testável agora"** — não é: o `StrategyContext` não carrega volume de 24 h, e o `ts`
   compartilhado entre REST e WS deixa volume velho parecer fresco.
9. **"−0,651 entre ATR e profundidade demonstra o mecanismo da M-A"** — associação transversal com
   medidas desalinhadas no tempo não demonstra custo condicionado ao sinal.
10. **"As memes têm funding menos extremo"** — vale só **por liquidação nesta janela**; a comparação
    exige normalizar por hora de exposição, e comparar mínimos de 21 contra 150 mercados favorece o
    grupo maior.
11. **"A coorte B amplifica quando acompanha e não acompanha o resto do tempo"** — β = ρ·σa/σb e
    R² = ρ²; inclinação e ajuste são coisas diferentes, e não há estado alternando.
12. **"0,39 em 15 min e 0,77 diário são comparáveis via efeito Epps"** — Epps explica um mecanismo
    possível sem atribuir a diferença a ele; e a fonte dos 0,77-0,78 **não abriu** (HTTP 403), então
    os números saíram.
13. **"O detector da literatura leva 25 segundos, logo o evento é curto"** — os 25 s são **tamanho de
    bloco**; o artigo descreve movimentos de horas. A Astra abriu o HTML que a minha ferramenta não
    abriu.
14. **"A `volume_anomaly_v1` é literalmente a regra de Kamps & Kleinberg com outro relógio"** —
    fechamento acima do meio da barra não é anomalia de preço contra histórico, e o teto de
    `2 × ATR` faz a estratégia **rejeitar** movimentos explosivos.
15. **"O diff do universo não existe em lugar nenhum depois de 30 minutos"** — está no stream do
    Redis; fui conferir e medi **52 entradas e 52 saídas em 20 h**. E os "30 minutos" eram observação
    da tabela, não política: `prune_dispatched` não fixa prazo e o documentado são sete dias.
16. **"Persistir a data de listagem custa uma linha"** — são duas camadas
    (`normalize.py:137` e `universe_repo.py:64`, que não transfere `metadata`).
17. **"A cauda ruim não está nas memes"** — 19 contra 133 mercados não decide cauda; só sobrevive
    "a maior queda **observada** pertence ao `E_resto`".
18. **"As memes concentram os dois extremos"** — amplitude mediana 11,51% na coorte A contra 12,10%
    no resto.
19. **"Uma barra de −10% atravessa qualquer stop de 1,5 ATR"** — pode ser queda contínua, e a
    distância do stop depende do ATR do instante.
20. **"`stop − exit_price` mede o gap"** — mistura gap e custo assumido (`walker.py:71,155`,
    `pricing.py:53`), inclusive quando não houve gap.
21. **"`R > 1` no alvo é gap favorável"** — o simulador credita só `target1` (`walker.py:73,157`).
22. **"O confundidor de ATR é de primeira ordem"** — se movimentos e barreiras escalam juntos, o
    processo em unidades de ATR preserva tempos e probabilidades de toque; o efeito que sobra anda na
    direção contrária (custo fixo em bps pesa **menos** em R quando o risco percentual é maior).
23. **"A população do Lab já é meme"** — são **92 de 978** sinais. A nota foi renomeada.
24. **"Guardar `occurred_at` evita look-ahead em dado social"** — falta o instante em que o evento
    **e a classificação** ficaram disponíveis.

### Correções da mesma data, com as mesmas IDs e o motivo (a regra desta página)

A revisão da fila pela Astra (`.claude/state/astra-review-fila-memecoins.md`) mostrou que **duas
retiradas minhas usavam argumento falso** e que **um status estava errado**. Linhas novas, nunca
edição das anteriores:

| ID | Correção | Motivo |
|---|---|---|
| T-029 | de "teto de funding **absoluto como custo simétrico**" para **"teto de funding extremo em módulo, com hipótese econômica a escrever"**; e de "proposta" para **"proposta, bloqueada pela alimentação do contexto"** | Dois erros. (a) O Lab só admite LONG e o funding é transferência **assinada** (`base.py:214`, `pricing.py:13,79`): +10 bps custa e −10 bps paga, então um filtro em módulo elimina os dois e atribui a exclusão a "custo" indevidamente. (b) `build_market_context` **não passa `funding`** (`context.py:75`), que é `None` em toda avaliação — o `load_funding` serve à apuração do outcome (`settle.py:60`), não à decisão. Cenário de falha: implementar supondo dado presente, e o filtro nunca atuar (ou tudo virar indisponível) |
| T-031 | de "bloqueada, o contexto não carrega volume de 24 h" para **"especificada por via alternativa"** | O caminho pelo hash `ticker` continua fechado (`ts` compartilhado entre REST e WS). Mas `NormalizedCandle.quote_volume` existe (`domain/market.py:264`) e o contexto tem 1560 minutos de velas, então o volume de cotação de 24 h é **reconstruível somando velas**, sem mudar contrato. Ressalva: o campo é *nullable* em parte do universo. **A minha declaração de impossibilidade estava errada** |
| T-032 | mantida retirada, **com outro motivo** | Eu retirei dizendo que "nenhuma regra sabe em que coorte está". **Falso:** a estratégia conhece o próprio `symbol` e uma lista estática versionada cabe em `default_parameters`. O motivo que sobrevive é **ausência de evidência** — dentro de cada estratégia as coortes não se distinguem, com 10 e 34 toques resolvidos |
| T-033 | mantida bloqueada, com o **aquecimento corrigido** | Eu atribuí 24 h à `volume_anomaly_v1`. Ela exige **289 barras de 5 min e 97 barras completas de 15 min** para o ATR (`volume_anomaly_v1.py:122`), ou seja **também ≥ 24 h 15 min**, com possível espera adicional por alinhamento. Cenário de falha: esperar avaliação em T+24 h e diagnosticar indisponibilidade normal como defeito |

**Correções de método na mesma revisão, que não mudam ID nenhuma:**

25. **"A M-A produz diferença pareada"** — só se a `C-META` avaliar aceitação e recusa sobre as
    **oportunidades fixadas pela base**. Rodada como versão autônoma, ela tem slots e rearme
    próprios (`decide.py:129,152`): recusar uma entrada pode liberar uma oportunidade posterior que
    a base não poderia aproveitar, e parear só sinais coincidentes omite parte do efeito.
26. **"Metade da diferença de funding entre coortes é cadência"** — a frase tinha voltado como fato
    na consolidação do backlog, contrariando a própria KB-0059. A razão entre medianas foi medida; a
    parcela explicada pela cadência **não**.
27. **`K ≥ 14` na M-G seria inoperante** — o ATR implementado inclui a barra corrente
    (`ATRₜ = (13·ATR₍ₜ₋₁₎ + TRₜ)/14`, `indicators.py:62,88`) e `high − low ≤ TR`, então a razão da
    M-G nunca passa de 14. Usar o ATR anterior é **outra definição**, e tem de ser declarada.

**Duplicação verificada pela Astra contra T-001 a T-027:** nenhuma duplicata exata. M-A é parente da
T-007 mas mexe no **teto** e não no piso; M-E difere da T-016 (direcional) e da T-012 (observação de
fase); M-G é parente da T-002 mas amplitude não é impulso, e não equivale à T-025, que compara ATRs
**anteriores**. Serem contrastes distintos **não** os torna buscas estatisticamente independentes.

**Consequência de multiplicidade, repetida:** T-028 a T-034 e D-042 a D-051 nasceram da inspeção do
código e do dado de 2026-09-06. Nenhuma pode ser confirmada nessa mesma população; a confirmação
exige janela futura reservada, declarada **antes** da coleta, e o piso de 100 outcomes e 30 dias
**não substitui cálculo de potência**.

## Relacionados

[[Strategy Backlog]] · [[Index]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] · [[Experiments Index]] ·
[[Strategy Performance]]
