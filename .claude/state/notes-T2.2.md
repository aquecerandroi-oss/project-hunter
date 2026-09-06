# Notas de desenho — T2.2 (`hunter_indicators.features`)

Decisões tomadas ao implementar `.claude/state/brief-T2.2-feature-engine.md`, com a segunda
opinião da Astra (`.claude/state/astra-review-T2.2-features.md`). Onde a "Decisão conjunta" de
`docs/plans/M2.md` (linhas 48–61) manda, ela manda; onde ela era omissa, a escolha está aqui com
o motivo. Nada aqui altera código de outra tarefa.

## 1. `MarketContext`: o corte é do tipo, não da disciplina
- Candle final entra só com `close_time <= as_of` (não `open_time`): às 12:00:30, admitir o
  candle 12:00–12:01 pela abertura revelaria os 30 s seguintes.
- O candle em formação entra separado (`forming`) e precisa de `open_time <= as_of < close_time`
  **e** `event_ts <= as_of`. Uma atualização parcial carimbada depois do corte é informação
  futura mesmo sendo do mesmo minuto (must-fix 1a da Astra).
- Cada fonte é um `SourceEntry` com `ts`, `covers_from`, `truncated` e `reason`. "Não tem book" e
  "book de 40 s" são fatos diferentes; nenhum vira zero.
- `deriv` guarda `funding_ts`, `mark_ts` e `oi_ts` **separados** (o hash do market-worker também
  guarda): um mark novo não pode fazer um OI de 20 min parecer fresco (must-fix 1c).
- `btc` é um `MarketContext` aninhado com o **mesmo** `as_of` e proibido de aninhar outro. Nenhuma
  feature v1 usa BTC (as features cross não estão no escopo do brief); o campo existe porque o
  contexto é o contrato de T2.3/T2.4.
- Duas portas, como em `hunter_core.strategies.base`: `MarketContext` estrito (levanta) e
  `build_context` filtrante (descarta) — filtrante **só para candles**, ver §14.7. Bug do scanner
  vira exceção, não score enviesado.

## 2. Fonte canônica dos extremos de 24 h
`distance_from_24h_high/low` usa **1440 candles finais contíguos**, nunca `high_24h`/`low_24h` do
hash de ticker. Motivo (aceito da Astra): o parser de `bookTicker` não fornece esses campos e a
escrita remove campos próprios ausentes, então a mesma chave alternaria entre duas janelas e duas
semânticas sem mudar de versão. Sem janela completa → `warmup`/`gap`, sem fallback silencioso.

## 3. `_live` = inclui o candle em formação (e só isso)
Sufixo `_live` sse o cálculo usa `forming`. Features de book/trades (`spread_pct`,
`orderbook_imbalance_20`, `buy_pressure_5m`, `sell_pressure_5m`, `trade_velocity_1m`) **não**
levam sufixo: não leem candle. Elas carregam `ts`, idade e cobertura próprios na proveniência do
vetor, e nada aqui alega que sejam reproduzíveis a partir de candles históricas — a garantia
continua sendo recomputar amostras gravadas (`docs/plans/M2.md:54`).
Conjunto `_live` v1: `return_1m_live`, `return_5m_live`, `return_15m_live`, `return_1h_live`.
As demais features de candle são bar-only na v1 (o scorer usa as `_live` de preço para a cadência
de 1 s; ampliar o conjunto é uma versão nova, não uma flag).

## 4. ATR: `anchored_checkpoint_v1` (≠ `rolling_window_v1` da S1)
- Estado explícito e serializável (`features/atr.py`): `origin_bar_open` (primeira barra, só dá o
  fechamento anterior do primeiro TR), `seed` = média dos 14 primeiros TRs, `seed_anchor`, `value`
  liberado **só** após uma suavização (16 barras completas para período 14), `last_bar_open`,
  `last_close`, `method`, `origin`, `state_version`.
- `advance(state, bars)` é transição pura: barra duplicada não avança, barra anterior não retrocede,
  barra faltante para o avanço com `gap` **sem** pular. `advance_from_context` reancora após gap e
  carimba `origin_reason = "gap_rebuild"` (ou `"bootstrap"` no início frio). A âncora **não** se
  move quando a janela de 1500 minutos rola — é isso que `docs/plans/M2.md:52` exige.
- Escolha entre checkpoint persistido e âncora de calendário: **checkpoint**, como a Astra
  recomendou (3a). Custo declarado: perder o checkpoint reancora e produz número levemente
  diferente; por isso o `origin_reason` viaja com o estado e T2.5 é quem persiste/recupera.
- **Divergência registrada com a S1:** `hunter_core.strategies.indicators.wilder_atr` reseeda na
  janela que recebe (`rolling_window_v1`, `.claude/state/notes-S1.md` §3). São calculadoras
  diferentes, com nomes diferentes; nenhuma alega ser a outra e nenhuma foi alterada.
- Não existe `atr_14_pct_live`: não agregamos bucket de 15 min parcial. Um ATR ao vivo seria uma
  cópia do checkpoint fechado (nunca o estado canônico avançado com parciais).

## 5. `relative_volume_*` **não** é a razão de 7 dias na mesma hora
v1 = volume da última janela ÷ **mediana das 23 janelas disjuntas anteriores** do mesmo tamanho,
sobre a mesma série de 1 min; os parâmetros declaram isso. A comparação "mediana de 7 dias na
mesma hora" de `PIPELINE.md` §2 é **baseline** e é a T2.3 que a calcula — a partir destas leituras.
Usar o mesmo nome para as duas faria a chave significar coisas diferentes no bootstrap e no
scanner (ressalva da Astra, 3c). `lookback_windows = 23` porque 24 janelas de 60 min = 1440 min
cabem no buffer de 1500; 24 janelas dariam exatamente 1500 e ficariam indisponíveis quase sempre.

Grafia congelada (a decisão conjunta prevalece sobre o brief, que usa o nome da família):
`relative_volume_5m/15m/1h`, `volume_acceleration`. Também entregue `return_4h`, que a alternativa
EXTENDED da T2.4 exige.

## 6. `momentum_15m` não é apelido de `return_15m`
`momentum_15m = return_15m / atr_14_pct` (quantos ATRs o preço andou) — é a grandeza que o
classificador de estágio compara com 1,5 e 4. `momentum_acceleration = (retorno atual − retorno
anterior) / atr_14_pct`, com o **ATR atual** escalando os dois termos (o checkpoint não pode ser
rebobinado; escalar o retorno antigo por outro denominador compararia unidades diferentes).
`breakout_strength_20` = fechamento de 15 min menos a máxima dos 20 fechamentos anteriores, em
unidades de ATR (preço).

## 7. Qualidade: por dependência, versionada, sem portão de vetor
- `quality_v1` (`features/quality.py`) com orçamentos declarados **como política**, não como TTL
  do Redis (2a da Astra): candle 1 m atrasado mais de 60 s além do fechamento esperado → `degraded`;
  book > 10 s; funding/mark > 120 s; OI > 600 s (dois ciclos de coleta de 5 min); candle em
  formação > 30 s.
- Cada feature herda a pior qualidade **das entradas que declarou** e de mais nenhuma: um
  `funding_change_8h` em warm-up não pode degradar um retorno bom (2c).
- Tape de trades: silêncio não é obsolescência. O que vale é **cobertura** — janela só existe se
  `covers_from <= início` e, quando ela sai vazia, se o coletor provar `covered_until >= fim`
  (§12.3); senão `insufficient_coverage`. Zero trades com cobertura provada é um zero real.
- Motivos: `warmup`, `gap`, `missing_input`, `stale_input`, `zero_divisor`,
  `insufficient_sample`, `insufficient_coverage`, `misaligned`, `after_cut`, `corrupt_input`
  (§14.2). Maturidade de baseline **não** está aqui: é da T2.3 (`docs/plans/M2.md:50`).
- Proveniência por entrada vai no vetor (`ts`, idade, disponibilidade, cobertura, truncamento) e as
  features apontam para ela por nome — é o que permite explicar depois por que algo degradou.

## 8. Mudanças de contrato de `_change_` de derivativos
`open_interest_change_1h/4h` e `funding_change_8h` exigem uma **referência** vinda de
`deriv_history` (o hot state só tem o valor atual). Sem referência dentro da tolerância
(±6/±24/±48 min) a feature é `missing_input`/`warmup` — nunca "variação desde o primeiro valor que
este processo viu", que depois de um restart é um número sobre o processo. OI muda em fração;
funding muda em **diferença absoluta** (a taxa cruza zero).

## 9. Desvios declarados do sketch de `docs/ARCHITECTURE.md` §6
`FeatureCalculator.compute(ctx) -> dict[str, float]` virou
`compute(ctx, state) -> FeatureValue`: (a) `float` não pode ser o tipo de um número persistido e
comparado com limiar (CLAUDE.md), e o resultado carrega qualidade/motivo, então "sem dado" nunca é
zero; (b) o checkpoint do ATR entra explicitamente em vez de ser recalculado por janela. O `state`
é `FeatureState`, serializável, e quem persiste é a T2.5.

## 10. NumPy/polars vs `Decimal`
NumPy faz o trabalho O(n) de janela (contiguidade de minutos sobre `int64`, corte do tape por
`searchsorted`). Preço, quantidade e volume **nunca** viram `float`: toda aritmética roda em
`Decimal` sob `hunter_core.strategies.numeric.CONTEXT` (28 dígitos, ROUND_HALF_EVEN). Polars é
dependência declarada do pacote mas não é usada na v1 — não havia operação colunar que justificasse
o custo; se T2.3 fizer varredura de baselines em lote, entra lá.

## 11. Pendências deixadas explícitas
- `NormalizedTicker.spread_pct` (hunter_core) ainda é ×100; a feature `spread_pct` daqui é fração e
  não usa aquele helper. O acerto é o follow-up T1.1c, fora dos arquivos desta tarefa.
- Liquidações não entram no `MarketContext` v1 (nenhuma feature do brief as usa);
  `LIQUIDATION_CLUSTER` da T2.3 vai precisar acrescentar a fonte com cobertura declarada.
- `deriv_history` é fornecido pelo chamador; T2.5 precisa preenchê-lo a partir das tabelas
  duráveis, ou as três features de mudança ficam indisponíveis (com motivo, o que é correto).
- Equivalência bootstrap/live de `trade_velocity_1m` **não** foi provada (a decisão conjunta a
  exige antes de habilitar velocidade histórica): candles têm `trade_count` por minuto, o tape tem
  eventos; são janelas e semânticas diferentes. Fica como pré-requisito da T2.3.

## 12. Correções após a revisão de diff da Astra (`astra-review-T2.2-diff.md`)
Cinco achados aceitos e corrigidos, cada um com teste que falhou antes:
1. **Checkpoint à frente do corte** (`atr.py::advance_from_context`): reavaliar 12:15 com o estado
   de 12:30 dobrava barras que o mercado não tinha impresso. Agora um checkpoint cujo
   `last_bar_close > as_of` é rejeitado e reancorado com `origin_reason = "cut_rebuild"`; o engine
   passou a usar `advanced.checkpoint` direto (não há mais fallback para o estado antigo).
2. **Estado do ATR virou entrada declarada** (`INPUT_ATR_STATE = "state:atr_15m"`): `atr_14_pct`,
   `momentum_15m`, `momentum_acceleration` e `breakout_strength_20` declaram-na, a proveniência a
   julga **uma vez** (`quality.py::_atr_state`) e `engine._inherit` propaga. Antes, um gap que
   impedia montar barras deixava `momentum_15m` dividir pelo ATR antigo publicando `ok`.
3. **Cobertura do tape de trades**: um trade antigo prova que a lista **começa** cedo, não que o
   coletor continuou conectado. `SourceEntry.covered_until` (só o coletor pode preenchê-lo) passou
   a ser obrigatório para publicar uma janela **vazia**; sem ele, `insufficient_coverage`. Efeito
   declarado: hoje o loader não preenche `covered_until`, então `trade_velocity_1m` nunca publica
   zero — T2.5 preenche isso com a saúde da coleta e o zero legítimo volta.
4. **Candle em formação sem `event_ts`** é recusado no construtor estrito e descartado no builder
   (antes entrava como `degraded/unknown_age`, o que não elimina o vazamento de uma atualização de
   12:00:50 numa avaliação de 12:00:20). `Reason.UNKNOWN_AGE` deixou de existir.
5. **Somas fora do contexto decimal fixo** (`micro.py`: `bid+ask`, `buys+sells`) rodavam sob a
   precisão ambiente. Agora tudo em `localcontext(CONTEXT)`; há teste com `prec = 6` provando que o
   vetor inteiro não muda.
Nice-to-have aceito: `FreshnessPolicy.identity` — um orçamento sobrescrito publica
`quality_v1+<digest>`, nunca `quality_v1`; e `_decimal` no loader recusa `NaN`/`Infinity`.

## 13. Rodada 2 da Astra (`astra-review-T2.2-diff-round2.md`)
Ela ratificou 1, 2, 4 e 5 como fechados e apontou dois caminhos restantes, ambos corrigidos:
- **Cobertura de trades ficou valendo para qualquer janela, não só a vazia.** Um trade às 12:00:55
  depois de uma reconexão não prova que 12:00:00–12:00:50 foi coletado; publicar 1/60 ou
  `buy=1, sell=0` seria um número sobre a reconexão, não sobre o mercado. Agora
  `trades_between` exige `covers_from <= início` **e** `covered_until >= fim`.
  **Consequência declarada e testada** (`test_engine.py::TestTradeCoverageAtVectorLevel`):
  enquanto o loader não tiver a prova do coletor, `trade_velocity_1m`, `buy_pressure_5m` e
  `sell_pressure_5m` saem `insufficient_coverage`. É o estado honesto, não um bug: T2.5 preenche
  `covered_until` a partir da saúde do stream (reconexão sem recuperação reinicia o início do
  intervalo coberto) e as três voltam. `InputProvenance` passou a carregar `covered_until` para
  que a decisão fique gravada na amostra.
- **Book com nível corrompido invalida o snapshot inteiro** (`hotstate.decode_book` →
  `reason="corrupt"`). Descartar só o nível ruim promovia o segundo melhor bid a melhor bid e
  publicava um spread que a exchange nunca cotou.
Ressalva registrada: a Astra prefere que a prova de cobertura descreva um **intervalo contínuo**
(reconexão sem recuperação não avança a cobertura). O tipo já permite isso (`covered_until` é do
coletor); a semântica exata é requisito escrito para a T2.5.

## 14. Revisão cruzada (quant-engineer B) — correções aplicadas
Dois MUST-FIX de comportamento (o terceiro, o catálogo `feature_definitions`, é da T2.1) e seis
nice-to-have baratos, cada um com teste que falhou antes. Nenhuma definição mudou, então
`feature_set_version` continua `a2b12fc…cac51`: o que mudou foi **quando** a feature se recusa a
publicar, não a fórmula. A v1 ainda não gerou nenhuma amostra persistida (T2.2 não commitada), então
apertar a guarda agora mantém "v1" significando uma coisa só — depois do primeiro snapshot gravado,
o mesmo aperto seria versão nova.

1. **`orderbook_imbalance_20` com livro raso** (`micro.py`): 7 bids × 20 asks de qty 1 publicava
   −0,4814… como `ok`. Isso é a razão entre **contagens de níveis** que a corretora mandou, não
   pressão a 20 níveis de profundidade; a chave promete `depth` níveis por lado. Agora
   `len(bids) < depth or len(asks) < depth` → `INSUFFICIENT_SAMPLE` (e não `degraded`: não existe
   número parcialmente certo aqui — o denominador seria outro). **Consequência operacional:** em
   mercados finos a feature fica indisponível com motivo, e é isso que se quer dizer.
2. **Livro cruzado** (`micro.py` + `hotstate.decode_book`): `bid = 101` sobre `ask = 100` publicava
   spread negativo como `ok`. `ask <= bid` (cruzado ou travado) não é um mercado apertado, é um
   snapshot que a corretora nunca cotou. Mesmo princípio do nível corrompido: o snapshot é recusado
   **inteiro** (`reason = "crossed"` no `SourceEntry`), e as calculadoras têm a sua própria defesa —
   `usable_book()` — porque o `MarketContext` também é montado por caminhos que não passam pelo
   decoder (backtest da T2.5, contexto vindo de tabelas duráveis). O motivo novo é
   `Reason.CORRUPT_INPUT`: "não havia book" e "o book que veio não descreve um mercado" são fatos
   diferentes, e colapsá-los em `missing_input` contrariaria a §1 destas notas.
   `orderbook_imbalance` recusa junto — a inconsistência é do snapshot, não de um lado dele.
3. `HotStateRaw.candles_limit` era carregado e nunca lido: `decode_candles(rows, limit)` agora
   devolve `SourceEntry` e marca `truncated` quando `len(rows) >= limit`, `MarketContext` ganhou
   `candles_truncated` e a proveniência de `candles:1m` publica isso. O buffer tem 1500 minutos e a
   janela mais funda pede 1440 — saber que a lista foi cortada é a diferença entre um histórico que
   alcança e um que só parece alcançar.
4. Idade sem `float` (`vector.seconds_between`, usada por `SourceEntry.age_s` e `quality._age`):
   `total_seconds()` é binário e aproxima; a idade decide `degraded` e é gravada na amostra. (A
   aritmética também passou a rodar sob `CONTEXT` — ver §17.1.)
5. `atr_14_pct`, `momentum_15m` e `momentum_acceleration` respondem a mesma coisa sobre o mesmo
   checkpoint (`_atr_pct_of`): sem checkpoint/sem gate → `warmup`; `last_close <= 0` →
   `ZERO_DIVISOR`. Escolhido `zero_divisor` porque `warmup` promete que esperar resolve, e um
   fechamento zero nunca preenche janela nenhuma. Separado disso, `_scale_of`: `atr_14_pct = 0` é
   **leitura legítima** (16 barras sem movimento) e é publicada; quem divide por ela é que recusa.
6. `decode_deriv` preserva `next_funding_time` (a T2.3 precisa: a mesma taxa significa coisas
   diferentes 8 h e 2 min antes da liquidação). É **compromisso**, não observação — fica fora de
   `DerivSnapshot.timestamps()` e por isso é o único campo do hash autorizado a estar no futuro.
7. `build_context` filtra **só candles**, e a documentação passou a dizer isso (era a alternativa ao
   trabalho de filtrar as outras quatro fontes). Motivo: escolher entre candles é *seleção* — a
   lista legitimamente contém o minuto em formação e minutos que fecham depois; um book carimbado
   depois do corte não é seleção, é relógio quebrado, e o caminho de produção (`decode_*`) já o
   transforma em `after_cut` com motivo. Quem chega aqui com uma entrada pós-corte tem bug no
   decoder próprio e levanta. Testado nas duas direções.
8. `default_definitions_rows()` (`engine.py`, reexportada em `features/__init__.py`) devolve as 28
   linhas de `feature_definitions` deste build — colunas exatas da tabela, `inputs` com o
   vocabulário do registry, cópia nova a cada chamada. É a porta única para a T2.1 semear e a T2.5
   fazer upsert; o `id`/`uuid7` é de quem escreve. O golden de
   `DEFAULT_REGISTRY.feature_set_version`
   (`a2b12fcdbd8431a1d5b731191007c1ae9b3e6542e08be176aa8a507b090cac51`) está fixado em teste, com o
   digest recalculado por fora (serialização independente + `sha256sum`).

## 15. Mapa de nomes: `PIPELINE.md` §2 → v1 entregue
A tabela do §2 é anterior à decisão conjunta de `docs/plans/M2.md`; onde as duas divergem, a
decisão conjunta prevalece e o nome gravado é o da direita.

| `PIPELINE.md` §2 | v1 (`hunter_indicators`) | por quê |
|---|---|---|
| `price_return_1m/5m/15m/1h/4h` | `return_1m/5m/15m/1h/4h` (+ `_live` de 1m/5m/15m/1h) | prefixo redundante; `_live` é a regra da §3 destas notas |
| `distance_from_24h_high_pct` / `_low_pct` | `distance_from_24h_high` / `_low` | o valor é fração; `_pct` sugeriria ×100 (a armadilha de `spread_pct`) |
| `buy_sell_pressure_1m/5m` | `buy_pressure_5m`, `sell_pressure_5m` | são duas features (uma por lado agressor), não uma; a janela de 1 min ficou fora da v1 |
| `orderbook_imbalance_5/25` | `orderbook_imbalance_20` | o hot state guarda top-20 (`hot_state.queue_book_set`); 25 não existe e 5 seria outra feature, não um apelido |
| `volatility` (grupo) | `atr_14_pct` | ATR de Wilder ancorado é o que a decisão conjunta pediu |
| `volume_relative` (brief) | `relative_volume_5m/15m/1h` | grafia congelada da decisão conjunta; e §5 destas notas: **não** é a razão de 7 dias |
| `momentum_15m` (ROC) | `momentum_15m` = `return_15m / atr_14_pct` | §6 destas notas: em ATRs, senão seria apelido de `return_15m` |

**Do §2 e fora da v1** (nenhuma foi implementada; nenhuma finge existir): `quote_volume_1h`,
`volatility_5m/1h` (desvio de retornos log), `volatility_ratio` (5m/1h), `rsi_14`, `ema_ratio_9_21`,
`oi_price_divergence`, `liquidation_pressure_1h` (liquidações não estão no `MarketContext` v1 —
§11), `buy_sell_pressure_1m`, `orderbook_imbalance_5`, e o grupo **cross** inteiro
(`btc_correlation_1h`, `market_beta_1h`, `relative_strength_vs_btc_1h`) — o campo `btc` do contexto
existe para elas, mas o brief da T2.2 não as pediu. Entram como features novas (com versão 1
própria), não como alteração das existentes.

## 16. Custo medido pelo revisor — requisito de otimização da T2.5 (não otimizar agora)
Medição da revisão cruzada, registrada como veio: **~50 ms por vetor**, dos quais **53 % em
`windows._epoch_minutes`**, chamado **17× por vetor**, e `bars_15m` recomputado **3× por vetor**.
Com ~200 mercados a 1 vetor/min isso é ~10 s de CPU por minuto — passa hoje, mas é o primeiro teto
que a T2.5 encontra ao subir a cadência ou o universo. **Nada disso foi otimizado nesta rodada, de
propósito:** cache de janela é estado, e estado dentro de uma função hoje pura muda o que significa
"recomputar a amostra gravada" — onde o cache vive (por vetor, por mercado, por processo) é decisão
da T2.5, junto com a persistência do `FeatureState`. Requisitos para quem otimizar: (a) o resultado
tem de continuar byte-idêntico ao atual para o mesmo contexto — o critério de aceite é o teste de
reprodutibilidade, não o benchmark; (b) o cache é por `(mercado, as_of)` e morre com o vetor, ou
vira estado que precisa de invalidação provada; (c) `_epoch_minutes` só existe para achar o rabo
contíguo: o caminho barato é calcular os minutos **uma vez por contexto** (eles não mudam entre
features) e passar o array adiante, não trocar `Decimal` por `float`.

## 17. Segunda opinião da Astra sobre este fix-pass (`astra-review-T2.2-fixes.md`)
Ela ratificou (a) `INSUFFICIENT_SAMPLE` para livro raso, (b) recusar também o `orderbook_imbalance`
no livro cruzado — "uma junção de bid novo com ask antigo combina quantidades de instantes
diferentes" — e (c) manter o construtor estrito. Levantou **dois must-fix, ambos aceitos e
corrigidos**, cada um com teste que falhou antes:

1. **Matar o `float` não bastava.** `seconds_between` somava e dividia sob a precisão ambiente:
   com `prec = 6`, um book de `10,000001 s` virava `10,0000` e voltava para dentro do orçamento de
   10 s — a **qualidade da amostra dependia do contexto decimal do processo** que a calculou. Agora
   a aritmética roda em `localcontext(CONTEXT)`; a função mudou de casa para `vector.py` (junto de
   `InputProvenance.age_s`, que é quem publica a idade) porque `context.py` estourava as 350 linhas.
   Testes: idade imune a `prec = 6` e o veredito de orçamento imune junto (`degraded` continua
   `degraded`).
2. **A corrupção sumia no caminho de produção.** `decode_book` marcava `crossed`, mas a calculadora
   via só `value = None` e publicava `missing_input`, e a proveniência idem: no envelope, um
   snapshot cruzado ficava indistinguível de "o Redis não tinha book" — outage e decode quebrado
   viram o mesmo fato. Agora `quality.source_reason()` traduz o veredito do loader
   (`missing_input`/`empty` → `MISSING_INPUT`, `after_cut` → `AFTER_CUT`, `corrupt`/`crossed` →
   `CORRUPT_INPUT`), `usable_book()` recebe o `SourceEntry` inteiro e `provenance_for` carimba o
   book com esse motivo. Teste integrado: bytes → `load_context` → `compute_features` mantém
   `corrupt_input` na feature **e** na proveniência; e o par negativo (sem book → `missing_input`).
   Quem acrescentar uma recusa nova ao loader acrescenta a tradução aqui.

**Não aceito nesta rodada** (registrado, não silenciado): publicar quantidade de níveis por lado na
proveniência para separar "mercado fino" de "coleta incompleta". Concordo com o objetivo, mas hoje
nenhuma fonte sabe a diferença — o snapshot do market-worker não diz se a corretora mandou 7 níveis
ou se 13 se perderam no transporte; publicar a contagem sem essa prova só moveria a dúvida para
dentro da amostra. É requisito para o **coletor** (T2.5/S2), na mesma linha do `covered_until` dos
trades: quem sabe é quem coleta.

**Requisito que ela deixou para a T2.5** (aceito e registrado aqui porque nasce desta decisão): como
`build_context` não filtra fontes pós-corte, o adaptador durável do backtest **tem de selecionar as
observações até o corte** ao montar cada `MarketContext` — carregar o histórico inteiro e avaliar um
corte anterior levanta, e capturar/ignorar essas exceções enviesaria a amostra (as avaliações que
levantam não são aleatórias).

## 18. T2.2b — desempenho sem mudar um byte (memo por contexto)

Fecha o requisito que a §16 deixou em aberto. Nada de fórmula mudou: o aceite foi **igualdade de
bytes** com a implementação anterior, e o benchmark veio depois.

### 18.1 Onde o memo mora: no próprio `MarketContext`

`MarketContext` ganhou `memo: dict[str, Any]` com `field(compare=False, repr=False, init=False)`,
preenchido no `__post_init__`. É o escopo mais estreito que resolve o problema, e a escolha responde
às três perguntas que a §16 fez a quem otimizasse:

- **vazamento:** não existe dicionário de processo. O memo nasce com o contexto e morre com ele; o
  scanner constrói um contexto novo por tick, então nada atravessa ticks nem mercados. Não há
  política de expulsão para errar;
- **invalidação:** tudo o que o memo guarda é função de `final_candles` e `as_of`, que num
  `frozen=True` sobre uma **tupla** não mudam. `init=False` mantém o campo fora do construtor e fora
  de `dataclasses.replace`, que portanto começa com o memo **vazio** — um contexto recortado nunca lê
  janelas de outro corte;
- **identidade:** `compare=False` tira o campo de `__eq__`/`__hash__`. Ressalva registrada da Astra:
  isso **não** o tira de `asdict()` nem do pickle, então não prometemos identidade dessas
  serializações do contexto — quem serializa é `FeatureVector.canonical_bytes()` e
  `FeatureState.as_wire()`, e esses são exatamente os que o teste compara.

Descartado: cache global com chave `(id(ctx), as_of)`. O CPython recicla `id()` assim que o contexto
anterior é coletado, e um contexto novo poderia colidir com a entrada de um morto — janelas de outro
mercado, sem nenhum sintoma.

**`final_candles` agora é normalizado para tupla no `__post_init__`** (must-fix da Astra na revisão
de desenho): `frozen` protege a ligação, não a lista ligada; um chamador que guardasse a própria
lista poderia dar `append` depois da primeira janela e deixar o memo descrevendo velas que o contexto
não tem mais.

### 18.2 O que é derivado uma vez

`windows.memoize(ctx, chave, fábrica)` guarda:

- `minute_index`: o array `int64` de minutos de epoch de `final_candles` (**read-only**) e o
  comprimento da cauda contígua. Era reconstruído 17× por vetor;
- `bars_15m`: o `BarWindow` das barras de 15 min completas. Era agregado 3× por vetor
  (`atr.advance_from_context`, `quality._atr_state`, `BreakoutStrength.compute`).

`_epoch_minutes` virou `_minutes_of`, com `np.fromiter` sobre divisão inteira de `timedelta` em vez
de `int(total_seconds()) // 60` — mesma resposta para toda vela que o tipo admite (`open_time` é
validado alinhado ao minuto, não há fração de segundo para arredondar) e sem nenhum float segurando
um timestamp.

**As duas caudas são números diferentes** (must-fix da Astra): a cauda contígua de `final_candles`
não é a cauda das velas *usáveis* para barras completas — um buraco dentro do balde ainda aberto
encurta a primeira e não toca nas barras fechadas. `_usable_for_bars` calcula as duas separadamente e
só reaproveita a **aritmética**: as velas usáveis normalmente são um prefixo, e o prefixo é provado
com uma comparação de identidade — `usable[-1] is candles[len(usable) - 1]`. Uma subsequência de
tamanho *m* cujo último elemento está no índice *m-1* só pode ocupar `0..m-1`, porque os *m-1*
elementos anteriores estão em índices estritamente menores e há exatamente essa quantidade de vagas
(a Astra conferiu o argumento). Quando o `close_time` está fora de ordem — possível no tipo — o array
é reconstruído para a subsequência, exatamente como o código antigo sempre fez.

**Fora das janelas, um desperdício por vetor:** `FeatureRegistry.feature_set_version` reconstruía as
28 `FeatureDefinition` e hasheava o JSON canônico delas **a cada vetor**, para uma string que só muda
quando alguém chama `register`. Passou a ser calculada uma vez e invalidada em `register` — que é o
único mutador do registro, e por isso a invalidação é provável em uma linha.

### 18.3 Aceite: os mesmos bytes, provados contra o código antigo

`packages/indicators/tests/reference/windows_v0.py` é a cópia **congelada** do `windows.py`
pré-T2.2b, só de teste, nunca importada pela produção.
`tests/unit/test_engine_identity.py` roda o motor inteiro duas vezes por corte — uma pela produção,
outra com todos os sítios de import (`atr`, `quality`, `trend`, `price`, `volume`, `micro`)
apontados para a referência — e compara `FeatureVector.canonical_bytes()` **e**
`canonical_json(FeatureState.as_wire())`. Detalhes que fazem disso prova e não ritual:

- os dois percursos carregam **estados independentes**, corte a corte, e os cortes andam **para a
  frente** (must-fix 1 da Astra na revisão do diff): a recursão ancorada do ATR só é exercitada quando
  uma barra nova é dobrada num estado que já existia;
- o teste do buffer circular **desliza de fato**: 101 cortes, 1500 minutos por corte, a vela mais
  antiga caindo fora enquanto o mesmo checkpoint continua (must-fix 2). Quatro cópias da mesma fatia
  com estado zerado não exercitavam nada;
- o *patch* é verificado: um espião conta as entradas na referência, e um percurso que nunca entrasse
  no código velho falharia em vez de comparar o novo consigo mesmo;
- há uma varredura de 100 posições de buraco sobre um corte fixo. Ela existe porque a primeira versão
  do teste (20 cortes espalhados) **não pegou** um off-by-one em `_tail_length`: a cauda contígua só
  *decide* algo nas fronteiras (61 minutos, 31, 16, cada múltiplo de 15 na contagem de barras).
  Verificado por mutação: `_tail_length` com -1 quebra 5 casos; um minuto errado em `_minutes_of`
  quebra 107 de 116;
- `test_windows_memo.py` prova as propriedades do memo pela **contagem de derivações** (não por
  tempo, que numa máquina compartilhada é cara ou coroa): uma vez por contexto, zero na segunda
  chamada, duas em dois contextos iguais (não há cache global), memo vazio depois de `replace`,
  tupla preservada quando o chamador esvazia a lista dele.

### 18.4 Medições (máquina do Everton, série sintética de 1500 velas)

| | antes | depois |
|---|---|---|
| custo por vetor, relógio (p50 de 60 contextos novos) | 24,4 ms | **4,5–4,8 ms** (mín. 3,9) |
| custo por vetor, CPU perfilada (cProfile, 10 vetores) | 45,8 ms | 10,5 ms |
| `compute_features` no caminho do scanner (40 mercados, CPU perfilada) | 1,507 s = 37,7 ms/mercado | 0,457 s = **11,4 ms/mercado** |

A linha de base "antes" do scanner é **conservadora**: ela roda com as janelas antigas mas já com o
`feature_set_version` em cache, então o ganho real é um pouco maior que o 3,3× medido. Os 37,7 ms
batem com os "~50 ms por vetor" da §16 medidos noutra máquina.

O que sobrou dentro de `compute_features` é, em ordem: `hunter_core.strategies.aggregate` (~50% —
dobrar até 100 barras de 15 min, fora do escopo desta tarefa e necessário para a identidade de
bytes), as somas de `Decimal` de `relative_volume_1h` sobre 1440 minutos e os extremos de 24 h.

### 18.5 O que **não** foi feito, e por quê

**O caminho incremental "só a cauda" (item 3 do brief) não foi implementado.** Não há por onde
ligá-lo sem o dono do scanner: `scanner.advance` constrói um `MarketContext` novo do zero a cada
tick, o único carregador por mercado que a T2.2 expõe é o `FeatureState`, e ele é **serializado**
(`as_wire`) — pendurar uma janela de barras nele mudaria os bytes que este mesmo aceite proíbe mudar.
Pior: uma chave barata de invalidação sobre 1500 minutos (âncora + contagem + cauda) **não** detecta
um minuto reescrito por backfill do REST, que é exatamente o caso em que o motor mais precisa estar
certo. A versão correta é "o scanner guarda o `MarketContext` e acrescenta o minuto fechado", e é da
T2.5b. O memo desta tarefa já está pendurado no contexto: no dia em que o contexto sobreviver ao
tick, ele passa a pagar mais sem nenhuma mudança aqui.

**`test_load.py` continua `xfail(strict=True)`** — com o motivo reescrito, porque o antigo estava
errado. Duas medições, ambas reproduzíveis por `.claude/state/tmp/bench_scanner.py`:

1. **o gargalo do scanner não é o motor de features, é o decode.**
   `hunter_indicators.features.hotstate.decode_candles` responde por **77–89%** do custo por mercado:
   1500 linhas msgpack revalidadas em `NormalizedCandle` do pydantic a cada tick (2,9 s de CPU
   perfilada em 40 mercados contra 0,457 s de `compute_features`). O orçamento de 3 s por ciclo com
   200 mercados são 15 ms por mercado; o decode sozinho passa disso;
2. **a fixture do teste mede o vazio.** `MultiMarketHotState.seed` grava as velas de `BTCUSDT` sob a
   chave de **todos** os símbolos, e `build_context` descarta as 1500 como estrangeiras: o contexto
   avaliado tem `final_candles = 0` e o motor nunca rodou ali. Por isso a otimização desta tarefa
   move o número do teste em ~1 ms.

Consertar (2) é uma linha na fixture; consertar (1) é o contexto incremental. Ambos são da T2.5b, e o
`xfail` estrito fica de pé para falhar alto no dia em que chegarem.

**Cache de decode foi considerado e recusado nesta tarefa.** Um memo por `(exchange, symbol)` de 1500
velas decodificadas custa ~487 MB para 200 mercados (medido com `tracemalloc`: 1625 B por
`NormalizedCandle`). É a mesma memória que um `MarketContext` incremental custaria — ou seja, é a
**mesma decisão**, e ela é do dono do scanner, não de um cache escondido dentro de um decodificador
que hoje é puro. A Astra concordou em não assumir essa retenção aqui.
