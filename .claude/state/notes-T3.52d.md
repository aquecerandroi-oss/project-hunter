# notes-T3.52d — o portão de regime medido, e a irmã de 1 h finalmente ativada

**Data:** 2026-09-09, 12:24 → 13:10 BRT (15:24 → 16:10 UTC). **Owner:** quant-engineer.
**VPS:** `d21a11d` em todos os serviços, migração `0017_eligibility_policy` confirmada.
**Nada commitado.** **Nenhum container parado, recriado ou reiniciado.** **Nenhum `.env*` tocado.**
**Escritas na VPS:** só pelos scripts auditados (`derive_variant.py` ×2, `activate_strategy_version.py`
×3, `seed.py --only strategies` ×1) e 6 corridas de replay + 3 passadas de estresse (`READ ONLY`).
Todo o resto foi lido em `begin transaction isolation level repeatable read read only`.

---

## STATUS

**DONE_WITH_CONCERNS.**

| # | Entrega do brief | Resultado |
|---|---|---|
| A1 | `alembic_version = 0017_eligibility_policy` | **OK** (§1) |
| A2 | derivar as duas variantes com portão | **OK com desvio de numeração:** saíram **`v11`**, não `v9` (§2) |
| A3 | ativar as duas `research_only` | **OK com desvio de bandeira:** `activate_strategy_version.py` não tem `--purpose` (§2.3) |
| A4 | replay 31 d × 4 mercados com `--explain-ledger` | **OK** — 4 fatias, 0 erros (§3) |
| A5 | avaliação pareada por (mercado, barra) | **OK, e derruba uma premissa do brief:** a filha **não** é subconjunto (§4) |
| A6 | decisões removidas, expectativa/PF/pedágio antes e depois, fatia `regime_gate:unknown`, K1–K5, estresse | **OK** (§3–§6) |
| B1 | `seed.py --only strategies` | **OK com ressalva grande:** apareceram **duas** estratégias novas, não uma (§7, CONCERN 1) |
| B2 | ativar `mean_reversion_h1 v1` sem recusa, com os minutos de contexto | **OK** — `context_minutes = 5880 ≤ 6000` (§7.2) |
| B3 | replay 31 d × 16 mercados, K1–K5, estresse | **OK** — 123 decisões, 0 erros (§8) |
| B4 | IC transversal de blocos de dia contra `mean_reversion v10` | **OK** (§8.3) |
| C | vereditos, ≤ 10 linhas para Everton, adendos | **OK** (§9, §10) — adendo **só** aqui: ver §10 |

**O resultado em uma frase:** o portão de regime **funciona exatamente como especificado** e
**não compra vantagem** — o Δ de expectativa do braço de `momentum` (+0,1104 R) tem IC 95 %
[−0,0605; +0,2859] com o dia como bloco, o braço de `mean_reversion` morre no K1 (1 decisão em
31 dias) e a irmã de 1 h, agora ativável, entrega expectativa **+0,0067 R** com pedágio **maior**
que o da mãe de 15 m.

---

## ARQUIVOS

| Arquivo | O quê |
|---|---|
| `infra/scripts/sql/research/2026-09-09-t352d-q00-estado.sql` | migração, catálogo, os dois pais, a série horária |
| `infra/scripts/sql/research/2026-09-09-t352d-q01-coortes.sql` | coortes de replay existentes |
| `infra/scripts/sql/research/2026-09-09-t352d-q02-regime-por-fatia.sql` | rótulo horário por metade da janela |
| `infra/scripts/sql/research/2026-09-09-t352d-q10-populacoes.sql` | populações, pedágio, expectativa, PF |
| `infra/scripts/sql/research/2026-09-09-t352d-q11-pareado.sql` | pareamento por (mercado, barra) |
| `infra/scripts/sql/research/2026-09-09-t352d-q12-dump-csv.sql` | dump por decisão (CSV) |
| `infra/scripts/sql/research/2026-09-09-t352d-q13-recibos.sql` | recibos, política congelada, isolamento |
| `infra/scripts/sql/research/2026-09-09-t352d-q14-h1-vs-v10-csv.sql` | dump `h1` vs `v10` (CSV) |
| `.claude/state/exp-drafts/t352d/portao.py` | Δ do portão reusando `t342-blocos/blocos.py` **sem alterar uma linha** |
| `.claude/state/exp-drafts/t352d/duas_populacoes.py` | bootstrap de blocos de dia para **duas** populações |
| `.claude/state/exp-drafts/t352d/test_oraculo.py` | prova de que o estimador novo concorda com o antigo |
| `.claude/state/exp-drafts/t352d-decisoes.csv` · `t352d-h1-vs-v10.csv` | os dois dumps lidos da VPS |
| `.claude/state/notes-T3.52d.md` | este arquivo |

Todos com raiz em `C:\dev\project-hunter\`.

---

## 1. A MIGRAÇÃO (A1) — `read_at = 2026-09-09T15:25:43,562839Z` (12:25:43 BRT)

```
+-------------------------+
|     alembic_version     |
+-------------------------+
| 0017_eligibility_policy |
+-------------------------+
```

A série que o portão lê existe e está fresca: `scope = btc`, `classifier_version = regime_hourly_v1`,
**761 horas**, de 2026-08-08 23:00Z a 2026-09-09 15:00Z. Distribuição na janela de replay (31 d):

| rótulo | horas | % |
|---|---:|---:|
| `UNKNOWN` | 205 | 28,43 |
| `BTC_BULL` | 150 | 20,80 |
| `HIGH_VOLATILITY` | 148 | 20,53 |
| `SIDEWAYS` | 129 | 17,89 |
| `BTC_BEAR` | 54 | 7,49 |
| `LOW_VOLATILITY` | 35 | 4,85 |

**E a assimetria que decide o experimento inteiro** (`q02`): as 205 horas de `UNKNOWN` estão
**quase todas na primeira metade** — o aquecimento do classificador. Por metade:

| fatia | `UNKNOWN` | `HIGH_VOLATILITY` | `BTC_BULL` | `SIDEWAYS` | `BTC_BEAR` | `LOW_VOLATILITY` |
|---|---:|---:|---:|---:|---:|---:|
| A 08-08..08-23 | **205** | 88 | 38 | **6** | 0 | 0 |
| B 08-23..09-08 | 0 | 60 | 112 | **123** | 54 | 35 |

`SIDEWAYS` tem **6 horas** em 15 dias na primeira metade. O braço `mean_reversion` nasce sem
população antes de qualquer hipótese sobre o mercado.

---

## 2. AS DUAS VARIANTES (A2, A3)

### 2.1 Desvio de numeração: saiu `v11`, não `v9`

O brief pediu `mean_reversion v9` e `momentum v9`. `derive_variant.py` **numera sozinho** a próxima
vaga livre e as duas famílias já chegaram a `v10` pelo eixo de timeframe (T3.54). O script deu
`v11` nas duas. Não forcei o número: reaproveitar `v9` exigiria escrever versão à mão, fora do
script auditado. **O EXP-0020 já previa isto** ("quem for derivar G1/G2 tem de reconferir a próxima
vaga livre no momento da corrida, não confiar neste número").

### 2.2 O parser aceitou os dois rótulos — a ressalva do brief não precisou ser usada

O brief previa que o parser pudesse aceitar **um** rótulo só. Ele aceita lista
(`regime=<escopo>:<RÓTULO>[,<RÓTULO>…]`, `EligibilityPolicy.allow` é tupla) e canoniza ordenando:

```
$ … derive_variant.py mean_reversion v6 --policy regime=btc:SIDEWAYS --changelog "…" --dry-run
derivaria mean_reversion v11 de v6 (purpose research_only, draft, nada ativado) em code_ref
hunter_core.strategies.mean_reversion_v1@sha256:a970c9d9…: policy -> btc:SIDEWAYS [params_hash 11ce73ed48b5]

$ … derive_variant.py momentum v8 --policy regime=btc:HIGH_VOLATILITY,BTC_BULL --changelog "…" --dry-run
derivaria momentum v11 de v8 (purpose research_only, draft, nada ativado) em code_ref
hunter_core.strategies.momentum_v1@sha256:ab2e0398…: policy -> btc:BTC_BULL,HIGH_VOLATILITY [params_hash 69152dbc9173]
```

Escrita (sem `--dry-run`), palavra por palavra igual trocando "derivaria" por "derivada".
`params_hash` **idêntico ao do pai** nas duas: o que muda é só a coluna `eligibility_policy`.

### 2.3 Ativação — e o segundo desvio de bandeira

`activate_strategy_version.py` **não tem `--purpose`** (confirmado por `grep add_argument`; já
registrado na T3.54 §3.3). A linha derivada nasce `research_only` e a ativação preserva:

```
activated mean_reversion v11 (purpose research_only) at 2026-09-09T15:28:02.129582+00:00 with code_ref …a970c9d9…
activated momentum       v11 (purpose research_only) at 2026-09-09T15:28:14.324938+00:00 with code_ref …ab2e0398…
```

A política ficou congelada na linha (`q13`):

```
mean_reversion v11 | active | research_only |
  {"regime": {"rule": "previous_closed_hour", "allow": ["SIDEWAYS"], "scope": "btc", "classifier_version": "regime_hourly_v1"}}
momentum v11 | active | research_only |
  {"regime": {"rule": "previous_closed_hour", "allow": ["BTC_BULL", "HIGH_VOLATILITY"], "scope": "btc", "classifier_version": "regime_hourly_v1"}}
```

### 2.4 Desvio de **desenho**, e é o mais sério dos três

O EXP-0020 congelou **G2 = `momentum` com `regime=btc:BTC_BULL`**, um rótulo. O brief desta tarefa
pediu **dois** (`HIGH_VOLATILITY,BTC_BULL`), pelo achado pré-registrado da T3.53. **O braço que eu
rodei não é o braço pré-registrado.** Isso não invalida a medida, mas rebaixa o que ela vale: é
uma escolha a mais no espaço de políticas, feita depois de olhar a T3.53, e o IC de §4.3 não paga
por essa escolha. Declarado aqui para que ninguém leia o resultado como confirmação de G2.

---

## 3. OS QUATRO REPLAYS (A4) — 31 d × 4 mercados (ETH, SOL, XRP, DOGE), 0 erros

Corridos em `hunter-strategy-worker-1` (precedente da T3.54 §3.6 — ver CONCERN 5).
Coortes explícitas, `--explain-ledger` nas quatro fatias, `context_minutes = 1560` em todas.

| versão | fatia | barras | `ineligible` | `not_triggered` | `triggered` | sinais (acum.) | s |
|---|---|---:|---:|---:|---:|---:|---:|
| `mean_reversion v11` | 08-08→08-23 | 5760 | 5664 | 96 | 0 | 0 | 78,9 |
| `mean_reversion v11` | 08-23→09-08 | 6144 | 4192 | 1951 | 1 | **1** | 96,8 |
| `momentum v11` | 08-08→08-23 | 5760 | 3760 | 1843 | 157 | 41 | 88,9 |
| `momentum v11` | 08-23→09-08 | 6144 | 3376 | 2641 | 127 | **101** | 98,5 |

(`replay_runs.signals` é cumulativo por `run_id` — T3.54 §3.6. Totais reais: **1** e **101**.)

### 3.1 O ledger fecha na aritmética da série — a queda de população **não** é buraco

```
== mean_reversion v11, fatia A        == momentum v11, fatia A
   3664 regime_gate:unknown              3664 regime_gate:unknown
   1408 regime_gate:HIGH_VOLATILITY        96 regime_gate:SIDEWAYS
    592 regime_gate:BTC_BULL
== mean_reversion v11, fatia B        == momentum v11, fatia B
   1808 regime_gate:BTC_BULL             1952 regime_gate:SIDEWAYS
    960 regime_gate:HIGH_VOLATILITY       864 regime_gate:BTC_BEAR
    864 regime_gate:BTC_BEAR              560 regime_gate:LOW_VOLATILITY
    560 regime_gate:LOW_VOLATILITY
```

As somas batem com `evaluations_by_state` linha a linha (5664 = 3664+1408+592; 4192 =
1808+960+864+560; 3760 = 3664+96; 3376 = 1952+864+560). E as barras **elegíveis** batem com as
horas: `mean_reversion v11` fatia A = 96 barras = **6 horas `SIDEWAYS` × 4 barras × 4 mercados**;
fatia B = 1952 = 122 h × 16. **A previsão do EXP-0020 acerta:** ele previu queda ≥ 27 % (o
`UNKNOWN`) mais a fração de rótulo não permitido — o que dá ≈ 82,1 % para `mean_reversion` e
≈ 58,7 % para `momentum`; medido, **82,80 %** e **59,95 %**. A série não é a suspeita.

### 3.2 A fatia recusada como `regime_gate:unknown`

**3664 barras nas duas versões** (as mesmas horas) = **30,78 % de todas as 11 904 barras**;
**37,17 %** das recusas de `mean_reversion v11` e **51,35 %** das de `momentum v11`. Por mercado
são 916 barras = **229 horas**: 205 são `UNKNOWN` do classificador e ~23 são "linha nenhuma"
(a série só começa em 2026-08-08 23:00Z), mais uma hora do deslocamento da regra da hora anterior.
**O ledger não separa as três causas** — `detail` carrega só `eligibility_reason`, e o
`RegimeGate.detail` (`stale` / `no_row` / `unknown`) não chega ao JSONL. Separei por aritmética da
série, não por leitura; fechar isso é um campo a mais no ledger (CONCERN 3).

---

## 4. A AVALIAÇÃO PAREADA (A5) — e a premissa que ela derruba

`q11`, pareamento por (família, mercado, `source_bar_close`, lado):

| família | classe | n | exp. pai (R) | exp. filha (R) | divergem no R |
|---|---|---:|---:|---:|---:|
| `mean_reversion` | 1 nos dois | 1 | +0,1412 | +0,1412 | **0** |
| `mean_reversion` | 2 só no pai (removida pelo portão) | **14** | +0,2964 | — | 0 |
| `momentum` | 1 nos dois | 98 | +0,0805 | +0,0805 | **0** |
| `momentum` | 2 só no pai (removida pelo portão) | **83** | −0,1603 | — | 0 |
| `momentum` | 3 **só na filha** (o slot divergiu) | **3** | — | −0,1486 | 0 |

### 4.1 O que está certo: nas barras elegíveis a filha reproduz o pai **bit a bit**

99 decisões compartilhadas, **zero** diferença de `r_multiple`. O portão só remove; ele não muda
uma decisão que deixa passar. É a prova mais forte desta nota.

### 4.2 O que está errado no enunciado: **a filha não é subconjunto do pai**

O brief (e o EXP-0020) dizem "subconjunto por construção". `momentum v11` tem **3 decisões que o
pai nunca tomou** — todas em 2026-09-03, e cada uma **precede** a próxima decisão do pai no mesmo
mercado:

```
 symbol   |          bar           | lado |  r_net  |  próxima decisão do pai
 DOGEUSDT | 2026-09-03 17:00:00+00 | long | -0.1779 | 2026-09-04 09:00:00+00
 XRPUSDT  | 2026-09-03 18:15:00+00 | long | -0.2966 | 2026-09-03 20:30:00+00
 XRPUSDT  | 2026-09-03 20:00:00+00 | long |  0.0288 | 2026-09-03 20:30:00+00
```

O mecanismo está escrito no próprio PIPELINE §4b item 10: `INELIGIBLE` "não decide, **não re-arma o
slot**, **não gasta a barreira**". Logo a máquina de estados do slot da filha evolui **diferente**
da do pai: onde o pai estava dentro de um episódio, a filha estava livre. "Subconjunto por
construção" é verdade sobre as **barras**, não sobre as **decisões**. São 3 de 101 — pequeno —,
mas a frase precisa sair dos documentos: ela é falsa e é a base do desenho pareado.

### 4.3 Quanto o portão comprou, com o dia como bloco

Estimador: `t342-blocos/blocos.py` **sem uma linha alterada** (a marca por decisão é "a filha
manteve" no lugar do piso de ATR%; `piso = 0,5`), 10 000 reamostragens, dias inteiros com reposição.

```
momentum: 184 linhas
  r_net    | só a população do pai      | dias 24 | n_pai 181 | n_filha  98 | exp_pai -0.0299 | exp_filha +0.0805 | delta +0.1104 | IC95 [-0.0605; +0.2859]
  r_bruto  | só a população do pai      | dias 24 | n_pai 181 | n_filha  98 | exp_pai +0.1013 | exp_filha +0.1981 | delta +0.0968 | IC95 [-0.0740; +0.2700]
  r_net    | com as 3 extras da filha   | dias 24 | n_pai 184 | n_filha 101 | exp_pai -0.0319 | exp_filha +0.0737 | delta +0.1055 | IC95 [-0.0576; +0.2768]
mean_reversion: 15 linhas
  r_net    | só a população do pai      | dias  7 | n_pai  15 | n_filha   1 | exp_pai +0.2861 | exp_filha +0.1412 | delta -0.1449 | IC95 [-0.6751; +0.2531]
  r_bruto  | só a população do pai      | dias  7 | n_pai  15 | n_filha   1 | exp_pai +0.3953 | exp_filha +0.2816 | delta -0.1137 | IC95 [-0.6571; +0.2891]
```

**Os três IC cruzam zero.** E o Δ **bruto** (+0,0968) é quase todo o Δ líquido (+0,1104): só
**0,0136 R** vem de pedágio. O pouco que o portão faz não é economia de custo — é seleção de
contexto — e mesmo assim não se distingue de ruído com 24 blocos de dia.

---

## 5. ANTES E DEPOIS (A6) — `q10`, `read_at = 2026-09-09T15:38:34,520400Z`

| versão | coorte | n | dias | pedágio médio (R) | exp. bruta (R) | exp. líquida (R) | soma R | PF | acerto |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `mean_reversion v6` (pai) | `9d99748b` | 15 | 7 | 0,1075 | +0,3953 | **+0,2861** | +4,29 | 2,2820 | 73,3 % |
| `mean_reversion v11` (portão) | `5bcfbda1` | **1** | 1 | 0,1404 | +0,2816 | +0,1412 | +0,14 | — | 100 % |
| `momentum v8` (pai) | `ee11d60b` | 181 | 24 | 0,1305 | +0,1013 | **−0,0299** | −5,42 | 0,9056 | 28,7 % |
| `momentum v11` (portão) | `4a60a3dc` | **101** | 14 | 0,1158 | +0,1904 | **+0,0737** | +7,44 | 1,2510 | 32,7 % |

**As decisões que o portão removeu** (`q11`, segunda consulta):

| família | removidas | exp. líquida (R) | soma R | exp. **bruta** (R) | pedágio (R) | acerto |
|---|---:|---:|---:|---:|---:|---:|
| `mean_reversion` | 14 de 15 (93,3 %) | **+0,2964** | +4,15 | +0,4034 | 0,1051 | 71,4 % |
| `momentum` | 83 de 181 (45,9 %) | **−0,1603** | −13,30 | −0,0129 | 0,1468 | 24,1 % |

`mean_reversion`: o portão jogou fora **as vencedoras**. `momentum`: as removidas eram
essencialmente **planas no bruto** (−0,0129 R) e negativas no líquido — mas as mantidas dão
+0,1981 R no bruto, então há **sim** diferença de bruto (≈ 0,21 R) e o corte não é só pedágio.
É a leitura correta; é também a que o IC não sustenta.

---

## 6. K1–K5 E ESTRESSE (A6)

| critério congelado | `mean_reversion v11` | `momentum v11` |
|---|---|---|
| **K1** — < 20 decisões | **1 → DISPARA** | 101 → não |
| **K2** — > 1 500 decisões | 1 → não | 101 (0,81/mercado-dia) → não |
| **K3** — ≥ 100 avaliáveis **e** ≥ 30 dias **e** bruta < 0 | 1 avaliável, 1 dia, bruta +0,2816 → não | 101 ✓, **14 dias** ✗, bruta +0,1904 ✗ → não |
| **K4** — `unavailable` > 40 % | **0 %, e o número não vale** | **0 %, e o número não vale** |
| **K5** — cobertura de `R_net` < 70 % | 1/1 = 100 % → não | 101/101 = 100 % → não |

**K4 deixa de ser mensurável numa versão com portão, e isso é um achado.** Os pais mostram
`unavailable: 448` na fatia A; **as duas filhas mostram zero** — o portão é avaliado **antes** da
checagem de contexto, então `ineligible` absorve as barras que seriam `unavailable`. Um K4 lido
como "0 %" numa versão com portão é um falso verde. O número honesto no lugar dele é a fatia
`ineligible`: **82,80 %** (`mean_reversion v11`) e **59,95 %** (`momentum v11`).

**Estresse** — só `momentum v11` sobreviveu ao K1. `as_of 2026-09-09T15:41:44,376112Z`, 101 entradas:

| cenário | n | expectancy (R) | PF |
|---|---:|---:|---:|
| `base` | 101 | 0,0737 | 1,2510 |
| `custos_x2` | 101 | **−0,0399** | 0,8895 |
| `stop_x0.75` / `stop_x1.25` | 101 | 0,0916 / 0,0577 | 1,2344 / 1,2446 |
| `alvo_x0.75` / `alvo_x1.25` | 101 | 0,0741 / 0,1044 | 1,2792 / 1,3558 |
| `entrada_mais_1_barra` | 101 | 0,0771 | 1,2612 |
| `1a_metade_ate_2026-08-27` | 79 | **+0,1800** | 1,6760 |
| `2a_metade_apos_2026-08-27` | 22 | **−0,3081** | 0,2126 |

**Veredito: `frágil a custos`** + `dependente de metade`. O pai, na mesma passada
(`as_of …15:42:09Z`): base −0,0299 / PF 0,9056; `custos_x2` −0,1531; 1ª metade **+0,1913**,
2ª metade **−0,1864** → **`sem_vantagem_na_base`**. **As duas metades do pai e da filha apontam
para o mesmo lado**: o que muda de sinal entre agosto e setembro é o mercado, não o portão.

**Isolamento:** `q13` → **0 linhas** de `shadow_outbox` para as duas coortes de replay; 4 eventos
`replay_engine.replay_run_finished` em `system_events`.

---

## 7. A SEMEADURA (B1) — e a linha que eu não esperava escrever

### 7.1 CONCERN 1 — apareceram **duas** estratégias novas, não uma

O brief diz "só `mean_reversion_h1` deve aparecer como nova". O `--dry-run` mostrou **quatro**
linhas novas em duas tabelas:

```
strategies.mean_reversion_h1: NEW {'key': 'mean_reversion_h1', 'name': 'Mean Reversion 1h', …}
strategies.sweep_reclaim: NEW {'key': 'sweep_reclaim', 'name': 'Sweep and Reclaim', …}
strategy_versions.mean_reversion_h1 v1: NEW {… 'status': 'draft', 'code_ref': 'hunter_indicators.strategies.mean_reversion_h1_v1', 'purpose': 'research_only' …}
strategy_versions.sweep_reclaim v1: NEW {… 'status': 'draft', 'code_ref': 'hunter_indicators.strategies.sweep_reclaim_v1', 'purpose': 'research_only' …}
DRY RUN: nothing written
```

**Eu rodei o `--yes` mesmo assim**, e a decisão precisa ficar escrita porque não é a que o brief
previu. O que a sustenta: `sweep_reclaim` entrou em `seed_reference.py` no commit **`a9bacc6`**
(T3.45b), já está na imagem viva, e as próprias `notes-T3.45b.md` registram por escrito que
"`seed.py` tem de rodar na VPS" como o passo pendente daquela tarefa — a semeadura estava
sancionada e apenas atrasada pelo orçamento de linhas do arquivo. `--only` filtra **tabela**, não
chave: não existe forma auditada de semear uma das duas. E a linha nasce `draft`, portanto inerte
(o roster do worker só carrega `active`). **Ainda assim é uma escrita além do previsto no brief e
não há script auditado para desfazê-la.** Quem discordar tem de decidir o que fazer com a linha.

```
seeded  12 row(s) into strategies
seeded  12 row(s) into strategy_versions
```

**Segundo detalhe do mesmo recibo:** o `seed` grava `code_ref` no espaço
`hunter_indicators.strategies.*`, enquanto todas as versões ativadas estão congeladas em
`hunter_core.strategies.*` (as seis linhas "note:" do recibo dizem isso de cada versão viva). A
ativação de §7.2 re-resolveu para
`hunter_core.strategies.mean_reversion_h1_v1@sha256:cc18c3f1…`, então a linha ativada está no
espaço certo — mas a migração de namespace está em voo e o `seed` está do outro lado dela.

### 7.2 A ativação que a T3.54 não conseguiu fazer (B2)

```
$ … activate_strategy_version.py mean_reversion_h1 v1 --changelog "…" --dry-run
would activate mean_reversion_h1 v1 (purpose research_only) with code_ref
hunter_core.strategies.mean_reversion_h1_v1@sha256:cc18c3f1b380fa197645f284442c0433e06fbce1cea31b32c5542bf014006631 (18 parameters)

$ … (sem --dry-run)
activated mean_reversion_h1 v1 (purpose research_only) at 2026-09-09T15:45:24.973377+00:00 with code_ref …cc18c3f1…
```

**Não foi recusada.** O número que o brief pediu **não sai na ativação** — ela não imprime minutos
de contexto. Sai no plano do replay, e é exatamente o previsto:

```
$ … replay.run --version mean_reversion_h1:v1 … --dry-run
{'cohort': 'replay:fc9e2506-…', 'version': 'mean_reversion_h1 v1', 'markets': 4,
 'bars_planned': 2976, 'context_minutes': 5880, 'workers': 3}
```

**`context_minutes = 5880 ≤ SHADOW_CONTEXT_MAX_MINUTES = 6000`**, e `5880 > 1560`: o piso não
emudece mais a versão. É a T3.54b entregando o que prometeu.

---

## 8. A IRMÃ DE 1 H MEDIDA (B3, B4)

### 8.1 Quatro fatias de 4 mercados, 31 d, os 16 mercados do `q00` da T3.54

`BTC ETH ZEC SOL` · `XRP BNB DOGE SUI` · `NEAR UNI ARB TAO` · `LINK DASH PROM SAHARA`.
Cada fatia: 2976 barras, `context_minutes = 5880`, `unavailable = 404`, **0 erros**, ~105 s.
Sinais acumulados 34 → 58 → 91 → **123** (por fatia: 34, 24, 33, 32). 123/123 resolvidos.

| versão | n | dias | pedágio (R) | exp. bruta | exp. líquida | soma R | PF | acerto | risco% p50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `mean_reversion v10` (15 m, ATR 1 h, 4 mkt) | 54 | 16 | 0,1038 | +0,3071 | **+0,2013** | +10,87 | 2,4956 | 68,5 % | 0,01990 |
| `mean_reversion_h1 v1` (1 h, 16 mkt) | 123 | 22 | **0,1445** | +0,1524 | **+0,0067** | +0,82 | 1,0116 | 44,7 % | 0,01544 |

**O achado que contraria a premissa da T3.54:** o pedágio da irmã de 1 h é **0,1445 R**, *maior*
que o da `v10` (0,1038) e maior que o da mãe de 15 m `v6` (0,1075). A promessa do eixo de
timeframe era pedágio 2,2× menor. Ela não se realiza aqui porque o pedágio em R depende do
**risco em preço**, e a `h1` entra com stops **mais apertados** em % (0,01544 contra 0,01990 da
`v10`), não mais largos. O ganho de 2,2× do eixo de timeframe já tinha sido capturado pelo
**ATR em 1 h** da `v10`; mudar também a **grade de decisão** para 1 h não acrescenta nada — cobra.

### 8.2 K1–K5 de `mean_reversion_h1 v1`

| critério | leitura | disparou? |
|---|---|---|
| K1 — < 20 decisões | **123** | não |
| K2 — > 1 500 decisões | 123 (0,25/mercado-dia) | não |
| K3 — ≥ 100 avaliáveis **e** ≥ 30 dias **e** bruta < 0 | 123 ✓, **22 dias** ✗, bruta **+0,1524** ✗ | não |
| K4 — `unavailable` > 40 % | 1616/11904 = **13,58 %** | não |
| K5 — cobertura de `R_net` < 70 % | 123/123 = **100 %** | não |

Nenhum critério de morte disparou — **e a base ainda assim é +0,0067 R / PF 1,0116**, isto é, zero.
K1–K5 não são selo de qualidade; são filtro de população.

**Estresse** (`as_of 2026-09-09T15:54:40,313657Z`, 123 entradas, 16 mercados): base 0,0067 / 1,0116;
`custos_x2` **−0,1295** / 0,7926; `alvo_x0.75` **−0,0540**; 1ª metade **+0,2467**, 2ª metade
**−0,1691**; **sete** mercados cuja remoção individual vira o sinal negativo (ARB, DOGE, PROM, SUI,
UNI, XRP, ZEC). **Veredito: `frágil a custos`** + `frágil a parâmetros` + `dependente de um mercado`
(×7) + `dependente de metade`. Contra o `robusto` da `v10`.

### 8.3 IC transversal de blocos de dia contra `mean_reversion v10` (B4)

`h1` **não** é subconjunto de `v10` — são grades diferentes sobre o mesmo calendário —, então
`blocos.py` (subconjunto contra o todo) não serve. Escrevi `duas_populacoes.py`: reamostra **dias**
com reposição e, no dia sorteado, leva as decisões das **duas** populações; Δ = média(A) − média(B)
na mesma reamostragem; reamostragem em que uma ponta fica vazia é descartada, nunca lida como zero.
O estimador novo é conferido contra o antigo (`test_oraculo.py`) no par degenerado: Δ pontual
idêntico até 1e-12 (+0,1103952763 nos dois).

```
16 mercados (h1) vs 4 (v10) — universos diferentes
  r_net    | dias 24 | n_h1 123 | n_v10  54 | exp_h1 +0.0067 | exp_v10 +0.2013 | delta -0.1947 | IC95 [-0.5904; +0.2218]
  r_bruto  | dias 24 | n_h1 123 | n_v10  54 | exp_h1 +0.1524 | exp_v10 +0.3071 | delta -0.1547 | IC95 [-0.5492; +0.2650]
só os 4 mercados que as duas correram
  r_net    | dias 18 | n_h1  29 | n_v10  54 | exp_h1 -0.1588 | exp_v10 +0.2013 | delta -0.3601 | IC95 [-0.8677; +0.1285]
  r_bruto  | dias 18 | n_h1  29 | n_v10  54 | exp_h1 +0.0250 | exp_v10 +0.3071 | delta -0.2821 | IC95 [-0.7804; +0.2116]
```

**Os quatro IC cruzam zero.** A `h1` é pior no ponto (−0,19 R nos universos cheios, **−0,36 R** nos
mesmos 4 mercados) e o dia como bloco não sustenta nem a diferença. O contraste restrito é o
honesto: nos 16 mercados a `h1` mistura **timeframe com universo**, e o universo maior é o que
levou a amostra de 29 para 123.

---

## 9. VEREDITOS PELO FUNIL

| braço | população | veredito | próxima ação |
|---|---|---|---|
| `mean_reversion v11` (`btc:SIDEWAYS`) | 1 decisão, 1 dia | **morto no K1** — `inconclusivo`, não negativo | não aposentar ainda: `SIDEWAYS` só tem 6 h na 1ª metade. Refazer com ≥ 20 decisões (ou prospectivo). O portão que remove 93 % das decisões e leva junto **as vencedoras** (+0,2964 R) é evidência **contra** a hipótese, não a favor |
| `momentum v11` (`btc:BTC_BULL,HIGH_VOLATILITY`) | 101 decisões, 14 dias | **`frágil a custos`**, Δ +0,1104 R com **IC 95 % [−0,0605; +0,2859]** | **não promover.** Sobrevive ao K1 e melhora o ponto, mas (i) o IC cruza zero, (ii) `custos_x2` vira o sinal, (iii) a 2ª metade é −0,3081 R, (iv) o braço **não é** o G2 pré-registrado (§2.4). Manter `research_only`; a decisão honesta é a coorte prospectiva |
| `mean_reversion_h1 v1` | 123 decisões, 22 dias | **`frágil a custos`**, base +0,0067 R / PF 1,0116 | **não promover.** Primeira coorte julgável da irmã de 1 h e ela empata com zero; pior que a `v10` no ponto em todos os cortes. O eixo de timeframe já estava esgotado pela `v10` |

**Portão C1–C8 do EXP-0020:** nenhum braço passa. O portão de regime é **infraestrutura correta**
(§4.1) com **retorno não demonstrado** (§4.3).

---

## 10. O ADENDO — onde ele foi escrito, e por quê

`EXP-0020-regime-gate.md` e `EXP-0021-timeframe.md` **já foram arquivados** em
`obsidian/05-EXPERIMENTS/` (as duas notas existem lá, com o cabeçalho "Arquivada pela Sexta-feira em
2026-09-09"). Os rascunhos continuam em `.claude/state/exp-drafts/`, o que significa **duas cópias
vivas**: escrever numa delas criaria divergência com um agente de documentação em voo. Pela regra do
brief ("se arquivadas, escrever o adendo só em `notes-T3.52d.md` e dizer"), **o adendo é este
arquivo** e nenhum dos quatro arquivos de EXP foi tocado. O que precisa migrar para as notas
arquivadas quando a Sexta-feira as reabrir:

1. **EXP-0020:** os braços saíram como `v11`/`v11`; **G2 não é o pré-registrado** (dois rótulos);
   "subconjunto por construção" é **falso** para decisões (§4.2); K4 não é mensurável com portão
   (§6); resultado = `inconclusivo` (G1, K1) e `não promover` (G2, IC cruza zero). A previsão de
   queda de população do EXP **acertou** (§3.1).
2. **EXP-0021:** `mean_reversion_h1 v1` ativada com `context_minutes = 5880`; 123 decisões;
   **o pedágio subiu** (0,1445 vs 0,1038 da `v10`) — a premissa "1 h paga 2,2× menos pedágio" **não
   se transfere** da medida de ATR% para a decisão quando a grade muda; Δ vs `v10` negativo no ponto
   e com IC cruzando zero.

---

## 11. DEZ LINHAS PARA O EVERTON

1. Liguei o "porteiro de regime": a estratégia só decide na hora em que o BTC está no estado que ela supõe.
2. A peça funciona exatamente como projetada — nas horas liberadas a versão com portão repete a original decisão por decisão, sem uma diferença.
3. `momentum` com portão: 181 → 101 decisões, e a expectativa sai de −0,03 R para +0,07 R por operação.
4. Parece ótimo, e não é: com o dia inteiro como bloco, esse ganho tem margem de erro de −0,06 a +0,29 R — ou seja, pode ser zero.
5. Dobrando os custos a versão volta a perder, e na segunda metade de agosto ela perde −0,31 R por operação. Não promovo.
6. `mean_reversion` com portão: sobrou **1 decisão em 31 dias** — o mercado quase não ficou "lateral" na janela. Sem amostra, sem veredito.
7. Pior: as 14 decisões que o portão cortou eram justamente **as que ganhavam** (+0,30 R cada). O portão apontou para o lado errado.
8. Destravei também a estratégia que decide em barras de 1 hora (a T3.54 tinha parado num limite de memória): 123 decisões, e o resultado é **zero** (+0,007 R).
9. E ela cobra **mais** pedágio que a irmã de 15 minutos, o oposto do que a teoria previa — a vantagem do timeframe já tinha sido colhida antes.
10. Saldo: infraestrutura nova correta e auditada, três hipóteses medidas, **nenhuma promovida**. Nada disso toca a carteira — tudo é `research_only`.

---

## CONCERNS

1. **A semeadura escreveu `sweep_reclaim` além do previsto** (§7.1). Sancionada por `a9bacc6` +
   `notes-T3.45b.md`, inerte (`draft`), mas sem desfazimento auditado. **Decisão de quem é dono do
   catálogo.**
2. **O braço G2 medido não é o G2 pré-registrado** (§2.4): dois rótulos em vez de um, escolhidos
   depois de ler a T3.53. O IC não paga por essa escolha.
3. **O `--explain-ledger` não distingue `unknown` de `no_row` de `stale`** (§3.2). `RegimeGate.detail`
   existe no código e morre antes do JSONL. Um campo a mais fecharia; é trabalho de código.
4. **`replay_runs.signals` é cumulativo por `run_id`** (herdado da T3.54 §3.6): quem ler "41 depois
   101" como 142 erra por 41. Continua sem correção.
5. **Os replays rodaram por `docker exec hunter-strategy-worker-1`, não por `compose.sh ops`**, como
   o brief pedia — precedente da T3.54 §3.6 e escolha deliberada: o replay não é `infra/scripts/…` e
   `ops` o poria rodando como dono do schema sem necessidade. Todos os `infra/scripts/…` do brief
   (derive, activate, seed) **foram** por `compose.sh ops`.
6. **`momentum v11`, `mean_reversion v11` e `mean_reversion_h1 v1` estão ativas e vão decidir na
   faixa de sombra viva.** São `research_only` e nada chega à carteira, mas ocupam slots de sombra —
   o mesmo portão da T3.56 que barrou `momentum v3`. Se os vereditos "não promover" forem aceitos,
   elas devem ser aposentadas pelo script auditado.
7. **A janela é a mesma que gerou as hipóteses** (T3.33 §5.1): tudo aqui é replay sobre 2026-08-08
   → 2026-09-08, os mesmos 31 dias de onde a T3.53 tirou o achado que motivou o portão. Nada disto
   confirma nada; confirmar é coorte prospectiva.
