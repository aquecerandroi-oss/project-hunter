# notes-T3.50 — toda operação concluída do Lab ganhou o seu gráfico traçado

**Quando:** 2026-09-08, 19:25–20:20 BRT (22:25–23:20 UTC). **Owner:** quant-engineer.
**Base:** `main @ 2e39774`. **Nada foi commitado.** **Nada foi escrito na VPS** (uma transação
`repeatable read read only` por leitura, consulta pelo stdin do `psql`, resultado pelo stdout do
`ssh`). **Nenhum container foi tocado.** **`matplotlib` NÃO entrou em nenhum `pyproject.toml`**
(`uv run --with matplotlib`, como na T3.34). **Nada tocado** em `.env*`, `apps/**`, `services/**`,
`packages/**`.

---

## STATUS

**DONE_WITH_CONCERNS.** Os seis itens do brief estão entregues e rodados de ponta a ponta; as duas
ressalvas estão na §7 e nenhuma delas é sobre correção do que foi desenhado.

| # | Entrega do brief | Resultado |
|---|---|---|
| 1 | `export` somente-leitura, uma linha JSONL por operação concluída + velas de 15 m | **OK.** 681 operações em 7 versões |
| 2 | `render`: velas, linhas do corte, entrada/stop/alvo, saída, título, ≤ 120 KB, idempotente | **OK.** 681 PNG, 47–99 KB, 44 MB |
| 3 | Nota por versão + índice, dizendo quem lê linha e quem não lê | **OK.** 7 notas + `README.md` |
| 4 | Rodar para **toda** versão com operação concluída da lista | **OK, e a lista cresceu durante a sessão** (§2) |
| 5 | Testes com operação real exportada, sem rede | **OK.** 7 testes (5 sem matplotlib) |
| 6 | `docs/PIPELINE.md` §9b | **OK** |

**Resposta curta em três linhas.** Existem agora **681 gráficos** no vault, um por operação
concluída de sete versões, com as linhas de tendência que estavam **válidas na barra da decisão** —
traçadas pelo mesmo `tl_scan` congelado que decide, cortado nessa barra. A prova mais forte de que o
desenho não é aproximação: nas 47 operações da `trendline_breakout v1`, a varredura do renderer
reencontrou **o mesmo `line_id` e o mesmo preço da linha na barra da decisão** que o worker gravou
no envelope, 47 de 47, com igualdade `Decimal` exata. E a leitura que só o traçado revela: **23 das
47** operações da `trendline_breakout v1` saíram por **invalidação** (fechar de volta abaixo da
linha), contra 8 no alvo e 7 no stop.

---

## 1. Arquivos

Escritos (nenhum commitado — o orquestrador commita por pathspec):

| arquivo | linhas | papel |
|---|---|---|
| `infra/scripts/render_operations.py` | 294 | CLI (`export`/`render`/`note`), exportação por `ssh`+`psql`, notas do Obsidian |
| `infra/scripts/render_operations_chart.py` | 228 | modelo `Operation`, leitura do JSONL, corte da barra da decisão e `tl_scan` — **sem matplotlib** |
| `infra/scripts/render_operations_draw.py` | 255 | a figura; **único** módulo com matplotlib e o único onde `Decimal` vira `float` |
| `infra/scripts/tests/test_render_operations.py` | 186 | 7 testes, operação real congelada no arquivo, sem rede |
| `infra/scripts/sql/research/2026-09-09-t350-00-catalogo.sql` | 33 | catálogo de operações concluídas por versão |
| `infra/scripts/sql/research/2026-09-09-t350-01-versoes.sql` | 22 | catálogo completo de versões (inclusive as sem operação) |
| `infra/scripts/sql/research/2026-09-09-t350-02-export.sql` | 121 | a exportação (uma linha JSON por operação, velas inclusas) |
| `obsidian/03-TRADING/Operacoes-tracadas/README.md` | — | índice, e a frase sobre o que as linhas significam |
| `obsidian/03-TRADING/Operacoes-tracadas/{trendline_breakout-v1,momentum-v6,momentum-v7,momentum-v8,session_orb-v1,mean_reversion-v2,mean_reversion-v3}.md` | — | uma nota por versão |
| `obsidian/attachments/operacoes/**` | — | **681 PNG**, 44 MB |
| `obsidian/09-OPERATIONS/Diario/2026-09-08.md` | — | seção T3.50 **acrescentada** ao fim |
| `docs/PIPELINE.md` | — | seção **§9b. Operações traçadas** acrescentada antes da §10 |
| `.claude/state/notes-T3.50.md` | — | este arquivo |

**Três módulos, não dois, e o motivo é orçamento mais uma consequência boa.** O brief previa "um
irmão pequeno se as 350 linhas apertarem"; saíram dois. A separação não é arbitrária:
`_chart.py` **não importa matplotlib**, então `export` e `note` rodam num ambiente que não o tem, e o
pyright do repositório (que resolve contra `.venv`, onde matplotlib legitimamente não existe) só
precisa de supressão em **um** arquivo, `_draw.py`, com o motivo escrito no topo dele.

---

## 2. O que havia para traçar — e o que mudou durante a própria sessão

**Primeira leitura, `read_at = 2026-09-08 22:29:34Z`** (`...-t350-00-catalogo.sql`): 20 pares
versão × coorte com operação concluída. E a leitura do catálogo completo (`...-01-versoes.sql`,
22:29:54Z) mostrou o motivo pelo qual o brief avisava:

```
 trendline_breakout | v1 | active | research_only | 2026-09-08 22:29:52.701952+00 | ... | 0 | 0
 momentum           | v7 | active | research_only | 2026-09-08 22:29:28.783999+00 | ... | 0 | 0
 momentum           | v8 | active | research_only | 2026-09-08 22:29:33.049734+00 | ... | 0 | 0
```

`trendline_breakout v1` tinha sido **ativada dois segundos antes** da minha consulta (T3.34c), e as
variantes da T3.47 (`momentum v7` e `v8`) trinta segundos antes disso. **Zero sinais nas três.** A
resposta correta naquele minuto era exatamente a que o brief antecipou: dizer que não há o que
traçar e renderizar as outras.

**Vinte minutos depois isso deixou de ser verdade.** Às 22:5x os replays da T3.34c já tinham
produzido 47 desfechos concluídos da `trendline_breakout v1`, e às 22:45Z os da T3.47 tinham
produzido 186 (`v7`) e 184 (`v8`). Renderizei as três — Everton pediu todas.

**Corte final, `read_at = 2026-09-08 23:05:40Z`:**

| versão | concluídas | coorte | R médio | PNG | tamanho |
|---|---|---|---|---|---|
| `trendline_breakout v1` | 47 | replay | **−0,0382** | 47 | 3,4 MB (48–99 KB) |
| `momentum v6` | 213 | replay + prospectiva | −0,0794 | 213 | 13,4 MB (47–96 KB) |
| `momentum v7` (T3.47 V1) | 186 | replay + prospectiva | −0,0616 | 186 | 11,5 MB (47–89 KB) |
| `momentum v8` (T3.47 V2) | 184 | replay + prospectiva | −0,0335 | 184 | 11,1 MB (47–80 KB) |
| `session_orb v1` | 20 | replay | −0,1928 | 20 | 1,3 MB (48–84 KB) |
| `mean_reversion v2` | 19 | replay + prospectiva | +0,1546 | 19 | 1,2 MB (48–75 KB) |
| `mean_reversion v3` | 12 | replay + prospectiva | +0,3830 | 12 | 0,7 MB (48–75 KB) |
| **total** | **681** | | | **681** | **44 MB** |

**Nada foi cortado por tamanho.** O brief autorizava limitar a 300 por versão acima de 150 MB; 44 MB
não chega perto e as 681 estão desenhadas. O teto de 200 imagens por invocação foi respeitado:
`momentum v6` (213) precisou de duas invocações, e a segunda **pulou as 200 já desenhadas**
(`200 já existia(m)`) — a idempotência é do arquivo, não da disciplina de quem chama.

**Os números desta tabela são um corte, não um estado.** Os workers vivos continuam produzindo:
entre 22:29Z e 23:05Z, `momentum v6` foi de 212 para 213 e `mean_reversion v2` de 19 para 20
operações prospectivas. Rodar `render` amanhã acrescenta as novas e não redesenha nenhuma das 681.

**Fora do escopo do brief, e por isso não traçadas:** `momentum v1` (929), `v2` (582), `v3` (315),
`v4` (144), `v5` (1), `volume_anomaly v1` (2 079) e `v2` (1 047), `mean_reversion v1` (65),
`breakout v2` (8). São ~5 100 operações a mais, ~330 MB de PNG. O comando é o mesmo; a decisão de
gastar o espaço não é minha.

---

## 3. As três decisões de projeto que valem registro

### 3.1 O corte da barra da decisão é uma expressão, não uma convenção

```sql
decision_bar_close = date_bin('15 minutes', observation_ts, timestamptz 'epoch')
```

É a **última barra de 15 min completamente fechada** no instante da decisão. Para uma versão de
15 min (`observation_ts` alinhado às 12:00Z) essa expressão devolve 12:00Z, isto é, a barra
11:45→12:00 — exatamente a que a estratégia leu. Para uma de 5 min (`volume_anomaly`, decidindo às
12:05Z) devolve a mesma 11:45→12:00, e **não** a 12:00→12:15, que ainda estava se formando.

O erro tentador aqui é `date_bin(observation_ts - 1 microsecond)`: acerta o caso alinhado e
**antecipa** o caso de 5 min. A expressão escolhida não tem esse caso.

### 3.2 A geometria do desenho é o código que decide, cortado na barra da decisão

`render_operations_chart.geometry()` chama `tl_scan(..., as_of = índice da barra da decisão)` com
`pattern_params(TrendlineBreakoutV1.default_parameters)`. Não há segunda implementação de linha de
tendência neste renderer, e `tl_scan` é o **único lugar onde o corte é aplicado**
(`bars[: as_of + 1]`, T3.34 §2.1): nenhuma regra a jusante consegue ler uma vela posterior nem por
acidente.

A janela é a **corrida contígua** de até 96 baldes completos terminando na decisão. Contígua porque
`atr_series` levanta em buraco (T3.34 §5.4) e um balde de 15 min a que falta um minuto não é
exportado; menos de 20 barras sai como "sem geometria", nunca como "nenhuma linha".

### 3.3 A validação forte não é um teste sintético — é o envelope do worker

As 47 operações da `trendline_breakout v1` carregam no `supporting_features` o `line_id` e o
`line_price_at_decision` que **o worker** calculou quando decidiu. Reconstruí a varredura a partir
das velas exportadas e comparei:

```
$ uv run python -c "..."   # infra/scripts, geometry() sobre o JSONL exportado
line_id do envelope reencontrado pela varredura do renderer: 47/47
line_price_at_decision identico em Decimal:                  47/47
```

Igualdade `Decimal` exata em 47 de 47 — não "próximo", **idêntico**. Isso fecha ao mesmo tempo três
perguntas que um teste sintético não fecharia: o corte da barra está certo, a dobra de 1 min para
15 min em SQL reproduz a que `aggregate()` faz em Python, e os parâmetros congelados que o desenho
usa são os que a versão usou.

---

## 4. Prova (comandos rodados nesta sessão)

### 4.1 Exportação (somente leitura)

```
$ uv run python infra/scripts/render_operations.py export --version <s> <v> --cohort all --out ...
session_orb v1 coorte=all: 20 operação(ões)
mean_reversion v2 coorte=all: 19 operação(ões)
mean_reversion v3 coorte=all: 12 operação(ões)
momentum v6 coorte=all: 213 operação(ões)
trendline_breakout v1 coorte=all: 47 operação(ões)
momentum v7 coorte=all: 186 operação(ões)
momentum v8 coorte=all: 184 operação(ões)
```

### 4.2 Desenho, e a idempotência provada em corrida real

```
$ uv run --with matplotlib python infra/scripts/render_operations.py render .../momentum-v6.jsonl --max 200
20260908-2000Z-FFUSDT-target.png               64.6 KB
213 operação(ões): 200 desenhada(s), 0 já existia(m); 200 PNG em ...\momentum-v6 (12.6 MB)

$ uv run --with matplotlib python infra/scripts/render_operations.py render .../momentum-v6.jsonl --max 200
20260908-2130Z-FFUSDT-invalidated.png          68.3 KB
20260908-2130Z-MIRAUSDT-stop.png               67.9 KB
20260908-2145Z-1000LUNCUSDT-invalidated.png    61.2 KB
213 operação(ões): 13 desenhada(s), 200 já existia(m); 213 PNG em ...\momentum-v6 (13.4 MB)
```

### 4.3 Tamanho das imagens (teto do brief: 120 KB)

```
mean_reversion-v2      n=19   min=48KB max=75KB
mean_reversion-v3      n=12   min=48KB max=75KB
momentum-v6            n=213  min=47KB max=96KB
momentum-v7            n=186  min=47KB max=89KB
momentum-v8            n=184  min=47KB max=80KB
session_orb-v1         n=20   min=48KB max=84KB
trendline_breakout-v1  n=47   min=48KB max=99KB
681 PNG, 44 MB no total. Maior imagem: 99,8 KB.
```

### 4.4 Testes

```
$ uv run --with matplotlib pytest infra/scripts/tests/test_render_operations.py -q
.......                                                                  [100%]
7 passed in 7.16s

$ uv run pytest infra/scripts/tests/test_render_operations.py -q -rs       # sem matplotlib
...ss..                                                                  [100%]
SKIPPED [1] test_render_operations.py:133: rodar com `uv run --with matplotlib`
SKIPPED [1] test_render_operations.py:153: rodar com `uv run --with matplotlib`
5 passed, 2 skipped in 1.42s
```

Os sete: a fixture é a operação que diz ser; as linhas desenhadas **são** `tl_scan` cortado na
decisão (comparadas contra uma chamada independente, e contra os três `line_id` medidos); vela
posterior à decisão não move nada **e** a mesma alteração muda a varredura trapaceira (o teste tem
dentes); o PNG cabe no teto e a segunda chamada não reescreve (`st_mtime_ns` idêntico) mas `--force`
reescreve; o título nomeia mercado, versão, hora de Brasília, hora UTC e R; a linha da tabela carrega
níveis, contagem de linhas e o link da imagem; a nota diz em letras que a versão **não lê** linha.

### 4.5 Portões

```
$ uv run ruff check infra/scripts/render_operations*.py infra/scripts/tests/test_render_operations.py
All checks passed!
$ uv run ruff format --check <idem>
4 files already formatted
$ uv run pyright infra/scripts/render_operations{,_chart,_draw}.py infra/scripts/tests/test_render_operations.py
0 errors, 0 warnings, 0 informations
$ uv run python infra/scripts/check_file_size.py
error   380 > 350  apps/api/hunter_api/services/system_status.py
error   369 > 350  infra/scripts/seed_reference.py
error   360 > 350  infra/scripts/seed.py
scanned 577 files; 3 over budget, 0 grandfathered
```

**Nenhum dos três acima do orçamento é desta task** — são de outras tarefas em voo na árvore
compartilhada. Os meus: 294 / 228 / 255 linhas.

```
$ uv run python infra/scripts/obsidian_lint.py
Resumo — Links mortos: 2, Links ambíguos: 0, Notas órfãs: 1, Frontmatter incompleto: 1,
         Valores fora do vocabulário: 1, ...
```

Os cinco achados são de `11-KNOWLEDGE/KB-0078-o-radar-preve.md` e
`06-DECISIONS/2026-09-08-limites-de-risco-teto-inerte.md`, notas de outros agentes. **As oito notas
desta task não produzem nenhum achado**: sem link morto, sem órfã, frontmatter completo.

```
$ uv run pytest infra/scripts/tests -q
2 failed, 149 passed, 2 skipped in 413.06s
FAILED infra/scripts/tests/test_seed_dry_run.py::TestDryRunWritesNothing::...
FAILED infra/scripts/tests/test_seed_dry_run.py::TestTheRiskDirectiveGate::...
```

As duas falhas são de `test_seed_dry_run.py`, que sobe Postgres por testcontainers e cujos alvos
(`seed.py`, `seed_dry_run.py`, `seed_reference.py`) estão **modificados na árvore por outra tarefa**.
Não toquei nesses arquivos; a falha é `ConnectionResetError` no contêiner.

### 4.6 Três imagens de exemplo

- `obsidian/attachments/operacoes/trendline_breakout-v1/20260820-1215Z-ETHUSDT-target.png` — a
  operação que o brief queria ver: suporte ascendente em roxo com "← usada", o pivô do stop marcado
  com ▼, a projeção tracejada da linha para depois da decisão (que é onde mora a invalidação
  estrutural), entrada/stop/alvo como segmentos e o X da saída no alvo. **+1,80 R.**
- `obsidian/attachments/operacoes/momentum-v6/20260908-2145Z-1000LUNCUSDT-invalidated.png` — uma cunha
  perfeita (resistência descendente + suporte ascendente) que a `momentum v6` **não leu**: aqui as
  linhas são contexto, e a nota diz isso em caixa `[!info]`.
- `obsidian/attachments/operacoes/session_orb-v1/20260821-0145Z-ETHUSDT-expired.png` — saída por
  horizonte, três linhas no corte, os dois alvos e o stop desenhados do instante da entrada ao da
  saída.

---

## 5. O que o traçado deixou ver, e que a tabela não mostrava

**`trendline_breakout v1`: a invalidação é o desfecho dominante.** Das 47 operações concluídas,
**23 saíram por invalidação** (fechar de volta abaixo da linha rompida/repicada), 9 por horizonte, 8
no alvo e 7 no stop. Metade das operações termina não porque o preço andou contra até o stop, mas
porque a **tese estrutural** foi desfeita. Isso é a regra da versão funcionando como escrita
(`trendline_breakout_v1`, "o que separa isto de `breakout_v1` é a invalidação"), e é também
exatamente o desenho que custou ≈ −53 R à `momentum v2` segundo a `notes-T3.45` — com uma diferença
que só o gráfico mostra: aqui a invalidação **é** a linha, não um segundo stop sem tese. Se a
expectância continuar negativa depois de 30 dias, o primeiro eixo a medir é este, com contraste
pareado: a mesma população sem a regra de invalidação.

**As três versões de `momentum` ordenam-se pelo stop.** v6 (stop base) −0,0794 R, v7 (×1,5)
−0,0616 R, v8 (×2) −0,0335 R sobre populações que são quase o mesmo conjunto (213/186/184). É a
direção que a T3.47 previu, é **pequena**, e não é minha conclusão a tirar — o contraste pareado é
daquela task. Registro aqui só porque os três conjuntos de gráficos agora existem lado a lado.

---

## 6. Divergências deliberadas do brief, com o motivo

1. **`![[wikilink]]` de imagem virou `![alt](../../attachments/...)`.** O brief pedia embed em
   `[[...]]`. O `obsidian_lint.py` **não indexa `.png`** como alvo linkável (`ASSET_SUFFIXES` são só
   `.base` e `.canvas`, `obsidian_lint_links.py:21`), então 681 embeds em `[[...]]` produziriam 681
   achados de **link morto**. A convenção que o vault já usa para figuras é markdown puro
   (`KB-0077-linhas-de-tendencia.md:152-162`, as figuras da T3.34). Segui a convenção existente. A
   alternativa — estender `ASSET_SUFFIXES` — está **fora do meu escopo de escrita** e mudaria o
   linter de todos.
2. **Dois irmãos em vez de um** (`_chart.py` e `_draw.py`), pelo orçamento de 350 linhas e porque
   isolar matplotlib num único arquivo é o que permite `export`/`note` rodarem sem ele. §1.
3. **O link `[[EXP-…]]` só existe quando a nota existe.** `momentum v6` → `[[EXP-0013-…]]`,
   `session_orb v1` → `[[EXP-0010-…]]`, `mean_reversion v2/v3` → `[[EXP-0009-…]]` (o contrato da mãe
   v1; as derivadas da T3.42 não ganharam EXP próprio). `trendline_breakout v1` (EXP-0016) e
   `momentum v7/v8` (EXP-0018) têm o contrato **em rascunho** em `.claude/state/exp-drafts/` ou em
   redação por outra task: a nota nomeia o arquivo em `code` e **não** cria wikilink, porque um link
   para nota inexistente é achado de link morto e uma afirmação falsa sobre onde o contrato está.

---

## 7. Ressalvas (por que `DONE_WITH_CONCERNS`)

1. **O nome do arquivo pode colidir, e a colisão sobrescreveria silenciosamente.**
   `<YYYYMMDD-HHMM>Z-<mercado>-<resultado>.png` é o formato do brief; duas operações **da mesma
   versão, no mesmo mercado, na mesma barra e com o mesmo desfecho** — o que pode acontecer se as
   coortes `replay` e `prospective` cobrirem o mesmo instante — mapeariam no mesmo arquivo, e a
   idempotência (`pula se existe`) faria a segunda ser **silenciosamente pulada** em vez de
   sobrescrita. **Nesta corrida não aconteceu** (681 operações → 681 PNG, contagem por diretório
   igual à contagem de linhas do JSONL em todas as sete versões), e é por isso que a ressalva é
   ressalva e não bug. A correção, se acontecer, é sufixar o `signal_id` curto; não a implementei
   para não inventar um formato de nome diferente do que o brief congelou.
2. **A escala do eixo Y é ditada pelas 96 barras anteriores, e às vezes esmaga a operação.** Num
   mercado que deu um salto grande dentro da janela de padrão (ETHUSDT 19/08, +20 % em duas horas),
   o gráfico fica com 450 pontos de amplitude e a operação inteira ocupa a faixa superior. É honesto
   — é a janela que a estratégia olhou — mas é menos legível. Um painel secundário com zoom na
   operação resolveria; não está feito.
3. **`momentum v7`/`v8` são pesquisa de outra task em voo.** Traçá-las era o pedido ("todas"), mas os
   números da §5 são leitura de população, **não** o contraste pareado que a T3.47 vai publicar. Não
   tome a ordenação v6 > v7 > v8 como resultado.
4. **Não existe teste de integração do `export`.** O subcomando fala com a VPS por `ssh`; o teste
   congelou uma operação **real já exportada** e cobre tudo depois disso. Um erro na SQL só aparece
   rodando de verdade — e a §3.3 é a checagem que faço no lugar dele: se a SQL exportasse a janela
   errada, os 47 `line_id` não bateriam.

---

## 8. Pendências registradas

1. **As ~5 100 operações fora do escopo** (`volume_anomaly v1/v2`, `momentum v1–v5`,
   `mean_reversion v1`, `breakout v2`) não estão traçadas. O comando é o mesmo; o custo é ~330 MB de
   PNG no repositório. Decisão do Everton, não minha.
2. **`obsidian_lint.py` não conhece `.png`.** Enquanto não conhecer, nenhuma figura do vault pode ser
   embutida como `![[...]]`. Brief para quem for dono do linter: acrescentar `.png`/`.jpg`/`.svg` a
   `ASSET_SUFFIXES` (eles entram como alvo e nunca são cobrados por frontmatter nem como órfãos,
   exatamente como `.base` e `.canvas`).
3. **Nenhum arquivo desta task entra em CI com matplotlib.** Os dois testes de desenho são pulados
   num `uv run pytest` limpo. Isso é deliberado (o lock da árvore compartilhada não pode se mexer),
   mas significa que uma regressão **no desenho** só é pega por quem rodar com `--with matplotlib`.
4. **`momentum v7`/`v8` ainda não têm EXP no vault** (EXP-0018 em redação): quando existir, as duas
   notas passam a poder linkar — basta rodar `note` de novo, que a nota é derivada.

## T3.50b — fechamento da revisão de 6a8679b (orquestrador, 2026-09-08 ~22:30 BRT)
- CRITICAL: `export` cita (`shlex.quote`) strategy/version/cohort/since antes de montar o comando remoto do `ssh` — nada do argv chega ao shell da VPS sem aspas.
- HIGH: `geometry()` compara o `pattern_params` do envelope com os defaults congelados do renderer e recusa (`ValueError`) em divergência — a igualdade 47/47 passa a ser garantida por código, não por coincidência de datas.
- MEDIUM: `expectancy` em `Decimal` puro (sem `fmean`/float); colisão de nome de arquivo dentro de um lote falha alto (`SystemExit`) em vez de pular a segunda operação.
- LOW: os briefs T3.44e/T3.49 entraram no commit 6a8679b por decisão do orquestrador (commit por pathspec agrupando os briefs escritos naquela hora), não pelo agente.
- Testes: 9 passed (`uv run --with matplotlib pytest infra/scripts/tests/test_render_operations.py`).
