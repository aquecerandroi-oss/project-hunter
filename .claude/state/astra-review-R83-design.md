## RESUMO

**O desenho é defensável, mas eu corrigiria três pontos antes de abrir os desfechos:** a interpretação da guarda temporal, o p-valor usado no Holm e a integração entre o veredito do moinho e a regra específica de H-023.

Concordo com tercis por estratégia, contraste alto−baixo, patamar externo e a errata da refutação. A reconstrução reproduz **a fórmula**, mas não toda a disponibilidade operacional da produção.

Revisão como `quant-engineer`, em modo OPINIÃO. Não consultei desfechos de R83.

## ARQUIVOS

Nenhum arquivo criado ou modificado; nenhum commit.

## TESTES

Não executei testes nesta revisão. Li os testes sintéticos e os registros existentes; portanto, não apresento “12 passaram” como verificação minha.

O registro de validação informa igualdade em **337/337** snapshots com a mesma vela final. Isso sustenta paridade nesse subconjunto, não equivalência operacional completa. [validate.txt:3](C:/dev/project-hunter/.claude/state/r83/validate.txt:3)

## MUST-FIX

**1. `max(received_at)` não pode ser apresentado como prova de recebimento das velas antes do sinal.**

O estudo usa esse máximo como `computed_at`. Porém, o modelo define `received_at` com `server_default=func.now()`, e a persistência não copia o recebimento do candle normalizado. É um carimbo do banco, não a observação original pelo coletor. [h023.py:149](C:/dev/project-hunter/.claude/state/r83/h023.py:149), [market_data.py:61](C:/dev/project-hunter/packages/core/hunter_core/db/models/market_data.py:61), [persist_rows.py:111](C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist_rows.py:111)

**Cenário de falha:** uma vela já estava no Redis antes da emissão, mas foi persistida depois; o estudo censura uma decisão operacionalmente observável. No sentido inverso, o timestamp da transação não prova que o scanner já tivesse acesso à linha antes da emissão.

**Correção de desenho:** manter essa guarda como **proxy de persistência**, explicitando a limitação. Separar “reconstrução histórica sem velas futuras” de “feature comprovadamente disponível na produção”. No replay, `computed_at=obs` é uma declaração da simulação, não evidência de disponibilidade histórica.

**2. A permutação individual não sustenta o controle familiar reivindicado pelo Holm.**

O moinho embaralha rótulos **linha a linha**, mesmo com estrato. Já o próprio desenho reconhece versões de momentum decidindo a mesma barra. O bootstrap por mercado preserva essa dependência no IC; não a preserva no p-valor. [resampling.py:164](C:/dev/project-hunter/infra/research/resampling.py:164), [notes-R83.md:116](C:/dev/project-hunter/.claude/state/notes-R83.md:116)

**Cenário de falha:** dez versões repetem um episódio de mercado. A permutação trata essas dez linhas como separáveis e pode produzir p muito menor sem dez novas observações independentes. Holm ajusta esse p, mas não recupera sua validade. O moinho já documenta essa limitação. [verdict.py:158](C:/dev/project-hunter/infra/research/verdict.py:158)

**Correção de desenho:** congelar uma inferência que preserve a dependência dos episódios/mercados e justificar a unidade permutável; ou deixar esse p e seu Holm explicitamente exploratórios, sem alegar controle familiar confirmatório. Apenas acrescentar `mercado` ao estrato ainda permite separar linhas dependentes dentro dele.

**3. O veredito final precisa de uma regra externa completa, preservando as guardas do moinho.**

H-023 refuta por tamanho quando `IC_sup < +0,01`; o moinho refuta quando `IC_sup < minimum_effect`, que aqui seria `+0,05`. Além disso, declarar `block` no moinho faz o IC temporal participar da confirmação, embora R83 o descreva como descritivo. [notes-R83.md:95](C:/dev/project-hunter/.claude/state/notes-R83.md:95), [notes-R83.md:105](C:/dev/project-hunter/.claude/state/notes-R83.md:105), [verdict.py:105](C:/dev/project-hunter/infra/research/verdict.py:105), [verdict.py:127](C:/dev/project-hunter/infra/research/verdict.py:127)

**Cenário de falha:** com IC hipotético `[+0,015; +0,040]`, o moinho retorna REFUTA, enquanto H-023 determina NÃO CONFIRMA. Se o relatório simplesmente publicar `report.verdict`, muda a regra congelada.

**Correção de desenho:** distinguir saída mecânica e rótulo H-023; calcular externamente patamar, Holm e limiar de refutação, mantendo antes deles as guardas de tamanho por braço, clusters, IC finito e réplicas inválidas. Essas guardas existem no moinho, mas não aparecem na ordem resumida de R83. [verdict.py:40](C:/dev/project-hunter/infra/research/verdict.py:40)

## NICE-TO-HAVE

- **Congelar a população que define os cortes.** O passo cego calcula tercis após exigir `has_r`. Isso define proximidade relativa entre casos com R disponível. Para comparar `R_net` com `r_ex_funding`, recomputar cortes também mudaria os braços. Eu publicaria uma sensibilidade com os mesmos cortes e separaria mudança de desfecho de mudança de população. [blind.py:109](C:/dev/project-hunter/.claude/state/r83/blind.py:109)
- **Contar partições distintas no patamar.** Sete valores diferentes de q podem produzir menos de sete partições por causa dos empates. `plateau_or_spike` também remove pontos não avaliáveis antes de contar consecutividade. Não deixaria quatro cópias do mesmo contraste, ou uma sequência atravessando um corte inválido, valerem como patamar. [h023.py:186](C:/dev/project-hunter/.claude/state/r83/h023.py:186), [stats.py:242](C:/dev/project-hunter/infra/research/stats.py:242)
- Publicar composição por estratégia/versão em cada braço: tercis por estratégia reduzem mistura, mas empates e tamanhos pequenos impedem balanceamento exato. [h023.py:222](C:/dev/project-hunter/.claude/state/r83/h023.py:222)

## O QUE EU FARIA DIFERENTE

Manteria o contraste principal congelado e acrescentaria uma emenda pré-desfecho com: significado exato dos timestamps; unidade da inferência; população dos cortes; e regra final H-023 independente do rótulo genérico do moinho.

Não exigiria equivalência com o scanner para estudar uma feature reconstruída. Exigiria que a conclusão fosse sobre **essa reconstrução retrospectiva**, deixando aplicação operacional para validação posterior.

## CONCORDO COM

**(1) Janela e causalidade.** Sim: com `obs` alinhado ao minuto, candles 1m finais e únicos, `[obs−1440min, obs)` contém precisamente as 1.440 velas que fecham até `obs`. A fórmula coincide com produção. A chave do banco garante unicidade por mercado/timeframe/abertura. [q_feat.sql:35](C:/dev/project-hunter/.claude/state/r83/q_feat.sql:35), [price.py:117](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/price.py:117), [market_data.py:46](C:/dev/project-hunter/packages/core/hunter_core/db/models/market_data.py:46)

**Não é disponibilidade equivalente.** Sem a última vela, a produção pode calcular sobre 1.440 anteriores contíguas; R83 censura. Inversamente, o banco reconstruído pode ter uma janela completa que o contexto do scanner não tinha. `tail_minutes` ancora na última vela disponível, enquanto `window_ok` exige término exato em `obs`. [windows.py:139](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/windows.py:139), [h023.py:82](C:/dev/project-hunter/.claude/state/r83/h023.py:82)

Essas diferenças **podem** selecionar períodos de melhor cobertura ou menor atraso. Não há evidência, nesta revisão cega, de qual seria a direção do viés.

**(2) Famílias.** Concordo com as quatro integrantes da continuação como definição operacional de “compra força/rompimento”. Os contratos descrevem momentum, expansão de volume, rompimento após contração e rompimento da faixa de abertura. [momentum_v1.py:1](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:1), [volume_anomaly_v1.py:1](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:1), [breakout_v1.py:1](C:/dev/project-hunter/packages/core/hunter_core/strategies/breakout_v1.py:1), [session_orb_v1.py:1](C:/dev/project-hunter/packages/core/hunter_core/strategies/session_orb_v1.py:1)

Aceito as restantes fora da primária, mas corrigiria a justificativa: **bounce em suporte ascendente também é continuação**, explicitamente no contrato; sweep/reclaim compra uma falha de rompimento de suporte. “Outras” é uma exclusão operacional legítima, não uma classificação universal de “nem continuação nem reversão”. [trendline_breakout_v1.py:9](C:/dev/project-hunter/packages/core/hunter_core/strategies/trendline_breakout_v1.py:9), [sweep_reclaim_v1.py:5](C:/dev/project-hunter/packages/core/hunter_core/strategies/sweep_reclaim_v1.py:5)

**(3) Tercis por estratégia.** Concordo. Respondem “estar relativamente perto da máxima dentro desta estratégia”, evitando transformar a primária em comparação de distribuições entre estratégias. Não equivalem a um limite absoluto único de distância. Manter cortes agregados e por versão como sensibilidades é adequado. [notes-R83.md:88](C:/dev/project-hunter/.claude/state/notes-R83.md:88)

**(4) Moinho, patamar e inferência.** O indicador alto=1/baixo=0, excluindo o meio, reproduz corretamente alto−baixo. A grade externa de q é coerente; não deve escolher o melhor q. Holm sobre as duas variáveis é apropriado **se os p-valores forem válidos**, com reversão e sensibilidades estritamente descritivas. Estratégia×dia controla composição desses estratos, mas não resolve dependência entre linhas; cluster mercado também não resolve sozinho choques compartilhados entre mercados. [protocol.py:150](C:/dev/project-hunter/infra/research/protocol.py:150), [notes-R83.md:98](C:/dev/project-hunter/.claude/state/notes-R83.md:98)

**(5) Errata.** Legítima, registrada antes dos desfechos e preservando a leitura literal. IC inferior negativo não demonstra efeito oposto: `[-0,02; +0,20]` admite vantagem relevante. Para sustentar efeito abaixo de −0,01, é o **limite superior** que precisa ficar abaixo disso. O princípio está explicitado no R76. [notes-R83.md:109](C:/dev/project-hunter/.claude/state/notes-R83.md:109), [notes-R76.md:122](C:/dev/project-hunter/.claude/state/notes-R76.md:122)

**(6) Deduplicação.** Concordo com versão×mercado×obs e preferência prospectiva, escolhidas sem R. Fazer a deduplicação antes da guarda evita substituir uma prospectiva recusada por replay com observabilidade apenas declarada. Isso preserva versões diferentes como observações distintas; a dependência continua sendo responsabilidade da inferência. A escolha lexicográfica de coorte/ID é determinística, não prova prioridade cronológica. [h023.py:163](C:/dev/project-hunter/.claude/state/r83/h023.py:163)

## OBSIDIAN

- **Fila de Hipoteses — H-023:** acrescentar ligação à emenda pré-desfecho, preservando o texto congelado.
- **Features:** distinguir paridade de fórmula, ancoragem temporal e disponibilidade efetiva no scanner.
- **Revisoes-Astra — R83/H-023:** registrar os três must-fix, os cenários e a concordância com a errata.
- **Dicionario de Variaveis:** documentar `distance_from_24h_high/_low` reconstruídas e a limitação do carimbo de persistência.

Nenhuma página foi alterada.