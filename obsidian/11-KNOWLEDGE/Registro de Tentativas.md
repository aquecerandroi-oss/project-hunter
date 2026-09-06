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

## Relacionados

[[Strategy Backlog]] · [[Index]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] · [[Experiments Index]] ·
[[Strategy Performance]]
