---
tags: [astra, revisao, cripto, tendencia, media-movel, h-027, pesquisa]
date: 2026-10-01
updated: 2026-10-01
status: fechada
owner: sexta-feira
decided_on: 2026-10-01
by: Astra + sexta-feira
---

# Revisão da Astra — base de evidência da C1/H-027 (KB-0173 a KB-0179, 01/10/2026)

**Tarefa:** leitura aberta sobre tendência diária em cripto, tendência como condicionante de sinais de curto
prazo e modos de falha (decaimento, regime, sobrevivência, data snooping), e a síntese "que resultado da C1 seria
compatível com a literatura e qual seria suspeito" ([[KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer]]).
Nenhuma medição nova; nenhum desfecho do banco consultado; a [[Fila de Hipoteses]] não foi editada.

**Fonte bruta:** `.claude/state/astra-review-KB-tendencia-diaria.md`.

**Conferência:** recalculou os três cenários da conta ilustrativa (0,0014 / 0,0167 / 0,1111 R) e achou a
inconsistência da fonte (0,263 % na legenda × 0,248 % na linha da tabela 2 de Deprez & Frömmel).

**Sete must-fix, todos aceitos:** (1) incorporar a emenda da H-027 (dois bootstraps dia/mercado, maior p, os dois
ICs, `LIMITE (instrumento)`, regra global — `momentum` refuta + `volume_anomaly` em limite = NÃO CONFIRMA global;
"análise retrospectiva"); (2) a conta de deriva vira ilustração, sem papel de teto (média incondicional não limita
o contraste condicional; stop/alvo e 1 R nominal); (3) contraste binário ≠ β ajustado, e β negativo não implica
média bruta maior no grupo ≤ 0; (4) lucro em nível ≠ superioridade sobre benchmark (KB-0174 corrigida; grupo > 0
lucrativo = "compatível; insuficiente para alfa"); (5) o resumo de Cameron, Gelbach & Miller não demonstra IC
estreito neste desenho (KB-0178 corrigida, wild cluster bootstrap-t só como sensibilidade, por dia e por mercado
separadamente); (6) tercil de ATR% não identifica mecanismo (KB-0176); (7) extrapolações de leitura — "robusto
entre estados" ≠ invariância (KB-0175), Li et al. lido em seções, Fieberg/Zarattini entram pelo resumo, "um ou dois
regimes" não estabelecido (KB-0175, KB-0177).

**Divergência parcial:** ela tiraria o tamanho de β da tabela de leitura; a síntese manteve β̂ ≥ ~0,15 R como
"não calibrado — investigar influência antes de acreditar" (nenhum mecanismo lido produz esse tamanho; 23 clusters
de dia), sem mudar rótulo. **Concordância:** β negativo é compatível no sentido de "não contradiz", não "previsto".

**Fila de Hipóteses:** nenhuma alteração proposta por ela nem feita aqui.

Notas: [[KB-0173-tendencia-diaria-em-cripto-o-tamanho-publicado]] · [[KB-0174-o-filtro-de-tendencia-corta-queda-nao-acrescenta-alta]] ·
[[KB-0175-estado-de-mercado-condiciona-momentum-mas-em-que-direcao]] · [[KB-0176-momento-intradiario-condicionado-o-vizinho-mais-perto]] ·
[[KB-0177-decaimento-e-regime-o-que-a-literatura-de-cripto-mostra]] · [[KB-0178-data-snooping-e-poucos-clusters-o-que-vale-para-a-h-027]] ·
[[Revisoes-Astra/Index|índice das revisões]]
