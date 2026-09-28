## RESUMO

**Recomendo `history_v2` com `{first_sample, status_changed, stage_changed, interval_elapsed}`, seguindo o desenho autorizado.** Isso significa **amostragem de 300 s com exceções**, não teto rígido por mercado. Corrigiria a recuperação da última amostra persistida na mesma entrega.

Parecer como `quant-engineer`: **DONE_WITH_CONCERNS**.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Revisão somente leitura.

## TESTES

Não executei testes nem consultei produção. As conclusões abaixo vêm da leitura do código; os números de volume vêm do contexto e do documento fornecido.

## MUST-FIX

**1. Resolver a contradição do brief antes de codificar o comportamento.**

O desenho explicitamente preserva mudanças de status/estágio ([desenho:263](C:/dev/project-hunter/docs/design/retencao-e-disco-2026-09-27.md:263)). Minha recomendação é corrigir o brief para:

> Primeira amostra de cada episódio, mudanças de status/estágio e primeira avaliação válida após 300 s desde a última amostra persistida.

Cenários:

- **Teto rígido:** amostra às 12:00; `WATCHING → HOT → WATCHING` entre 12:01 e 12:03. Às 12:05, o histórico não revela que houve `HOT`. O envelope completo das pontas não recupera o evento intermediário.
- **Exceções:** status/estágio oscilam repetidamente; o volume ultrapassa 12 linhas/h. Portanto, usar 12/h como teto garantido no orçamento de disco seria incorreto.
- **Por mercado versus episódio:** um episódio pode terminar e outro começar dentro dos mesmos cinco minutos. Um teto por mercado também pode suprimir a primeira amostra do novo episódio. Hoje o fechamento libera a identidade para um novo episódio ([collect.py:164](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/collect.py:164)).

**2. Corrigir o marcador durável; sim, o restart é problema em v2.**

Hoje:

- `storage_envelope` grava a marca da avaliação corrente ([rows.py:75](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/rows.py:75));
- a marca em memória avança somente quando houve histórico, após commit ([collect.py:143](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/collect.py:143));
- o restart recupera a marca do snapshot de `opportunities` ([repo.py:254](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/repo.py:254), [runners.py:335](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/runners.py:335)).

**Cenário:** histórico às 12:00; avaliações sem gravação até 12:04; restart. Recupera 12:04 e adia a próxima amostra para aproximadamente 12:09. Restarts repetidos antes do intervalo podem impedir indefinidamente a amostragem periódica de um episódio estável.

Correção: guardar separadamente a **última marca efetivamente persistida**, mantendo-a quando a avaliação não gera histórico; quando gera, atualizar oportunidade e histórico na mesma transação, preservando a promoção em memória após commit.

**A transição v1→v2 também precisa de tratamento:** marcas antigas já têm a semântica errada. Eu recuperaria a última linha real do histórico por oportunidade no bootstrap; sem linha, `None`. Apenas mudar o escritor deixa o primeiro restart vulnerável.

**3. Não declarar preservação integral da trajetória ao remover os outros gatilhos.**

Minha recomendação para **esta entrega autorizada** é removê-los como gatilhos. Mas o contrato precisa dizer: **cada amostra preservada continua explicável; os acontecimentos entre amostras deixam de ser integralmente observáveis**.

| Gatilho removido | Perda concreta, se status/estágio permanecerem iguais |
|---|---|
| Direção e direção do estágio | Uma inversão e reversão entre amostras pode desaparecer. |
| Versões | O instante da troca fica indeterminado; uma versão transitória pode nunca aparecer. |
| Elegibilidade | Um intervalo inelegível pode desaparecer. |
| Regime | Uma mudança breve de regime pode desaparecer. |
| Qualidade | Uma queda e recuperação do livro pode desaparecer. |

Esses cenários são justamente a justificativa atual dos gatilhos ([history.py:16](C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/history.py:16)). Envelope completo não recompõe uma avaliação descartada.

**Custo:** não há dados suficientes para quantificar cada gatilho. O documento diz “96% com score diferente”, o que **não significa 96% disparadas exclusivamente pelo score** ([desenho:111](C:/dev/project-hunter/docs/design/retencao-e-disco-2026-09-27.md:111)). Os motivos podem coexistir ([history.py:160](C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/history.py:160)).

Com episódio contínuo, avaliações regulares e sem transições, a referência é **~12 linhas/h**, redução aproximada de **76%** contra 50/h. Exceções acrescentam gravações e reiniciam o intervalo; não cabe simplesmente somar as taxas antigas de cada motivo.

## NICE-TO-HAVE

**Leitores: nenhum dos três exige mudança de schema; há efeitos semânticos.**

- **`bridge_universe.radar_score`:** a implementação faz `UNION ALL` de histórico e oportunidades e escolhe o maior timestamp `<= at`; não é fallback estrito, nem filtra somente episódios abertos ([bridge_universe.py:311](C:/dev/project-hunter/services/execution-worker/hunter_execution_worker/bridge_universe.py:311)). Com histórico esparso, a ordenação pode usar score mais antigo. Exemplo: A tem 80 às 12:00, cai para 45 às 12:03 sem mudar status/estágio; B tem 60. Para corte 12:04, se `opportunities` já foi atualizado depois desse corte, a ponte pode priorizar A pelo 80. **Não introduz look-ahead; perde resolução temporal.** A ausência de limite de idade já existe e os 300 s não garantem frescor quando faltam avaliações.

- **`radar._change_expr`:** continua significando “score atual menos última amostra persistida” ([radar.py:95](C:/dev/project-hunter/apps/api/hunter_api/repositories/radar.py:95)). A diferença pode acumular mais e zera quando a nova amostra é gravada. **Não vira variação de cinco minutos**, porque transições antecipam a amostra. Documentaria esse significado.

- **`list_history`:** continua devolvendo as últimas N linhas em ordem cronológica ([opportunities.py:323](C:/dev/project-hunter/apps/api/hunter_api/repositories/opportunities.py:323)). A aproximadamente 12/h, 500 linhas cobrem ~41,6 h; com transições, menos. Com envelope, o teto continua **50**, aproximadamente 4,1 h nesse cenário ([schemas/opportunities.py:38](C:/dev/project-hunter/apps/api/hunter_api/schemas/opportunities.py:38)). São estimativas de cobertura, não janelas garantidas.

Acrescentaria métricas de linhas gravadas por motivo e distribuição de intervalos reais. Elas permitem validar a economia sem atribuir causalidade à mera diferença de score.

## O QUE EU FARIA DIFERENTE

- Manteria v1 congelada e selecionaria v2 explicitamente no scanner. **Trocar apenas `policy.version` não altera os gatilhos atuais**, que são executados incondicionalmente ([history.py:166](C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/history.py:166)).
- Passaria o intervalo pela configuração e por `EvaluationInputs`, validando valor positivo e finito. Preservaria a rejeição de timestamp repetido/regressivo ([history.py:158](C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/history.py:158)).
- Persistiria metadados aditivos de amostragem: versão, intervalo efetivo e motivos. Hoje o escritor acrescenta a marca, mas não serializa o `HistoryVerdict` ([rows.py:67](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/rows.py:67)).
- Exigiria testes de 299/300 s, transições antes do intervalo, alterações removidas sem gravação, restart após avaliação descartada, rollback e recuperação de marcas legadas.

## CONCORDO COM

Política pura e versionada, intervalo operacional configurável com padrão 300 s, v1 preservada e envelope completo em cada linha. O escritor já conserva decomposição e envelope juntos ([rows.py:181](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/rows.py:181)).

## OBSIDIAN

- **Workers** — documentar v2, exceções ao intervalo e recuperação da última amostra persistida.
- **Data Flow** — registrar os efeitos da amostragem na ordenação da ponte e na variação do Radar.
- **Revisoes-Astra/2026-09-27-history-v2** — registrar este parecer, cenários de falha e perdas de resolução aceitas; página proposta, não criada.