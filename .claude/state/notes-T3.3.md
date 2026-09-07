# Notas da T3.3 — ledger, `PortfolioState` e a metade "abertura" da T3.11

**Autor:** backend-specialist, 2026-09-06. **Para:** Sexta-feira, T3.5, T3.6, T3.11 e T3.12.
**Eu não editei `docs/**`, `infra/migrations/**`, `packages/risk-core/**`, `services/**` nem `apps/**`.**

Consulta prévia à Astra: `.claude/state/astra-review-T3.3-ledger.md` (quatro perguntas: política de
arredondamento, `não_realizado_no_início_do_dia`, N minutos da FX, direção da dependência entre
pacotes). Todas as quatro respostas dela estão implementadas; duas mudaram o que eu ia fazer.

## 1. Políticas declaradas nesta tarefa (novas, versionadas)

| Política | Valor | Onde | Por quê |
|---|---|---|---|
| `rounding_policy` da abertura | `floor_10dp_v1` | `hunter_core/portfolio/attribution.py` | `credited = floor10(origin/rate)` na divisão exata dos coeficientes inteiros; o resíduo é `floor10` do resto, ou `ceil10` quando a fração descartada passa de meio quantum, empate para o floor. **Correção da Astra:** a prova certa é sobre a fração `ε = d − floor10(d)`, não sobre `d` inteiro — com `origin=100000` e `rate=3,5` o resto é `2,5e-10` e só o floor mantém o CHECK `conversion_is_exact` verdadeiro. Erro do resíduo armazenado: `[−5e-11, +5e-11)` BRL, nunca negativo. |
| Validade da FX na abertura | `available_at ≤ 300 s` **e** `observed_at ≤ 600 s`, medidos contra o instante do ato | `FxPolicy` em `hunter_core/portfolio/opening.py` | Dois limites, não um (Astra): sem o segundo, um backfill que chega agora transforma cotação de uma hora atrás em cotação fresca, porque o `available_at` dela é honesto. Também recusa `pair`/`source` diferentes dos declarados, `rate ≤ 0`, `observed_at > available_at` e `available_at > as_of`. |
| Fonte declarada | `binance.spot.ticker`, par `USDTBRL` | `PAPER_FX_POLICY` | **Ponto de acoplamento com a T3.11:** se o coletor gravar outra string em `fx_observations.source`, a abertura recusa. Precisa ser a mesma constante nas duas metades. |
| Moeda operacional | `USDT`; origem `BRL` | `attribution.py` | Diretiva §1 e decisão conjunta item 1. |
| `LEDGER_CONTEXT` | `Context(prec=50, ROUND_HALF_EVEN)` | `attribution.py` | O contexto de 28 dígitos das estratégias arredonda `E·Ft` a partir de uma carteira de sete dígitos, e um produto arredondado quebra a identidade da atribuição. |
| Lane da curva usada pelo ledger | `Timeframe.H1` (`REFERENCE_RESOLUTION`) | `db/repositories/equity.py` | `1m` é podado aos 30 dias; o ponto de abertura de uma carteira permanente e a referência diária têm de continuar legíveis. A cadência intradiária da T3.5 é outra lane e não colide. |
| Caixa | `creditado + vendas − compras − taxas em USDT` | `db/repositories/ledger.py` | Taxa em ativo-base **não** mexe no caixa: reduz as unidades recebidas (problema da posição, T3.4). |
| Realizado do dia | **bruto**, `qty × (saída − entrada)` com sinal da direção, de `trades` | idem | `trades.pnl` não tem convenção fixada por migração; os custos são subtraídos uma vez só, em `daily_costs`. |
| Custos do dia | `fills.fee` em USDT **mais** a taxa cobrada em ativo-base, valorizada pelas marcas do build | idem + §8/A | Slippage já está dentro do preço do fill; somar `trades.slippage_cost` cobraria duas vezes. |
| Risco planejado de posição | `qty × max(0, marca − stop) + notional × exit_cost_rate`; **sem stop = notional + custo de saída** | `hunter_core/portfolio/ledger.py` | Perda planejada desconhecida não é perda planejada zero; e a perda no stop inclui o custo de sair (§8/B). `exit_cost_rate` é parâmetro obrigatório, sem default. |

## 2. `não_realizado_no_início_do_dia` — a pendência do item 5 das notas da T3.2

`PortfolioState.daily_unrealized_pnl` passa a receber a **variação** do não realizado no dia
(`não_realizado_agora − não_realizado_da_referência`), que é o que fecha a identidade do
`daily_decomposition_gap`.

O nível de referência sai de `portfolio_equity_snapshots.unrealized_pnl` do ponto **exatamente** em
`portfolio_risk_state.day_reference_observed_at`, na lane `REFERENCE_RESOLUTION`. **Correção da
Astra:** eu ia usar "o último ponto com `ts <= referência`", e isso prova ordem temporal, não
identidade contábil — o último ponto das 23:59 com não realizado 8 contra uma referência de
meia-noite com não realizado 10 fabrica R$2 de resultado diário num patrimônio que não se moveu.
Sem o ponto vinculado, os **três** campos de relato saem `None` e `daily_decomposition` entra em
`PortfolioStateBuild.unavailable`; nada é preenchido com zero.

**Pedido de schema para a T3.1/T3.6 (não implementado aqui, migração fora do meu escopo):** uma
coluna `unrealized_day_start` em `portfolio_risk_state`, gravada **na mesma transação e sob a mesma
trava** que `equity_day_start`, torna o vínculo uma chave em vez de uma coincidência de timestamp e
elimina a dependência da retenção da curva. Enquanto ela não existir, **a T3.6 tem de gravar o ponto
da curva no mesmo instante de `day_reference_observed_at`** na virada do dia, senão a decomposição
diária fica indisponível todo dia (o USDT e o kill switch continuam corretos — a perda do dia vem do
patrimônio, não desses campos).

## 3. Duas indisponibilidades diferentes, de propósito

- **Referência diária ausente ou de outro dia** → `PortfolioStateBuild.state is None`,
  `unavailable=("daily_reference",)`. Entradas bloqueadas, proteções preservadas
  (`RISK_ENGINE.md` §5); os números em USDT continuam sendo devolvidos, porque a tela e a saída
  precisam deles. `evaluate_exit` não precisa de `PortfolioState` (notas T3.2, item 6).
- **Preço ou decomposição ausente** → o estado **é** construído, com `marks_complete=False` ou com os
  três campos em `None`. O motor rejeita entrada nova por conta própria e a saída continua.

Posição sem preço válido nunca marca a zero: usa a última marca durável (`positions.mark_price`),
senão o preço de entrada, e o mercado entra em `stale_marks`.

## 4. Direção da dependência entre pacotes — decisão registrada

`packages/core/pyproject.toml` passa a declarar `hunter-risk`. Isso fecha um **ciclo de
distribuição** (`hunter-risk` já dependia de `hunter-core`), e foi a opção (a) da Astra: o brief manda
o ledger **montar** o `PortfolioState` do motor, não redefini-lo, e dependência oculta é pior que
ciclo declarado. Ciclo de distribuição não é ciclo de inicialização de módulo: `hunter_risk` só
importa `hunter_core.domain`/`strategies`, que não importam `hunter_core.portfolio`.

`uv sync --all-packages` resolve (saída real no relatório). **Fora do escopo de arquivos da T3.3 em
`docs/plans/M3.md:56`:** `packages/core/pyproject.toml` e `uv.lock` mudaram; a Astra pede que o
orquestrador assuma isso explicitamente. As imagens (`infra/docker/Dockerfile.api-workers`) já
copiam os manifests dos dois pacotes e rodam `uv sync --all-packages --frozen` — nenhum `COPY` novo é
necessário, mas o build precisa do `uv.lock` atualizado junto (`--frozen` não revalida o manifesto).

## 5. Trava e reconstrução

`build_portfolio_state` toma `SELECT ... FOR UPDATE` na linha de `portfolio_risk_state` — a linha de
trava da ordem sistema → organização → portfolio, conforme `packages/core/hunter_core/db/models/
paper_wallet.py`. Trava de linha, nunca advisory de sessão (pooler em modo transação). Teste de
contenção real: um segundo construtor espera o primeiro commit.

Todo o estado sai do banco; não há cache de módulo. Teste: dois `session_factory` distintos produzem
`state.model_dump()` idêntico.

## 6. Sem aporte e sem reset

`open_paper_wallet` é a única função pública do pacote que credita caixa. Além do que o schema já
impede (âncora imutável, `initial_capital` congelado, índice único parcial da principal), há um teste
que lê o **AST do próprio `hunter_core`** e falha se `create_anchor`/`create_wallet` forem chamados
de qualquer módulo que não seja `portfolio/opening.py`, se `initial_capital` aparecer num terceiro
lugar, ou se surgir nome público com `deposit`/`top_up`/`recapitalis`/`reset_wallet`. É verificação
auxiliar, como a decisão conjunta (item 4) exige que se diga: a garantia é o caminho único de escrita
mais o schema.

Segunda abertura no mesmo workspace: `WalletAlreadyOpen`, inclusive com a carteira pausada,
arquivada ou com `deleted_at` preenchido (D7). Corrida perdida no índice único vira o mesmo erro, com
rollback integral.

## 7. Pendências e limites honestos desta entrega

1. **`beta_btc` é parâmetro e, hoje, sempre ausente.** `build_portfolio_state(..., betas=...)` recebe
   um mapa; sem ele toda posição sai com `beta_btc=None`, o agregado de β fica desconhecido e o motor
   rejeita entrada nova (R-OPS-1). É o comportamento correto até a T3.7 entregar `market_betas`, mas
   significa que **nenhuma entrada será aprovada** enquanto o chamador não passar os β.
2. **Custo de saída não entra no risco planejado da posição.** A hipótese de custo da posição não é
   persistida hoje; `planned_risk` é só a distância até o stop. Quem persistir `AssumedCosts` por
   posição (T3.5) deve reabrir isto.
3. **A expiração de reserva não é aplicada aqui.** `held_reservations` filtra só por
   `reservation_state = 'held'`, como o schema manda; a varredura que expira compete pela mesma trava
   e é da T3.12/T3.5.
4. **`record_equity_point` não valida frescura da FX.** Abrir é ato e recusa cotação velha; registrar
   a curva é escrituração de um instante que já aconteceu, e recusar o ponto em USDT por causa do BRL
   perderia justamente o histórico. O ponto guarda a **proveniência** (`fx_observation_id`), não uma
   promessa de recência.
5. **O gate de tamanho de arquivo está vermelho por dois arquivos que não são meus:**
   `packages/core/hunter_core/db/models/execution.py` (359) e
   `packages/exchange-adapters/hunter_exchanges/binance/streams.py` (353). Ambos tinham 329 e 323 no
   HEAD `a88daac` e cresceram em trabalho em voo de outros agentes. Nenhum arquivo meu passa de 321.
6. **`pyright packages/core` está vermelho em `hunter_core/risk/**` e `tests/integration/
   test_schema_paper.py`**, ambos de tarefas em voo (T3.6, T3.1). Zero erro nos meus arquivos.

## 8. Segunda rodada da Astra — revisão do diff (`.claude/state/astra-review-T3.3-diff.md`)

Veredito dela: REQUEST_CHANGES, com quatro MUST-FIX. **Os quatro foram implementados**, com teste
que falhava antes.

| # | Achado | O que mudou |
|---|---|---|
| A | `daily_costs` ignorava taxa cobrada em ativo-base. Cenário: compra bruta de 1 unidade a 100 com taxa de 0,01 unidade — caixa cai 100, a carteira fica com 0,99 valendo 99, o patrimônio perde 1, e realizado/não realizado/custos relatavam zero. | `LedgerRepository.daily_base_asset_fees` devolve a taxa em **unidades da base por mercado**; `_daily_decomposition` valoriza com as mesmas marcas que o build usou e soma em `daily_costs`. Sem preço para a moeda, os três campos vão `None` (indisponível, nunca zero). Testes: `TestTheCostsOfTheDayIncludeFeesPaidInCoins` (gap zero no cenário dela; `None` sem preço). Taxa em ativo-base continua **sem** debitar caixa. |
| B | `planned_risk_quote` promete "perda remanescente incluindo custos" e eu entregava só a distância até o stop. Cenário: 190 de distância + 2 de saída cabiam num teto de 200. | `mark_positions(..., exit_cost_rate)` e `build_portfolio_state(..., exit_cost_rate)` passam a ser **obrigatórios, sem default**: quem monta o estado declara a hipótese de custo de saída (fração do notional). Com stop: `qty·max(0, marca−stop) + notional·taxa`. Sem stop: `notional + notional·taxa`. Testes: `TestTheExitCostIsPartOfThePlannedLoss`. |
| C | Os componentes da decomposição usavam cortes diferentes: não realizado vinha do instante da referência, realizado e custos vinham da meia-noite. Cenário: taxa de 2 às 00:00:00,5 com referência amostrada às 00:00:01 é subtraída duas vezes. | O corte passa a ser **o instante da referência**, para os três, com regra de fronteira **inclusiva** (`ts >= referência`) declarada em código e nas docstrings — é o que a própria referência enxerga, já que ela valoriza a carteira a partir das linhas comitadas antes dela. |
| D | `record_equity_point` convertia qualquer observação recebida. Cenário: o ponto das 15:40 reconstruído com uma cotação que só ficou disponível às 16:30 gravava informação do futuro sem sinalizar nada. | O ponto valida a FX contra o **próprio instante do ponto**, com a mesma `FxPolicy` da abertura (par, fonte, causalidade, as duas idades). Recusada: o ponto em USDT é gravado do mesmo jeito, `fx_observation_id` fica **nulo** (não se nomeia uma observação de onde o número não veio), `brl=None`, `brl_unavailable_reason='fx_rejected'` e `brl_unavailable_detail` com a frase do validador. Testes: `TestTheCurveRefusesAnFxItMayNotUse`. |

Ponto E (nice-to-have) também endereçado: `test_no_funding_route.py` passou a varrer **`packages/`,
`apps/` e `services/`** (não só `hunter_core`), a reconhecer chamada por nome simples além de
atributo, a recusar **alias** de `create_wallet`/`create_anchor`, a pegar atribuição a
`.initial_capital` e a procurar **definições** de funções com nome de aporte/reset em todo o
repositório, com um teste que prova que a varredura realmente alcança `apps/` e `services/` (uma
varredura que não achasse nada passaria em tudo). Continua sendo verificação auxiliar: SQL textual e
módulo não importado seguem fora do alcance de um parser, e a defesa principal continua sendo o
caminho único de escrita mais as triggers.

Discordância registrada: nenhuma. O ponto dela sobre "reconciliação por fill" (aceite da T3.3 em
`docs/plans/M3.md:159`) fica **parcialmente coberto** — caixa, taxas e custo do dia por fill estão
provados; quantidade líquida e realizado parcial por fill dependem do escritor (T3.5) e o contrato
por fill precisa ser fechado com ela. Está no item 7 das pendências.

## 9. Efeito na T3.5 e na T3.12 (assinaturas mudaram nesta rodada)

- `build_portfolio_state(session, *, organization_id, portfolio_id, as_of, marks, exit_cost_rate, betas=None)` — `exit_cost_rate` é **obrigatório**.
- `mark_positions(rows, marks, *, exit_cost_rate)` — idem.
- `record_equity_point(session, *, build, fx, resolution=1h, fx_policy=PAPER_FX_POLICY)` — a FX é validada contra `build.as_of`.
- `to_open_positions` / `to_pending_entries` / `market_identity` vivem em `hunter_core/portfolio/ledger.py` (movidos de `state.py` pelo orçamento de 350 linhas).

## 10. T3.3b — fechamento da revisão adversarial de `8a6a69f` (2026-09-07)

Bloqueante 3, deve-corrigir 5/6/7 e sugestões 12–14/16 corrigidos, cada um com teste que falhava
antes. Detalhe por item no relatório da tarefa; aqui só o que muda a superfície e as dívidas novas.

**Reorganização de arquivo (sem mudança de comportamento, só o orçamento de 350 linhas).**
`opening.py` (376 linhas depois do bloqueante 3) virou dois módulos: `FxPolicy`,
`FxObservationRejected`, `PAPER_FX_POLICY` e `validate_fx_observation` foram para
`hunter_core/portfolio/fx_policy.py`; `opening.py` os reimporta com o idioma `import X as X`
(reexport explícito, para o ruff não acusar F401) — quem importava de `hunter_core.portfolio.opening`
continua funcionando sem mudar uma linha. Pelo mesmo motivo, `ledger.py` (339 linhas depois das
auditorias do item 5) perdeu `MarkedPosition`/`mark_positions`/`_planned_risk` para
`hunter_core/portfolio/marking.py` e `market_identity`/`to_open_positions`/`to_pending_entries` para
`hunter_core/portfolio/positions.py`, com o mesmo reexport. `hunter_core/portfolio/__init__.py` não
mudou.

**Dívida nova para a T3.1c (deve-corrigir 5):** `portfolio_equity_snapshots` não tem coluna para
`brl_unavailable_reason` nem para `stale_marks` — os dois só existiam em memória
(`EquityPoint`/`PortfolioStateBuild`) e uma linha com `fx_observation_id = NULL` era indistinguível
de uma marcação obsoleta ou de uma FX recusada. `record_equity_point` agora grava um `AuditEvent`
(`portfolio.equity_point.brl_unavailable` / `portfolio.equity_point.stale_marks`) e um log
estruturado (`equity_point_brl_unavailable` / `equity_point_stale_marks`) no instante em que nota
cada um, mas isso é auditoria, não a coluna — quem consulta o ponto direto na tabela ainda não vê o
motivo sem juntar `audit_logs`. A T3.1c (ou quem migrar `portfolio_equity_snapshots` a seguir)
precisa decidir a coluna: `brl_unavailable_reason text NULL` (o enum `Literal["no_fx_observation",
"fx_rejected"]` já existe em `hunter_core.portfolio.ledger.BrlUnavailableReason`) e algo equivalente
para os mercados obsoletos do ponto (hoje só `PortfolioStateBuild.stale_marks`, uma tupla de
`market_id`, nunca persistida por linha da curva).

**Assinaturas que mudaram nesta rodada, para quem já as chama:**

- `PortfolioRepository.principal_paper_id()` — perdeu o parâmetro `workspace_id` (deve-corrigir 6:
  o índice é `(organization_id)` desde a T3.1b). Nenhum outro chamador existia além de `opening.py`.
- `open_paper_wallet(..., _testing_capital_override: bool = False)` — parâmetro novo, kwarg-only,
  default `False`; não quebra chamada existente. Com `capital_brl != DEFAULT_CAPITAL_BRL` e sem essa
  flag, a função agora recusa com `ValueError` antes de tocar a sessão (sugestão 14). **A T3.8a
  (`apps/api/tests/integration/test_portfolio_api.py:93`) chama `open_paper_wallet(...,
  capital_brl=CAPITAL_BRL)` com `CAPITAL_BRL = Decimal("100000")` — igual a `DEFAULT_CAPITAL_BRL`,
  então não precisa de nenhum ajuste.** `infra/scripts/open_paper_wallet.py --capital-brl` idem: não
  toquei no script (fora do escopo desta tarefa), e o comportamento novo é o correto por diretiva —
  um operador que passar um valor diferente de R$100.000 agora recebe a recusa com motivo em vez de
  abrir uma carteira fora do número da diretiva; vale registrar se alguém quiser trocar o
  `argparse` por uma constante fixa (removendo `--capital-brl` de vez) numa tarefa futura.
- `validate_fx_observation(..., last_accepted: FxObservation | None = None)` — parâmetro novo,
  kwarg-only, default `None` (desativa a comparação). Não usado ainda por nenhum chamador real
  (`open_paper_wallet`/`record_equity_point` não passam `last_accepted`): a comparação com a última
  observação aceita ficou pronta e testada, mas **quem vai buscar "a última observação aceita" no
  banco é uma dívida em aberto** — não há hoje um repositório que responda essa pergunta, e inventar
  um só para este parâmetro opcional estaria fora do escopo do bloqueante 3 (a review chamou essa
  parte de "opcionalmente").
- `mark_positions` recusa qualquer `PositionRow.direction != "long"` com `NonLongPosition` (sugestão
  13, D1 é spot-only). Nenhum caminho de produção grava posição `short` hoje; se um dia gravar, esse
  raise é o primeiro lugar que vai doer, de propósito.

## 11. Segunda rodada da Astra sobre o diff da T3.3b (`astra-review-T3.3b-ledger-fixes.md`)

REQUEST_CHANGES com dois MUST-FIX (medium), ambos corrigidos com teste que falhava antes:

1. **O teste de corrida original (`asyncio.gather` puro) não garantia exercitar o ramo
   `IntegrityError → WalletAlreadyOpen`.** Se a transação vencedora terminasse antes do `SELECT`
   pré-check da perdedora, esta seria recusada pelo próprio pré-check, e o `except IntegrityError`
   nunca rodaria — o teste passaria do mesmo jeito com esse ramo quebrado. Corrigido com uma barreira
   (`asyncio.Barrier(2)`, via `monkeypatch` em `PortfolioRepository.principal_paper_id`) que só libera
   as duas transações depois que **ambos** os `SELECT`s reais já devolveram "carteira nenhuma", e uma
   asserção nova em `failures[0].__cause__` provando que é mesmo um `IntegrityError` por trás do
   `WalletAlreadyOpen` (não outro motivo). Mais contagens: âncora, estado de risco, ponto da curva e
   auditoria da abertura, todos em exatamente 1.
2. **A auditoria de indisponibilidade não guardava a chave completa do ponto.** A PK de
   `portfolio_equity_snapshots` é `(portfolio_id, resolution, ts)`; o evento só levava
   portfolio+timestamp. Dois pontos na mesma marca (`1m` e `1h`) com destinos diferentes (um recusado,
   outro saudável) ficariam ambíguos. `_audit_unavailability` e os dois payloads de
   `record_equity_point` ganharam `"resolution"`; a recusa de FX também ganhou
   `"rejected_fx_observation_id"` (a observação que falhou, nunca confundida com o
   `fx_observation_id` gravado no ponto, que continua `NULL` numa recusa).

Sugestões (não bloqueantes, todas endereçadas):

- `last_accepted` (comparação de desvio) ganhou causalidade: só compara contra uma observação do
  mesmo par/fonte, observada **estritamente antes** da atual e já **disponível** no instante `as_of`
  — sem isso um replay podia mudar de veredito ao "aprender" sobre uma observação aceita depois.
  Continua sem uso real (nenhum chamador passa `last_accepted` hoje; ver item 9 acima).
- Teste novo provando a auditoria também no ramo `fx_rejected` (o primeiro só cobria
  `no_fx_observation`), com o id da observação recusada conferido.
- O teste do AST sobre `_testing_capital_override` ganhou um segundo teste dedicado a
  `infra/scripts/*.py` (fora dos três diretórios que `_modules()` varre) e a docstring passou a
  declarar os dois limites reais do parser (não pega `**kwargs`, não alcança `infra/scripts` sem essa
  segunda checagem) em vez de prometer "nenhum módulo de produção" sem qualificação.

Concordância registrada com o restante do parecer dela: escopo por organização alinhado ao índice,
recusa de posição não-longa e `LEDGER_CONTEXT` na acumulação de custos, todos corretos sem mudança.
A banda `[1, 100]` continua aceitando um erro de escala 10× (ex. `54,321` no lugar de `5,4321`) — já
reconhecido como proteção parcial no item 3/9 acima, não reaberto como bloqueante por ela.
