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

## Relacionados

[[Strategy Backlog]] · [[Index]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] · [[Experiments Index]] ·
[[Strategy Performance]]
