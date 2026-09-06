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

## Relacionados

[[Strategy Backlog]] · [[Index]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] · [[Experiments Index]] ·
[[Strategy Performance]]
