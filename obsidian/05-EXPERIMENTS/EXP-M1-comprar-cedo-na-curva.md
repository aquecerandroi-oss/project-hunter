---
tags: [experimento, meme, pumpfun, curva, paper, pre-registro, m4]
updated: 2026-09-12
status: pre-registrado
owner: quant-engineer
exp: EXP-M1
strategy: "meme/pumpfun — conjunto de regras sobre a curva de bonding (carteira paper, sem ordem real)"
version: "gate comprar_cedo_na_curva v1 + saida alvo_2x_trailing_30_tempo_15m v1 (perfil meme_paper_v0)"
result: reprovada
evaluable: 4
days: 1
last_eval: "2026-09-12"
---

# EXP-M1 — comprar cedo na curva e vender em ROI alto

> **Pré-registro escrito na T4.5 em 2026-09-12, ANTES de existir uma única linha de
> `meme_curve_snapshots` e ANTES de qualquer replay.** O protocolo abaixo é congelado: nada nesta
> seção muda depois; avaliações são **acrescentadas** datadas, nunca reescritas (regra
> `exp_reescrita` do `obsidian_lint.py`). Nada aqui é dinheiro real — a carteira é
> `hunter_indicators.meme.paper.PaperCurveWallet`, que não assina transação, não tem chave e não
> conhece RPC. A numeração é a série `EXP-M<n>` declarada em [[03-TRADING/Meme/README|Meme
> (Trading)]], não a sequência `EXP-NNNN` de quatro dígitos do mundo SPOT/perp.

## Hipótese (congelada)

**Comprar cedo na curva de bonding da pump.fun — token com idade entre 30 e 600 segundos e progresso
de curva entre 2 % e 50 % — e vender num múltiplo alto (2× o que foi pago, com trailing de 30 % do
pico, time stop de 15 minutos e piso de perda de 50 %) produz expectância líquida positiva em SOL,
depois da taxa de 1,25 % da curva, da taxa do caminho de execução, do priority fee e do impacto da
própria ordem na curva.**

É a frase do Everton ("comprar cedo na curva e vender em ROI alto") escrita como regra falseável,
com os números do perfil `meme_paper_v0` de `docs/RISK_ENGINE_MEME.md` §3.1 (T4.4). A previsão
registrada abaixo é que ela **não** sobrevive — o experimento existe para medir isso com o dinheiro
de ninguém, não para confirmar a intuição de quem o escreveu.

## Portão de desenho (C1–C8) — congelado, escrito antes do primeiro arquivo

O portão de `_TEMPLATE-EXP.md` foi desenhado para o mundo SPOT/perp com orderbook. Onde um critério
não se aplica à curva, ele **não** é declarado PASS por omissão: fica dito o que o substitui.

| # | Critério | Veredito | Justificativa (obrigatória) |
|---|---|---|---|
| C1 | Plausibilidade da vantagem | **REVISE** | Mecanismo declarado: quem compra depois de nós na mesma curva paga um preço mecanicamente mais alto (a curva é determinística), e o comprador tardio é quem financia a saída. Só que é a mesma tese de todo bot de sniping já presente nessa disputa, com latência e bundle Jito melhores que os nossos ([[KB-0061-pump-and-dump-o-detector-que-precisa-de-25-segundos]]), e [[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]] mede ≥ 17 % de wash trading atômico e 63 % das criações vindas de clusters de criadores: parte do "comprador tardio" pode ser o próprio criador fingindo demanda. O mecanismo existe; a vantagem **nossa** dentro dele não está argumentada |
| C2 | Risco de sobreajuste | **PASS** | Seis condições de entrada (idade mín./máx., progresso mín./máx., criador não vendedor líquido, participação ≤ 1 % do volume orgânico do último minuto) e cinco de saída (2×, trailing 30 %, time stop 900 s, piso de perda 50 %, dump do criador), abaixo do teto de 8 na entrada. Todo limiar tem no máximo 2 algarismos significativos: 30 s, 600 s, 2 %, 50 %, 1 %, 2×, 30 %, 900 s, 50 % — e **nenhum foi escolhido por mim**: vêm do perfil `meme_paper_v0` (T4.4), o que remove o garimpo, não o risco |
| C3 | Adequação da amostra | **REVISE** | ~38 mil criações/dia (`docs/plans/T4-MEME-RADAR.md` §4) é população de sobra, mas o gargalo é **nosso**: as fontes gratuitas de hoje não medem progresso de curva por token nem volume orgânico do último minuto (ver P1), então a amostra *avaliável* pode ser zero por semanas. Estimativa declarada antes de rodar: com o coletor da T4.2 acompanhando N ≤ 300 mints e ~1 entrada elegível por 200 mints observados, 30 dias dariam ~100–800 desfechos; se a régua de progresso ou a de participação ficar cega, dá **0** |
| C4 | Dependência de regime | **REVISE** | A régua de regime do projeto (`market_regimes`, BTC) não descreve este mercado; o estado que importa aqui (fluxo de criação/hora, fração Mayhem, ondas de clones — M-P1..M-P5 em [[Hipoteses-do-plantao]]) ainda não é série medida. A avaliação vai **estratificar por hora UTC e por dia**, que é o que existe, e dizer que o resto não foi controlado |
| C5 | Calibração das saídas | **N/A → substituído** | Não há ATR nem `min/max_stop_distance_pct` do `paper_v1`: uma curva não tem livro onde pôr stop. O par correspondente é o piso de perda de 50 % do custo (uma **venda**, não uma garantia) contra o alvo de 2×. **O risco inicial de R é o valor gasto inteiro** (`docs/RISK_ENGINE_MEME.md` §5: "o resultado plausível de uma compra é −100 %"), então R = ROI líquido: o alvo vale +1,0 R e o piso −0,5 R, o que exige **≥ 33 %** de alvos só para empatar (conta em "Regra de sucesso") |
| C6 | Concentração de risco | **PASS condicionado** | Os tetos são os do perfil `meme_paper_v0` (`docs/RISK_ENGINE_MEME.md` §3.1) e entram no simulador como **parâmetros**, nunca constantes: `MEME_WALLET_MAX_SOL = 2,0`, `MEME_MAX_SOL_PER_TRADE = 0,05`, `MEME_DAILY_LOSS_CAP_SOL = 0,20` (latched), `max_open_positions = 3`, `max_exposure_per_mint_sol = 0,05`. Condicionado porque esses valores são **propostas revisáveis pelo Everton** (§14 daquele documento) — se ele escrever outros, os números desta página mudam de significado e o sucessor é `EXP-M1b` |
| C7 | Realismo de execução | **REJECT para dinheiro real, PASS para papel** | O simulador modela o custo determinístico da curva, a taxa nas duas pontas, o priority fee e o impacto da própria ordem, e preenche sempre contra as reservas do **snapshot seguinte** à intenção (§10.4 da doutrina). O que ele **não** modela: disputa de inclusão/ordenação com bots, bundles Jito, transação falhada, blockhash expirado, MEV e finalidade. Um veredito positivo aqui é condição necessária e longe de suficiente para uma ordem real |
| C8 | Qualidade da invalidação | **REVISE** | As invalidações próprias seriam "o criador despejou" e "o token é rug". A primeira **existe como regra** (`exit_on_creator_dump`), mas depende de `meme_features_1m.creator_sold`, que hoje é nulo sem feed de trades; a segunda **não tem detector** — `rug_suspected` é `None` e a decisão de saída carrega `rug_signal_unknown`/`creator_dump_unknown` em vez de fingir que o risco foi descartado. Enquanto isso, quem invalida é o piso de perda e o time stop — declaradamente genéricos |

**Regras mecânicas:** 6 condições de entrada (< 8 ✓); nenhum limiar com mais de 2 algarismos
significativos ✓; frequência esperada acima de 30/ano por construção ✓; controle pré-declarado
nomeado ✓ (abaixo).

**Veredito do portão:** **`REVISE`** — 2026-09-12, quant-engineer (T4.5). Três critérios pedem
revisão por falta de instrumento, não por desenho: C3 (a amostra depende de features que as fontes
gratuitas não dão), C4 (não há régua de regime para este mercado) e C8 (não há detector de rug). O
experimento **abre assim mesmo**, porque medir a própria cegueira é o primeiro resultado útil — e a
régua de sucesso abaixo é exigente o bastante para que abrir cedo não vire ativar cedo.

## Protocolo (congelado na primeira ativação — nunca editar)

- **Conjunto de regras:** `comprar_cedo_na_curva v1` (entrada) + `alvo_2x_trailing_30_tempo_15m v1`
  (saída), ambos `hunter_indicators.meme.rules`. Mudar qualquer limiar é **versão nova** e
  `EXP-M1b`, nunca edição desta página.
- **code_ref:** `packages/indicators/hunter_indicators/meme/` — `curve.py` (aritmética da curva),
  `paper.py` + `models.py` + `guards.py` + `valuation.py` (carteira paper, recusas e marcação),
  `rules.py` (portas), `replay.py` + `series.py` (o laço e o desfecho). Commit registrado na
  primeira avaliação.
- **Parâmetros de entrada (JSON completo, nada implícito):**
  `{"min_age_s": 30, "max_age_s": 600, "min_progress_pct": 2, "max_progress_pct": 50,
  "max_participation_pct": 1, "require_creator_not_net_seller": true}`.
  *Unidade declarada:* a doutrina escreve `curve_progress_min_pct = 0.02` e
  `max_participation_pct = 0.01` em **fração** apesar do sufixo `_pct`; aqui os mesmos números estão
  em **ponto percentual** (2 e 1). Mesmo valor, unidade dita.
- **Parâmetros de saída:** `{"target_multiple": 2, "trailing_drawdown_pct": 30, "time_stop_s": 900,
  "max_loss_pct": 50, "exit_on_curve_complete": true, "exit_on_migration": true,
  "exit_on_creator_dump": true}`. Os três primeiros e o dump do criador são do perfil
  `meme_paper_v0`; o **piso de perda de 50 %** é parâmetro deste pré-registro (a doutrina não
  fixa um) e existe para que uma posição morta não fique ocupando teto até o time stop.
- **Tamanho e tetos (parâmetros, não constantes):** `size_sol = 0,05` (= `MEME_MAX_SOL_PER_TRADE`,
  que numa curva **é o risco da operação**), `max_balance_sol = 2,0`, `daily_loss_cap_sol = 0,20`
  (latched, retomada só por OWNER), `max_open_positions = 3`, `max_exposure_per_mint_sol = 0,05`,
  `priority_fee_sol` = o observado na sessão, com teto `0,002` **e** 5 % do trade,
  `fill_delay_snapshots = 1`.
- **Custos aplicados (não são hipótese — são tarifa publicada):** `fee_pct = 1,75 %` por ponta =
  **1,25 %** da curva (creator incluído; `pump.fun/docs/fees`, 20/05/2026, reconferido pela Astra em
  12/09) **+ 0,5 %** do caminho PumpPortal Local. A doutrina manda: "o papel nunca simula um caminho
  mais barato do que o live vai usar" (§10.2). Se o caminho final for a construção direta da
  instrução (sem os 0,5 %), este pré-registro terá sido **pessimista** — o lado certo de errar.
  Priority fee em SOL nas duas pontas; impacto da própria ordem pela fórmula da curva. Transação
  falhada, tip Jito, rent de ATA, MEV e taxa de rede base **não** entram — e por isso todo número
  desta página é **teto otimista** do que uma carteira real conseguiria.
- **Preço de entrada e de saída:** a intenção nasce no snapshot `i` e o preenchimento é cotado
  contra as reservas do snapshot `i + 1` (`fill_delay_snapshots`). Se esse snapshot não existir, não
  há operação (`no_fill_snapshot`) ou a posição fica **censurada** (`open_at_series_end`) — nunca
  preenchida ao preço que decidiu.
- **Marcação:** *mark-to-curve* — o que uma venda **inteira** renderia agora, taxas incluídas
  (§6/§10.6 da doutrina). O alvo de 2× é sobre esse valor honesto, não sobre o preço marginal.
- **R em SOL:** risco inicial = **o valor gasto inteiro** (custo da curva + taxas + priority fee),
  porque numa curva não existe distância de stop que a cadeia honre. R = PnL ÷ custo.
- **Timeframe de decisão / de desfecho:** o snapshot do coletor (alvo: 1 min por mint, T4.2), UTC.
- **Coorte:** `paper:<run_id>` — replay sobre snapshots gravados. Uma coorte prospectiva só existe
  quando o `meme-worker` estiver escrevendo continuamente, e será **outra** coorte nesta página.
- **Controle pré-declarado** (`docs/plans/REPLICATION.md` §3.6, adaptado): **mesmos mints, mesmos
  snapshots, mesma geometria de saída, entradas sorteadas em snapshots aleatórios da janela de
  observação, sem a porta de idade/progresso**, na mesma frequência. A vantagem é reportada como Δ
  contra esse controle. Se o Δ não for positivo, a porta não fez trabalho — e a hipótese do Everton
  é sobre a **porta**, não sobre comprar meme coin.
- **Cláusula de identidade:** se o mesmo Δ aparecer cortando o controle por qualquer coisa já
  disponível (hora do dia, fração Mayhem), a porta é redundante e o veredito é `descartar` mesmo com
  expectância positiva.
- **Universo elegível:** todo mint criado na janela de coleta, **sem** filtro de sobrevivência —
  inclusive os que morreram, os que nunca graduaram e os que sumiram da API. Excluir o que morreu é
  a forma mais barata de inventar um retorno.
- **Data de início da coleta:** `‹pendente›` — depende do `meme-worker` (T4.2) gravando
  `meme_curve_snapshots`; até lá esta página fica `result: nao-iniciado`, 0 avaliáveis, 0 dias.

## O que este pré-registro NÃO checa (e a doutrina checa)

A porta da T4.5 tem quatro critérios; a admissão de compra da T4.4 tem 23
(`docs/RISK_ENGINE_MEME.md` §4). Ficam **fora** deste experimento, e portanto os resultados dele são
**mais permissivos** que a carteira real seria: fração bundled (`max_bundled_share_pct`, nulo →
recusa), concentração top-10 por owner, frescura do estado (`max_state_age_s = 5 s`) e skew de
relógio, teto de impacto da própria compra (`max_price_impact_pct`), teto de slippage, tetos de
priority fee/tip, política Mayhem e banimento de mint que rugou. Um Δ positivo aqui **não**
sobrevive automaticamente àquelas recusas — quando `hunter_risk_meme` existir, a coorte tem de ser
recontada com elas ligadas, e isso será `EXP-M1c`.

## Priors contrários, com número, registrados antes

1. **Graduação é rara e não é lucro.** [[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]]: as
   seis medições abertas vão de **0,198 %** (limite inferior, janela efetiva de ~6 min) a **< 2 %**,
   e das que migram a MELT rotula **84,13 %** como alto risco (preço < 0,3 do de referência em
   20 min). Vida mediana de um token: **0,01 dia** (Chen et al.).
2. **O pedágio come vantagem pequena.** [[KB-0086-ic-positivo-nao-paga-o-pedagio-btc-perp-5-min]]:
   460/460 células de custo negativas no perp do BTC a 5 min. Aqui o pedágio de ida e volta é
   **3,44 %** do custo só de taxa proporcional (ver P2) — duas ordens de grandeza acima dos 8 bps do
   mundo SPOT.
3. **Nós não somos o bot mais rápido.** A revisão da Astra (`astra-review-t40-pumpfun.md`) diz com
   todas as letras: "comprar cedo pode significar fornecer saída aos primeiros".
4. **Um teto de participação existe por um motivo.**
   [[KB-0088-o-teto-de-participacao-nos-motores-de-backtest]] — sem ele, um backtest compra volume
   que não existia.
5. **Base rates próprias (T4.0e, vencedor vs rug):** `‹pendente›`. Quando aquela tarefa entregar, os
   números entram numa avaliação datada, **sem** reescrever esta seção.

## Previsões congeladas (escritas antes de qualquer dado)

- **P1 — a cegueira é o primeiro achado.** Com as fontes gratuitas de hoje, **≥ 95 %** das
  avaliações de porta vão recusar por falta de insumo (`progress_unknown`,
  `creator_net_seller_unknown`, `curve_volume_1m_unknown`), não por o token estar fora da janela.
  *Já medido nas 7 criações reais capturadas na T4.1: **7/7** recusadas exatamente assim*
  (`test_meme_replay.py::test_the_real_capture_of_a_launch_cannot_be_traded_and_says_why`).
- **P2 — o pedágio exato.** A marcação honesta imediatamente após a entrada, sem nenhum outro
  negociador, é **−3,4398 %** do custo — `1 − (1 − f)/(1 + f)` com `f = 1,75 %` —, **independente**
  do tamanho e do ponto da curva. (Com a taxa da curva sozinha, `f = 1,25 %`, seriam −2,4691 %.) Se
  a primeira medição real divergir disso, o errado é o modelo de taxa, não o mercado.
- **P3 — acerto necessário contra acerto esperado.** O alvo de 2× com piso de 50 % precisa de
  **≥ 33,3 %** de alvos para empatar (`0,5 / 1,5`). Previsão: a fração medida de entradas que
  alcançam 2× fica entre **10 % e 25 %**, e a expectância líquida por operação cai entre
  **−0,015 e 0,000 SOL** com tamanho de 0,05 SOL — ou seja **−0,30 a 0,00 R**, ponto **−0,10 R**.
  **Veredito previsto: `descartar`.**
- **P4 — a concorrência custa tokens.** Com snapshots de 60 s, a mediana da perda entre o preço que
  decidiu e o preço que preencheu fica **≥ 2 %** dos tokens e o p90 **≥ 10 %**. (No exemplo
  sintético dos testes, com a curva andando entre dois snapshots, foram 12 %.)
- **P5 — a população não fecha.** Em 30 dias de coleta com as fontes gratuitas, o número de
  desfechos avaliáveis fica **abaixo de 100** — o resultado mais provável desta página em outubro é
  **`inconclusivo` por população**, antes de ser `reprovada` por expectância.

## Regra de sucesso (congelada)

`validada` exige **todas**:

1. expectância líquida em SOL por operação **> 0**, com IC 95 % por **blocos de dia** (mesmo
   bootstrap de `.claude/state/exp-drafts/t362b/blocos90.py`, semente **20260912**) **inteiramente
   acima de zero**;
2. **≥ 100** desfechos avaliáveis **e** **≥ 30** dias distintos (a régua editorial do projeto, sem
   desconto por ser mercado novo);
3. expectância positiva em **≥ 2 de 3** janelas de calendário disjuntas;
4. **leave-top-1 %-out**: removido o 1 % de melhores operações (mínimo 1), a expectância continua
   positiva — se o saldo inteiro vier de dois tokens, não é estratégia, é bilhete;
5. Δ contra o controle pré-declarado **positivo** e a cláusula de identidade **não** dispara;
6. **≤ 20 %** dos desfechos censurados (`open_at_series_end`) — acima disso o que está sendo medido
   é a cadência do coletor, não a regra.

Qualquer coisa menos: **`descartar`**, com o conjunto marcado como tal no mesmo dia. E a página
fica — retenção sem seleção por sucesso: um `EXP-M` reprovado é um resultado, não um rascunho a
apagar.

## Regras de morte (o experimento para antes de terminar)

- **K1** — `progress_unknown` em > 50 % das avaliações de porta: estamos medindo a nossa cegueira,
  não a hipótese. Parar, consertar o insumo (T4.2), reabrir como `EXP-M1b`.
- **K2** — > 30 % de censura: a cadência de snapshot é o limite do instrumento.
- **K3** — qualquer entrada preenchida sem um snapshot posterior à intenção: bug de look-ahead,
  invalida a coorte inteira (hoje impossível por construção — a carteira recusa
  `fill_not_after_intent` e `fill_delay_snapshots = 0` nem é representável).
- **K4** — expectância positiva vinda de < 3 mints distintos.

## Avaliações (acrescentadas, nunca reescritas)

*Nenhuma.* A página nasce em 2026-09-12 com `result: nao-iniciado`, `evaluable: 0`, `days: 0` — não
há uma única linha de `meme_curve_snapshots` no banco nesta data e nenhuma regra desta página foi
executada sobre dado real. O que já existe é o instrumento (T4.5) e os testes que o provam, com as
fixtures reais da T4.1 como entrada de fumaça.

### Avaliação 2026-09-12 (T4.16, 15:xx BRT) — veredito `descartar`, conjunto `meme_paper_v0/1` aposentado

**Coorte:** prospectiva na VPS, 12/09/2026 (o primeiro e único dia; `infra/scripts/sql/research/2026-09-12-t416-caso-das-21-apostas.sql`,
lido pelo orquestrador às 14:0x BRT e cruzado no [[03-TRADING/Meme/Estudo-2026-09-12-21-apostas|estudo das 21 apostas]]).
**Números:** 9 apostas fechadas de `meme_paper_v0/1`, **9 negativas**, expectância −0,85 R/aposta —
**das quais 5 são artefato** (`rug_no_snapshot` a −1 R sem a moeda ter morrido: sem fotografia por 3 min antes
das 12:14 BRT, mcap 30 min depois = mcap da entrada). Sem o artefato: 4 apostas, todas negativas, ≈ −0,17 R/aposta
(a taxa). A `0030` reclassifica os artefatos como `indeterminate` (script auditado), então o placar honesto desta
página é **4 medidas, 0 acertos, 5 indeterminadas**.
**Contra a régua:** 1 dia (< 30), 4 medidas (< 100), expectância < 0 — `inconclusivo` por população e
`descartar` por desenho: em 17 de 21 apostas do dia a moeda nunca subiu depois da entrada; a porta comprava
moedas paradas no valor inicial (~28 SOL) com 1–7 holders, 99–289 s depois de nascerem, sem nenhum critério de
demanda (P3 previa −0,10 R; o medido, mesmo sem o artefato, é pior). **P1 confirmada** (cegueira primeiro:
`creator_net_seller_unknown`/`curve_volume_1m_unknown` dominaram as recusas até a fita da T4.2c). **P2** (−3,44 %
na marcação imediata) confirmada nas entradas. **P5** (< 100 em 30 dias) — não chegou a 30 dias.
**Decisão:** `descartar`; `meme_paper_v0/1` **aposentado por script auditado** (`infra/scripts/meme_rule_set.py
--deprecate meme_paper_v0/1 --reason … --apply`, `system_events`), não pela migração. A sucessora é a porta de
fluxo e holders — [[EXP-M5-fluxo-e-holders]] (`flow_v2/1`, relógio de 15 s) — com as exclusões de pedigree
([[EXP-M6-exclusoes-de-pedigree]]) na frente. A página fica; a hipótese "comprar cedo na curva e vender em ROI
alto" **sem critério de demanda** está falseada dentro do que um dia permite dizer.

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| — | — | — | — |

## Relacionadas

[[Experiments Index]] · [[03-TRADING/Meme/README|Meme (Trading)]] · [[02-MARKET/Meme/2026-09-12]] ·
[[Hipoteses-do-plantao]] · [[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]] ·
[[KB-0086-ic-positivo-nao-paga-o-pedagio-btc-perp-5-min]] ·
[[KB-0061-pump-and-dump-o-detector-que-precisa-de-25-segundos]] ·
[[KB-0088-o-teto-de-participacao-nos-motores-de-backtest]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] ·
[[KB-0064-a-cauda-de-queda-e-o-que-o-risk-engine-vai-precisar]] ·
[[06-DECISIONS/2026-09-12-meta-7m-e-lab-meme]] · [[Risk Engine]]

## Fontes

`packages/indicators/hunter_indicators/meme/` (curve, paper, models, guards, valuation, rules,
series, replay) · `packages/indicators/tests/unit/test_meme_curve.py`, `test_meme_paper.py`,
`test_meme_rules.py`, `test_meme_replay.py` ·
`packages/exchange-adapters/tests/fixtures/pumpfun/` (captura ao vivo de 2026-09-12, T4.1) ·
`docs/RISK_ENGINE_MEME.md` §3.1 (perfil `meme_paper_v0`), §4 (checks que ficam fora), §5 (o risco é
o valor inteiro), §6 (marca honesta), §10 (o simulador de papel) ·
`docs/plans/T4-MEME-RADAR.md` §3–§5 · `.claude/state/astra-review-t40-pumpfun.md` (taxa de 1,25 %,
`Δ` de custo, critério de graduação) · `.claude/state/notes-T4.0.md`, `.claude/state/notes-T4.1.md` ·
`.claude/state/exp-drafts/t362b/blocos90.py` (IC por blocos de dia).
