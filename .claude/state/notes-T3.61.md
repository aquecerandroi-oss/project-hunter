# notes-T3.61 — a linha `paper` não se move com o instrumento que existe: **PAREI antes de escrever**

**Data:** 2026-09-09, janela 16:16–16:30 BRT (**19:16–19:30 UTC**).
**Owner:** quant-engineer. **Origem:** Everton, 2026-09-09 15:50 BRT — "enquanto a estratégia tiver
funcionando vamos estar em cima dela"; a linha paper deveria sair de `momentum v3` para
`mean_reversion v6`.
**Continuação de** `.claude/state/notes-T3.56.md` §4 e CONCERN 2 (o portão de slots abertos).

**Árvore local:** `HEAD = d450038`. **Nada commitado, nada indexado, nenhum `.env*` tocado, nenhum
container parado, recriado ou reiniciado. Nenhum `git pull` na VPS.**
**Escritas na VPS: ZERO.** Só `--dry-run` e leituras em `repeatable read read only`. Nenhum SQL de
escrita, nenhum `UPDATE` manual. `ENABLE_PAPER_AUTONOMY` continua `false` (medido, §6).

---

## STATUS

**BLOCKED** — no ponto exato em que o brief mandou parar.

O item (1) do brief dizia: *"se NÃO existir caminho auditado para mudar o `purpose` de uma versão já
ativa, PARE e reporte a lacuna exata (não use SQL)"*. **Não existe.** É o que o `--help` da imagem
implantada mostra e o que o código confirma. Não escrevi nada.

| # | Pedido do brief | Resultado |
|---|---|---|
| 1 | achar a via sancionada para mudar a linha paper | **Não há** via para mudar `purpose` de versão ativa. Não existe `--purpose`. A única via auditada que produz uma linha paper é `--paper-line`, e ela **cria uma versão nova** (`mean_reversion v14`), não promove a `v6`. §2, §3 |
| 2 | aposentar `momentum v3` — até 6 tentativas em ~10 min | **10 amostras em 10,5 min: nunca chegou a zero** (7,7,7,6,6,6,6,6,6,6). Duas corridas do próprio script (`--dry-run`), as duas recusadas. §4 |
| 2b | o script aceita duas linhas paper? | **Aceita**, quando são de estratégias diferentes: a unicidade de `paper_line()` é por `strategy_id`. `momentum v3` (paper) e uma `mean_reversion` paper poderiam coexistir. §3.2 |
| 3 | promover `mean_reversion v6` a `paper` | **NÃO FEITO** — e é impossível como escrito: nenhuma ferramenta muda o `purpose` de uma linha congelada. §2 |
| 4 | verificar que a ponte segue a nova linha | **A ponte não segue ninguém hoje:** `SELECT count(*) FROM agents` = **0**. §5 — a lacuna que ninguém tinha medido nesta rodada |

**A frase honesta:** mesmo que eu tivesse escrito tudo o que o brief pediu, **a linha da carteira não
teria mudado**, porque a carteira não segue `purpose` — ela segue `agents.strategy_version_id`, e essa
tabela está vazia (ACTIVATION.md §8a nunca foi executada).

---

## FILES

| arquivo | o quê |
|---|---|
| `C:\dev\project-hunter\infra\scripts\sql\research\2026-09-09-t361-q00-linha-paper.sql` | a leitura única (catálogo, as duas versões do ato, exposição aberta, vínculo `agents`, mérito por coorte, estado da ponte) |
| `C:\dev\project-hunter\.claude\state\notes-T3.61.md` | este arquivo |

Nenhum arquivo de código tocado. Nenhuma ferramenta nova escrita.

---

## 1. O QUE ESTÁ IMPLANTADO (conferido antes de qualquer coisa)

```
$ ssh hunter-vps 'date -u; date; cd /opt/project-hunter && git rev-parse --short HEAD; \
    docker images hunter-api --format "{{.Tag}}" | head -5; docker ps --format "{{.Names}}\t{{.Image}}\t{{.Status}}"'
Wed Sep  9 19:16:10 UTC 2026                          <- 16:16:10 Brasília
d450038
d450038 / 3c9a8d8 / d21a11d / f1475c4 / 188ff72
hunter-web-1                 hunter-web:d450038   Up 47 minutes (healthy)
hunter-api-1                 hunter-api:d450038   Up 47 minutes (healthy)
hunter-strategy-worker-1     hunter-api:3c9a8d8   Up 57 minutes (healthy)
hunter-execution-worker-1    hunter-api:d21a11d   Up 4 hours (healthy)
hunter-scanner-worker-1      hunter-api:d21a11d   Up 4 hours (healthy)
hunter-market-worker-{1,2,3,spot}-1  hunter-api:d21a11d  Up 4 hours (healthy)
hunter-caddy-1 / hunter-postgres-1 / hunter-redis-1  Up 2 days (healthy)
```

Os três arquivos que decidem esta tarefa são **byte a byte** os do commit `d450038`, na imagem e no
git — conferido, não assumido:

```
$ ssh hunter-vps 'docker run --rm --entrypoint sha256sum hunter-api:d450038 \
    /app/infra/scripts/activate_strategy_version.py \
    /app/services/strategy-worker/hunter_strategy_worker/paper_line.py \
    /app/services/strategy-worker/hunter_strategy_worker/deprecate.py'
a96042568f2a8412cd9620b281e50a4bb47576a00e9009e467b5462d021f5ff3  activate_strategy_version.py
d33ea6f145e5d27fa4c0437794962ab568775916368bd1d198e453e114b38372  paper_line.py
7b84d4c328d07bb80ae66cdd3a83da75a124c8434b9a15eb03c48ec5e25b9601  deprecate.py

$ git show d450038:<cada um> | sha256sum   ->  a9604256… / d33ea6f1… / 7b84d4c3…   (idênticos)
```

---

## 2. A LACUNA, EXATA — o `--help` da imagem que rodaria o ato

```
$ ssh hunter-vps 'cd /opt/project-hunter && export MARKET_SHARDS=4 MARKET_SPOT=1; \
    bash infra/vps/compose.sh ops python infra/scripts/activate_strategy_version.py --help'
options:
  -h, --help
  --changelog CHANGELOG   why this version is being activated
  --dry-run               run every check, write nothing
  --supersede             retire this frozen version and activate version+1 with the current code_ref
  --paper-line            derive a draft purpose=paper line (next free v<n>) from this frozen
                          research version; activates nothing (T3.15, D10)
  --deprecate             set status=deprecated on this active version (T3.39); refuses purpose=live,
                          and refuses purpose=paper without --force-paper and a clean
                          positions/shadow_episodes check
  --successor SUCCESSOR   --deprecate only: the version (v<n>) that replaces this one …
  --force-paper           --deprecate/--supersede only: required to retire a purpose=paper version
exit=0
Wed Sep  9 19:16:48 UTC 2026
```

**Não existe `--purpose`.** O comando hipotetizado pelo brief
(`mean_reversion v6 --purpose paper --force-paper`) não existe em nenhuma forma; `--force-paper`
sozinho é rejeitado pelo próprio `argparse` (`--force-paper requires --deprecate or --supersede`,
`activate_strategy_version.py::main`). E o código fecha a porta por três lados:

1. **`activate()`** nunca escreve `purpose`: o `UPDATE` dele lista `status, activated_at, code_ref,
   parameters_schema, default_parameters, params_format, changelog` — e ainda casa
   `WHERE id = :id AND activated_at IS NULL`. Numa versão já ativa a resposta é
   `"was already activated at …; nothing to do"`.
2. **`paper_line()`** só escreve `purpose` **num `INSERT`** de linha nova — é o comentário do próprio
   módulo: *"`purpose` is written only here, on the migration/owner connection: `0010` revoked it
   from every application role"*.
3. **`deprecate()`/`supersede()`** movem `status`, nunca `purpose` — e `supersede()` **copia** o
   `purpose` do pai de propósito (T3.39b, ALTA-2).

**Consequência de esquema, não de política:** `purpose` é congelado pela primeira ativação
(DATABASE.md §16.1; a trigger da `0002` deixa mutável só `status`). Uma versão ativa `research_only`
**nunca** vira `paper`. Não é lacuna de flag: é a garantia de que uma coorte não muda de destino no
meio do experimento. Nenhum SQL foi usado para contornar isso, como o brief manda.

---

## 3. O QUE **existe** — e por que não é o que o brief pediu

### 3.1 `--paper-line`: cria uma versão nova, não promove a `v6`

`--dry-run` (não escreve nada; recibo verbatim):

```
$ … activate_strategy_version.py mean_reversion v6 --paper-line \
      --changelog "T3.61 DRY-RUN: sondagem do caminho auditado para mover a linha paper (nada escrito)" --dry-run
Wed Sep  9 19:18:11 UTC 2026
 Container hunter-ops-run-7e14415b2cc4 Created
2026-09-09 19:18:15 [debug] shadow_version_bound_by_code_ref module=mean_reversion_v1 strategy=mean_reversion_v6
would derive mean_reversion v14 (purpose paper, draft, not activated) from v6 at code_ref
hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f
(18 parameters copied)
exit=0
Wed Sep  9 19:18:15 UTC 2026
```

O caminho **funciona** (o `code_ref` congelado da `v6` bate com o desta imagem, os 18 parâmetros
copiam), mas o que ele produz é **`mean_reversion v14`**, `draft`, `purpose=paper` — uma linha nova
com **população zero**. O mérito medido (§7) é da coorte da `v6`, que continua `research_only` e
continua correndo ao lado. Chamar a `v14` de "a `v6` promovida" seria falso: é uma cópia byte a byte
dos parâmetros com id, coorte e histórico novos. Ativá-la seria **outra** corrida auditada
(`activate`, rota derivada).

### 3.2 Duas linhas `paper` ao mesmo tempo: o script **aceita** (entre estratégias diferentes)

A pergunta do brief tem resposta no código e no `--dry-run` acima. A checagem de unicidade de
`paper_line()` é

```sql
SELECT version FROM strategy_versions
 WHERE strategy_id = :strategy_id AND purpose = 'paper' AND status <> 'deprecated'
```

— **por `strategy_id`**. Como `momentum v3` pertence a outra estratégia, ela **não** bloqueou a
derivação da `mean_reversion` (o `--dry-run` passou com a `momentum v3` viva e paper), e
`activate_derived()` não tem nenhuma checagem cruzada de linha paper. Ou seja: **o sistema
permitiria `momentum v3` e `mean_reversion v14` ativas e `paper` ao mesmo tempo** — o que também
significa que "aposentar a antiga" **não é pré-requisito técnico** de nada; é decisão de carteira.
Duas linhas paper com dois vínculos `agents` seriam duas coortes disputando o mesmo capital, e o
motor de risco não sabe que elas são "a mesma linha em transição".

---

## 4. O PORTÃO DE SLOTS — dez amostras em 10,5 min, nunca zerou

Duas corridas do próprio script (`--dry-run`, nada escrito), no começo e no fim da janela:

```
Wed Sep  9 19:18:26 UTC 2026     <- 16:18:26 BRT
 Container hunter-ops-run-e659acc11eb3 Created
REFUSED: momentum v3 still has skin in the game: 7 shadow slot(s) tracking an open outcome.
Close or hand them off before deprecating the paper line.
exit=1

Wed Sep  9 19:30:11 UTC 2026     <- 16:30:11 BRT
 Container hunter-ops-run-e56dfd4cf637 Created
REFUSED: momentum v3 still has skin in the game: 6 shadow slot(s) tracking an open outcome.
exit=1
```

Entre as duas, dez amostras da **mesma consulta** que `open_paper_exposure()` usa
(`shadow_episodes.open_outcome_signal_id IS NOT NULL`), em transação `repeatable read read only`:

| leitura (UTC) | BRT | slots abertos |
|---|---|---|
| 19:19:22 | 16:19:22 | 7 |
| 19:21:17 | 16:21:17 | 7 |
| 19:21:28 | 16:21:28 | 7 |
| 19:23:23 | 16:23:23 | 6 |
| 19:23:33 | 16:23:33 | 6 |
| 19:24:53 | 16:24:53 | 6 |
| 19:26:13 | 16:26:13 | 6 |
| 19:26:35 | 16:26:35 | 6 |
| 19:28:15 | 16:28:15 | 6 |
| 19:29:55 | 16:29:55 | 6 |

**Nunca zerou, e não vai zerar sozinho** — é o CONCERN 2 da T3.56 reconfirmado 4,5 h depois: a versão
continua viva no roster, então fecha um slot e abre outro. O portão exige um estado (`zero slots`)
que só existe se a versão parar de decidir **antes**, e a única forma de ela parar de decidir é sair
do roster, que é exatamente o que o portão está barrando. **Nada foi forçado.** Posições abertas:
**0** em todas as leituras (nada executou; autonomia desligada).

---

## 5. A DESCOBERTA QUE MUDA O ENUNCIADO: `agents` está VAZIA

```
== 5. o vinculo agents (quem a ponte seguiria) ==
 agent_id | name | status | allowed_directions | versao | purpose | portfolio_id | deleted_at
----------+------+--------+--------------------+--------+---------+--------------+------------
(0 rows)
```

`bridge_repo._SIGNAL_SELECT` só considera candidato um sinal cuja versão **a carteira roda**:

```sql
AND EXISTS (SELECT 1 FROM agents a WHERE a.organization_id = :org AND a.portfolio_id = :pf
            AND a.strategy_version_id = s.strategy_version_id AND a.deleted_at IS NULL)
```

e `bridge_screen` só admite `purpose = 'paper'` **depois** disso. Ou seja, "a linha que a ponte
seguiria" é a **interseção** de duas coisas:

1. `strategy_versions.purpose = 'paper'` + `status = 'active'` → hoje: `momentum v3`, e só o
   `activate_strategy_version.py` escreve isso (criando versão nova);
2. uma linha em `agents` ligando essa versão à carteira `ever` → hoje: **nenhuma**.

**Não existe script auditado que escreva `agents`.** Procurei:
`grep -rn "INSERT INTO agents" infra/ services/ apps/ packages/` só acha `tests/builders.py` e
`tests/shadow_builders.py`. `open_paper_wallet.py` abre carteira e não toca `agents`;
`replicate_strategy_version.py` diz explicitamente que nunca chega perto. A única via documentada é o
**SQL do ACTIVATION.md §8a**, que a própria doc define como *"comando auditado que o operador roda —
ninguém mais"* — e que este brief me proíbe de usar. **A segunda metade do ato é do Everton, por
definição.**

---

## 6. A PONTE NÃO MUDOU (autonomia desligada) — medido às 19:18:56Z = 16:18:56 BRT

```
== hb:execution:paper ==            == hb:strategy:shadow ==
paper_autonomy   false              cohort           prospective
kill_switch      ACTIVE             outbox_pending   0
open_positions   0                  outbox_lag_s     0.0
pending_requests 0                  open_trackings   119
mark_quality     1                  evaluated_bars   16248
equity           19333.0111164813   evaluations_by_state {"not_triggered":7209,"ineligible":2768,
last_mtm         2026-09-09 19:18:00.007109+00                     "unavailable":6187,"triggered":84}
errors           0                  errors           0

== /ready ==  200  {"database":true,"redis":true}
```

E o funil, na leitura das 19:17:35Z:

```
 outbox_total | pendentes |         ultimo_evento
--------------+-----------+-------------------------------
         8166 |         0 | 2026-09-09 19:16:15.829045+00
 propostas_total: 0 | ordens: 0 | fills: 0 | posicoes: 0
```

`shadow_outbox` drena normalmente (0 pendentes); **0 propostas, 0 ordens, 0 fills, 0 posições** — o
estado esperado com `ENABLE_PAPER_AUTONOMY=false` **e** com `agents` vazia. Nada do que eu fiz tocou
nisso: minhas duas únicas linhas em `system_events` são recusas de `--dry-run` (§8).

---

## 7. O MÉRITO, MEDIDO POR MIM (não copiado do brief) — `read_at 2026-09-09T19:17:35Z`

Desfecho `terminal`, `r_multiple` não nulo, coorte por `supporting_features->>'cohort'`
(`replay:%` → replay, resto → prospective):

| versão | coorte | n | expectância líquida | soma R | ganhos | profit factor |
|---|---|---|---|---|---|---|
| `mean_reversion v6` | prospective | **30** | **+0,2116 R** | +6,35 | 18 | 1,550 |
| `mean_reversion v6` | replay | **15** | **+0,2861 R** | +4,29 | 11 | **2,282** |
| `momentum v3` (paper) | prospective | **485** | **−0,2100 R** | −101,87 | 168 | 0,583 |

### 7.1 Onde o brief e a medição divergem

| | brief (15:50 BRT) | medido (19:17Z) | leitura |
|---|---|---|---|
| `mean_reversion v6` replay | +0,29 R, PF 2,28 | **+0,2861, PF 2,282**, n **15** | idêntico — e o n é **15** |
| `mean_reversion v6` prospectiva | +0,39 R, 16 resultados | **+0,2116 R, n 30** | **o n dobrou e a expectância caiu 46 %** |
| `momentum v3` prospectiva | −0,24 R, n 453 | **−0,2100 R, n 485** | mesma direção, n +7 % |

**A leitura honesta:** a `mean_reversion v6` continua **muito** melhor que a `momentum v3` (sinal
oposto, PF 1,55 contra 0,58), mas a evidência dela é K1 — **n=30 e n=15**. Os ~14 desfechos novos
desde o brief derrubaram a expectância prospectiva de 0,39 para 0,21, que é o comportamento típico de
uma amostra pequena voltando para a média. Isso não desfaz a decisão do Everton; muda o tamanho da
aposta que ela justifica hoje.

---

## 8. O QUE ESTE TRABALHO ESCREVEU NA VPS (a resposta completa: duas recusas de `--dry-run`)

```
 created_at (UTC)              | level   | event                               | msg
 2026-09-09 19:18:29.743616+00 | warning | strategy_version_activation_refused | momentum v3 still has skin in the game: 7 shadow slot(s)…
 2026-09-09 19:30:14.906502+00 | warning | strategy_version_activation_refused | momentum v3 still has skin in the game: 6 shadow slot(s)…
```

São as duas linhas de auditoria que **toda** corrida do script deixa (T3.15c), inclusive `--dry-run`
recusado. Nenhuma outra escrita minha. Estado final conferido na mesma transação:

```
 versoes_paper_ativas: 1     (momentum v3, intacta)
 agents:               0
 mean_reversion_versoes: 13  (nenhuma v14 nasceu)
```

### 8.1 Havia outro operador escrevendo na mesma janela

No mesmo `system_events`, entre as minhas duas linhas:

```
 2026-09-09 19:21:11.969512+00 | warning | strategy_version_activation_refused | successor momentum momentum v11 does not exist
 2026-09-09 19:21:15.939098+00 | warning | strategy_version_activation_refused | successor momentum momentum v11 does not exist
 2026-09-09 19:21:38.424335+00 | info    | strategy_version_deprecated         | momentum v8 (purpose research_only) deprecated at 19:21:38…
```

**Não fui eu** (nunca rodei nada sem `--dry-run`, e nunca toquei a `momentum v8`). Alguém aposentou a
`momentum v8` às 16:21:38 BRT enquanto eu media. Registro porque muda a leitura de qualquer tabela de
roster desta janela — e porque duas tarefas escrevendo no mesmo roster sem se ver é como se perde um
experimento.

---

## 9. O QUE FALTA PARA O ATO ACONTECER — as três decisões que são do Everton

1. **A linha paper nova é uma versão nova.** `mean_reversion v14` (`--paper-line` da `v6`, depois
   `activate`) carrega os parâmetros da `v6` byte a byte, mas nasce com histórico zero. O experimento
   que acompanhar a carteira acompanha a `v14`, não a `v6` — as duas correm em paralelo e só a `v6`
   acumula a série de pesquisa. É o custo estrutural de `purpose` ser congelado.
2. **`momentum v3` provavelmente não vai poder ser aposentada** enquanto estiver no roster (§4). Duas
   saídas honestas, as duas do operador: (a) deixar as duas linhas paper coexistirem — o script
   permite (§3.2) — e simplesmente não criar vínculo `agents` para a `momentum v3`; ou (b) mudar o
   portão de `deprecate()` para exigir "zero **posições**" e deixar os slots de shadow em voo seguirem
   até o desfecho (que é o que a própria ACTIVATION.md §7b já diz do roster: *"aposentar para a
   decisão nova, não a operação em voo"*) — mas isso é **mudança de código auditado com revisão do
   risk-engine-guardian**, não uma flag, e não era o escopo desta tarefa.
3. **O vínculo `agents` (ACTIVATION.md §8a) nunca foi feito.** Sem ele, mexer em `purpose` não muda
   nada do que a ponte faria: `agents = 0` recusa tudo antes de olhar o rótulo. Se o objetivo é "a
   carteira segue a `mean_reversion`", o ato que **de fato** decide isso é o SQL do §8a com o
   `strategy_version_id` da linha paper nova — e a doc diz, com todas as letras, que é o Everton quem
   roda.

**Regra de saída do brief** ("7 dias corridos negativos → volta a `research_only`"): registro que ela
**não é implementável como escrita** — nada volta de `paper` para `research_only`, porque `purpose` é
congelado. A forma real da mesma regra é: *7 dias corridos negativos → `--deprecate --force-paper` na
linha paper* (com o portão da §4 no caminho), ou pausar o vínculo `agents` (`status='paused'`,
ACTIVATION.md §8a), que é reversível e instantâneo. Vale escolher qual das duas **antes** de ligar.

---

## 10. CONCERNS

1. **O portão de slots é um impasse estrutural, não azar de janela** (§4): 10 amostras em 10,5 min,
   mínimo 6. A T3.56 já tinha registrado o mesmo com 5–6. Enquanto ninguém decidir entre "mudar o
   portão" e "conviver com duas linhas paper", `momentum v3` é imortal.
2. **`agents` vazia torna toda a discussão de `purpose` teórica** (§5) — e isso não estava no brief,
   que assumia que trocar a linha paper mudaria o que a ponte seguiria.
3. **A evidência da `mean_reversion v6` encolheu ao ser remedida** (§7.1): +0,39 R → +0,2116 R com o
   dobro do n. Ainda é a melhor da família por larga margem; ainda é n=30.
4. **Outro operador escreveu no roster durante a minha janela** (§8.1).
5. **Meu arquivo de leitura foi varrido para o commit de outra tarefa.** Eu não commitei nada; o
   `973e1ac` (T3.59c + T3.57b, 16:26:24 BRT) levou junto o
   `infra/scripts/sql/research/2026-09-09-t361-q00-linha-paper.sql`, que estava `??` na árvore
   compartilhada. É exatamente o incidente que a regra "commit por pathspec, nunca `add` de
   diretório" existe para evitar — terceira ocorrência registrada. O `notes-T3.61.md` continua
   `??` (não commitado).
