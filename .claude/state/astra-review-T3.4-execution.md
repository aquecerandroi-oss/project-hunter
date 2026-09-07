**RESUMO**

Como `risk-engine-guardian`: recomendo **adaptador puro, um fill agregado por tentativa e aplicação exclusiva pelo ledger da T3.3, coordenada pela T3.5**. A proposta precisa explicitar consumo persistente do livro, disponibilidade temporal dos dados e gatilho durável.

**ARQUIVOS**

Nenhum arquivo criado ou modificado.

**TESTES**

Não executados: revisão de contrato antes da implementação.

**MUST-FIX**

**1. Assinatura e escritor único.** Concordo com os dois métodos síncronos retornando `ExecutionReport`. Acrescentaria argumentos nomeados: `attempt_context` — identidade, decisão, latência e limites executáveis —, `consumed_depth` e `filter_price_reference`, com preço médio, janela, fonte e disponibilidade.

O `SpotFilters(Protocol)` deve expor `round_qty_down(qty: Decimal) -> Decimal` e `check_market_order(qty: Decimal, *, avg_price: Decimal | None = None, last_price: Decimal | None = None) -> MarketCheck`. `MarketCheck` também estrutural, com propriedades somente leitura `ok`, `qty`, `notional`, `reason`; isso acomoda a dataclass congelada existente sem importar `hunter_exchanges`. A referência média é necessária: o filtro atual pode devolver `avg_price_unavailable` ([filters.py:173](/C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance_spot/filters.py:173)).

A T3.5 obtém dados **fora da transação**, adquire as travas canônicas, relê saldo/reservas/consumo, chama o cálculo puro e aplica, pelo ledger, **fill + saldo + intenção + consumo + auditoria/outbox atomicamente**. Replay retorna o resultado persistido. Essa fronteira segue a decisão de concorrência ([M3.md:140](/C:/dev/project-hunter/docs/plans/M3.md:140)).

**Falha:** dois escritores descontam o mesmo saldo; ou duas tentativas com IDs diferentes reutilizam profundidade já consumida. O relatório precisa devolver consumo **por snapshot/lado/nível**, mesmo agregando o fill. `participation_consumptions` registra orçamento de entrada, não substitui esse controle; proteção não consome participação ([RISK_ENGINE.md:250](/C:/dev/project-hunter/docs/RISK_ENGINE.md:250)).

**2. Marcação e relógios.** Aceito **10 s como limite inicial declarado**, não como valor empiricamente validado ou garantia de proteção. Não defenderia outro número sem medir intervalos entre negócios e atraso de recepção. Exigiria:

- `0 <= now − trade.ts <= 10 s`, mais `trade.available_at <= now`. Idade negativa é indisponibilidade.
- IDs comparados **numericamente**, no escopo exchange/SPOT/símbolo/fonte `aggTrade`; nunca misturar IDs de negócios individuais.
- Crescimento estrito para **aceitar observação nova**. Duplicata não atualiza frescor, mas o último negócio aceito continua utilizável até vencer.
- `attempt_decision_at + latency <= book.received_at <= now`, idade máxima própria do livro e sequência sem regressão. Seleção do primeiro snapshot elegível disponível, sem escolher retrospectivamente o mais favorável.

O normalizador preserva `lastUpdateId`, usa recepção como timestamp do livro e transforma o ID do negócio em string ([normalize.py:203](/C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance_spot/normalize.py:203), [normalize.py:236](/C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance_spot/normalize.py:236)). Portanto, recepção prova disponibilidade local, não o instante de formação do livro na exchange.

Separaria `trigger_state = not_triggered | triggered | unavailable` de `execution_state/reason`. Depois de disparado, **persistir `triggered_at` e a observação causadora**; as próximas tentativas não exigem novo cruzamento.

**Falhas:** exigir ID novo a cada chamada invalida um negócio ainda fresco; olhar só o último negócio de cada ciclo perde um toque intermediário; reavaliar o cruzamento depois de um fill parcial abandona o restante quando o preço recupera. Avaliar negócios novos em ordem; lacuna não autoriza afirmar “sem gatilho”.

**3. Identidade e granularidade.** Concordo com **zero ou um fill agregado, imutável e terminal por tentativa**. Guardaria `gross_qty`, `gross_quote = Σ(qᵢpᵢ)`, VWAP e decomposição por nível; o notional exato não deve ser reconstruído multiplicando VWAP arredondado.

Usaria `exit:{attempt_id}` e `entry:{proposal_id}`, com `attempt_id` globalmente único ou namespace incluindo `intent_id`. O schema distingue tentativa de intenção e garante unicidade da chave por organização ([DATABASE.md:1815](/C:/dev/project-hunter/docs/DATABASE.md:1815), [DATABASE.md:1917](/C:/dev/project-hunter/docs/DATABASE.md:1917)).

**Falha:** publicar dois incrementos sob a mesma chave engole o segundo parcial legítimo. A agregação funciona porque todos os níveis entram num único resultado atômico; se houver publicação incremental, precisará de `fill_index` estável. Outra tentativa recebe outra identidade, mas não recupera profundidade consumida. Preservar também tentativas sem fill impede que uma entrada terminal seja executada novamente.

**4. Fee em base e resíduo.** Publicaria `gross_base_qty`, `gross_quote_qty`, `fee_asset`, `fee_qty`, `fee_quote_equivalent`, preço/fonte da conversão, política de arredondamento, `net_base_delta` e `net_quote_delta`.

Na compra com taxa em base: `Δbase = gross_qty − fee_base`; `Δquote = −gross_quote`. Na venda com taxa em quote: `Δbase = −sold_qty`; `Δquote = gross_quote − fee_quote`. **O equivalente em quote da taxa em base é informativo, não um segundo débito.** O helper atual calcula taxa em quote; sua moeda não pode ser reinterpretada silenciosamente ([fees.py:82](/C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance_spot/fees.py:82)).

Separaria `attempt_unfilled_qty`, `intent_remaining_qty`, `position_remaining_qty` e `blocked_residual_qty`. Publicaria `residual_value_quote`, `valuation_price/source/as_of/status`; sem marca válida, valor nulo com motivo, quantidade preservada. Liquidez insuficiente não é dust; referência de filtro ausente não prova mínimo violado.

**Falha:** descontar BTC e USDT pela mesma taxa duplica o custo; arredondar o saldo inteiro ao step apaga patrimônio. `blocked_residual` permanece reavaliável; intenção concorrente liquidada por outra proteção não recebe fill fictício ([DATABASE.md:1929](/C:/dev/project-hunter/docs/DATABASE.md:1929)).

**5. Pior que o stop.** Concordo: registrar o resultado, sem limitar artificialmente a perda. Além dos campos anteriores, exigiria:

- Identidades de proposta/posição/intenção/tentativa/ordem, mercado e lado.
- `planned_stop_price`, referência à decisão de risco, `trigger_price`, `trigger_trade_id`, timestamps de evento/disponibilidade/gatilho.
- `attempt_decision_at`, `eligible_at`, `executed_at`, latência e versões das políticas.
- Identidade/sequência/recepção do livro, níveis consumidos, VWAP antes e depois de eventual ajuste, modelo e ajuste aplicado.
- `slippage_vs_plan_quote` e `slippage_vs_plan_bps`, com convenção explícita: **positivo = adverso**.

Para SELL: `slippage_quote = stop × filled_qty − gross_quote`; `bps = slippage_quote / (stop × filled_qty) × 10000`. Fees separadas; sem fill, métricas nulas.

**Falha:** guardar apenas bps não permite distinguir gap, taxa ou ajuste artificial. A T3.9 deve provar os valores contra uma fixture conhecida, não apenas verificar que dois campos calculados pelo mesmo código concordam ([M3.md:62](/C:/dev/project-hunter/docs/plans/M3.md:62)).

**NICE-TO-HAVE**

Histogramas de idade do negócio, atraso de recepção e tempo entre gatilho e execução para revisar os 10 s com evidência.

**O QUE EU FARIA DIFERENTE**

Separaria avaliação pura do gatilho, cálculo da tentativa e aplicação transacional; módulos pequenos dentro de `hunter_core.execution`, respeitando os arquivos em voo.

**CONCORDO COM**

Pureza, Protocol estrutural, walk único, fill agregado, intenção durável, resíduo visível e slippage sem correção artificial.

**OBSIDIAN**

- **Execution Engine** — registrar fronteira cálculo/ledger/worker e identidade das tentativas.
- **Paper Trading** — documentar validade temporal, consumo do livro e evidências do fill.
- **Portfolio** — registrar deltas por ativo, taxa em base e resíduo sem baixa fictícia.
- **Diálogo Claude ⇄ Astra — M3** — registrar esta proposta de contrato da T3.4, ainda sujeita à convergência.