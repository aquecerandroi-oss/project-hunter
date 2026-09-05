# Notas de desenho — S1 (`hunter_core.strategies`)

Decisões tomadas ao implementar o brief `.claude/state/brief-S1-strategies.md`, com a segunda
opinião da Astra (`.claude/state/astra-review-S1-strategies.md`). Nada aqui contradiz a
"Decisão conjunta" de `docs/plans/SHADOW-LAB.md`; onde o plano era omisso, a escolha está
registrada com o motivo.

## 1. `evaluate` + `explain` (motivo sem quebrar o contrato)
`Strategy.evaluate(ctx, params) -> Decision | None` é o contrato do brief e da arquitetura §6.
O motivo de "não houve sinal" **não** vai para `supporting_features` (o envelope só existe
quando há sinal) e sim para o log de avaliação do worker, via `explain(ctx, params) ->
Evaluation`. `evaluate` é literalmente `self.explain(...).decision`, então não há dois caminhos
de cálculo; o worker deve chamar `explain` uma vez.

## 2. `EvaluationState` (must-fix 5 da Astra)
`Evaluation.state ∈ {triggered, not_triggered, rejected, unavailable, ineligible}`.
Motivo: o item 4 da decisão só rearma um mercado depois de uma barra em que a condição foi
**comprovadamente falsa**. `decision is None` não distingue "condição falsa" de "não consegui
avaliar" (gap/warm-up/mercado inelegível) nem de "condição verdadeira, decisão recusada"
(geometria). Só `not_triggered` comprova condição falsa; a transição de rearme em si é a máquina de estados do worker. O enum vive em `strategies/base.py` porque
`domain/enums.py` é da S0; se a S0 quiser promovê-lo ao enum global, é um movimento mecânico.

## 3. ATR: origem e extensão declaradas (`rolling_window_v1`)
`wilder_atr` **reseeda** na primeira barra da janela que recebe. Não é o estado incremental
contínuo que a T2.2 do M2 vai manter em checkpoint (`.claude/state/dialogue-M2.md`, rodada 4 §2:
"inicialização com origem reproduzível ou checkpoint persistido, sem reseed a cada janela
móvel"). Como a S1 é função pura, sem checkpoint, a política é outra e está **declarada**:

- `atr_bars` é parâmetro congelado (97 barras de 15 min nas duas estratégias);
- a leitura carrega `method="wilder_v1"`, `origin="rolling_window_v1"`, `seed`, `seed_anchor`,
  `window_start`, `window_end` e `bars_used`, tudo persistido no envelope;
- 97 barras ⇒ 82 atualizações de Wilder depois da seed; o peso residual da seed é
  (13/14)^82 ≈ 0,2%. Isso **limita**, mas não anula, a influência da origem arbitrária: perto de
  um limiar (por exemplo a borda de 5% do ATR%) uma diferença pequena ainda pode mudar a
  decisão. Por isso a origem e a extensão são parâmetro congelado e evidência persistida, não
  detalhe de implementação (ressalva da Astra na revisão do diff, aceita);
- é isso que faz bootstrap == execução contínua por construção (teste
  `test_momentum_bootstrap_equals_continuous_execution`).

**Divergência registrada:** o número da S1 e o número que a T2.2 vier a produzir com checkpoint
contínuo podem diferir. São calculadoras diferentes com nomes diferentes; nenhuma alega ser a
outra. Se o M2 quiser unificar, é uma versão nova de estratégia (item 1 da decisão).

Gate adotado da rodada 4 do diálogo M2: são necessárias `period + 2` barras — a seed (14 TRs)
**não** é servida como ATR corrente; a leitura só é liberada depois de uma suavização.

## 4. Duas janelas, dois fechamentos (must-fix 2 da Astra)
`source_bar_close` é o fechamento da barra de referência da estratégia (5 min ou 15 min).
O ATR de 15 min usa `atr_bar_close = align_open_time(source_bar_close, 15m)`: às 12:05 o ATR
termina em 12:00. Arredondar para cima seria look-ahead; passar 12:05 direto ao agregador de
15 min tornaria duas de cada três avaliações indisponíveis. `atr_pct` usa o último fechamento
**de 15 min** (denominador de `docs/plans/M2.md` T2.2), não o fechamento de 5 min.

## 5. Geometria
`stop < reference_price < target1` é invariante do tipo `Decision`. A estratégia valida antes
de construir e devolve `Evaluation(state=rejected, reason="geometry")` — nunca captura
`ValidationError` (isso esconderia erro de timestamp ou de envelope). Com ATR > 0 e as condições
de entrada satisfeitas a geometria sempre vale nas duas estratégias (no volume, `close > (high+
low)/2` já implica `low < close`), então o ramo só é alcançável por parâmetro; os testes o
exercitam com `target_atr = 0` e o guarda permanece porque a entrada revalida os níveis contra
`P_entry` (item 3 da decisão).

## 6. Invalidações
Não usamos "fechamento abaixo do stop" (seria implicado pelo próprio stop na maioria dos casos).
- `momentum_v1`: fechamento de 15 min abaixo do nível de rompimento (máxima dos 20 fechamentos
  anteriores);
- `volume_anomaly_v1`: fechamento de 5 min abaixo do meio da barra de sinal.
São as condições que definiram o setup. Ressalva da Astra aceita: em sinais com rompimento
muito abaixo do stop a invalidação pode ficar redundante — não afirmamos independência do stop
em todos os casos.

## 7. `confidence` não calibrada
`confidence = base_confidence` (0,5) e `confidence_method = "constant_uncalibrated_v1"` no
envelope. Não existe calibração nenhuma; inventar fórmula sobre rvol seria número sem evidência.
Quem mede é o Lab. Uma confidence calibrada é um novo `confidence_method` e uma nova versão.

## 8. `parameters_schema` descreve as duas representações
Os números aparecem tipados (`Decimal`/`int`) em memória e como **string normalizada** na forma
canônica (`params_format = 1`) que vai para o JSONB. Por isso cada parâmetro é
`{"type": ["string","number"|"integer"], "pattern": ...}`. Limitação declarada: o schema
restringe forma e presença, **não faixas** (`minimum`/`maximum` não se aplicam à string). No v0
só rodam os `default_parameters`; validar override de operador é trabalho do M4. O contrato
`tipado → JSONB → tipado → mesmo params_hash e mesma decisão` está testado
(`test_the_jsonb_round_trip_keeps_the_hash_and_the_decision`).

## 9. Precisão
Todo cálculo roda em `localcontext(CONTEXT)` (`strategies/numeric.py`, prec 28,
ROUND_HALF_EVEN) — somas e multiplicações também, não só divisões. Teste:
`test_a_decimal_of_the_ambient_context_cannot_move_the_numbers`.

## 10. Identidade do mercado no contexto (must-fix 4 da Astra)
`StrategyContext` carrega `exchange`/`symbol` e valida cada vela, funding e OI contra eles, além
de exigir vela de exatamente um minuto. Cenário evitado: uma consulta que misturasse dois
símbolos passaria em "crescente e sem lacuna" e agregaria dois ativos na mesma barra.

## 11. Achado da revisão de diff (Astra) — corrigido
`_ratio()` (formatação do texto do `reason`) chamava `quantize` **fora** de
`localcontext(CONTEXT)` nas duas estratégias. A Astra reproduziu: com `ROUND_UP`/`ROUND_DOWN` no
contexto ambiente o texto mudava (2.00x vs 2.01x) e com `prec = 2` a avaliação levantava
`InvalidOperation` **depois** de todas as condições terem passado — ou seja, um sinal válido
virava exceção. Corrigido e coberto por
`test_no_arithmetic_escapes_the_declared_context` (parametrizado em prec 2/6/28 ×
ROUND_DOWN/UP/HALF_EVEN, com o contexto montado antes de alterar o ambiente). Verifiquei que o
teste falha com o código antigo (5 falhas, incluindo o `InvalidOperation`) e passa com o novo.

## 12. Pendências para quem vier depois
- **S0 / `canonical.py`:** `_number_string` ainda aceita `float` (via `repr`). Nenhum caminho da
  S1 produz float (`param_decimal` recusa), mas um chamador futuro poderia gravar um parâmetro
  vindo de float sem perceber. Sugestão à S0: recusar `float` explicitamente.
- **S2:** `decision_at`, `cohort`, `params_hash` e a idempotência (`uuid5`) são do worker; o
  envelope é escrito uma vez e nunca reescrito. `Evaluation.state` é o que decide rearme.
- **`code_ref`** da versão congelada precisa cobrir `hunter_core/strategies/**` inteiro
  (estratégias **e** calculadoras), como diz o item 1 da decisão conjunta.
- **Proveniência (S2):** o corte em `source_bar_close` controla *tempo de mercado*, não
  disponibilidade. Uma vela antiga que chegue por backfill **depois** da decisão passa pelo
  filtro (não olhamos `received_at`). Reproduzir fielmente uma decisão passada exige que a S2
  registre o que estava disponível em `decision_at` — o envelope carrega `observation_ts`, não a
  proveniência.
- **Retenção (S2):** o envelope permite conferir as condições e os níveis, mas recomputar os TRs
  exige as barras da janela declarada. Manter as velas de 1 min enquanto o sinal importar é
  obrigação de persistência (item 8 da decisão), não da função pura.
- **Escala do banco (S2):** `Decimal` de 28 dígitos aqui vs `NUMERIC(28,10)` no banco — exigir
  round-trip real dos níveis (`stop`/`target1`) e comparar o nível usado após restart.
