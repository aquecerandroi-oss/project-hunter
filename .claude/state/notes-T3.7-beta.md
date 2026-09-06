# notes-T3.2 — β versionado contra o BTC, com validade (`beta_v1`)

Data: 2026-09-06. Autor: quant-engineer. Escopo entregue: **apenas** o pacote puro
`packages/indicators/hunter_indicators/beta/**` e os testes
`packages/indicators/tests/unit/test_beta_{estimate,returns}.py`. Nada em `services/**`,
nada em `apps/**`, nenhuma migração, nenhum commit.

Pré-requisito do M3: a diretiva do Everton (`directive-risk-engine-2026-09-06.md` §4) diz
"sem beta validado, manter o ativo apenas em shadow", e a análise do orquestrador (item 4)
fixou a proposta — 30 dias de retornos horários, recalculado a cada hora fechada, válido só
com ≥ 20 dias contíguos, BTC β = 1 por definição.

## 1. Arquivos

| Arquivo | Linhas | O quê |
|---|---:|---|
| `packages/indicators/hunter_indicators/beta/__init__.py` | 64 | contrato em um parágrafo + exports |
| `packages/indicators/hunter_indicators/beta/model.py` | 295 | `BetaSpec`, `BetaEstimate`, `HourlyReturn`, motivos, `beta_version`, `is_known_version` |
| `packages/indicators/hunter_indicators/beta/returns.py` | 122 | velas 1m → fechamentos horários → retornos horários; `window_bounds`, `floor_bar` |
| `packages/indicators/hunter_indicators/beta/estimate.py` | 331 | `compute_beta`, `reference_beta`, `invalidates` |
| `packages/indicators/tests/unit/test_beta_estimate.py` | 31 testes | estimador, protocolo de validade, identidade, reprodutibilidade |
| `packages/indicators/tests/unit/test_beta_returns.py` | 11 testes | agregação horária e a prova de não-look-ahead |

## 2. Decisões, com o motivo e onde ficam registradas

### 2.1 Estimador: **MQO com intercepto** (`estimator = "ols_with_intercept"`)

`β = Sxy/Sxx` sobre retornos **centrados**, com `α = ȳ − β·x̄` reportado.

Motivo, que é álgebra e não gosto: `β_origem = β_mqo + α·Σx / Σx²`. Um ativo que caiu o mês
inteiro enquanto o BTC subiu tem a inclinação pela origem puxada pela sua **própria média**.
As médias horárias são pequenas, não nulas — e a KB-0060 e a KB-0071 mediram o universo com
`regr_slope` do Postgres, que **inclui** intercepto, então o número operacional continua
comparável ao publicado (β mediano 2,80 nas memes estabelecidas, 1,44 no resto).

Provado por teste, não por afirmação: `test_intercept_absorbs_drift_that_regression_through_the_origin_would_not`
constrói uma série com drift e mostra 2,50000000 com intercepto contra 2,35714286 pela origem.
Astra concordou com a escolha na opinião prévia (`.claude/state/astra-review-T3.2-beta.md`).

### 2.2 R² é **reportado, nunca gate**

A KB-0060 mediu R² mediano de 0,152 nas memes estabelecidas e 0,021 no resto. Um mínimo de R²
prenderia quase todo o universo em shadow para sempre pela regra da §4 — e, mais ao ponto,
R² baixo não torna a inclinação errada: torna o fator uma parcela pequena da variância.

Ressalva que a Astra impôs e que fica registrada: os números da KB-0060 são de **42 h em
barras de 15 min**, não de 30 dias em barras horárias, então eles **não** demonstram que o
gate prenderia tudo — só que a distribuição de R² é baixa na única janela que medimos. O
argumento que sustenta a decisão é o outro (β é sensibilidade, R² é fração de variância).

Consequência para o Risk Engine: com R² = 0,02 usa-se `|notional × β|` como está, **sem
margem automática** e sem multiplicar β por R² (isso daria mais capacidade justamente quando
o fator explica menos). Uma política de margem por incerteza da inclinação, se um dia for
quista, é decisão própria e versionada à parte.

### 2.3 Retorno **simples**, não log (`return_kind = "simple"`)

`r = c_t/c_{t−1} − 1`. As duas KBs usam log; o consumidor aqui não é o mesmo. O teto da
diretiva é `Σ|notional × β| ≤ 0,5 × patrimônio`, uma afirmação sobre **dinheiro**, e só o
retorno simples faz `Δvalor = notional × r` ser exato. A uma hora a diferença não é de
segunda ordem nas observações que mais influenciam a regressão: uma queda horária de 50% é
−0,5 simples e −0,693 log.

As medições históricas das KBs ficam como estão (são log, e são de 15 min); a nota que as
liga a este estimador é o item de Obsidian listado no §8.

### 2.4 Contiguidade: **480 barras horárias ininterruptas terminando no corte**

"Contíguo" tem aqui exatamente o critério de lacuna de `ingestion_gaps`, propagado para cima:

- a unidade de buraco é a **vela de 1 min ausente** — que é o que uma linha de `ingestion_gaps`
  registra, `[gap_start, gap_end]` inclusivo nos dois extremos;
- uma vela faltando mata a sua hora (uma hora é 60 velas 1m finais, ou não existe);
- matar uma hora mata **dois** retornos: o dela e o da hora seguinte, que perde o predecessor
  (`test_a_missing_minute_costs_its_hour_and_the_next_return`);
- `required_bars = min_contiguous_days × 1440 / bar_minutes` = **480**. A corrida de pares
  ininterruptos (cada um exatamente uma barra depois do anterior) tem de ter ≥ 480 **e
  terminar no corte**, com `max_bar_lag = 1` barra de folga.

**Divergência declarada da Astra (aceita por ela na revisão de diff):** ela propôs "24 horas
pareadas por dia UTC e ≥ 20 dias UTC consecutivos". Medi em **barras** em vez de dias UTC.
É estritamente mais forte do lado do frescor (resolve o cenário de falha que ela mesma
levantou: "vinte dias antigos seguidos de interrupção continuam autorizando entradas") e
remove um alinhamento de meia-noite que não significa nada para β — ao contrário das
baselines, que agrupam por hora do dia. Diferença concreta que ela apontou e que aceito: uma
corrida do meio-dia de D ao meio-dia de D+20 tem 480 horas e apenas **19 dias UTC completos**;
o critério por barras a aceita, o por dias UTC a recusaria por alinhamento de calendário.

A **regressão usa todos os pares válidos da janela** (`n`), não só os da corrida — é mais
eficiente e cada par continua sendo um retorno hora-a-hora legítimo. A corrida é reportada à
parte (`contiguous_bars`): maturidade e tamanho da amostra são números diferentes.
Consequência registrada: uma lacuna no início dos 30 dias mantém o β válido
(`test_a_gap_older_than_the_required_run_still_validates`), que é literalmente "≥ 20 dias
contíguos **dentro** dos 30".

Pareamento é **estrito**: só entra a hora em que ativo e BTC têm hora válida, e o retorno vem
sempre da hora imediatamente anterior. É a correção que a KB-0060 teve de fazer no próprio
SQL (`lag` atravessando lacuna emparelhava um retorno de 30 min com um de 15 min); aqui a
correção é estrutural, não uma cláusula de consulta.

### 2.5 Validade e invalidação

- `valid_until = window_end + 1 h` (`valid_for_minutes = 60`). **Divergência do brief**, que
  dizia `as_of + 1 h` — ver §5.
- `invalidates(estimate, gap_start, gap_end)`: qualquer interseção de `[gap_start, gap_end]`
  (inclusivo, convenção de `ingestion_gaps`) com **`[input_start, window_end)`** descarta a
  estimativa antes do `valid_until`. Deliberadamente grosseiro: uma lacuna fora da corrida
  também invalida, porque um backfill que a preencha muda o conjunto de pares que a regressão
  viu. Os dois extremos foram corrigidos na revisão de diff da Astra: começa uma barra antes
  (a âncora é lida) e é **exclusivo** em `window_end` (o minuto carimbado `window_end` é o
  primeiro da barra que ainda não fechou).

### 2.6 `beta_version` — identidade declarada, não digest do source

`BETA_METHOD_VERSION = "beta_v1"`; `beta_version(spec)` devolve `"beta_v1"` para os parâmetros
publicados e `"beta_v1+<sha256[:12]>"` para qualquer override, sobre
`canonical_json({"params": spec.as_wire(), "numeric": NUMERIC_POLICY})`.

O brief pediu "digest do módulo + parâmetros". **Não hasheio os bytes do módulo**, e a Astra
concordou. Dois motivos: (a) é o padrão já estabelecido duas vezes no repo — `FeatureDefinition`
tira a *descrição* do `feature_set_version` de propósito, e `RegimeThresholds.identity` hasheia
parâmetros; (b) reformatar um comentário invalidaria retroativamente todo β guardado que o
Risk Engine esteja segurando. Hashear este arquivo também **não** cobriria o contexto
aritmético de `hunter_core`, então compraria confiança falsa. Mudança de fórmula = bump manual
de `BETA_METHOD_VERSION`, com a implementação anterior preservada para replay, exatamente como
uma versão de feature. Proveniência do artefato (qual build produziu a linha) é outra pergunta
e pertence ao registro de deploy.

`is_known_version(version, *, allowed=KNOWN_BETA_VERSIONS)` é o gancho para o Risk Engine
recusar um β de versão desconhecida.

### 2.7 Numérica — **onde entra float64: em lugar nenhum**

O brief autorizava `numpy` em `float64` **sobre retornos** (nunca sobre preço), com retorno a
`Decimal` quantizado, e pediu "diga onde". A resposta é: **não uso `numpy` nem `float` em
nenhum ponto deste pacote**, e a justificativa é da Astra, aceita:

- a janela tem no máximo 720 pares, então a aritmética é gratuita nos dois caminhos;
- a estratégia de somatório e a largura de SIMD do NumPy **não são contratuais**, então o mesmo
  insumo pode diferir nos últimos bits entre a máquina Windows do Everton e a VPS Linux — e um
  valor em cima de uma fronteira de quantização passa a serializar em duas cadeias canônicas
  diferentes. O M2 exige reprodutibilidade byte a byte;
- portanto: tudo é `Decimal` sob `hunter_core.strategies.numeric.CONTEXT` (28 dígitos,
  `ROUND_HALF_EVEN`), duas passagens (médias, depois somas centradas), **ordem cronológica
  fixa**. Preços nunca viram float; retornos também não.

Quantums: β e α em `1e-8`, R² em `1e-6`, `−0` normalizado para `0`. São resoluções de
armazenamento, não precisão estatística.

A Astra verificou o determinismo empiricamente na revisão de diff: alterando o contexto
ambiente para precisão 6, `ROUND_UP` e trap de `Inexact`, os bytes canônicos não mudaram; e não
achou dependência de ordem de `dict`/`set` no resultado.

### 2.8 Degenerações

- BTC constante (`Sxx = 0`): inclinação **não identificável** → `beta = None`, `r_squared = None`,
  `valid = False`, `reason = degenerate_variance`. Nunca zero, nunca um.
- Ativo constante (`Syy = 0`): a inclinação **é** identificável e é exatamente zero, mas R² é
  `0/0` → `beta = 0`, `r_squared = None`, também recusado (uma série que não se moveu por 30
  dias é feed morto, não hedge). Os dois fatos ficam separados na linha.
- **Bug encontrado pela Astra e corrigido**: testar `Sxx == 0` não detecta constantes com mais
  dígitos que `CONTEXT.prec` — a média de 720 cópias de `0.0001234567890123456789012345678`
  arredonda, as diferenças centradas saem não nulas, e duas séries chatas eram pontuadas
  `β = 1`, `R² = 1`, **válidas**. Reproduzi antes de corrigir. A constância agora é decidida
  **nos valores de entrada**, exata, sem epsilon; o teste de `Sxx`/`Syy` fica só como rede.
- `HourlyReturn` recusa valor não finito no construtor (NaN chegava à regressão e aparecia como
  `InvalidOperation` lá dentro).

### 2.9 BTC contra BTC

`reference_beta(as_of=..., market="BTCUSDT")` → `beta = 1.00000000`,
`estimator = "definition"`, `n = 0`, `r_squared = None`, sem gate de maturidade.
`R² = 1` seria vestir uma definição de medição; `n = 0` e `estimator = definition` na própria
linha é o que impede um consumidor de misturar esse 1 numa distribuição de estimativas.
`test_a_series_regressed_on_itself_also_lands_on_one` mostra que o atalho não é fraude: o
estimador, alimentado com a mesma série dos dois lados, também dá 1 com R² = 1.

## 3. Motivos de invalidade (o vocabulário completo)

| `reason` | Quando | Cura |
|---|---|---|
| `btc_missing` | nenhuma hora da referência dentro da janela | coletar/backfill do BTC |
| `insufficient_history` | alcance (par mais antigo → corte) < 480 barras | esperar |
| `gaps` | alcança, mas a corrida < 480 ou não chega ao corte (`max_bar_lag`) | backfill |
| `degenerate_variance` | referência ou ativo constante na janela | nenhuma; o dado não responde |

A precedência é a ordem acima. Ela **empresta o vocabulário** de `features/windows.py`
(warm-up vs gap) mas **não** a regra dele, e a diferença fica declarada: lá, um buraco dentro
de um histórico que alcança é gap; aqui o alcance é medido primeiro, então 100 horas com um
buraco saem como `insufficient_history` — "ainda não poderia ter amadurecido", que é a
afirmação mais fraca das duas.

## 4. Onde o scanner vai chamar (não implementado nesta tarefa, de propósito)

A T2.5c está em voo; o brief manda deixar só a interface pura. Quando for a hora:

- **Quando:** em `services/scanner-worker`, num laço **por hora fechada** (o mesmo gatilho do
  minuto fechado, com passo de hora), depois do BTC estar disponível. `as_of` = o instante do
  disparo; `window_bounds` já o piso para a última hora fechada.
- **Como:** para cada mercado do universo, carregar as velas 1m persistidas de
  `[window_start − 1 h, window_end]` (a barra extra é a âncora do primeiro retorno), chamar
  `hourly_returns(candles, as_of=..., spec=...)` uma vez para o mercado e uma vez para o
  BTCUSDT (o BTC é carregado **uma** vez por ciclo e reusado), e então
  `compute_beta(asset_returns, btc_returns, as_of=..., market=..., reference="BTCUSDT")`.
  Para o próprio BTCUSDT, `reference_beta(...)` — nunca `compute_beta`.
- **O que grava:** uma linha em `market_betas` por mercado por hora, `estimate.as_wire()`
  praticamente pronto para a linha (a serialização já é canônica).
- **Invalidação:** quando o market-worker publicar uma lacuna nova, o consumidor chama
  `invalidates(estimate, gap_start, gap_end)` para as estimativas vigentes daquele mercado e
  marca as atingidas como não utilizáveis antes do `valid_until`.
- **Custo:** ~200 mercados × 720 pares de aritmética `Decimal` por hora. Não medi; se pesar, o
  carregamento das velas é o candidato a otimizar, não o estimador.

## 5. Divergências do brief — as duas, explícitas

1. **`valid_until = window_end + 1 h`, não `as_of + 1 h`.** O brief pedia `as_of + 1 h`. A
   Astra reproduziu o problema: último par fechando às 11h, cálculo às 12h59, validade até
   13h59 — **2h59** de idade máxima do dado, e um β sobrevivendo uma hora além da recomputação
   que deveria tê-lo substituído. Ancorado em `window_end` os dois coincidem no caso nominal
   (job na hora cheia) e divergem só quando o job atrasa, e aí na direção segura. `as_of`
   continua gravado na linha, então a diferença é visível. **Reversível numa linha** se o
   Everton/orquestrador preferir a redação literal.
2. **Sem `numpy`/`float64`.** O brief permitia; escolhi não usar, pelo motivo do §2.7.

## 6. Esquema proposto para `market_betas` (proposta ao database-architect, sem migração)

```sql
CREATE TABLE market_betas (
  id                  UUID PRIMARY KEY,               -- uuid7; a identidade da REVISÃO
  organization_id     UUID NOT NULL,                  -- RLS, como o resto do schema
  market_id           UUID NOT NULL REFERENCES markets(id),
  reference_market_id UUID NOT NULL REFERENCES markets(id),   -- o BTC da MESMA exchange/venue/cotação
  as_of               TIMESTAMPTZ NOT NULL,           -- o corte pedido
  window_start        TIMESTAMPTZ NOT NULL,
  window_end          TIMESTAMPTZ NOT NULL,           -- última barra fechada
  input_start         TIMESTAMPTZ NOT NULL,           -- window_start - 1 barra (a âncora)
  last_pair_end       TIMESTAMPTZ,                    -- frescor observado
  valid_until         TIMESTAMPTZ NOT NULL,
  computed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),  -- quando o job rodou
  available_at        TIMESTAMPTZ NOT NULL DEFAULT now(),  -- a partir de quando pode ser consumido
  beta_version        TEXT NOT NULL,
  estimator           TEXT NOT NULL,                  -- 'ols_with_intercept' | 'definition'
  beta                NUMERIC(18,8),
  alpha               NUMERIC(18,8),
  r_squared           NUMERIC(9,6),
  n                   INT  NOT NULL,
  contiguous_bars     INT  NOT NULL,
  valid               BOOLEAN NOT NULL,
  reason              TEXT,
  params              JSONB NOT NULL,                 -- spec.as_wire() + numeric policy
  superseded_at       TIMESTAMPTZ,                    -- preenchido quando uma revisão nova a substitui
  UNIQUE (market_id, as_of, beta_version, computed_at)
);
CREATE INDEX ix_market_betas_current ON market_betas (market_id, as_of DESC);
```

Notas que vêm da revisão da Astra e que o database-architect deveria ler antes de decidir:

- **PK `(market_id, as_of)` é errada.** Um backfill produz **outro** β para o mesmo mercado e o
  mesmo corte, sob a **mesma** `beta_version`. Ou se guardam as duas revisões, ou a evidência
  anterior é destruída. Daí `id` próprio de revisão, `computed_at` na chave de idempotência, e
  `superseded_at` para a vigente ser determinável sem depender de `valid`.
- **Índice parcial `WHERE valid` não pode sozinho determinar a revisão vigente**: se uma revisão
  posterior registra invalidez, buscar só as válidas ressuscita a anterior. Por isso o índice
  acima é por `(market_id, as_of DESC)` e a leitura filtra `superseded_at IS NULL`.
- **`NUMERIC(12,8)` era estreito demais** (4 dígitos inteiros): uma referência quase constante
  pode produzir inclinação maior. `NUMERIC(18,8)`, e o carregador deve recusar em vez de
  truncar em silêncio.
- `available_at` existe para impedir uso retroativo de uma revisão conhecida **depois** da
  decisão de risco — a mesma disciplina causal das baselines.

## 7. O que fica em aberto (e não finjo ter resolvido)

- **Quantos mercados passam na validade?** Não medi. A KB-0074 registra 34 de 232 mercados com
  lacunas nas últimas 24 h, e o critério exige 480 horas ininterruptas terminando no corte. Se
  a taxa de aprovação for baixa, a diretiva §4 prende quase tudo em shadow — isso é uma
  **consequência da regra do Everton**, não um defeito do cálculo, e a medição tem de ser
  apresentada a ele antes de qualquer relaxamento de `min_contiguous_days` ou `max_bar_lag`.
  Um relaxamento é um `beta_version` novo, por construção.
- **β de MQO em 30 dias é ruidoso** e o ruído tem direção quando R² é baixo (KB-0071). "Válido"
  aqui significa **elegível pelo protocolo**, nunca "comprovadamente preciso". O contrato do
  Risk Engine não deve ler `valid = true` como precisão.
- **Estabilidade de β em stress não é testada por nada disto** (KB-0034, KB-0071): a única
  janela que medimos foi de calmaria.
- Diagnósticos que a Astra sugeriu e que não estão aqui: estabilidade por subjanela, influência
  de observações extremas, comparação simples vs log. São pesquisa, não pré-requisito do M3.
- `2h` de idade máxima do dado (`max_bar_lag = 1` + validade de 1 h) é decisão **operacional
  explícita**, não garantia estatística — uma observação extrema pode ter muita influência.

## 8. Obsidian (a atualizar por quem cuida da base)

- **Features / Feature Engine** — registrar o contrato `beta_v1`: fórmula, 480 barras, âncora,
  identidade, aritmética `Decimal`, e a correção da degeneração numérica.
- **Risk Engine** — validade ancorada em `window_end`, consumo de β com R² baixo sem margem,
  e a revisão exata de β consumida por cada decisão.
- **KB-0060 / KB-0071** — ligar ao estimador operacional, distinguindo as medições (log, 15 min,
  42 h) do estimador (simples, 1 h, 30 dias) e preservando o histórico.
- **Revisões da Astra — T3.2** — `.claude/state/astra-review-T3.2-beta.md` (opinião prévia) e
  `.claude/state/astra-review-T3.2-beta-diff.md` (revisão de diff, três must-fix reproduzidos).
