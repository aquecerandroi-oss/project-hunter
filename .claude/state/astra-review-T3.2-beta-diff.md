**RESUMO**

**Não aprovaria ainda.** A regressão e o pareamento estão bem encaminhados, mas reproduzi três falhas: séries constantes aceitas por arredondamento, invalidação que ignora a âncora e validade chegando a **2h59 após o último par**.

Assumi `quant-engineer`, em modo OPINIÃO. Aceito substituir minha recomendação anterior de dias UTC completos por **480 barras consecutivas**; abaixo explico a diferença.

**ARQUIVOS**

Nenhum criado ou modificado. Li integralmente os quatro módulos e os dois arquivos de testes solicitados.

**TESTES**

Executei sondas com `uv run python -B -`, sem sincronização de dependências e sem escrita de bytecode. Chamei diretamente os testes existentes e fiz uma mutação exclusivamente em memória:

```text
direct_test_functions: 33 passed (not pytest runner)
is_final_mutant: KILLED (AssertionError)
ambient_context_same_bytes: True
480_hours_full_UTC_days: 19
anchor_gap_invalidates: False
anchor_return_counts: 2 1
stale: True
age_at_expiry: 2:59:00
constant_btc valid= True reason= None beta= 0E-8 r2= 0.000000
constant_asset valid= True reason= None beta= 0E-8 r2= 0.000000
both_constant valid= True reason= None beta= 1.00000000 r2= 1.000000
```

Não reexecutei pytest, ruff ou pyright; os **865 passed** são o resultado informado por você.

**MUST-FIX**

**1. A detecção de variância degenerada falha para constantes não zero.**

Em [estimate.py:163](/C:/dev/project-hunter/packages/indicators/hunter_indicators/beta/estimate.py:163), a soma de valores constantes pode arredondar; a média resultante difere ligeiramente do próprio valor. As diferenças centradas passam a produzir `Sxx > 0` ou `Syy > 0`, escapando dos testes de igualdade com zero.

Reprodução: 720 repetições de `Decimal("0.0001234567890123456789012345678")`.

- BTC constante: aceitou beta zero.
- Ativo constante: aceitou beta zero.
- Ambos constantes: aceitou **beta 1 e R² 1**.

**Cenário:** uma referência sem dispersão recebe beta válido e autoriza consumo pelo Risk Engine. Os testes atuais usam constantes zero, cuja soma não sofre esse problema: [test_beta_estimate.py:167](/C:/dev/project-hunter/packages/indicators/tests/unit/test_beta_estimate.py:167).

Correção mínima: identificar constância diretamente nos valores de cada série antes da regressão, preservando a distinção entre os dois casos. Acrescentar os três testes acima; não introduzir epsilon arbitrário.

Também falta rejeição explícita de retornos não finitos na fronteira: `HourlyReturn` só valida o timestamp; `NaN` chegou à regressão e levantou `InvalidOperation`. Recusar explicitamente é suficiente; não precisa fabricar um resultado. [model.py:195](/C:/dev/project-hunter/packages/indicators/hunter_indicators/beta/model.py:195)

**2. (d)+(e): `invalidates()` não cobre toda a dependência real.**

A âncora admitida começa em `window_start - bar`, mas a invalidação começa em `window_start`. [returns.py:73](/C:/dev/project-hunter/packages/indicators/hunter_indicators/beta/returns.py:73), [estimate.py:287](/C:/dev/project-hunter/packages/indicators/hunter_indicators/beta/estimate.py:287)

**Cenário reproduzido:** gap de um minuto em `window_start - 1min`. Sua ausência remove o primeiro retorno; preenchê-lo altera o conjunto pareado. Mesmo assim, `invalidates()` retorna `False`.

Minha decisão:

- **Invalidar fora da corrida, mas dentro das dependências da regressão: correto.** A regressão usa todos os pares.
- **Extremo direito inclusivo: conservador.** Um gap começando exatamente em `window_end` já pertence à próxima barra; invalidar nesse caso custa disponibilidade, sem proteger uma observação usada.
- **Extremo esquerdo atual: insuficiente.** Deve incluir a barra de âncora.

Para gaps rotulados pelo início do minuto, a interseção relevante é com **`[window_start - bar, window_end)`**.

A janela reportada não mente **se significar janela dos retornos**. Mente se o consumidor a interpretar como extensão completa dos dados lidos. Documentaria essa distinção e exporia `input_start` ou equivalente.

**3. (b): aceito uma barra de tolerância, mas não esse cálculo de expiração.**

O código mede lag contra `floor(as_of)`, enquanto expira em `as_of + 1h`. [estimate.py:147](/C:/dev/project-hunter/packages/indicators/hunter_indicators/beta/estimate.py:147), [estimate.py:230](/C:/dev/project-hunter/packages/indicators/hunter_indicators/beta/estimate.py:230)

**Cenário reproduzido:** último par encerrado às 11h; cálculo às 12h59; estimativa válida até 13h59. São **2h59**, não duas horas. O teste de chamada às `:37` confirma que esse deslocamento é comportamento deliberado da implementação: [test_beta_estimate.py:220](/C:/dev/project-hunter/packages/indicators/tests/unit/test_beta_estimate.py:220).

Recomendo **manter `max_bar_lag=1` e ancorar `valid_until = window_end + 1h`**. Assim, a idade máxima fica limitada a duas horas, sem depender do atraso do job. Isso também segue o contrato atual: [RISK_ENGINE.md:262](/C:/dev/project-hunter/docs/RISK_ENGINE.md:262).

Não sustentaria a afirmação de que duas horas são necessariamente “imateriais” para uma regressão de 30 dias: uma observação extrema pode ter muita influência. A tolerância é uma decisão operacional explícita, não uma garantia estatística.

**4. (3): o esquema precisa de identidade da referência e identidade temporal da revisão.**

O contrato exige revisões imutáveis e admissão por disponibilidade: [RISK_ENGINE.md:257](/C:/dev/project-hunter/docs/RISK_ENGINE.md:257).

Acrescentaria:

| Campo | Necessidade |
|---|---|
| `reference_market_id` | Identificar BTC na exchange, modalidade e cotação corretas. |
| `available_at` | Impedir uso retroativo de revisão conhecida depois da decisão. |
| `computed_at` | Separar execução do cálculo do corte analisado; `created_at` pode cumprir isso se o contrato o definir. |
| `revision_id` | Referenciar precisamente a revisão consumida pela decisão de risco. |
| `last_pair_end` | Mostrar o frescor observado, que `window_end` não informa quando há tolerância. |
| `input_start` | Declarar a dependência da âncora e orientar invalidação. |

**Cenário:** backfill gera outro beta para o mesmo mercado e corte. A PK `(market_id, as_of)` impede guardar ambas as revisões, ou incentiva sobrescrita que destrói a evidência anterior. Usaria uma identidade própria de revisão e uma chave de idempotência explicitamente definida; acrescentar apenas `beta_version` à PK não resolve revisões dos dados sob a mesma versão.

O índice parcial `WHERE valid` pode ser auxiliar, mas **não pode determinar sozinho a revisão vigente**: se uma revisão posterior registra invalidez, buscar apenas válidas pode ressuscitar a anterior.

**NICE-TO-HAVE**

**(a) Barras versus dias UTC completos:** existe diferença, mas aceito sua escolha. Uma corrida do meio-dia de D até o meio-dia de D+20 tem **480 horas e apenas 19 dias UTC completos**. Isso não enfraquece a duração contínua observada; exigir meia-noite acrescentaria espera por alinhamento do calendário. A implementação mede a corrida separadamente de `n`, corretamente: [estimate.py:143](/C:/dev/project-hunter/packages/indicators/hunter_indicators/beta/estimate.py:143).

**(c) Alcance para distinguir warm-up/gaps:** correto **como política declarada**, sem erro de uma barra: o timestamp marca o início do retorno, então 480 barras terminando no corte dão alcance 480. Porém, não é equivalente a `tail_minutes`: ali a classificação depende de existir histórico antes da quebra, mesmo curto. [features/windows.py:123](/C:/dev/project-hunter/packages/indicators/hunter_indicators/features/windows.py:123)

Exemplo: 100 horas de alcance com uma quebra interna serão `insufficient_history` aqui. Isso comunica “ainda não poderia atingir maturidade”, não “não existe dano”. Sem pares, também não é possível distinguir aquecimento de ausência causada por gaps apenas com os argumentos atuais. Eu manteria a precedência, retirando a alegação de equivalência.

Para armazenamento, `NUMERIC(12,8)` limita beta/alpha a quatro dígitos inteiros. O estimador não impõe esse limite: referência quase constante pode produzir inclinação maior. Definir representação ou tratamento explícito antes da migração; não truncar silenciosamente. [estimate.py:176](/C:/dev/project-hunter/packages/indicators/hunter_indicators/beta/estimate.py:176)

**O QUE EU FARIA DIFERENTE**

**(1) Determinismo:** não encontrei dependência da ordem de dict/set no resultado calculado. Os retornos são ordenados; a entrada da regressão exige ordem estrita; o pareamento preserva essa ordem. [returns.py:110](/C:/dev/project-hunter/packages/indicators/hunter_indicators/beta/returns.py:110), [estimate.py:95](/C:/dev/project-hunter/packages/indicators/hunter_indicators/beta/estimate.py:95)

A alteração do contexto ambiente para precisão 6, `ROUND_UP` e trap de `Inexact` preservou os bytes. A serialização Decimal também evita normalização dependente do contexto: [canonical.py:52](/C:/dev/project-hunter/packages/core/hunter_core/strategies/canonical.py:52).

Isso não elimina o erro de degeneração: **um resultado pode ser determinístico e numericamente incorreto**. Fixaria testes para constantes extensas, fronteira da âncora, lag 0/1/2 e expiração com `as_of` não alinhado.

**CONCORDO COM**

**(2) O teste da vela em formação não é vacuoso.** Há um retorno válido preservado, e remover `is_final` faz o teste falhar; reproduzi a mutação em memória. [test_beta_returns.py:88](/C:/dev/project-hunter/packages/indicators/tests/unit/test_beta_returns.py:88)

Uma precisão sobre sua descrição: o helper altera os preços das **60 velas** da terceira hora, embora só a última seja não final. Isso não anula a prova, mas eu modificaria somente a última vela para corresponder literalmente ao enunciado. [test_beta_returns.py:35](/C:/dev/project-hunter/packages/indicators/tests/unit/test_beta_returns.py:35)

Concordo também com OLS com intercepto, R² informativo, retornos simples, pareamento estrito, quantums e BTC definido separadamente. O teste de drift distingue efetivamente regressão pela origem: [test_beta_estimate.py:88](/C:/dev/project-hunter/packages/indicators/tests/unit/test_beta_estimate.py:88).

**OBSIDIAN**

- **Features (Feature Engine)** — registrar o contrato de 480 barras, âncora e correção da degeneração numérica.
- **Risk Engine** — registrar expiração ancorada, disponibilidade e revisão exata do beta consumido.
- **Revisões da Astra — T3.2** — guardar os casos reproduzidos e as decisões aceitas.
- **KB-0071** — ligar ao estimador operacional, distinguindo validade pelo protocolo de precisão estatística.