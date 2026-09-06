## RESUMO

**Eu manteria a estrutura proposta, mas não congelaria os contratos ainda.** Recomendo: corte por fechamento e disponibilidade; proveniência por entrada; extremos de 24 h calculados de candles finais; qualidade versionada por feature; ATR com checkpoint persistido; `_live` reservado à dependência de candle em formação.

Parecer como `quant-engineer`, em modo OPINIÃO. As recomendações abaixo não constituem nova decisão conjunta.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Nenhum commit.

## TESTES

Não executei testes: esta revisão é documental e de contratos. Os cenários abaixo são casos de aceite propostos, não resultados verificados.

## MUST-FIX

### 1 — `MarketContext`

**1a — Sim: `close_time <= as_of`, nunca apenas `open_time`.** O construtor existente já verifica duração de um minuto, identidade do mercado, ordenação estrita, finalidade e fechamento até o corte; o builder filtra por fechamento ([base.py:135](C:/dev/project-hunter/packages/core/hunter_core/strategies/base.py:135), [base.py:188](C:/dev/project-hunter/packages/core/hunter_core/strategies/base.py:188)).

**Cenário de falha:** às 12:00:30, admitir uma vela final de 12:00–12:01 pela abertura revela os 30 segundos seguintes.

Há uma segunda condição: **fechamento não comprova disponibilidade histórica**. Para `forming`, exigir `open_time <= as_of < close_time` e timestamp da atualização `<= as_of`. O modelo já possui `event_ts`; o hot state também grava `ts` quando recebe esse timestamp ([market.py:252](C:/dev/project-hunter/packages/core/hunter_core/domain/market.py:252), [hot_state_candles.py:83](C:/dev/project-hunter/services/market-worker/hunter_market_worker/hot_state_candles.py:83)).

**Cenário de falha:** ao reconstruir 12:00:20, usar a atualização de 12:00:50 do candle em formação vaza informação futura, embora sua abertura seja válida.

Para candles finais históricos, distinguir explicitamente **bootstrap sobre histórico disponível agora** de **reprodução do que estava disponível na decisão original**. O segundo depende do envelope preservado, conforme [M2.md:54](C:/dev/project-hunter/docs/plans/M2.md:54). Não fabricar `received_at=agora` durante decodificação pura.

**1b — Prefiro snapshot reduzido e imutável de BTC**, com identidade, mesmo `as_of`, candles necessários e proveniência. `MarketContext` aninhado também funciona se impedir ciclos e exigir `btc.btc=None`; não considero a escolha estrutural um must-fix.

O obrigatório é alinhar **as observações usadas**, além do corte: correlação não pode juntar barras por posição quando existem gaps.

**Cenário de falha:** contexto do ativo cortado em 12:00 e BTC atualizado em 12:01 introduzem futuro; dois contextos cortados em 12:00, mas com minutos faltantes diferentes, produzem correlação entre horários distintos. BTC integra o contrato de features cross em [PIPELINE.md:72](C:/dev/project-hunter/docs/PIPELINE.md:72).

**1c — Faltam históricos, cobertura e qualidade da coleta.** Eu acrescentaria entradas explícitas para:

- **Derivativos por campo:** funding, mark e OI com timestamps próprios; histórico ou referências anteriores para `oi_change_1h` e `funding_change_8h`, preservando `funding_kind`.
- **Liquidações:** janela de eventos e cobertura/saúde da rota.
- **Trades:** intervalo coberto, truncamento e saúde da coleta, além dos eventos.
- **Gaps e universo:** qualidade da coleta, gaps relevantes, motivo de elegibilidade e referência à composição temporal do universo. O breadth completo pertence ao contexto de regime.

O hash de derivativos separa `funding_ts`, `mark_ts` e `oi_ts`; um `SourceEntry[DerivSnapshot]` com apenas um timestamp perde essa informação ([hot_state.py:61](C:/dev/project-hunter/services/market-worker/hunter_market_worker/hot_state.py:61)). Um snapshot atual também não contém a referência de uma hora atrás exigida pelo estágio ([M2.md:52](C:/dev/project-hunter/docs/plans/M2.md:52)).

**Cenário de falha:** mark novo faz OI de vinte minutos atrás parecer fresco; comparar OI atual com a primeira leitura após restart produz “variação de 1 h” usando poucos segundos.

Trades são limitados a 2.000 entradas ([hot_state.py:290](C:/dev/project-hunter/services/market-worker/hunter_market_worker/hot_state.py:290)).

**Cenário de falha:** esses 2.000 registros cobrem apenas vinte segundos, mas a calculadora divide por cinco minutos e publica pressão/velocidade como janela completa. Liquidações vazias com rota desconhecida também não provam pressão zero. Ausência de eventos só pode produzir zero quando a cobertura correspondente estiver comprovada.

**Fonte canônica dos extremos de 24 h:** recomendo **1.440 candles finais contíguos**, terminando no último fechamento de minuto esperado até `as_of`; preço de referência = último fechamento. Sem janela completa, `unavailable`. Sem fallback silencioso para ticker.

Há um motivo concreto: o parser de `bookTicker` não fornece `high_24h/low_24h`, e a escrita remove campos próprios ausentes ([streams.py:168](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/streams.py:168), [hot_state.py:117](C:/dev/project-hunter/services/market-worker/hunter_market_worker/hot_state.py:117)).

**Cenário de falha:** alternar ticker e candles sob a mesma chave muda extremos, janela e participação intraminuto sem mudar a versão. Se houver variante de ticker, ela precisa de identidade e semântica próprias; `ts <= as_of` sozinho não torna as duas fontes equivalentes.

### 2 — `FeatureVector` e `quality`

**2a — Não acoplar qualidade ao TTL.** Os valores 10/30/600 s podem ser parâmetros iniciais, mas TTL define retenção do cache; frescor define validade do insumo. Escritas renovam a expiração do hash compartilhado ([hot_state.py:83](C:/dev/project-hunter/services/market-worker/hunter_market_worker/hot_state.py:83)).

Eu manteria **qualidade calculada na feature**, com política versionada, e permitiria que consumidores aplicassem restrições adicionais. Expor apenas idade e transferir toda classificação ao scorer não atende ao brief ([brief-T2.2-feature-engine.md:18](C:/dev/project-hunter/.claude/state/brief-T2.2-feature-engine.md:18)).

A expressão “entrada mais nova” precisa mudar: avaliar cada dependência conforme sua função. Um timestamp recente não pode encobrir outro stale; uma observação histórica usada como referência não deve ser penalizada simplesmente por ser histórica.

**Cenário de falha:** funding novo mascara OI stale; no sentido oposto, uma referência legítima de OI de uma hora atrás torna toda variação de 1 h indisponível.

Para candles, usar **fechamento esperado por timeframe e atraso tolerado**. Não aplicar 120 s indistintamente ao fechamento de 15 min.

**Cenário de falha:** às 12:14, ATR baseado na barra de 15 min encerrada às 12:00 continua sendo o ATR fechado corrente; uma regra genérica de 120 s o degrada durante quase todo o intervalo. O alinhamento por timeframe já está explicitado em [notes-S1.md:47](C:/dev/project-hunter/.claude/state/notes-S1.md:47).

**2b — Concordo com `unavailable` e motivos distintos**, com estes ajustes:

- `warmup`: a janela necessária ainda não existe.
- `gap`: falta dado dentro da janela exigida.
- `missing_input`: fonte/campo necessário ausente.
- `stale_input`: valor calculável, mas vencido; normalmente `degraded`.
- `zero_divisor`: cálculo indefinido.
- `insufficient_sample`: amostra estatística insuficiente.
- Preservar `misaligned` ou tratá-lo como violação explícita do contrato.

O agregador já distingue `misaligned`, `warmup` e `gap` ([aggregate.py:102](C:/dev/project-hunter/packages/core/hunter_core/strategies/aggregate.py:102)).

**Maturidade da baseline deve continuar separada da qualidade da feature.** Feature fresca pode estar `ok` enquanto o detector está indisponível por baseline imatura, conforme [M2.md:50](C:/dev/project-hunter/docs/plans/M2.md:50).

**Cenário de falha:** marcar essa feature como fonte degradada impede acumular justamente as observações válidas necessárias para amadurecer a baseline.

**Falta proveniência por entrada no vetor.** `inputs_used`, um `source_ts` e um `age_s` não bastam. Acrescentaria um mapa compartilhado com timestamp, disponibilidade, qualidade, motivo e cobertura por insumo. Os campos escalares podem permanecer como resumo, com semântica documentada.

**Cenário de falha:** não é possível explicar ou reproduzir por que uma feature composta ficou degradada quando apenas o timestamp mais recente foi preservado. O envelope exige esses dados por entrada ([M2.md:54](C:/dev/project-hunter/docs/plans/M2.md:54)).

**2c — Não usaria o pior valor do vetor inteiro como gate.** Pode existir um resumo para exibição, mas consumidores devem avaliar suas dependências e a qualidade operacional do mercado.

**Cenário de falha:** `funding_change_8h` em warm-up bloqueia retornos e liquidez válidos. A decisão conjunta prevê componentes ausentes sem redistribuir pesos e com redução de confiança ([M2.md:53](C:/dev/project-hunter/docs/plans/M2.md:53)).

### 3 — ATR, `_live` e nomes

**3a — Escolho checkpoint persistido. Não aceitaria reancoragem silenciosa após restart.** Essa escolha corresponde ao brief e ao acordo de origem recuperável sem reseed móvel ([brief-T2.2-feature-engine.md:9](C:/dev/project-hunter/.claude/state/brief-T2.2-feature-engine.md:9), [dialogue-M2.md:186](C:/dev/project-hunter/.claude/state/dialogue-M2.md:186)).

A âncora diária produz outra política. Se o `floor` for na grade de 15 min, ela muda a cada quinze minutos; se for diário, pode exigir quase 48 h de histórico, excedendo o buffer de 1.500 minutos ([hot_state_candles.py:14](C:/dev/project-hunter/services/market-worker/hunter_market_worker/hot_state_candles.py:14)).

**Cenário de falha:** com retorno/ATR perto de 1,5 ou 4, restart ou troca da âncora muda o estágio sem nova informação de mercado.

Eu definiria transição pura **`advance(state_in, closed_bars) -> state_out`**. O scanner possui e persiste o estado. Checkpoint deve preservar origem, seed, contagem, ATR, fechamento anterior, última barra processada e versão numérica, sem perda de precisão.

Regras obrigatórias: duplicata não avança; evento anterior não retrocede; gap interrompe avanço até recuperação; checkpoint perdido exige reconstrução da origem registrada ou indisponibilidade explícita.

**Cenário de falha:** processar a mesma barra duas vezes aplica Wilder duas vezes; pular uma barra elimina seu TR. Ambos alteram o resultado após reentrega/recovery.

Concordo com o gate: barra inicial fornece fechamento anterior, 14 TRs formam a seed e o 15º TR libera a leitura — **16 barras completas quando o fechamento anterior vem de uma barra adicional** ([indicators.py:70](C:/dev/project-hunter/packages/core/hunter_core/strategies/indicators.py:70)). Distinga `origin_bar_open` de `seed_anchor`; na S1, `seed_anchor` identifica a barra que completa a seed ([indicators.py:98](C:/dev/project-hunter/packages/core/hunter_core/strategies/indicators.py:98)).

**3b — Concordo com `_live` somente quando inclui candle em formação.** Book/trades podem manter nomes sem `_live`, com timestamps e cobertura próprios. Isso não significa que sejam reproduzíveis por candles históricos: a garantia continua sendo recomputar amostras gravadas ([M2.md:54](C:/dev/project-hunter/docs/plans/M2.md:54)).

Para ATR `_live`, calcular sobre uma cópia do checkpoint fechado; nunca avançar o estado canônico com parciais.

**Cenário de falha:** dez atualizações intrabar aplicadas ao checkpoint equivalem a dez barras na recursão, contaminando depois o ATR fechado.

**3c — Congelaria `relative_volume_1h` e `relative_volume_15m`**, conforme o acordo prevalente; `volume_relative` fica como nome da família no brief. Incluir `return_4h`, necessário à alternativa EXTENDED, e fechar o mapeamento dos demais nomes antes de T2.3 ([M2.md:52](C:/dev/project-hunter/docs/plans/M2.md:52)).

**Cenário de falha:** T2.2 emite `volume_relative`, T2.3 procura `relative_volume_1h`, e EARLY permanece indisponível com dados válidos.

**Também falta congelar o denominador do volume relativo.** O pipeline especifica mediana de sete dias na mesma hora; o helper S1 usa mediana das barras anteriores ([PIPELINE.md:67](C:/dev/project-hunter/docs/PIPELINE.md:67), [indicators.py:124](C:/dev/project-hunter/packages/core/hunter_core/strategies/indicators.py:124)). Não substituir uma pela outra implicitamente.

**Cenário de falha:** a mesma chave representa razões diferentes no bootstrap e no scanner, tornando o limiar `≥ 3` inconsistente. O contrato precisa receber a referência histórica causal e sua identidade; ela não cabe apenas no contexto de 1.500 minutos.

## NICE-TO-HAVE

- Tornar `available` derivado de um estado validado, evitando combinações contraditórias.
- Usar `Mapping` efetivamente imutável, inclusive nos valores internos.
- Acrescentar metadados de unidade, janela e compatibilidade com perfil `bar-only` às definições.

## O QUE EU FARIA DIFERENTE

Separaria três responsabilidades: contexto causal com proveniência; calculadoras puras, incluindo transição do ATR; persistência e recuperação no scanner. T2.2 entrega o contrato serializável do checkpoint; a integração durável precisa entrar explicitamente em T2.5.

## CONCORDO COM

`Decimal` na borda; ausência como `None`; construtor estrito e builder filtrante; qualidade por dependência; distinção entre S1 `rolling_window_v1` e M2 `anchored_checkpoint_v1`; seed inelegível até a primeira suavização.

## OBSIDIAN

- **Features (Feature Engine)** — registrar contexto causal, fontes canônicas, nomes, qualidade por entrada e checkpoint ATR.
- **Anomalies (Anomaly Engine)** — distinguir baseline imatura de fonte degradada e documentar dependências dos detectores.
- **Market Collector** — documentar limitações dos hashes e buffers, timestamps por campo e cobertura necessária.
- **Diálogo Claude ⇄ Astra — M2** — acrescentar os contratos ratificados após reconciliação deste parecer.
- **Revisões Astra — T2.2** — criar registro deste parecer com cenários de aceite e ligação às páginas acima.