# notes-T3.89 — EXP-0027 "amplitude como estado": os dois braços de `breadth_v2` são `descartar`

**Data:** 2026-09-11, 22:00 → 22:20 BRT (2026-09-12 01:00 → 01:20 UTC). **Owner:** quant-engineer
(T3.89b — análise e veredito; T3.89 passo 1/2 já tinham sido feitos por passadas anteriores desta
mesma tarefa: pré-registro arquivado 09:52 BRT, derivação/ativação de `v18`/`v19` às 12:45–12:46
UTC, replay de 24 fatias concluído à mão pelo orquestrador depois de o primeiro agente morrer num
limite de API).
**Base local:** árvore compartilhada, **nada commitado**. **VPS:** HEAD `/opt/project-hunter` =
`e7cee807` (2026-09-11 11:22:21 -03:00), imagem `hunter-api:e7cee80` presente — `compose.sh ops`
funcionou sem bloqueio (ao contrário da T3.76).
**Nenhum container parado, recriado ou reiniciado. Nenhum `.env*` tocado. Nenhum `git pull` na VPS.
Nenhuma escrita SQL à mão** (todas as leituras em `begin transaction isolation level repeatable
read read only`). **Escritas na VPS, todas por caminho auditado:** 2 `activate_strategy_version.py
--deprecate` via `compose.sh ops` (dry-run primeiro nos dois) e 2 passadas de
`hunter_strategy_worker.replay.stress` via `compose.sh replay` (sessão somente-leitura).

---

## STATUS

**DONE** — as duas condições de sucesso do brief (verificar replays já feitos, aplicar a régua
pré-registrada e aposentar quem falhar no mesmo dia) foram cumpridas sem bloqueio.

| # | Entrega do brief | Resultado |
|---|---|---|
| 1 | Confirmar que os replays de `v18`/`v19` estão completos e corretos | **OK** — §1, 24 fatias, 270 336 barras, 0 erros, versões corretas nas coortes |
| 2 | Estresse por braço | **OK** — §2, os dois rodaram sem o portão recusar |
| 3 | Análise (blocos de dia, semente 20260912, LOMO, 3 janelas, K1–K6, C5, pareamento por barra, cláusula de identidade) | **OK** — §3 |
| 4 | Vereditos, página EXP-0027 (append-only), `mean_reversion.md`, Index, aposentar quem falhar no mesmo dia | **OK** — §4, os dois braços `descartar`, ambos deprecated às 01:15:24Z/01:16:02Z |
| 5 | Notas, SQL, `obsidian_lint` | **OK** — esta nota, 3 SQL novos, `obsidian_lint.py` termina "base limpa" (§5) |

**Veredito de uma linha:** os dois braços de `breadth_v2` são `descartar` — a célula "de dentro"
(`v18`) saiu **pior** que o pai (Δ −0,0184 R, sinal oposto ao que a hipótese principal precisa), o
braço de falseamento (`v19`) saiu melhor mas abaixo do piso (Δ +0,0372 R, IC cruza zero), o Δ pareado
por (mercado, barra) confirma que o portão é só um portão (0,0000 R nos dois) e a **cláusula de
identidade dispara nos dois**: cortar o pai por `regime_hourly_v1` produz separação igual ou maior
do que `breadth_v2` produziu de fato.

---

## ARQUIVOS (`git status --porcelain`, só os meus desta tarefa)

```
 M obsidian/03-TRADING/Estrategias/mean_reversion.md
 M obsidian/05-EXPERIMENTS/EXP-0027-amplitude.md
 M "obsidian/05-EXPERIMENTS/Experiments Index.md"
?? .claude/state/exp-drafts/t389-decisoes.csv
?? .claude/state/exp-drafts/t389/analise.py
?? .claude/state/notes-T3.89.md
?? infra/scripts/sql/research/2026-09-11-t389-q10-recibos-replay.sql
?? infra/scripts/sql/research/2026-09-11-t389-q11-dump-decisoes-bracos.sql
?? infra/scripts/sql/research/2026-09-11-t389-q12-k4-pai.sql
```

Raiz em `C:\dev\project-hunter\`. **Não commitei nada.** Nenhum módulo de produção mudou — só
Obsidian, SQL de pesquisa (somente leitura) e um script de análise local (NumPy sobre CSV, nada de
Decimal, nada de IO além de leitura de arquivo). Os arquivos `q00`-`q04` de `2026-09-11-t389-*` já
existiam de uma passada anterior desta tarefa (medição da distribuição, pré-registro) e não foram
tocados.

---

## 1. CONFIRMAÇÃO DOS REPLAYS (q10, 01:03Z)

```sql
-- infra/scripts/sql/research/2026-09-11-t389-q10-recibos-replay.sql
```

```
                   coorte                    | fatias | barras | unavailable | ineligible | triggered | erros |            de             |            ate            
---------------------------------------------+--------+--------+-------------+------------+-----------+-------+---------------------------+---------------------------
 replay:a94701c9-3459-463e-8922-c1403e91d60a |     12 | 135168 |           0 |      87552 |       401 |     0 | 2026-06-14T00:00:00+00:00 | 2026-09-10T00:00:00+00:00
 replay:f2c44f18-5f63-435f-97bb-5f5aaf31cea7 |     12 | 135168 |           0 |      71648 |       909 |     0 | 2026-06-14T00:00:00+00:00 | 2026-09-10T00:00:00+00:00
(2 rows)

                   coorte                    |       versao       |  n  | mercados | dias 
---------------------------------------------+--------------------+-----+----------+------
 replay:a94701c9-3459-463e-8922-c1403e91d60a | mean_reversion v19 | 316 |       16 |   75
 replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3 | mean_reversion v10 | 798 |       16 |   89
 replay:f2c44f18-5f63-435f-97bb-5f5aaf31cea7 | mean_reversion v18 | 540 |       16 |   84
(3 rows)
```

12 fatias por braço, 135 168 barras cada (16 mercados × 88 d × 96 barras de 15 min), **0 erros**,
janela `2026-06-14 → 2026-09-10` — exatamente a janela declarada no pré-registro (o início de
`breadth_v2`). A cohort redundante `replay:a42c888d-e0c7-40fa-9536-ed2378d59493` (4 fatias de `v18`
de um loop quebrado, citada no brief) foi checada e **confirmada existente e ignorada**:

```
$ psql ... "select distinct meta->>'cohort' from signal_outcomes where meta->>'cohort' like 'replay:a42c888d%';"
                  ?column?                   
---------------------------------------------
 replay:a42c888d-e0c7-40fa-9536-ed2378d59493
(1 row)
```

Não entra em nenhuma soma desta nota. Também confirmei `strategy_versions` (q03, já existente):
`v18`/`v19` têm o mesmo `code_ref@sha256:a970c9d9…` e `params_hash d4fcf66f9449` de `v10`, só a
`eligibility_policy` muda — o contraste é de portão, não de parâmetro.

## 2. DUMP DE DECISÕES E K4 DO PAI (q11, q12, 01:05–01:07Z)

`infra/scripts/sql/research/2026-09-11-t389-q11-dump-decisoes-bracos.sql` (irmão do
`2026-09-10-t376-q04-dump-decisoes-bracos.sql`) traz o pai `v10` **cortado em 2026-06-14** (798 →
789 decisões, as 9 de 06-12/06-13 saem — a única diferença de calendário entre pai e filhas,
declarada no pré-registro) mais os dois braços, com `(mercado, barra)` para o pareamento da condição
5 e o rótulo `regime_hourly_v1` vigente em cada barra para a cláusula de identidade. Saída: **1 645
linhas** (789 + 540 + 316), salva em `.claude/state/exp-drafts/t389-decisoes.csv`.

`2026-09-11-t389-q12-k4-pai.sql`: K4 do pai (a única leitura honesta para uma versão com portão,
`docs/PIPELINE.md` §4b item 12) — **0,93 %** (1 280/138 240 barras `unavailable`, coorte original de
90 d, o efeito de 2 dias de diferença de janela em 90 é desprezível e fica declarado).

## 3. ESTRESSE (sessão somente-leitura, 2026-09-12 01:12–01:14Z / 22:12–22:14 BRT)

```
$ timeout 290 ssh hunter-vps "... STRATEGY_SHARDS=4 MARKET_SPOT=1 MARKET_SHARDS=4 timeout 250 \
    bash infra/vps/compose.sh replay python -m hunter_strategy_worker.replay.stress \
    --cohort replay:f2c44f18-5f63-435f-97bb-5f5aaf31cea7"
```

`v18`: base −0,0509 R (n=538, eixo `r_net`), `custos_x2` −0,1487 (Δ −0,0978, IC
[−0,1025;−0,0933]), 1ª metade (até 07-27) −0,1497 (n=287) × 2ª metade +0,0621 (n=251) →
**`sem_vantagem_na_base`**. O portão do replay **não recusou** (ao contrário do bloqueio da T3.84 —
o defeito de heartbeat/consumer-lag por shard aparentemente não afeta o `--stress`, que não passa
pelo mesmo portão do `run`).

```
$ timeout 290 ssh hunter-vps "... bash infra/vps/compose.sh replay python -m \
    hunter_strategy_worker.replay.stress --cohort replay:a94701c9-3459-463e-8922-c1403e91d60a"
```

`v19`: base +0,0033 R (n=315), `custos_x2` −0,0902 (Δ −0,0935, IC [−0,1007;−0,0866]), dependente de
4 mercados isolados (BNB/DASH/SAHARA/XRP viram negativos ao serem excluídos) e de metade (1ª −0,0858
× 2ª +0,0953) → **`frágil a custos`**.

## 4. A ANÁLISE (`.claude/state/exp-drafts/t389/analise.py`, blocos de dia, semente **20260912**)

Semente do pré-registro EXP-0027, **diferente** da semente-padrão de `blocos90.py` (20260910) usada
nas EXP-0025/0026 — fica destacado porque um leitor apressado poderia estranhar o número.

```
$ uv run python .claude/state/exp-drafts/t389/analise.py

linhas: 1645  arquivo: C:\dev\project-hunter\.claude\state\exp-drafts\t389-decisoes.csv

== 1. populacao e expectativa (eixo r_exf, IC por blocos de dia, semente 20260912) ==
versao                     n  dias     media     soma     PF  IC95
mean_reversion v10       789    87   -0.0291   -22.95  0.911  [-0.1344; +0.0734]
mean_reversion v18       540    84   -0.0475   -25.63  0.851  [-0.1559; +0.0620]
mean_reversion v19       316    75   +0.0081    +2.55  1.024  [-0.1553; +0.1629]

== 2. condicao 1: delta NAO PAREADO = media(braco) - media(pai), blocos de dia ==
braco                  n_braco  media_br  media_pai    delta  IC95   veredito
mean_reversion v18         540   -0.0475    -0.0291  -0.0184  [-0.1692; +0.1350]  FALHA
mean_reversion v19         316   +0.0081    -0.0291  +0.0372  [-0.1574; +0.2232]  FALHA

== 3. condicao 2: n >= 100 avaliaveis e >= 30 dias distintos ==
mean_reversion v18     n= 540  dias= 84  PASSA
mean_reversion v19     n= 316  dias= 75  PASSA

== 4. condicao 3: media por janela de 30 d (positivo em >= 2 de 3) ==
mean_reversion v10         -0.1248 (n=328)      -0.0822 (n=181)      +0.1174 (n=280)   1/3 FALHA
mean_reversion v18         -0.1696 (n=226)      -0.0936 (n=131)      +0.1364 (n=183)   1/3 FALHA
mean_reversion v19         -0.1096 (n=130)      -0.0097 (n= 63)      +0.1416 (n=123)   1/3 FALHA

== 5. condicao 4: leave-one-market-out (16 reajustes, nunca negativo) ==
mean_reversion v10     mercados=16  pior LOO: sem SOLUSDT      -0.0390 (n=743)  negativos=16  FALHA
mean_reversion v18     mercados=16  pior LOO: sem ZECUSDT      -0.0633 (n=482)  negativos=16  FALHA
mean_reversion v19     mercados=16  pior LOO: sem DASHUSDT     -0.0042 (n=290)  negativos= 1  FALHA

== 6. condicao 5: delta pareado por (mercado, barra) contra o pai ==
braco                  n_braco  compart so_do_braco    delta  veredito
mean_reversion v18         540      393         147  +0.0000  PASSA
mean_reversion v19         316      192         124  +0.0000  PASSA

== 8. rotulo de regime das decisoes de cada braco ==
mean_reversion v10     HIGH_VOLATILITY=218, BTC_BULL=166, SIDEWAYS=159, BTC_BEAR=140, UNKNOWN=63, LOW_VOLATILITY=43
mean_reversion v18     HIGH_VOLATILITY=147, BTC_BULL=107, BTC_BEAR=106, SIDEWAYS=106, UNKNOWN=42, LOW_VOLATILITY=32
mean_reversion v19     HIGH_VOLATILITY=102, SIDEWAYS=65, BTC_BULL=61, BTC_BEAR=50, UNKNOWN=27, LOW_VOLATILITY=11

== 7. clausula de falsificacao: cortar o PAI por regime_hourly_v1 em vez de breadth_v2 ==
braco                 rotulos_permitidos                     n_perm media_perm delta_regime delta_breadth  veredito
mean_reversion v18    BTC_BEAR,BTC_BULL,HIGH_VOLATILITY         524    -0.0285      +0.0017       -0.0184  FALSIFICADO (regime >= breadth)
mean_reversion v19    HIGH_VOLATILITY,SIDEWAYS                  377    +0.0470      +0.1456       +0.0372  FALSIFICADO (regime >= breadth)

== 9. K1-K6, C5 e pedagio medido nas decisoes ==
versao                     n  dias   k1   k2   k3  k6_pct  c5_pct pedagio_p50
mean_reversion v10       789    87    .    .    S   10.5%   16.9%     +0.1064  flags=K3
mean_reversion v18       540    84    .    .    S   10.7%   15.0%     +0.1092  flags=K3
mean_reversion v19       316    75    .    .    .   12.0%   19.6%     +0.0988  flags=nenhuma
```

**Método da cláusula de falsificação:** como não há uma versão derivada com portão de regime cortada
*exatamente* como `v18`/`v19` para reexecutar aqui (isso seria uma corrida nova, fora do orçamento),
a leitura repete o método do §2b da T3.76/EXP-0026 — partição **dentro** do pai (rótulos permitidos
menos proibidos, pareada por dia) — usando como "permitidos" os rótulos que somam **≥ 50 % das
decisões** de cada braço (medido em §8). O Δ dessa partição é comparado, em magnitude, ao Δ **não
pareado** braço-vs-pai da condição 1. Nos dois braços o corte por regime vence ou empata com o corte
por amplitude: a cláusula **dispara nos dois**.

### 4.1 O que os números dizem, em três frases

1. **A hipótese principal está refutada duas vezes.** A célula "de dentro" (`v18`, onde H-P8 afirma
   que vive a vantagem) saiu **pior** que o pai (Δ −0,0184 R) — o sinal oposto ao que a hipótese
   precisa. O braço de falseamento (`v19`) saiu melhor (Δ +0,0372 R), replicando a leitura descritiva
   monótona pré-replay (T1 baixo > T2 meio > T3 alto), mas fica abaixo do piso de aprovação e o IC
   cruza zero.
2. **O portão está correto.** Δ pareado por (mercado, barra) = **0,0000 R** nos dois braços (393/540
   e 192/316 barras compartilhadas); as 147/124 decisões que sobram são a divergência de máquina de
   estados do slot que `docs/PIPELINE.md` §4b item 11 já previa, não bug de leitura.
3. **A cláusula de identidade fecha o caso.** Em ambos os braços, cortar o pai por `regime_hourly_v1`
   produz separação igual ou maior do que `breadth_v2` produziu de fato (+0,0017 ≥ −0,0184 em A;
   +0,1456 ≥ +0,0372 em B) — `breadth_v2`, nesta coorte, é consistente com ser o regime horário do
   BTC reamostrado por minuto, e a EXP-0026 já mostrou que esse regime não sobrevive à régua (mesmo
   sinal de calendário, mesmo IC cruzando zero, mesmo padrão de 1/3 janelas positivas).

## 5. VEREDITOS, PÁGINAS E APOSENTADORIAS (01:15–01:16Z)

**Veredito pré-registrado, aplicado sem desvio: `descartar` nos dois braços** (qualquer coisa a menos
que as cinco condições = descartar, EXP-0027 congelada). Dry-run primeiro nos dois, depois a escrita:

```
$ bash infra/vps/compose.sh ops python infra/scripts/activate_strategy_version.py mean_reversion v18 \
    --deprecate --changelog '...' --dry-run
would deprecate mean_reversion v18 (purpose research_only), code_ref ...a970c9d9...395f,
  params_hash d4fcf66f9449, successor=none: T3.89/EXP-0027: descartada. Delta nao pareado vs pai
  -0,0184 R (IC blocos de dia [-0,1692;+0,1350], semente 20260912; n=540, 84 dias). ...

$ bash infra/vps/compose.sh ops python infra/scripts/activate_strategy_version.py mean_reversion v18 \
    --deprecate --changelog '...'
deprecated mean_reversion v18 (purpose research_only) at 2026-09-12T01:15:24.377325+00:00, successor=none

$ bash infra/vps/compose.sh ops python infra/scripts/activate_strategy_version.py mean_reversion v19 \
    --deprecate --changelog '...' --dry-run
would deprecate mean_reversion v19 ...

$ bash infra/vps/compose.sh ops python infra/scripts/activate_strategy_version.py mean_reversion v19 \
    --deprecate --changelog '...'
deprecated mean_reversion v19 (purpose research_only) at 2026-09-12T01:16:02.045394+00:00, successor=none
```

Changelogs completos (caractere por caractere) estão nos comandos reais executados; resumidos acima
para caber na nota. Ambos `successor=none` — nenhuma versão nova nasce desta EXP.

**Páginas atualizadas (append-only onde a convenção pede):**
- `obsidian/05-EXPERIMENTS/EXP-0027-amplitude.md` — nova seção "Avaliação de 2026-09-11" acrescentada
  depois da seção de pré-registro (não reescrita), frontmatter atualizado (`status: avaliado`,
  `result: reprovada`, `evaluable: 856`, `days: 84`, `last_eval: "2026-09-11"`), fontes ampliadas.
- `obsidian/03-TRADING/Estrategias/mean_reversion.md` — linhas `v15`–`v19` acrescentadas à tabela
  gerada (as três de regime da EXP-0026 estavam faltando na tabela, embora já narradas em prosa;
  acrescentei para não deixar `v18`/`v19` como as únicas linhas novas órfãs), ligação nova para
  EXP-0027, e um novo parágrafo "Acréscimo de 2026-09-11/12" com o resumo dos dois braços.
- `obsidian/05-EXPERIMENTS/Experiments Index.md` — as duas linhas de `EXP-0027` (a de "IDs
  reservados" e a tabela detalhada) atualizadas com o veredito final, substituindo "pré-registrado,
  replay em andamento".

## 6. CONCERNS HONESTOS

1. **A cláusula de falsificação não reexecuta um replay gêmeo por regime** — reusa o método de
   partição-dentro-do-pai da T3.76/EXP-0026 (mesma amostra, corte por rótulo em vez de replay
   dedicado). É a leitura mais barata que ainda responde à pergunta pré-registrada ("o corte por
   regime produz Δ igual ou maior?") sem gastar um novo orçamento de replay — e ela é conservadora a
   favor de `breadth_v2`: o corte-dentro-do-pai está correlacionado com a população total (viés que
   a própria T3.76 §2 declarou), então se mesmo assim ele empata ou vence, a leitura por replay
   dedicado dificilmente inverteria o resultado.
2. **A previsão numérica 6 do pré-registro acertou a direção e errou a magnitude por ~2×** nos dois
   braços (previsto Δ_A ≈ −0,039 R / medido −0,0184 R; previsto Δ_B ≈ +0,013 R / medido +0,0372 R).
   Fica registrado porque é informação sobre a calibração do método descritivo pré-replay (célula
   medida sobre o pai, sem gate real), não só sobre esta EXP.
3. **O `--stress` não foi bloqueado pelo defeito de heartbeat/consumer-lag por shard que travou o
   `replay.run` na T3.84.** Não investiguei a fundo o porquê (não era o escopo desta tarefa), só
   registro o fato: os dois comandos de stress rodaram e produziram tabela completa sem refusal.
4. **`v15`/`v16`/`v17` (EXP-0026) continuam `active`** nesta VPS apesar de `descartar` — o bloqueio
   de deploy da T3.76 (HEAD sem imagem construída) não existe mais hoje (`e7cee80` está implantado),
   então as três aposentadorias pendentes da T3.76 §7 **poderiam** ser concluídas agora, mas isso é
   fora do escopo do brief T3.89 e não fiz (mudaria o roster por uma tarefa que não é esta).

## 7. SQL DE PESQUISA

| arquivo | o que responde |
|---|---|
| `2026-09-11-t389-q00-catalogo.sql` … `-q04-faixa-b-meia-aberta.sql` | já existiam (medição da distribuição, passo 1 desta tarefa) |
| `2026-09-11-t389-q10-recibos-replay.sql` | confirma as 24 fatias completas, 0 erros, e a composição de versão de cada coorte |
| `2026-09-11-t389-q11-dump-decisoes-bracos.sql` | dump por decisão (CSV) do pai cortado e dos dois braços, com `(mercado, barra)` e rótulo de regime, para o bootstrap local |
| `2026-09-11-t389-q12-k4-pai.sql` | K4 do pai na coorte original de 90 d (leitura honesta para versão com portão) |

Receita de leitura (somente leitura, `repeatable read read only`, `statement_timeout` explícito):

```bash
timeout 290 ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter \
  -v ON_ERROR_STOP=1 -f -" < infra/scripts/sql/research/2026-09-11-t389-q11-dump-decisoes-bracos.sql
```

## 8. `obsidian_lint.py`

```
$ uv run python infra/scripts/obsidian_lint.py
LINT DA BASE OBSIDIAN — 256 NOTA(S) ANALISADA(S)
Resumo — Links mortos: 0, Links ambíguos: 0, Notas órfãs: 0, Frontmatter incompleto: 0,
Valores fora do vocabulário: 0, Procedência da Knowledge Base (KB-*): 0,
Reescrita de experimentos (append-only): 0.

RESULTADO: base limpa
```

## 9. `git status --porcelain` FINAL (só os meus arquivos)

```
 M obsidian/03-TRADING/Estrategias/mean_reversion.md
 M obsidian/05-EXPERIMENTS/EXP-0027-amplitude.md
 M "obsidian/05-EXPERIMENTS/Experiments Index.md"
?? .claude/state/exp-drafts/t389-decisoes.csv
?? .claude/state/exp-drafts/t389/analise.py
?? .claude/state/notes-T3.89.md
?? infra/scripts/sql/research/2026-09-11-t389-q10-recibos-replay.sql
?? infra/scripts/sql/research/2026-09-11-t389-q11-dump-decisoes-bracos.sql
?? infra/scripts/sql/research/2026-09-11-t389-q12-k4-pai.sql
```

Nada commitado.
