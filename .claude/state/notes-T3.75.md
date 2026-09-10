# notes-T3.75 — o funding dos 90 dias existe, e o estresse deixou de ser cego fora de agosto

**Data:** 2026-09-10, 01:55 → 02:35 BRT (04:55 → 05:35 UTC). **Owner:** quant-engineer.
**Base local:** árvore compartilhada, nada commitado. **VPS:** `HEAD 40bb39a`;
`hunter-api-1`/`hunter-strategy-worker-1` na imagem `40bb39a`, os cinco `market-worker` na
`d21a11d` (14 h). **Nenhum container parado, recriado ou reiniciado. Nenhum `.env*` tocado.
Nenhum `git pull` na VPS. Nenhuma escrita SQL.**
**Escritas na VPS:** duas, e só pelo caminho autorizado — `compose.sh ops python
infra/scripts/request_backfill.py --kind funding` (a segunda é a prova de idempotência).
**Testcontainers:** dois arquivos, **um de cada vez** (`test_funding_backfill.py`,
`test_replay_stress_db.py`).

---

## STATUS

**DONE_WITH_CONCERNS** — as duas entregas estão feitas e provadas; o que não deu para
fazer está em §5 e é uma permissão, não uma dúvida técnica.

| # | Entrega do brief | Resultado |
|---|---|---|
| 1 | Histórico de funding 2026-06-12 → 2026-08-08, 16 mercados, auditado, idempotente | **OK.** §1–§2. 3 265 assentamentos; segunda passada insere **0** |
| 1b | Re-contagem de `r_multiple` NULO por versão + existe caminho de re-liquidação? | **OK.** §3. Contagens **idênticas**; `recompute_funding.py` é o caminho |
| 2 | Queda para `r_ex_funding` em `funding_schedule_unknown`, declarada na saída | **OK.** §4. TDD, 18 testes novos, limiares e vereditos intocados |
| 3 | `PIPELINE.md` §4b/§6b, notas, SQL, ≤ 10 linhas em português | **OK.** §6–§8 |

---

## ARQUIVOS (`git status --porcelain`, só os meus)

```
 M docs/PIPELINE.md
 M packages/indicators/hunter_indicators/replay/stress.py
 M packages/indicators/hunter_indicators/replay/stress_table.py
 M services/strategy-worker/hunter_strategy_worker/replay/stress.py
 M services/strategy-worker/hunter_strategy_worker/replay/stress_report.py
?? .claude/state/brief-T3.75-funding-90d-e-stress.md
?? .claude/state/notes-T3.75.md
?? infra/scripts/sql/research/2026-09-10-t375-q00-funding-cobertura.sql
?? infra/scripts/sql/research/2026-09-10-t375-q01-rnet-nulo-por-versao.sql
?? infra/scripts/sql/research/2026-09-10-t375-q02-escopo-da-recomputacao.sql
?? packages/indicators/tests/unit/test_replay_stress_axis.py
?? services/strategy-worker/tests/test_replay_stress_axis.py
```

Raiz em `C:\dev\project-hunter\`. **Não commitei nada.**

---

## 1. A FAIXA DE FUNDING JÁ EXISTIA — o brief supôs um script que não é CLI

O brief manda rodar `infra/scripts/backfill_funding.py`. Esse arquivo **não tem `main()`**:
ele é o módulo `--kind funding` de `request_backfill.py` (T3.7c, commit `31d2078`), importado
por ele e nunca o contrário. O CLI real é:

```
infra/scripts/request_backfill.py --kind funding --days 90 --markets <16>
```

O caminho inteiro estava pronto e implantado, e não precisou de uma linha de código nova:

| peça | onde | o que faz |
|---|---|---|
| `backfill_funding.window_for` | `infra/scripts/` | `[agora − N d, agora)`, teto `MAX_REQUEST_DAYS = 370` |
| `backfill_funding.envelope_for` | idem | **uma** requisição por mercado (não fatia de 7 d como a vela), `event_id = uuid5(stream, market, "funding", início, fim)` |
| `backfill_request.KINDS` | `market-worker` | `{"candles", "funding"}` |
| `backfill.py:192` | `market-worker` | despacha `kind == "funding"` para `funding_backfill.serve` |
| `funding_backfill.serve` | `market-worker` | uma chamada REST, `normalize_window`, filtro `[start, end)`, `upsert_funding` |
| `BinanceRestClient.fetch_realized_funding` | `exchange-adapters` | `GET /fapi/v1/fundingRate`, pagina sozinho, `limit` 1000 (~333 d a 8 h) |

**Por que a tabela estava vazia antes de 08/08, então:** a T3.7c rodou `--days 31`, e 31 dias
antes daquela data é exatamente `2026-08-08 16:00Z`. O backfill de 90 dias da T3.62
(`request_backfill.py` sem `--kind`) trouxe **vela**; funding é outra série e outro pedido.

**Idempotência é da chave, não da disciplina:** `upsert_funding` insere com
`ON CONFLICT (market_id, funding_time) DO NOTHING` **qualquer que seja o chamador** — a linha
que chegou primeiro sobrevive, viva ou de backfill.

### 1.1 Prova local antes de tocar na VPS

```
$ timeout 290 uv run pytest infra/scripts/tests/test_request_backfill.py -q
.........                                                                [100%]
9 passed in 2.00s

$ timeout 290 uv run pytest services/market-worker/tests/test_funding_backfill.py -q -p no:randomly
.........                                                                [100%]
9 passed in 33.55s
```

O segundo é o testcontainer (Postgres real) e traz, por nome,
`test_a_rerun_of_the_same_window_never_duplicates_rows` e
`test_a_backfilled_row_never_overwrites_one_the_live_poller_already_wrote`.

---

## 2. O BACKFILL NA VPS — 3 265 assentamentos, e a segunda passada insere 0

### 2.1 Linha de base (q00, somente leitura, 02:00 BRT)

```
+---------------+----------------------+----------+
| linhas_totais | linhas_antes_de_0808 | mercados |
+---------------+----------------------+----------+
|          1902 |                    0 |       16 |
+---------------+----------------------+----------+
```

Todos os 16 mercados começavam em `2026-08-08 16:00:00.002+00`. Confere com a T3.62b §3.

### 2.2 Ensaio (nada escrito)

```
$ timeout 290 ssh hunter-vps 'cd /opt/project-hunter && bash infra/vps/compose.sh ops \
    python infra/scripts/request_backfill.py --kind funding --days 90 \
    --markets ARBUSDT,BNBUSDT,BTCUSDT,DASHUSDT,DOGEUSDT,ETHUSDT,LINKUSDT,NEARUSDT,\
PROMUSDT,SAHARAUSDT,SOLUSDT,SUIUSDT,TAOUSDT,UNIUSDT,XRPUSDT,ZECUSDT --dry-run --show 20'
kind    funding
window  2026-06-12T05:01:00+00:00 -> 2026-09-10T05:01:00+00:00
markets 16: ARBUSDT, BNBUSDT, BTCUSDT, DASHUSDT, DOGEUSDT, ETHUSDT, LINKUSDT, NEARUSDT,
            PROMUSDT, SAHARAUSDT, SOLUSDT, SUIUSDT, TAOUSDT, UNIUSDT, XRPUSDT, ZECUSDT
windows 16 (1 per market, newest first)
[dry-run] 16 request(s) would be queued on the outbox
```

A janela cai **exatamente** sobre a da coorte de 90 d da T3.62b (`2026-06-12 → 2026-09-10`).

### 2.3 A passada real, 02:01 BRT

```
$ ... (o mesmo comando, sem --dry-run)
16 request(s) queued on outbox_events
```

Os cinco shards do coletor serviram os 16 pedidos em **3,3 s** (05:01:35 → 05:01:38 UTC),
cada um pela sua fatia do universo. Um log verbatim:

```
{"exchange":"binance","symbol":"ETHUSDT","gap_start":"2026-06-12T05:01:00+00:00",
 "gap_end":"2026-09-10T05:01:00+00:00","fetched":270,"matched":270,"inserted":172,
 "truncated":false,"event":"market_funding_backfill_served","role":"market","level":"info",
 "timestamp":"2026-09-10T05:01:35.286002Z"}
```

Inseridos: **172** em cada um dos 13 mercados de cadência 8 h e **343** em `PROMUSDT`,
`SAHARAUSDT`, `TAOUSDT` (cadência 4 h em parte da janela) → **3 265**. Nenhum `truncated`,
nenhum `refused`, nenhum `rate_limited`.

### 2.4 Conferência (q00 de novo)

```
| 2026-06-01 | 16 | 1061 | 2026-06-12 08:00:00+00     | 2026-06-30 20:00:00.003+00 |
| 2026-07-01 | 16 | 1767 | 2026-07-01 00:00:00+00     | 2026-07-31 20:00:00.001+00 |
| 2026-08-01 | 16 | 1826 | 2026-08-01 00:00:00.001+00 | 2026-08-31 20:00:00+00     |
| 2026-09-01 | 16 |  513 | 2026-09-01 00:00:00.005+00 | 2026-09-09 20:00:00+00     |

+---------------+----------------------+----------+
| linhas_totais | linhas_antes_de_0808 | mercados |
+---------------+----------------------+----------+
|          5167 |                 3265 |       16 |
+---------------+----------------------+----------+
```

5 167 − 1 902 = **3 265**, o mesmo número que a soma dos `inserted` dos logs. Os 16 mercados
começam agora em `2026-06-12 08:00:00+00` (o primeiro assentamento da grade dentro da janela).

### 2.5 Idempotência, medida (02:02 BRT)

O mesmo comando um minuto depois: como `event_id` é `uuid5` sobre a janela e a janela anda com
o relógio, são **16 requisições novas de verdade**, servidas de verdade, com uma nova chamada
REST cada. E:

```
"symbol":"ETHUSDT","gap_start":"2026-06-12T05:02:00+00:00", ... "fetched":270,"matched":270,"inserted":0
"symbol":"PROMUSDT",                                        ... "fetched":598,"matched":598,"inserted":0
```

**`inserted: 0` nos 16.** É a prova forte: não é o pedido que foi deduplicado, é a **linha**.

---

## 3. O QUE O BACKFILL **NÃO** CONSERTA — e qual é o caminho de re-liquidação

`signal_outcomes` é append-honesto (`SHADOW-LAB.md` §6): nada reprocessa sozinho. Medido
depois do backfill (q01, 02:03 BRT):

```
+--------+-----------+-----------+---------------+-------+
| rotulo | terminais | com_r_net | cobertura_pct | nulos |
+--------+-----------+-----------+---------------+-------+
| v1     |       542 |       253 |         46.68 |   289 |
| v10    |       798 |       300 |         37.59 |   498 |
| v2     |       302 |       175 |         57.95 |   127 |
+--------+-----------+-----------+---------------+-------+

| v1  | funding_schedule_unknown | 288 |    | v1  | funding_ambiguous_exit | 1 |
| v10 | funding_schedule_unknown | 498 |    | v2  | funding_ambiguous_exit | 1 |
| v2  | funding_schedule_unknown | 126 |
```

**Idênticas às da T3.62b §3, dígito a dígito.** K5 continua disparando nas três **hoje** — e
isso é a resposta certa, não um defeito: o desfecho gravado é o que o Lab viu quando fechou.

**Existe caminho de re-liquidação, e não é `settle.py`:** é
`infra/scripts/recompute_funding.py` (S2-funding). Ele recalcula a leitura de funding com o
código atual sobre as **entradas gravadas** (`entry_ts`, `exit_ts`, `virtual_entry`,
`virtual_stop`, `exit_price`, `meta.assumed_costs`, `meta.progress`), nunca re-caminhando
barra; preserva `meta.r_ex_funding`; guarda o objeto anterior em `meta.funding.previous`
com `recomputed_at`/`recompute_reason`; e deixa intacta qualquer linha que continue
indeterminável. **Re-rodar o replay não é necessário** para isso (e produziria uma coorte
nova, quebrando a comparabilidade com a T3.62b).

**Quanto ele recuperaria** (q01 §3): usando o **mesmo predicado** que `resolve_funding`
aplica para dizer `funding_schedule_unknown` — ≥ 2 instantes distintos de assentamento na
janela que `settle()` carrega, `[entry_ts − 3 d, exit_ts + 2 s]`:

```
| rotulo |          motivo          | nulos | cadencia_legivel | ainda_cega |
| v1     | funding_schedule_unknown |   288 |              288 |          0 |
| v10    | funding_schedule_unknown |   498 |              498 |          0 |
| v2     | funding_schedule_unknown |   126 |              126 |          0 |
```

**914 de 914 passaram a ter cadência legível.** Isso é uma **previsão por contagem**, não a
recomputação: um desfecho com cadência legível ainda pode cair em `funding_missing` ou
`funding_ambiguous_exit`. Eu **não rodei** `recompute_funding.py` — nem `--dry-run`: ele exige
`DATABASE_URL_MIGRATIONS` (dono do schema), não tem filtro de coorte nem `--limit`, e o meu
brief autoriza uma escrita só, a do backfill.

**Raio de alcance, para quem for decidir isso** (q02):

```
| funding_schedule_unknown | 1580 |     | outro replay | 545 |   | v10 | 498 |
| funding_missing          |   75 |     | v1           | 289 |   | v2  | 127 |
| funding_ambiguous_exit   |   13 |     | sombra viva  | 209 |
sem_insumo_para_recomputar: 0
```

1 668 linhas no total, **0** sem insumo gravado. Uma transação por linha.

---

## 4. O EIXO DO ESTRESSE (CONCERN 2) — TDD, e o que **não** mudou

### 4.1 O que estava errado

`stress.py::_as_outcome` carimbava `dropped = "funding_indeterminado"` para **todo** `R_net`
ausente, e `aggregate` só conta o que não foi descartado. Resultado medido na T3.62b §7.2:
`base` com n = 300 de 798, `1a_metade → n = 0, no_evaluable_outcomes`, veredito
`dependente de metade` — um artefato de cobertura de tabela vestido de leitura sobre a
estratégia.

### 4.2 A correção, e onde está a linha que ela não cruza

`funding_schedule_unknown` é fato sobre a **cobertura de `funding_rates`** (não há
assentamento nenhum perto da entrada, nem para ler a cadência). Só ele cai para
`r_ex_funding`. `funding_ambiguous_exit`, `funding_missing`, `funding_conflicting_rows`,
`funding_boundary_uncertain`, `funding_price_missing` **continuam descarte** — ali a dúvida é
sobre *aquela* operação, e trocar o eixo esconderia uma ambiguidade real. O descarte que
sobra passa a ser nomeado **pelo próprio prefixo** em vez do rótulo genérico, que agora
colidiria com a contagem do eixo.

| arquivo | mudança |
|---|---|
| `hunter_indicators/replay/stress.py` | `StressAxis` (`r_net` \| `r_ex_funding`) + o porquê |
| `hunter_indicators/replay/stress_table.py` | `StressOutcome.r_ex_funding`/`.funding_indeterminate`, propriedades `.axis`/`.r`, `evaluable` sobre `.r`; `StressRow.axis`/`.funding_indeterminate`; `aggregate` conta a queda |
| `replay/stress.py` | `_as_outcome` traduz o motivo do `settle()` para eixo ou descarte |
| `replay/stress_report.py` | `StressRun.axis`/`.funding_indeterminate`, coluna `eixo` na tabela, `axis: …, funding_indeterminado: N` no cabeçalho e `axis`/`funding_indeterminado` no JSONL; o Δ pareado passa a usar `.r` |

**O que eu não toquei, de propósito:** `MIN_SAMPLE`, `stress_verdict`, a precedência das
famílias, `STRESS_VERSION`, os fatores dos cenários, `hunter_indicators/replay/policies.py`,
`walker.py`, `settle.py`, `funding.py` e todo módulo do fecho de `code_ref`
(`packages/core/hunter_core/strategies/*.py` — o fecho é **só** aquele diretório,
`code_ref.module_closure`). A queda muda o **denominador**; a régua fica onde estava, e há
teste para isso (`test_the_verdict_rules_do_not_move_because_the_axis_moved`).

**Uma assimetria declarada, não escondida:** o Δ pareado usa `.r` de cada membro. Os dois
membros de um par são a mesma decisão no mesmo mercado, então na prática partilham o eixo;
quando não partilharem (uma saída deslocada que muda a legibilidade da cadência), o Δ mistura
os dois — e é a coluna `eixo` da linha que avisa. Descartar o par seria voltar a emudecer
exatamente a metade da janela que motivou a queda. Está no comentário de `deltas()`.

### 4.3 TDD — vermelho antes de verde

```
$ timeout 290 uv run pytest packages/indicators/tests/unit/test_replay_stress_axis.py -q
E   ImportError: cannot import name 'StressAxis' from 'hunter_indicators.replay.stress'
1 error in 1.21s

$ timeout 290 uv run pytest services/strategy-worker/tests/test_replay_stress_axis.py -q
...
7 failed, 2 passed in 2.26s
```

Depois da implementação:

```
$ timeout 290 uv run pytest packages/indicators/tests/unit/test_replay_stress_axis.py \
    packages/indicators/tests/unit/test_replay_stress.py \
    services/strategy-worker/tests/test_replay_stress_axis.py \
    services/strategy-worker/tests/test_replay_stress.py \
    infra/scripts/tests/test_request_backfill.py -q
.......................................................                  [100%]
55 passed in 2.70s
```

Regressão do caminho de replay inteiro (unitários) e o testcontainer do estresse:

```
$ timeout 290 uv run pytest packages/indicators/tests/unit/test_replay_stress.py \
    services/strategy-worker/tests/test_replay_stress.py \
    services/strategy-worker/tests/test_replay_engine.py \
    services/strategy-worker/tests/test_replay_contract.py -q
79 passed in 205.34s (0:03:25)

$ timeout 290 uv run pytest services/strategy-worker/tests/test_replay_stress_db.py -q -p no:randomly
...........                                                              [100%]
11 passed in 175.47s (0:02:55)
```

**Não criei testcontainer novo:** a queda de eixo é aritmética pura sobre um `ArmOutcome` que
o `replay_arm` já monta, e o arquivo de banco que existe (`test_replay_stress_db.py`, 11
casos, Postgres real, inclui `test_the_rendered_table_names_its_population`) passa sem
alteração — um segundo arquivo mediria o mesmo caminho por um preço de três minutos.

**18 testes novos**, todos com valor esperado calculado à mão. Os dois que valem citar:
`test_the_first_calendar_half_is_no_longer_empty_when_only_funding_was_missing` (o artefato
do §7.2 em miniatura: 40 entradas cegas na primeira metade saem de `n = 0` para `n = 40`,
expectancy 0,10 conferida à mão) e `test_the_receipt_names_the_axis_and_the_count_it_rests_on`
(a frase literal `axis: r_ex_funding, funding_indeterminado: 2`).

### 4.4 A saída, verbatim

Sobre uma coorte sintética com a mesma forma do artefato (40 entradas cegas na primeira
metade, 40 com `R_net` na segunda):

```
coorte replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3 · as_of 2026-06-12T00:00:00+00:00 · 80 entradas congeladas · 1 mercados · axis: r_ex_funding, funding_indeterminado: 40

| cenário | tipo | n | eixo | expectancy (R) | PF | Δ vs base | IC 95 % do Δ | descartes |
|---|---|---:|---|---:|---:|---:|---|---|
| `base` | reprecificacao | 80 | r_ex_funding (40) | 0.1500 | nulo (no_losses) | — | — | — |
| `1a_metade_ate_2026-07-21` | recorte | 40 | r_ex_funding (40) | 0.1000 | nulo (no_losses) | — | — | — |
| `2a_metade_apos_2026-07-21` | recorte | 40 | r_net | 0.2000 | nulo (no_losses) | — | — | — |

**Veredito:** robusto
```

Antes desta tarefa a primeira metade sairia `n = 0 / no_evaluable_outcomes` e o veredito seria
`dependente de metade`. O `eixo` por linha é o que impede a leitura oposta — "agora tudo tem
n" —, porque ele diz de que material aquele n é feito.

### 4.5 Portões

```
$ timeout 290 uv run ruff check <os 6 arquivos>            -> All checks passed!
$ timeout 290 uv run ruff format --check <os 6 arquivos>   -> 6 files already formatted
$ timeout 290 uv run pyright <os 6 arquivos>               -> 0 errors, 0 warnings
$ timeout 290 uv run python infra/scripts/check_file_size.py
scanned 594 files; 0 over budget, 0 grandfathered
```

`replay/stress.py` chegou a 357 linhas na primeira escrita e foi comprimida para **349**
(orçamento 350) sem perder nenhuma afirmação — o porquê comprido mora em `StressAxis`.

---

## 5. O QUE EU NÃO CONSEGUI MEDIR (o concern desta nota)

Eu **não rodei** uma passada de `--stress` na coorte real para mostrar a base saindo de
n = 300. Duas razões independentes, e a primeira já bastaria:

1. **O código não está implantado.** `stress.py` novo está na minha árvore, não commitado; a
   imagem da VPS é `40bb39a`. Uma passada lá mediria o código antigo.
2. **A permissão foi negada.** A tentativa
   (`ssh hunter-vps 'timeout 270 docker exec hunter-strategy-worker-1 python -m
   hunter_strategy_worker.replay.stress --cohort replay:c7d138eb-… --limit 30'`, somente
   leitura por construção) foi bloqueada pelo classificador de permissões. Não tentei
   contornar.

**O que se pode afirmar mesmo assim, e é bastante:** o `--stress` reprecifica chamando
`settle()`, que lê `funding_rates` **agora**. Com o histórico no lugar e as 914 linhas cegas
todas com cadência legível (§3), uma passada nova sobre a mesma coorte já resolveria o funding
na maioria delas **mesmo com o código antigo** — a queda de eixo desta tarefa é o que cobre o
resíduo (`funding_missing`, `funding_ambiguous_exit`) **e o que torna a mistura visível** em
vez de silenciosa. Confirmar isso é uma medição de uma linha depois do deploy.

**Para o orquestrador:** ordem sugerida — (1) deploy; (2) `--stress` na coorte
`replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3` e ler o `axis:` do cabeçalho; (3) decidir sobre
`recompute_funding.py --apply` (1 668 linhas, §3), que é escrita em `signal_outcomes` e não
estava no meu brief.

---

## 6. SQL

| arquivo | o quê |
|---|---|
| `infra/scripts/sql/research/2026-09-10-t375-q00-funding-cobertura.sql` | cobertura de `funding_rates` nos 16 mercados: por mercado, por mês, e o total antes de 08/08 (o antes/depois) |
| `infra/scripts/sql/research/2026-09-10-t375-q01-rnet-nulo-por-versao.sql` | `r_multiple` nulo por versão nas três coortes da T3.62b, o motivo, e quantos passariam a ter cadência legível |
| `infra/scripts/sql/research/2026-09-10-t375-q02-escopo-da-recomputacao.sql` | o raio de alcance de `recompute_funding.py` antes de alguém rodá-lo |

Receita (somente leitura, `repeatable read read only`, `statement_timeout = 240s`):

```bash
timeout 290 ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter \
  -v ON_ERROR_STOP=1 -f -" < infra/scripts/sql/research/2026-09-10-t375-q00-funding-cobertura.sql
```

---

## 7. DOCUMENTAÇÃO

- `docs/PIPELINE.md` §4b, **item 13 novo**: K5 mede cobertura de `funding_rates`, não
  qualidade da estratégia; a faixa `--kind funding`; a queda para `r_ex_funding` e o que ela
  não autoriza.
- `docs/PIPELINE.md` §6b, **um parágrafo novo**: funding tem faixa de backfill própria (vela e
  funding são duas séries e dois pedidos), a idempotência é da chave, e um desfecho já gravado
  não se recalcula sozinho — `recompute_funding.py` é o caminho, re-rodar o replay não é.

---

## 8. RESUMO EM PORTUGUÊS (para o Everton)

1. O banco não tinha **taxa de funding** antes de 08/08 — o backfill de 90 dias tinha trazido só vela.
2. Trouxe o histórico que faltava às **02:01 BRT**: 3 265 cobranças, 16 mercados, de 12/06 a 08/08.
3. Rodei o mesmo comando de novo: **inseriu 0**. A proteção é da chave da linha, não do cuidado de quem roda.
4. Os resultados **já gravados** continuam sem o R líquido — o Lab nunca reescreve o passado sozinho, e isso é regra, não bug.
5. Mas agora **914 de 914** deles têm o dado necessário para serem recalculados por `recompute_funding.py`, quando você mandar.
6. O teste de estresse ficava cego fora de agosto: media 300 de 798 operações e dizia "depende de metade" — era falta de dado, não da estratégia.
7. Corrigi: onde falta só o funding, ele passa a medir pelo **R sem funding** e **escreve na tabela que fez isso**.
8. Onde a dúvida é da operação (saída ambígua, cobrança faltando), continua descartando — trocar o eixo ali seria esconder problema.
9. Não mexi em nenhum limiar nem em nenhuma regra de veredito; há teste provando que a régua não andou.
10. Falta uma medição: só dá para rodar o estresse na VPS **depois do deploy** — o código novo ainda está só na minha árvore.

---

## 9. NÚMEROS ASSUMIDOS

1. **`--days 90`** foi escolhido por cobrir `2026-06-12 → 2026-09-10`, que é a janela exata da
   coorte da T3.62b; o teto da faixa é 370 dias, então não houve truncamento (`truncated:
   false` nos 16 logs).
2. **~170 linhas por mercado** era a estimativa do brief (57 d × 3/dia). Medido: **172** nos 13
   mercados de 8 h e **343** em `PROMUSDT`/`SAHARAUSDT`/`TAOUSDT`, que rodaram parte da janela
   a 4 h. A diferença é cadência real da exchange, não erro de janela.
3. **`[entry_ts − 3 d, exit_ts + 2 s]`** na q01 §3 não é escolha minha: é
   `settle._CADENCE_LOOKBACK` mais `funding.MATCH_TOLERANCE`, para que a contagem use o mesmo
   material que `resolve_funding` usaria.
4. **"≥ 2 instantes distintos"** é a condição literal de `funding._cadence()` (com
   `_distinct_instants` colapsando duplicatas dentro de 2 s) para **não** devolver
   `funding_schedule_unknown`.
5. **O eixo de um agregado misto é `r_ex_funding`**, não "misto": a média de um pool que
   contém uma linha do eixo mais fraco não pode reivindicar o mais forte. É decisão minha,
   está declarada em `StressAxis` e é o que produz a frase que o brief pediu.
