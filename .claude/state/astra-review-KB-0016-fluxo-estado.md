**RESUMO**

**A síntese é defensável como hipótese motivadora, mas não como conclusão conjunta demonstrada. H-KB0016a não é executável pelo envelope atual; H-KB0016b admite apenas um diagnóstico aproximado com snapshots externos ao envelope.**

**1. Os dois resultados se somam?**

Eles são compatíveis, mas medem coisas distintas:

- **2607.09230:** o fluxo acrescenta previsão de **estado de liquidez**, sobretudo no ETH sob estresse. BTC fica inconclusivo. É dependência de estado **dentro do ativo**, sem demonstração de retorno negociável ou custo de execução. O próprio artigo distingue seu alvo daquele do outro preprint. [Fonte, §§2.2 e 5.2–5.3](https://arxiv.org/html/2607.09230v1).
- **2602.00776:** encontra padrões SHAP semelhantes entre ativos, com resultados econômicos diferentes por estratégia de execução. Isso não demonstra que menor liquidez causa maior informação incremental do fluxo. [Fonte, §§1 e 7](https://arxiv.org/html/2602.00776v1).

Minha redação seria: **“Os estudos motivam investigar se o valor preditivo e os custos variam com o estado de liquidez; não estabelecem uma relação monotônica entre volume, informação e rentabilidade.”**

**2. Top-50 é, por construção, onde há menos sinal?**

**É extrapolação.** Selecionar por volume restringe a população; não determina onde o sinal será menor. Você está atravessando quatro relações ainda não demonstradas: volume→liquidez, liquidez→informação, informação→expectancy e segundos→duas horas.

O segundo preprint seleciona ativos por posições de **capitalização** no início da amostra, não testa a fronteira top-50 por volume. [Fonte, §3](https://arxiv.org/html/2602.00776v1).

Também não trataria “top-50” como descrição universal do Lab: o tamanho é configurável, com padrão **200**, e a seleção admite allowlist/blocklist ([settings.py:128](C:/dev/project-hunter/packages/core/hunter_core/settings.py:128), [universe_repo.py:195](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe_repo.py:195)). A memória registra uma execução da VPS com 200 mercados; isso exige identificar ambiente e período da coorte, sem presumir que o override local define todos os sinais.

**3. H-KB0016a: composição e ranking estão no envelope?**

**Não. A afirmação da nota está incorreta.**

| Evidência | O que efetivamente existe |
|---|---|
| [envelope.py:110](C:/dev/project-hunter/packages/core/hunter_core/strategies/envelope.py:110) | `SupportingFeatures` contém features, ATR, custos e `eligible`/`eligibility_reason`; não contém composição, ranking ou volume 24h. |
| [repo.py:53](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/repo.py:53) | A consulta do mercado nem lê `monitor_rank` ou `volume_24h_usd`. |
| [record.py:138](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/record.py:138) | O worker acrescenta `decision_at`, coorte e proveniência, incluindo `eligibility_observed_at`; não acrescenta o universo. |
| [persist.py:63](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/persist.py:63) | Esse objeto é persistido em `supporting_features`. |

**Elegibilidade observada não equivale a posição no ranking.** O ranking atual é sobrescrito nos refreshes ([universe.py:155](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe.py:155)). O evento de mudança contém entradas, saídas e total, sem ranking; uma troca de posições mantendo os mesmos membros nem dispara esse evento ([durable.py:281](C:/dev/project-hunter/services/market-worker/hunter_market_worker/durable.py:281), [universe.py:171](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe.py:171)).

Há `quote_volume_24h` nos snapshots, mas reconstruir uma ordenação entre mercados com dados disponíveis seria **outro diagnóstico**, condicionado à cobertura — não recuperação garantida do ranking utilizado pelo coletor ([market_data.py:64](C:/dev/project-hunter/packages/core/hunter_core/db/models/market_data.py:64)).

**4. H-KB0016b: dá para medir spread?**

**Não no instante exato pelo envelope.** A lista de evidências da estratégia não inclui book, bid/ask ou spread ([volume_anomaly_v1.py:198](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:198)).

Entretanto, `market_snapshots` recebe bid, ask e spread a partir do ticker ([sampling.py:184](C:/dev/project-hunter/services/market-worker/hunter_market_worker/sampling.py:184)). Portanto, ausência de book no envelope **não implica ausência total de histórico de spread**.

As limitações são decisivas:

- O sampler arredonda a observação para o minuto; o modelo não preserva seu horário exato nem o timestamp original da cotação ([sampling.py:189](C:/dev/project-hunter/services/market-worker/hunter_market_worker/sampling.py:189), [market_data.py:64](C:/dev/project-hunter/packages/core/hunter_core/db/models/market_data.py:64)).
- Nesse caminho, `spread_pct` é **fração**: `spread_bps = spread_pct × 10.000`; 2 bps correspondem a `0,0002` ([sampling.py:72](C:/dev/project-hunter/services/market-worker/hunter_market_worker/sampling.py:72)).
- Os 2 bps são spread **total**; o preço sintético aplica metade mais 5 bps de slippage por lado ([pricing.py:35](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:35)).
- A entrada planejada ocorre na abertura seguinte à decisão. Spread na decisão não mede automaticamente spread na entrada ou na saída ([plan.py:94](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/plan.py:94)).

**ARQUIVOS**

Nenhum arquivo criado ou modificado por mim.

**TESTES**

Revisão estática e consulta aos dois preprints. Não executei testes nem SQL; **a cobertura real dos snapshots e das coortes não foi medida**.

**MUST-FIX**

1. **Retirar “ranking/composição gravados no envelope” e “executável sobre a coorte já coletada”.** Cenário: mercado era rank 40 na decisão e vira rank 10 depois; um join com `markets` atual atribui seu resultado ao terço errado.

2. **Retirar “confirma os artigos” e “expectancy plana refuta”.** Cenário: um dia com poucos resultados produz médias próximas e intervalos amplos; a nota declara ausência de efeito. Ou um único ativo domina um terço e sua rentabilidade é atribuída à liquidez.

3. **Não usar snapshot do mesmo minuto como informação comprovadamente anterior.** Cenário: decisão às 12:00:05 e snapshot coletado às 12:00:40, gravado com `ts=12:00:00`; `ts <= decision_at` aceita futuro. Para uma aproximação retrospectiva, usar bucket inteiramente anterior, idade máxima declarada e cobertura explícita.

4. **Não concluir custo total otimista apenas porque spread mediano excede 2 bps.** Cenário hipotético: spread real de 4 bps e slippage zero custam 2 bps por lado contra os 6 assumidos. O componente spread está subestimado, mas o total não necessariamente. Spread tampouco valida os 5 bps de slippage.

5. **Corrigir a leitura numérica do segundo preprint.** A tabela apresenta ARC 4,06/5,78/7,00 sem `%`; pela equação definida como fração, seriam 406%/578%/700%, não os percentuais transcritos. Maker BTC tem ARC positivo; ausência de significância não significa resultado negativo ou irrelevante. A discussão dos p-valores também alterna comparação com buy-and-hold e média zero. Cortaria esses números da síntese até explicitar unidades e hipótese testada. **Falha:** calibrar expectativas com escala errada e interpretar um teste de benchmark como prova de lucro absoluto. [Fonte, §4.1 e tabelas 1–4](https://arxiv.org/html/2602.00776v1).

**NICE-TO-HAVE**

Reportar cobertura, mercados e dias por faixa, concentração por ativo e intervalos que respeitem dependência temporal. Para spread, acrescentar caudas e proporção acima de 2 bps; a mediana sozinha esconde episódios caros.

**O QUE EU FARIA DIFERENTE**

Cortaria H-KB0016a **como entrega retrospectiva garantida**. Para coleta futura, registraria ranking, tamanho/regra do universo e timestamp do refresh; composição completa pode ser referenciada por snapshot imutável.

Reduziria H-KB0016b a **auditoria de cobertura e distribuição do spread anterior à decisão**, inicialmente sem terços. Qualquer análise de custos seria sensibilidade declarada, sem apresentá-la como execução observada.

**CONCORDO COM**

Manter a nota diagnóstica, reconhecer a incompatibilidade de horizontes e não propor automaticamente uma variante. A pergunta sobre dependência de estado merece investigação; a ponte empírica ainda precisa ser construída.

**OBSIDIAN**

- **Quando o fluxo importa: dependência de estado** — corrigir síntese, unidades, disponibilidade dos dados e critérios de confirmação/refutação.
- **EXP-0002-volume-anomaly-v1** — acrescentar errata datada sobre composição/ranking e delimitar o universo por ambiente/período, preservando o protocolo original.
- **Market Collector** — distinguir ranking atual, histórico de mudanças de membros e snapshots por minuto.
- **Strategy Backlog** — marcar H-KB0016a como dependente de proveniência histórica; limitar H-KB0016b à auditoria de cobertura.