**RESUMO**

As quatro notas são recuperáveis, mas eu corrigiria os pontos abaixo antes de publicar. A inferência que derrubo por completo é: **“R médio no alvo acima de 1 demonstra gap favorável atravessando o alvo.” O simulador não credita esse movimento.**

**ARQUIVOS**

Nenhum arquivo criado ou modificado por mim. Revisão do código local; não confirmei o código implantado nem repeti as consultas na VPS.

**TESTES**

Não executei suítes em modo OPINIÃO. Conferi código, referências e aritmética das tabelas. Resultado da conferência:

```text
sinais_tabela          : 978
monitorados_declarados : 982
estados_resto          : 813
sinais_resto           : 814
barras_volume_minutos  : 1445
barras_atr_minutos     : 1455
```

**MUST-FIX**

1. **KB-0062 — a cegueira das estratégias existe, mas o aquecimento descrito está errado.**

   `momentum_v1` exige **97 barras de 15 minutos**, tanto pela janela de volume — 96 anteriores mais a atual — quanto pelo ATR. Isso corresponde a **24h15 de buckets completos**. [momentum_v1.py:144](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:144)

   `volume_anomaly_v1` exige **289 barras de 5 minutos**, não 288: a atual mais 288 anteriores. Além disso, exige **97 barras de 15 minutos para ATR**, terminando na última fronteira completa. Portanto, também não começa após apenas 24h. O alinhamento UTC e as lacunas podem aumentar a espera. [volume_anomaly_v1.py:122](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:122)

   Concordo que backfill não fabrica história anterior à listagem. A constante 1499 define a diferença entre timestamps inicial e final; como os extremos são inclusivos, pode representar **1500 candles de um minuto**. [recovery.py:63](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:63), [recovery.py:238](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:238)

   **Cenário de falha:** planejar a primeira avaliação de volume em T+24h e interpretar a indisponibilidade como defeito. Reformular para “as duas estratégias atuais não emitem no primeiro dia”; isso não impede observar preço, volume ou funding nesse período.

2. **KB-0062 — “uma linha na normalização” não persiste a listagem.**

   Não encontrei outra fonte **alimentada pelo fluxo atual** que identifique a data real de listagem. `first_seen_at` tem default do relógio do banco; candles e gaps delimitam cobertura observada, não nascimento do contrato. [markets.py:80](C:/dev/project-hunter/packages/core/hunter_core/db/models/markets.py:80)

   Há dois pontos no caminho: a normalização guarda somente `contractType` nos metadados, e o upsert **não transfere metadata**, nem na inserção nem na atualização. [normalize.py:137](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/normalize.py:137), [universe_repo.py:64](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe_repo.py:64)

   `onboardDate` está confirmado na [documentação oficial da Binance](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Exchange-Information) e aparece na fixture local, [exchange_info.json:94](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/testing/fixtures/exchange_info.json:94). Não consultei uma resposta ao vivo.

   **Cenário de falha:** acrescentar o campo ao normalizador, acreditar que a idade passou a ser registrada e continuar com `{}` no banco. A correção precisa atravessar normalização **e persistência**.

3. **KB-0062 — 30 minutos não é a política comprovada; “não existe em lugar nenhum” está errado.**

   O mecanismo encontrado é `prune_dispatched(session, older_than, batch)`: apaga somente linhas despachadas antes do corte fornecido, em lotes padrão de 5.000; pendentes nunca qualificam. **A função não fixa prazo.** [outbox_store.py:287](C:/dev/project-hunter/packages/core/hunter_core/events/outbox_store.py:287)

   A política documentada é **sete dias após `dispatched_at`**, com job diário atribuído ao analytics-worker no M5. Não encontrei chamada operacional que implemente 30 minutos no código pesquisado. [DATABASE.md:70](C:/dev/project-hunter/docs/DATABASE.md:70)

   Além disso, o diff é persistido na outbox e publicado no Redis; o stream `market.universe.changed` tem retenção aproximada por **1.000 entradas**, não por 30 minutos. [durable.py:288](C:/dev/project-hunter/services/market-worker/hunter_market_worker/durable.py:288), [streams.py:47](C:/dev/project-hunter/packages/core/hunter_core/events/streams.py:47), [produce.py:25](C:/dev/project-hunter/packages/core/hunter_core/events/produce.py:25)

   **Cenário de falha:** declarar o passado irrecuperável e deixar de recuperar eventos ainda presentes no Redis. A medição prova apenas a extensão temporal das linhas encontradas naquele instante. O mecanismo da VPS permanece sem identificação; não vou inventá-lo.

4. **KB-0064 — o pior caso está fora das memes; a conclusão sobre a cauda não está demonstrada.**

   Sobrevive: **“o maior drawdown observado entre os mercados incluídos pertence a E_resto.”** Não sobrevive: “a cauda ruim não está nas memes”. Comparar extremos de 19 contra 133 mercados dá muito mais oportunidades ao segundo grupo de produzir um extremo. Medianas não resolvem essa comparação de caudas.

   Também não há suporte para “as memes concentram os dois extremos”: a amplitude mediana de A é **11,51%**, contra **12,10%** de E; amplitude não determina a ordem subida→queda.

   **Cenário de falha:** transformar essa abertura em justificativa para limites menos conservadores para memes.

   A ressalva temporal tem a direção correta **para a magnitude da perda**, mas precisa de precisão: ao estender uma trajetória preservando as observações anteriores, o drawdown máximo pode **piorar ou permanecer igual**. Com a convenção negativa usada, o valor fica mais negativo, não “viciado para baixo” em magnitude. Janelas móveis diferentes não obedecem necessariamente à monotonicidade. Mesma janela nominal também não garante mesma cobertura, especialmente com o filtro de 150 barras.

5. **KB-0064 — queda de 15 minutos não prova gap; saída abaixo do stop não mede somente gap.**

   Uma queda de 10% pode ocorrer continuamente, negociando através do stop. Não prova salto sem negócios, nem atravessa “qualquer stop de 1,5 ATR”: a distância depende do ATR naquele instante.

   No simulador, stop intrabar sai na barreira; abertura abaixo dela sai na abertura. Depois, o preço recebe custos adversos. Portanto, `stop − exit_price` mistura **gap e custo assumido**, inclusive quando não houve gap. [walker.py:71](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:71), [walker.py:155](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:155), [pricing.py:53](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:53)

   **Cenário de falha:** medir déficit de saída em stops sem gap e usá-lo como estimativa empírica de gap para dimensionamento.

   No diagnóstico, separar `exit_at_open`, `exit_base`, barreira e custos. Chamar o resultado de **gap observado na resolução do modelo**, não custo de execução real.

6. **KB-0065 — separar estratégias antes de publicar comparações de outcome.**

   É recuperável: o sinal conserva `strategy_version_id`, e o outcome referencia o sinal. [agents.py:108](C:/dev/project-hunter/packages/core/hunter_core/db/models/agents.py:108), [agents.py:153](C:/dev/project-hunter/packages/core/hunter_core/db/models/agents.py:153)

   Mas a limitação declarada não resolve a interpretação: além de horizontes diferentes, **o stop de volume é a mínima da barra**, enquanto momentum usa 1,5 ATR. [volume_anomaly_v1.py:183](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:183), [momentum_v1.py:217](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:217)

   **Cenário de falha:** memes terem mais sinais da estratégia com maior payoff nominal, produzindo diferença agregada sem vantagem dentro de nenhuma estratégia.

   Refazer por estratégia/versão, incluindo mercados desmonitorados. Reconciliar **978 versus 982** e **813 versus 814**. Publicar `count(r_multiple)` junto à média: funding não apurável pode produzir `NULL`, então o número de outcomes não é necessariamente o denominador de `r_medio`. [settle.py:83](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/settle.py:83)

7. **KB-0065 — retiro a explicação por gap favorável e o confundidor “quase determinante” de ATR.**

   **Gap favorável:** mesmo quando a abertura supera o alvo, o simulador credita somente `target1`; intrabar também sai no alvo. [walker.py:73](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:73), [walker.py:157](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:157)

   `R > 1` pode vir de entrada abaixo da referência, geometria de volume ou funding. A própria fórmula divide pelo risco da **entrada efetiva**, não pelo ATR nominal. [pricing.py:74](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:74)

   **ATR:** o efeito contrário que falta é a normalização. Se movimentos e barreiras aumentarem proporcionalmente à volatilidade, o processo em unidades de ATR pode preservar aproximadamente os tempos e probabilidades de toque. Barreiras maiores em preço não implicam maior distância em tempo.

   Há ainda um efeito mecânico favorável ao risco percentual maior: **custos fixos em bps pesam menos em R**, mantendo o restante comparável. Isso pode aproximar o stop líquido de −1 e melhorar o alvo líquido sem qualquer vantagem comportamental.

   **Cenário de falha:** atribuir diferenças a momentum, gaps ou “efeito meme” quando geometria e custos normalizados bastam para explicá-las.

   Também retiraria “sumiu ao parear por ATR, logo meme não acrescenta informação nenhuma”: ausência de diferença detectada numa amostra pequena não demonstra redundância.

8. **KB-0063 — o requisito temporal proposto ainda permite look-ahead.**

   Guardar `occurred_at` é necessário, mas não suficiente. É preciso saber quando o evento **e sua classificação ficaram disponíveis** à estratégia. O schema já distingue `occurred_at` de `ingested_at`. [intelligence.py:48](C:/dev/project-hunter/packages/core/hunter_core/db/models/intelligence.py:48)

   **Cenário de falha:** notícia publicada às 10h, ingerida às 10h07 e classificada às 10h08 entrar retrospectivamente numa decisão das 10h01. Preservar horário do evento, ingestão e disponibilidade da classificação; não retroagir informação enriquecida.

**NICE-TO-HAVE**

- **KB-0063:** o inventário funcional está correto. Trocar “zero consumidores” por **“zero consumidores funcionais”**, pois health e frontend leem as flags. Elas têm default `False`, e não encontrei pipeline de leitura/escrita de `intelligence_events`. [settings.py:119](C:/dev/project-hunter/packages/core/hunter_core/settings.py:119), [health.py:85](C:/dev/project-hunter/apps/api/hunter_api/health.py:85), [feature-flags-table.tsx:27](C:/dev/project-hunter/apps/web/components/system/feature-flags-table.tsx:27)
- **KB-0065:** o título sugere maioria meme, mas A+B somam apenas **92 dos 978 sinais apresentados**. “Majoritariamente altcoins” é sustentado; “majoritariamente memes” não.
- **KB-0064/0065:** anexar SQL completo, corte temporal e classificação utilizados. A KB-0064 apresenta um fragmento; a KB-0065 não apresenta SQL apesar do frontmatter “SQL colado”.
- Os números e dimensões citados nos resumos conferem com [Mancino](https://arxiv.org/abs/2512.11850) e [Xiang et al.](https://arxiv.org/abs/2512.00377). Isso não valida transporte para perpétuos nem a expressão “resultados mais fortes da literatura”.

**O QUE EU FARIA DIFERENTE**

Publicaria primeiro um retrato reconciliado por **estratégia/versão × coorte**, com cobertura, custos em R, geometria efetiva e todos os estados. Para frequência de sinais, usaria avaliações elegíveis ou tempo elegível como denominador: dividir pelo número atual de mercados mistura tempos diferentes de exposição.

Na cauda, começaria por frequências de perdas acima de limiares comuns, com cobertura comparável. Deixaria mínimos como observações individuais.

**CONCORDO COM**

- Backfill não supera ausência de história anterior à listagem.
- `first_seen_at` não representa idade do contrato.
- Outbox e Redis não substituem um histórico durável de composição.
- Comparação de coortes não responde, sozinha, “momentum ou reversão”.
- Não há base aqui para ativar variante, alterar risco ou declarar vantagem.

**OBSIDIAN**

- **O primeiro dia que não conseguimos ver:** corrigir aquecimento, persistência de metadata e distinção entre retenção documentada e observação da VPS.
- **Social e on-chain — a linha que não atravessamos:** acrescentar disponibilidade temporal da informação e da classificação.
- **A cauda de queda — e o que o Risk Engine vai precisar:** restringir conclusão sobre cauda e separar queda, gap e custos simulados.
- **A população do Lab já é meme:** reconciliar contagens, separar estratégias e retirar explicações por gap favorável e determinismo do ATR.
- **Market Collector:** registrar a lacuna de proveniência da listagem e as fontes existentes do diff.
- **Risk Engine:** manter os requisitos como propostas; distinguir evidência de preço de evidência de execução.