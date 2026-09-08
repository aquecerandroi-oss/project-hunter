# notes-T3.7b — o produtor horário de β e a profundidade de histórico que ele exige

Data: 2026-09-08. Autor: quant-engineer. Base: `main` em `e26a4ee`. **Nada commitado.**
Escopo: `services/scanner-worker/**`, `infra/scripts/request_backfill.py`, uma extração pura em
`packages/indicators/hunter_indicators/beta/returns.py`, docs. **Nada em
`services/market-worker/**`, `infra/docker/**`, `infra/vps/**`, `apps/**`, `.env*`.**

## 1. O problema, em uma frase

A T3.7 (`da2fb49`) entregou o estimador `beta_v1` e o esquema `market_betas` (`0006`) e **o job
nunca foi escrito**. Com a tabela vazia a admissão responde `unavailable` para todo candidato
("sem β validado só shadow", diretiva §4) e a carteira paper não abre nada. β existir é
pré-condição; nada aqui aciona operação.

## 2. Arquivos

| Arquivo | Linhas | O quê |
|---|---:|---|
| `services/scanner-worker/hunter_scanner_worker/beta_repo.py` | 99 | as barras agregadas **em SQL** (`date_bin` da época, `is_final`, `open_time < window_end`, barra completa) |
| `services/scanner-worker/hunter_scanner_worker/beta_writer.py` | 166 | uma revisão imutável: reconhece retentativa → aposenta a vigente → insere; `input_digest` |
| `services/scanner-worker/hunter_scanner_worker/beta_job.py` | 251 | uma passada: corte, referência uma vez, estimativa e escrita por mercado, métricas, `BetaHealth` |
| `services/scanner-worker/hunter_scanner_worker/beta.py` | 163 | cadência horária + trava por corte + `python -m hunter_scanner_worker.beta --once` |
| `services/scanner-worker/hunter_scanner_worker/{main,health,metrics}.py` | +~40 | task no TaskGroup, `beta_last_run`/`beta_valid` no heartbeat, status detail, 2 métricas |
| `packages/indicators/hunter_indicators/beta/returns.py` | 149 | **extração pura** de `returns_from_closes` (sem mudança de valor) |
| `infra/scripts/request_backfill.py` | 334 | pedidos de 7 dias, do mais novo para o mais antigo, pela outbox |
| `services/scanner-worker/tests/test_beta_job.py` | 377 | 8 testes com testcontainers |
| `infra/scripts/tests/test_request_backfill.py` | 119 | 4 testes puros da aritmética de janela |

## 3. Decisões, com o motivo

### 3.1 `as_of` é a **barra fechada**, não o relógio

`as_of = floor_bar(now)`: rodar às 12:37 mede a janela que terminou às 12:00. Consequência que é o
ponto todo: uma reexecução dentro da mesma hora é o **mesmo corte**, então a idempotência que o
brief pede (`(market_id, window_end, estimator)`) sai da chave do banco
(`uq_market_betas_revision = (market_id, as_of, beta_version, input_digest)`) e não da disciplina
de quem chama. O relógio de parede fica em `computed_at`/`available_at`, escritos pelo chamador e
não por `now()` do servidor — duas linhas da mesma passada não têm por que discordar em
milissegundos.

`estimator` não entra na chave do banco porque **não é livre**: `definition` é a referência e
`ols_with_intercept` é todo o resto, decidido pelo `market_id`. A tripla do brief e a quádrupla do
esquema selecionam a mesma linha.

### 3.2 As barras são agregadas em SQL, e o contrato numérico continua tendo **uma** implementação

Trinta dias de um mercado são 43 200 velas de 1 min; a passada cobre 200 mercados por hora. Trazer
8,6 M de linhas para o Python de hora em hora não é opção, então `beta_repo.bar_closes` dobra os
sessenta minutos de cada barra no servidor.

Isso obrigaria a reescrever `hourly_closes` como consulta **e** a reescrever a aritmética de
retorno — que é congelada. Em vez de duas grafias do mesmo contrato, extraí
`returns_from_closes(closes, as_of, spec)` de `hourly_returns` em `packages/indicators`:
`hourly_returns` passou a ser `returns_from_closes(hourly_closes(...))`, byte a byte a mesma
função. **É uma refatoração sem mudança de valor, não uma versão nova** — `BETA_METHOD_VERSION`
continua `beta_v1` — e a prova é a suíte congelada da T3.7 rodando inteira sem alteração (874
testes de `packages/indicators`). A cláusula "versão velha nunca é editada" vale para a fórmula; a
fórmula não mudou, mudou onde ela mora.

A consulta reafirma o contrato de `hourly_closes` cláusula por cláusula: `is_final`,
`open_time < window_end` (nunca `<= now`), `count(*) = 60` **e** último minuto exatamente em
`bucket + 59 min`, `date_bin` a partir da época (o mesmo que `floor_bar`). A segunda metade do
teste de completude é redundante enquanto `(market_id, timeframe, open_time)` for a PK, e está
escrita mesmo assim: é barato e não depende de alguém não mexer numa constraint.

### 3.3 Anti-look-ahead, provado contra Postgres

`test_a_minute_that_is_not_final_does_not_complete_its_bar`: os mesmos sessenta minutos com o
último `is_final = false` produzem `gaps` e nenhum coeficiente; um `UPDATE ... SET is_final = true`
naquele minuto — exatamente o que o coletor faz quando o minuto fecha — faz a hora existir, e a
recomputação do **mesmo corte** aposenta a revisão que ela corrige em vez de editá-la.
`test_the_hour_that_has_not_closed_is_never_measured` semeia a barra que começa no corte
**completa e final** (forma que o coletor não produz) e mostra que ela não entra.

### 3.4 Retentativa vs recomputação: reconhece **primeiro**

`write_revision` faz, na mesma transação: (1) existe alguma linha com este `input_digest` neste
corte? então é retentativa, escreve nada; (2) senão, `SELECT ... FOR UPDATE` da vigente e
`superseded_at = now`; (3) insere. A ordem importa: aposentar antes de descobrir que não há nada
para inserir deixaria o mercado **sem revisão vigente** naquele corte.

`input_digest = params_hash({reference_market_id, **estimate.as_wire()})` — a serialização canônica
já cobre coeficientes, janela, `n`, `contiguous_bars`, `last_pair_end`, validade, motivo e
parâmetros; o id da referência entra porque o `as_wire` a nomeia por **símbolo**, e símbolo não é
identidade. Hashear só os coeficientes faria uma reexecução corrigida por backfill parecer idêntica
à execução que ela corrige (§18.6 da DATABASE.md diz isso explicitamente).

**Limite declarado:** um digest que já existiu naquele corte conta como retentativa mesmo se tiver
sido aposentado, porque ressuscitar revisão aposentada é justamente o que o trigger recusa. Chegar
lá exige uma recomputação voltar a um resultado byte a byte anterior — velas persistidas que
sumiram. A cura honesta é o corte seguinte, uma hora depois, não uma edição.

### 3.5 Uma transação **por mercado**

Os modos de falha são por mercado: coeficiente largo demais para `NUMERIC(18,8)` (que o carregador
deve recusar, não truncar) ou um segundo produtor correndo com o índice de vigência. Isso custa a
hora **daquele** mercado (`outcome="failed"`, log com traceback), não a dos outros 199. Custo: ~3
round-trips por mercado por hora; medido em 13,1 s para 200 mercados no stack local.

### 3.6 Mercado sem referência não vira linha

`reference_market_id` é `NOT NULL`. β contra nada não é representável, e auto-referenciar faria o
mercado parecer um segundo BTC. A passada conta `outcome="no_reference"`, zera
`hunter_beta_valid_markets` e não escreve. É o **único** caso em que o silêncio é honesto — toda
outra recusa é representável e fica gravada com motivo.

### 3.7 Vocabulário de invalidade: o congelado, não o do brief

O brief cita `insufficient_contiguity` e `no_reference`. O vocabulário **congelado** da T3.7 §3 é
`btc_missing` | `insufficient_history` | `gaps` | `degenerate_variance`, e é o que as linhas usam —
renomear motivo é mudar contrato de consumidor por conveniência de redação. O mapeamento:
"contiguidade insuficiente" é `gaps` (alcança 480 barras mas a corrida quebrou ou não chega ao
corte) ou `insufficient_history` (nem alcança — warm-up, espera em vez de backfill); "sem
referência" é `btc_missing` quando o mercado de referência existe mas não tem série, e o
`outcome="no_reference"` da métrica quando o mercado de referência não está no universo.

### 3.8 Trava: um produtor por exchange **por corte**

`beta:producer:{exchange}:{corte}`, `SET NX EX 7200`, sem release. Uma trava liberada no fim da
passada deixaria uma segunda instância refazer a mesma hora na hora seguinte (200 mercados de
agregação de 30 dias para não escrever nada); uma trava sem o corte no nome precisaria ser renovada
por um processo ocupado. **Correção nunca depende dela** — a chave única faz de uma passada
duplicada um no-op —, é economia de banco. Custo declarado: líder que morre no meio pula aquela
hora; pular é seguro (a revisão vale uma hora e a admissão recusa vencida) e aparece como
`beta_last_run` envelhecendo.

Não usei `MARKET_SHARD`: é o knob do coletor, e o scanner não é fatiado. A trava dá a exclusão que
o "shard 0 only" do brief pedia sem inventar topologia para o scanner.

### 3.9 Prontidão: **degradado, não fora**

β é *status detail* (`WorkerRuntime.status_details["beta"]` → `"ok (12/200 valid, 0.3h ago)"` /
`"stale (...)"` / `"never ran"`), nunca readiness check. `STALE_AFTER = 2 h` = uma hora perdida mais
a retentativa: às duas horas toda revisão da tabela já venceu e a admissão já está recusando por
frescor. Isso o operador tem de ver; e não significa nada para o Radar, as baselines ou o regime,
que é tudo o que o `/ready` do scanner protege. Mesmo padrão do `rest_gate` (§1 item 7 do PIPELINE)
e do `fx` (§1c item 5).

### 3.10 O script de backfill respeita o teto de 7 dias **antes** de mandar

`backfill_plan.MAX_REQUEST_MINUTES` é 10 080 e uma janela maior é **truncada para os sete dias mais
recentes**, dizendo isso só no log do coletor. Pedir 31 dias numa mensagem entregaria um quarto do
pedido parecendo ter funcionado. Então a faixa vira janelas inteiras de 7 dias publicadas **da mais
nova para a mais antiga** (a ponta recente é a que a contiguidade precisa), a identidade é a janela
(`event_id_for(stream, market_id, gap_start, gap_end)` — a mesma chamada do scanner, provada por
teste), e a ponta recente é cortada em 2 min (`DETECTION_GRACE`) para o pedido não ficar
eternamente parcial. O número 10 080 está **duplicado**, não importado: `infra/scripts` não depende
do pacote do market-worker e esse número é contrato publicado (PIPELINE §1b item 4), não detalhe de
implementação. Se divergirem, o coletor ainda trunca com segurança — só faz isso no log dele.

## 4. Prova no stack local (2026-09-08, compose de pé há 25 h)

Rodado **de dentro do container `docker-api-1`** com os módulos novos copiados (`docker cp`) para os
mesmos caminhos da imagem — o compose não monta o fonte e reconstruir imagem é `infra/docker/**`,
fora do meu escopo.

1. `request_backfill.py --days 31 --markets BTCUSDT,ETHUSDT,SOLUSDT --dry-run` → 15 janelas
   (5 por mercado, 4×10 080 min + 1×4 380 min), nenhuma partição faltando.
2. Execução real → 15 linhas na outbox, publicadas em < 1 s (0 pendentes).
3. Coletor: `market_backfill_planned outcome=accepted`, `requested_minutes=10080`,
   `chunks=42`, **sem truncamento**; a janela mais nova saiu `empty` (aqueles minutos já estão
   persistidos — subtração correta do que já existe). Total: 131 + 131 + 144 = **406 linhas novas
   em `ingestion_gaps`**, todas `open`.
4. `python -m hunter_scanner_worker.beta --once` → 200 mercados, 13,1 s, `{'invalid': 199,
   'valid': 1}`, `reference_bars=226`.
5. Reexecução → `{'unchanged': 200}`, 200 linhas na tabela, 0 aposentadas.
6. `market_betas`: BTCUSDT `definition` β=1 válido; os outros 199 `insufficient_history` com
   `beta`/`alpha`/`r_squared` **nulos** e 225 barras contíguas contra as 480 exigidas.

**O que a prova local não mostra e por quê:** nenhum mercado tem 20 dias contíguos ainda, então
não há β válido medido no stack. O estrato histórico do coletor drena 6 pedaços de 240 min por
ciclo de 60 s, compartilhado com o universo inteiro: 757 lacunas históricas abertas na fila (406
minhas), ordenadas por `gap_end DESC` **globalmente** — as minhas, que terminam em 2026-08-29, ficam
atrás das lacunas mais recentes de outros ~180 mercados. Em 11 min de observação, 3 dos meus 393
pedaços antigos foram recuperados. O caminho "β válido" é provado pela suíte com testcontainers
(`test_a_valid_revision_carries_the_numbers_the_estimator_produces`, β = 2,00000000 exato).

## 5. Como os testes fixam números conhecidos

A spec dos testes é **comprimida de propósito** (`window_days=1`, `min_contiguous_days=1` → 24
barras horárias): 30 dias são 43 200 velas por mercado e a janela de 24 barras mostra tudo o que a
de 480 mostra. De brinde, exercita o nome `beta_v1+<digest>` de um conjunto de parâmetros
sobrescrito, que o default de produção nunca exercita.

A série é construída para o esperado ser **exato**, não "o que o estimador disse": 22 das 24 barras
são planas (retorno exatamente zero, preço inteiro) e nas duas que se movem o ativo move exatamente
o dobro da referência (+0,4/−0,2 contra +0,2/−0,1). Com `y = 2x` exato, β = 2,00000000, α = 0E−8
(a diferença de última casa entre `ȳ` e `2·x̄` a 28 dígitos é ~1e−30 e some no quantum de 1e−8) e
R² = 1,000000. Cada teste semeia **seus próprios** mercados de referência e ativo: o banco é
compartilhado pelo módulo e um `BTCUSDT` comum faria as velas de um teste decidirem a resposta do
seguinte.

## 6. O que fica em aberto (não finjo ter resolvido)

1. **A fila histórica é o gargalo real do primeiro β válido.** 6 pedaços de 240 min por minuto de
   relógio, compartilhados por todo o universo. 31 dias de 3 mercados são 406 pedaços (~68 min se a
   fila fosse só minha); os ~20 perpétuos com par spot seriam ~2 700 pedaços, **~7,5 h de relógio**
   — e a ordenação `gap_end DESC` global coloca um pedido deliberado de histórico atrás de toda
   lacuna recente de qualquer outro mercado. Isso é do market-worker (fora do meu escopo) e é
   decisão de produto: ou se espera, ou o estrato histórico ganha um orçamento próprio quando há
   pedido explícito. **Medição, não opinião:** 757 lacunas históricas abertas às 04:20Z.
2. **Custo da passada em 30 dias de verdade não foi medido.** 13,1 s são com 11 dias (~15 k velas
   por mercado); com 30 dias completos são ~43 k por mercado, e a consulta por mercado tem
   `statement_timeout = 15 s` (`hunter_worker`). Se apertar, o alvo de otimização é a leitura (um
   índice ou um cache incremental de fechamentos horários), nunca o estimador. Registrado como
   verificação obrigatória na primeira hora em que o histórico estiver cheio.
3. **`market.candles.backfilled` não invalida β.** A T2.9c já registra que ninguém consome esse
   stream no scanner; `invalidates(estimate, gap_start, gap_end)` existe desde a T3.7 e **não está
   ligado**. Hoje o efeito prático é limitado — a revisão vale uma hora e a passada seguinte
   recomputa —, mas uma lacuna preenchida no meio da hora deixa uma revisão viva construída sobre
   um conjunto de barras que mudou. Trabalho próprio, com o consumidor do stream.
4. **Quantos mercados vão passar não é afirmação.** A T3.7 §7 já dizia; a medição continua
   pendente até o histórico existir. Se a taxa for baixa, é a regra do Everton funcionando —
   relaxar `min_contiguous_days`/`max_bar_lag` é `beta_version` novo, por construção, e passa por
   ele.
5. **18 lacunas `failed` na tabela** (5 886 min), de mercados que não são os meus e de antes desta
   tarefa. Não investiguei: é do coletor.
6. **Não pedi opinião à Astra** nesta tarefa (fora do meu alcance de ferramentas aqui). As duas
   decisões que mais mereciam revisão adversarial são a extração em `packages/indicators` (§3.2) e a
   ordem reconhece→aposenta→insere (§3.4).
