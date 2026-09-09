# notes-T3.57b — `trendline_bounce v1` medida: melhor que a mãe, e mesmo assim descartada

**Quando:** 2026-09-09, 15:25 → 16:20 BRT (UTC−3) · em UTC, 18:25Z → 19:20Z.
**Quem:** quant-engineer. **VPS:** `3c9a8d8`, imagem `hunter-api:3c9a8d8`, migração
`0017_eligibility_policy`. **Nada commitado.** **Nenhum container parado, recriado ou
reiniciado. Nenhum `.env*` tocado. Nenhum `git pull` na VPS.**
**Escritas na VPS:** `seed.py --only strategies` (×1 dry-run, ×1 real),
`activate_strategy_version.py trendline_bounce v1` (×1 dry-run, ×1 real, ×1 dry-run e ×1 real
de `--deprecate`), 2 corridas de replay e 1 passada de estresse (`READ ONLY`). Todo o resto foi
lido em `begin transaction isolation level repeatable read read only`.

---

## STATUS

**DONE.** Semeada, ativada com o digest pré-registrado conferido, replayada 31 d × 4 mercados
com `--explain-ledger`, avaliada pelo dia um da EXP-0022 item a item, estressada (K1 sobreviveu)
— e **descartada e depreciada**, pela régua congelada do `docs/plans/SHADOW-LAB.md` §4.

**O resultado em uma frase:** a versão é a **melhor abertura de dia um desta casa até hoje**
(+0,1230 R líquidos, PF 1,2576, K1–K6 todos limpos, e a mãe que ela substitui dá −0,0382 R) e
**mesmo assim é descartada**, porque o estresse dispara **quatro** dos cinco vereditos de
fragilidade e porque **um único dia** (21/08, +8,653 R) carrega mais do que o total da coorte.

| leitura | número | régua | veredito |
|---|---:|---|---|
| expectativa líquida | **+0,1230 R** | — | melhor abertura da casa |
| PF líquido | **1,2576** | — | > 1 |
| n / dias / mercados | **33 / 12 / 4** | K1 ≥ 20 | **passa** |
| Δ pareado vs a mãe (24 barras comuns) | **+0,0337 R** | > 0 | falsificador próprio **não** dispara |
| IC 95 % do Δ pareado (blocos de dia) | **[−0,1372; +0,2410]** | acima de zero | **cruza zero** |
| p de Holm (família de 2 pareados) | **1,0000** | < 0,05 | **não rejeita** |
| projeção pré-registrada | **+0,2401 R** | — | medido **+0,1230**, ~metade |
| estresse | `frágil a custos` + 3 | 0 disparos | **4 de 5 disparam** |
| um dia (21/08) | **+8,653 R** de +4,058 R totais | — | a vantagem é um dia |

**Veredito: `descartar`.** Não é julgamento meu: o SHADOW-LAB §4 diz, congelado antes desta
corrida, que cada disparo do estresse "é **motivo suficiente para não gastar trinta dias de
prospectivo**". Dispararam quatro. E como o único valor de manter uma versão `research_only`
ativa é justamente a coorte prospectiva, aposentar é o ato consistente com a régua.

---

## ARQUIVOS

| Arquivo | O quê |
|---|---|
| `infra/scripts/sql/research/2026-09-09-t359c-q00-estado.sql` · `-q01-coortes.sql` | estado e coortes antes (compartilhados com a T3.59c) |
| `infra/scripts/sql/research/2026-09-09-t359c-q10-populacoes.sql` | população da v2 e da v1 lado a lado |
| `infra/scripts/sql/research/2026-09-09-t357b-q20-dia-um.sql` | decomposição por mercado (K6) |
| `infra/scripts/sql/research/2026-09-09-t357b-q21-pareado.sql` | pareamento por (mercado, barra) |
| `infra/scripts/sql/research/2026-09-09-t357b-q22-rvol-cauda.sql` | terceis de RVOL, cauda esquerda, leitura condicionada |
| `infra/scripts/sql/research/2026-09-09-t357b-q23-dump-csv.sql` · `-q24-dump-pareado-csv.sql` | os dois dumps |
| `infra/scripts/sql/research/2026-09-09-t357b-q25-por-dia-e-geometria.sql` | por dia (C4) e geometria das linhas |
| `infra/scripts/sql/research/2026-09-09-t359c-q30-portas-k.sql` | K5 e a identidade do pedágio |
| `.claude/state/exp-drafts/t357b/pareado.py` | Δ pareado por (mercado, barra) com o dia como bloco + Holm |
| `.claude/state/exp-drafts/t357b/test_pareado.py` | oráculo do estimador (5 casos, séries sintéticas) |
| `.claude/state/exp-drafts/t357b/populacoes.py` | contraste de população, reusando `t352d/duas_populacoes.py` **sem alterar uma linha** |
| `.claude/state/exp-drafts/t357b/familia.py` | os três contrastes + Holm |
| `.claude/state/exp-drafts/t357b-populacoes.csv` · `t357b-pareado.csv` | os dumps lidos da VPS |
| `.claude/state/notes-T3.57b.md` | este arquivo |

Todos com raiz em `C:\dev\project-hunter\`.

---

## 1. O SEED — só uma estratégia nova, como o brief exigia

`seed.py --only strategies --dry-run` (as linhas `note:` são informativas e pré-existentes; o
diff real são estas duas linhas e só elas):

```
strategies.trendline_bounce: NEW {'key': 'trendline_bounce', 'name': 'Trendline Bounce',
  'description': 'Long a confirmed bounce on an ascending trend line, on above-median volume.
  No structural invalidation: exits by stop, target or horizon (T3.57, EXP-0022).',
  'category': 'trend'}
strategy_versions.trendline_bounce v1: NEW {'version': 'v1', 'status': 'draft',
  'code_ref': 'hunter_indicators.strategies.trendline_bounce_v1', 'params_format': 1,
  'purpose': 'research_only', 'eligibility_policy': None, …}
DRY RUN: nothing written
```

**Nenhuma outra chave aparece.** Isto fecha a CONCERN 1 da T3.52d, em que o mesmo comando semeou
`sweep_reclaim` de surpresa junto com o que se pedia: aquela chave já existe hoje e não voltou a
aparecer. Corrida real (`--yes`): mesmo diff, mais `seeded 13 row(s) into strategies` /
`seeded 13 row(s) into strategy_versions` (13 = as 12 de antes + a nova; as 12 saem `unchanged`).

## 2. A ATIVAÇÃO — o digest pré-registrado bate dígito a dígito

```
$ … activate_strategy_version.py trendline_bounce v1 --changelog T3.57_EXP-0022_trendline_bounce_v1 --dry-run
would activate trendline_bounce v1 (purpose research_only) with code_ref
hunter_core.strategies.trendline_bounce_v1@sha256:fb7263ce5f06956f6d57c86f2a0790c62644b3f453904d83546674de4dabdb75
(34 parameters)
```

`…fb7263ce…` é exatamente o previsto pela EXP-0022 ("conferir no `--dry-run` antes de escrever;
se divergir, PARAR"), e **34 parâmetros** é o número congelado (as 36 da v1 menos `mode` e
`max_violations_breakout`). O `params_hash` apareceu depois, no recibo da depreciação:
`9b1e882f169c` — os 12 primeiros hex de `9b1e882f169c89ca`, também pré-registrado. Nada divergiu;
não houve motivo para parar. Escrita:

```
activated trendline_bounce v1 (purpose research_only) at 2026-09-09T18:26:15.002949+00:00
with code_ref hunter_core.strategies.trendline_bounce_v1@sha256:fb7263ce…
```

`context_budget` não recusou: a janela de 1 470 min declarada cabe no piso de 1 560 já implantado,
e o replay confirmou `context_minutes = 1560` nas duas fatias.

## 3. O REPLAY — 31 d × 4 mercados, 0 erros

Coorte `replay:7e498c13-d79b-4466-8ff8-30550d75c21e`, duas fatias, `--explain-ledger` nas duas.

| fatia | barras | `unavailable` | `not_triggered` | `triggered` | `rejected` | sinais | s |
|---|---:|---:|---:|---:|---:|---:|---:|
| 08-08 → 08-23 | 5 760 | 448 | 5 294 | 18 | 0 | 10 | 105,4 |
| 08-23 → 09-08 | 6 144 | 0 | 6 110 | 31 | 3 | 23 | 122,9 |
| **total** | **11 904** | **448** | **11 404** | **49** | **3** | **33** | 228,3 |

- **`ineligible = 0`**, porque esta versão não tem portão — e por isso, ao contrário dos braços
  da EXP-0023, **K4 é mensurável aqui**: 448/11 904 = **3,76 %**, muito abaixo dos 40 %.
- As **3 recusas** (`rejected`) são as duas portas declaradas (`geometry`, `risk_too_wide`); a
  terceira porta da mãe, `geometry_invalidation`, não existe nesta versão por construção.
- **49 gatilhos → 33 sinais:** a diferença é a barreira do slot, não perda de dado.

## 4. A POPULAÇÃO, LADO A LADO COM A MÃE — `read_at = 2026-09-09 18:44:24,802178+00`

| versão | coorte | n | dias | mercados | pedágio (R) | exp. bruta (R) | exp. líquida (R) | soma R | PF | acerto |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **`trendline_bounce v1`** | `7e498c13` | **33** | 12 | 4 | 0,1345 | **+0,2609** | **+0,1230** | **+4,058** | **1,2576** | **45,5 %** |
| `trendline_breakout v1` (mãe) | `d78c14d1` | 47 | 14 | 4 | 0,1401 | +0,1045 | −0,0382 | −1,794 | 0,9220 | 31,9 % |

Desfechos da v2: **8 alvos, 14 stops, 11 expirações, 0 invalidações** — a identidade da versão
("não há invalidação") aparece no banco, não só no docstring.

### 4.1 A identidade do pedágio, conferida (item 2 do dia um)

```
n 33 | pedágio medido 0,1345 R | identidade 0,002·entrada/risco = 0,1344 R | p50 0,1340 | máx 0,2028
```

A identidade fecha na quarta casa. E o **teto declarado do C7 (0,20 R) é o máximo observado**
(0,2028 R) — a correção que a EXP-0022 fez sobre o 0,1333 R do EXP-0016 estava certa: aquele
número era o melhor caso simultâneo e este é o teto real.

## 5. A POPULAÇÃO **NÃO É** SUBCONJUNTO DA MÃE (item 1 do dia um)

Pareamento por (mercado, barra):

| classe | n | exp. v1 (R) | exp. v2 (R) |
|---|---:|---:|---:|
| **1 nas duas** | **24** | +0,0519 | +0,0856 |
| 2 só na v1 (mãe) | 23 | −0,1321 | — |
| 3 **só na v2 (filha)** | **9** | — | **+0,2225** |

As três fontes de divergência que a EXP-0022 pré-registrou aparecem todas: (a) barras em que a
mãe achou **rompimento** primeiro e a filha devolve repique; (b) a barra que a mãe recusou por
`geometry_invalidation`, que aqui não é recusada; (c) os repiques com RVOL < 1,0. **A filha tem
9 decisões que a mãe nunca tomou, e elas são as melhores da coorte (+0,2225 R).** Ler o Δ sem os
dois `n` de borda seria ler outra coisa — é literalmente o aviso do item 5 do pré-registro.

**É também a explicação do desvio da projeção.** O pré-registro projetou **+0,2401 R** partindo
dos 26 repiques com RVOL ≥ 1,0 da mãe (média +0,1676 R) mais o Δ por episódio invalidado da
T3.34c (+0,188462 R). Medido: **+0,1230 R**, ~metade. A causa é o item 1 e não uma narrativa
nova: a população real não são aqueles 26 — são 33, das quais só 24 são compartilhadas, e nessas
24 a **mãe** rende +0,0519 R (não +0,1676 R). A projeção supunha uma população que a versão não
tem.

## 6. O CONTRASTE PAREADO (item 5 do dia um) — e o que ele diz da tese

`t357b/pareado.py`, 10 000 reamostragens de **dias inteiros**, semente `20260909`:

```
1 pareado (todas)          | dias 11 | pares 24 | exp_v1 +0.0519 | exp_v2 +0.0856 | delta +0.0337 | IC95 [-0.1372; +0.2410] | p 0.8304
2 pareado (v1 invalidou)   | dias  6 | pares 10 | exp_v1 -0.5804 | exp_v2 -0.4995 | delta +0.0809 | IC95 [-0.3666; +0.5160] | p 0.8092
3 populacao inteira        | dias 14 | n_v2 33 | n_v1 47 | delta +0.1611 | IC95 [-0.1333; +0.4178] | cruza zero

Holm sobre os 2 contrastes pareados (o de populacao publica so o IC):
  1 pareado (todas)          p_holm 1.0000
  2 pareado (v1 invalidou)   p_holm 1.0000
```

- **O falsificador próprio da versão não dispara:** Δ pareado = **+0,0337 R > 0**. Retirar a
  invalidação **não** piorou nas barras compartilhadas.
- **Mas ele também não prova nada:** IC cruza zero e Holm não rejeita. E o Δ é **cinco vezes
  menor** que o +0,188462 R que a T3.34c mediu na mesma família — a evidência prévia, que já
  tinha IC contendo zero, encolheu ao ser remedida.
- **Condicionado aos episódios que a mãe invalidou** (10 pares em 6 dias): Δ +0,0809 R, IC
  cruzando zero. A KB-0006 continua sem confirmação forte; ela sobrevive como hipótese, não como
  achado.
- **Por que o contraste de população não entra no Holm:** `duas_populacoes.contraste` é reusado
  **sem alteração** e não devolve a distribuição, logo não há `p` dele para corrigir. Publica-se
  o IC, que é o que aquele estimador de fato mede — inventar um `p` ali seria inventar um número.

### 6.1 A CAUDA ESQUERDA — o que substitui o C8, e ela contraria a tese

| versão | n | p10 de R | média das perdedoras | pior R | n perdedoras | pedágio |
|---|---:|---:|---:|---:|---:|---:|
| `trendline_breakout v1` (com invalidação) | 47 | −1,0743 | **−0,7189** | −1,1082 | 32 | 0,1401 |
| `trendline_bounce v1` (sem invalidação) | 33 | −1,0924 | **−0,8751** | −1,1303 | 18 | 0,1345 |

**A cauda esquerda ficou pior nos três recortes.** É a medição de mão dupla que o C8 exigia, e
ela dá o resultado desconfortável: a invalidação **estava** cortando perda (as perdedoras da mãe
param em −0,72 R; as da filha vão até o stop cheio, −0,88 R). O que salva a expectativa da filha
não é a cauda — é a **frequência**: 45,5 % de acerto contra 31,9 %, e 18 perdedoras em 33 contra
32 em 47. Escrito aqui porque a EXP-0022 mandou que aparecesse "com a mesma clareza".

## 7. O PORTÃO DE VOLUME É DECORAÇÃO (item 4 do dia um)

Terceis de `relative_volume_15m` **dentro** da população da v2:

| tercil | n | RVOL | exp. líquida (R) | soma R | acerto |
|---|---:|---|---:|---:|---:|
| 1 (baixo) | 11 | 1,013 – 1,360 | **+0,1907** | +2,098 | 45,5 % |
| 2 (médio) | 11 | 1,384 – 1,866 | +0,1296 | +1,426 | 45,5 % |
| 3 (alto) | 11 | 2,160 – 12,775 | **+0,0485** | +0,534 | 45,5 % |

**Monótono na direção errada:** quanto **mais** volume, **pior** o resultado. O tercil colado no
limiar é o melhor dos três. O pré-registro escreveu, palavra por palavra, o que fazer com isto:
*"Se o tercil baixo não for pior que os outros, o portão não selecionou nada e o `rvol_min` desta
versão é decoração — o que é um resultado, e tem de ser escrito."* Está escrito. **`rvol_min = 1,0`
não seleciona.** (E note-se que a taxa de acerto é 45,5 % nos três terceis: o volume não move nem
a frequência — move só o tamanho, e para baixo.)

## 8. K1–K6 (item pré-registrado de falsificação)

| porta | régua da EXP-0022 | medido | dispara? |
|---|---|---|---|
| **K1** | < 20 decisões | **33** | **não** |
| **K2** | > 1 500 decisões | 33 | não |
| **K3** | ≥ 100 avaliáveis **e** ≥ 30 dias **e** exp. bruta < 0 | 33 avaliáveis, 12 dias, bruta **+0,2609** | não (nem chega à condição) |
| **K4** | `unavailable` > 40 % | **3,76 %** (448/11 904) | não |
| **K5** | cobertura de `R_net` < 70 % | 33/33 = **100 %** | não |
| **K6** | ≥ 60 % das decisões de **um** mercado | máx **27,3 %** (DOGE) | **não** |
| **próprio** | Δ pareado vs a v1 ≤ 0 | **+0,0337** | não |

**Nenhuma porta de morte dispara.** É a primeira versão desta casa a chegar limpa ao estresse.
Geometria comparável à da mãe (item 7 do dia um): `line_touches` médio **3,30** (min 3, máx 5)
contra 3,17 nos 42 repiques da mãe; os 33 eventos são **todos** `bounce`, nenhum `breakout` —
a identidade da versão fecha.

## 9. O ESTRESSE — e é ele que mata

`replay.stress --cohort replay:7e498c13…`, `as_of 2026-09-09T19:11:10Z`, 33 entradas congeladas:

```
| cenário | tipo | n | expectancy (R) | PF | Δ vs base | IC 95 % do Δ |
|---|---|---:|---:|---:|---:|---|
| `base`                     | reprecificacao | 33 |  0.1230 | 1.2576 | —       | — |
| `custos_x2`                | reprecificacao | 33 | -0.0162 | 0.9691 | -0.1392 | [-0.1627, -0.1082] |
| `stop_x0.75`               | reprecificacao | 33 | -0.0886 | 0.8756 | -0.2116 | [-0.4205, +0.0347] |
| `stop_x1.25`               | reprecificacao | 33 |  0.1205 | 1.3160 | -0.0024 | [-0.1554, +0.1474] |
| `alvo_x0.75`               | reprecificacao | 33 |  0.1217 | 1.2734 | -0.0012 | [-0.1736, +0.2227] |
| `alvo_x1.25`               | reprecificacao | 33 |  0.1565 | 1.3279 |  0.0336 | [-0.0610, +0.0924] |
| `entrada_mais_1_barra`     | reprecificacao | 33 |  0.2263 | 1.5065 |  0.1033 | [-0.0006, +0.3965] |
| `sem_binance:DOGEUSDT`     | recorte        | 24 |  0.2406 | 1.5105 | — | — |
| `sem_binance:ETHUSDT`      | recorte        | 25 | -0.0344 | 0.9359 | — | — |
| `sem_binance:SOLUSDT`      | recorte        | 25 | -0.0308 | 0.9419 | — | — |
| `sem_binance:XRPUSDT`      | recorte        | 25 |  0.3211 | 1.8639 | — | — |
| `1a_metade_ate_2026-08-26` | recorte        | 24 |  0.1995 | 1.4001 | — | — |
| `2a_metade_apos_2026-08-26`| recorte        |  9 | -0.0811 | 0.8074 | — | — |

**Veredito:** frágil a custos
- frágil a custos: custos_x2 → expectancy -0.0162 (n=33)
- frágil a parâmetros: stop_x0.75 → expectancy -0.0886 (n=33)
- dependente de um mercado: sem_binance:ETHUSDT → expectancy -0.0344 (n=25)
- dependente de um mercado: sem_binance:SOLUSDT → expectancy -0.0308 (n=25)
- dependente de metade: 2a_metade_apos_2026-08-26 → expectancy -0.0811 (n=9)
```

**Quatro dos cinco vereditos de fragilidade disparam** (custos, parâmetros, mercado ×2, metade).
Só `alvo` e `entrada` sobrevivem — e `entrada_mais_1_barra` **melhora** a expectativa, o que é
por si um sinal ruim: uma vantagem que aumenta quando a entrada é atrasada não é a vantagem que
a hipótese descreve.

### 9.1 A decomposição por dia (item 3 do dia um) diz a mesma coisa mais cruamente

| dia | n | exp. (R) | soma R |
|---|---:|---:|---:|
| 19/08 | 1 | −0,0480 | −0,048 |
| 20/08 | 1 | +1,7966 | +1,797 |
| **21/08** | **7** | **+1,2361** | **+8,653** |
| 22/08 | 1 | −1,0162 | −1,016 |
| 23/08 | 3 | −1,0695 | −3,208 |
| 24/08 | 8 | −0,1165 | −0,932 |
| 25/08 | 2 | −1,0763 | −2,153 |
| 26/08 | 1 | +1,6955 | +1,696 |
| 27/08 | 3 | −0,2628 | −0,788 |
| 28/08 | 2 | −1,1140 | −2,228 |
| 31/08 | 2 | +0,6338 | +1,268 |
| 02/09 | 2 | +0,5095 | +1,019 |

**21/08 sozinho vale +8,653 R** contra +4,058 R da coorte inteira. **Sem esse dia, a versão soma
−4,595 R nos outros 11 dias.** É isto que o IC de blocos de dia estava medindo quando cruzou zero
— e é o C4 da EXP-0022 (`FAIL` declarado: sem regime, o que sobra é a decomposição por mercado e
por dia) respondendo exatamente o que temia.

Por mercado (K6, item 3): ETH +0,6145 R (n 8), SOL +0,6035 R (n 8), DOGE −0,1907 R (n 9),
XRP −0,4963 R (n 8). **Dois mercados ganham, dois perdem** — coerente com o estresse, que fica
negativo quando ETH ou SOL sai.

## 10. VEREDITO E DEPRECIAÇÃO (auditada, dry-run antes)

**`descartar`.** A cadeia, na ordem em que a régua a impõe:

1. K1–K6 limpos → o funil manda estressar. Estressei.
2. O estresse dispara quatro dos cinco vereditos. O SHADOW-LAB §4 diz que **cada um deles** é
   "motivo suficiente para não gastar trinta dias de prospectivo".
3. A única leitura que a EXP-0022 reconhece como confirmatória é a prospectiva. Se ela está
   proibida pela régua, manter a versão ativa custa avaliação por barra e não pode render
   evidência. Aposentar é o ato consistente.
4. E a decomposição por dia diz por que a régua está certa aqui: a vantagem é um dia.

```
$ … activate_strategy_version.py trendline_bounce v1 --deprecate --changelog … --dry-run
would deprecate trendline_bounce v1 (purpose research_only), code_ref
hunter_core.strategies.trendline_bounce_v1@sha256:fb7263ce…, params_hash 9b1e882f169c,
successor=none: EXP-0022_descartar_estresse_fragil_a_custos_e_parametros_dependente_de_ETH_SOL_e_da_2a_metade

$ … (sem --dry-run)
deprecated trendline_bounce v1 (purpose research_only) at 2026-09-09T19:13:39.426297+00:00, successor=none
```

**O que sobrevive à morte da versão** (e é o que ela custou 33 decisões para comprar):

1. **A KB-0006 continua de pé, e mais fraca.** Retirar a invalidação deu Δ +0,0337 R pareado
   (positivo, IC cruzando zero, Holm 1,0) contra +0,0922 R medido na T3.34c. A frase "a
   invalidação adianta a perda, ela não a cria" agora tem uma quinta população que **não a
   contraria** e uma cauda esquerda que **a complica**: as perdedoras sem invalidação são
   0,16 R piores.
2. **O portão de RVOL a 1,0 não seleciona.** Qualquer versão futura desta família que queira um
   piso de volume tem de justificá-lo de novo — este está medido como decoração.
3. **O `horizon_s = 28800` continua sob suspeita e agora com número:** 11 das 33 saídas foram por
   expiração. Era a próxima variante candidata da EXP-0022 e continua sendo, para uma família
   nova, não para esta versão.

Catálogo depois: `trendline_bounce v1` `deprecated`, sem sucessora; nenhuma versão viva se moveu.

## 11. NÚMEROS E SUPOSIÇÕES QUE TIVE DE ASSUMIR

1. **A fatia em duas metades** do replay é operacional (teto de `timeout 290`), não de desenho.
2. **`r_bruto` reconstruído** como `(exit_base − entry/1,0006)/initial_risk` — a mesma identidade
   das notas anteriores; `1,0006` é o custo de entrada assumido, não medido aqui.
3. **A semente do estimador pareado é `20260909`**, escolhida por mim (o estimador é novo).
   O oráculo prova que ele concorda com o bootstrap ordinário quando há um par por dia.
4. **A família do Holm tem dois membros** (os dois contrastes pareados). Incluir o de população
   exigiria um `p` que o estimador reusado não devolve; a alternativa seria alterá-lo, o que a
   disciplina de reuso proíbe.
5. **`atr_pct` não está no envelope** com esse nome, então a coluna saiu vazia na consulta de
   geometria. `line_touches` está e foi o que publiquei.
6. **A elegibilidade replayada é a de hoje** (PIPELINE §6c).
7. **A metade do estresse corta em 26/08** (escolha do próprio `stress.py`), e a segunda metade
   tem **n = 9** — abaixo dos 30 que o próprio estresse chama de `amostra_insuficiente` nos
   cenários de reprecificação. O veredito "dependente de metade" está portanto apoiado numa
   amostra pequena e deve ser lido com essa ressalva; **os outros três disparos não dependem
   dele.**

## 12. ADENDO A ACRESCENTAR À EXP-0022 (rascunho; o EXP é append-only no obsidian, não editei)

> ### Avaliação 1 — 2026-09-09 (REPLAY, dentro da amostra duas vezes) · quant-engineer
>
> Semeada, ativada (digest `…fb7263ce…` conferido contra o pré-registro, 34 parâmetros,
> `params_hash 9b1e882f169c`), replayada 31 d × 4 mercados (ETH/SOL/XRP/DOGE), coorte
> `replay:7e498c13-d79b-4466-8ff8-30550d75c21e`. Recibos e método:
> `.claude/state/notes-T3.57b.md`.
>
> **Números:** n 33 · 12 dias · 4 mercados · expectancy bruta **+0,2609 R** · pedágio
> **0,1345 R** · expectancy líquida **+0,1230 R** · PF **1,2576** · acerto 45,5 % · soma
> **+4,058 R** · desfechos 8 alvos / 14 stops / 11 expirações / **0 invalidações**.
> A mãe (`trendline_breakout v1`, mesma janela, mesmos mercados): −0,0382 R, PF 0,9220.
>
> **Os sete itens que o dia um tinha de publicar:**
> 1. *População, e por que não é subconjunto:* 24 barras nas duas, **23 só na mãe**, **9 só na
>    filha** (+0,2225 R — as melhores da coorte). As três fontes pré-registradas de divergência
>    aparecem todas. Pareamento por (mercado, barra), nunca por decisão.
> 2. *Identidade do pedágio:* medido 0,1345 R contra 0,1344 R da identidade
>    `0,002/(risco_atr·ATR%)`; máximo observado **0,2028 R** = o teto de 0,20 R declarado no C7.
> 3. *Por mercado e por dia:* ETH +0,6145 / SOL +0,6035 / DOGE −0,1907 / XRP −0,4963.
>    **21/08 sozinho soma +8,653 R** dos +4,058 R totais; sem esse dia a versão soma −4,595 R.
> 4. *O portão de volume:* **decoração.** Tercil baixo de RVOL (1,013–1,360) = **+0,1907 R**,
>    tercil alto (2,160–12,775) = **+0,0485 R**. Monótono na direção errada. `rvol_min = 1,0`
>    não selecionou nada, exatamente a hipótese nula que este item pré-registrou.
> 5. *Contraste pareado contra a v1:* n pareado **24**, só-v2 **9**, só-v1 **23**;
>    Δ **+0,0337 R**, IC 95 % de blocos de dia **[−0,1372; +0,2410]**, **p de Holm 1,0000**.
>    Cauda esquerda: p10 −1,0924 (v2) contra −1,0743 (v1); média das perdedoras **−0,8751**
>    contra **−0,7189** — **pior**. Condicionado aos 10 pares em que a v1 saiu por `invalidated`:
>    Δ +0,0809 R, IC [−0,3666; +0,5160].
> 6. *Expectancy pré-registrada:* projetada **+0,2401 R**, medida **+0,1230 R**. A explicação é
>    o item 1 (a população não são os 26 repiques da projeção: nas 24 barras compartilhadas a
>    própria mãe rende +0,0519 R, não +0,1676 R), não uma narrativa nova.
> 7. *Geometria:* `line_touches` 3,30 médio (3 a 5) contra 3,17 nos repiques da mãe; 33 de 33
>    eventos são `bounce`.
>
> **K1–K6: nenhum dispara.** K1 33 ≥ 20 · K2 33 · K3 n/a (bruta positiva) · K4 3,76 % ·
> K5 100 % · K6 máx 27,3 %. O falsificador próprio (Δ ≤ 0) também não dispara.
>
> **Estresse (K1 sobreviveu, então foi rodado):** veredito `frágil a custos`, e mais três —
> `frágil a parâmetros` (stop ×0,75 → −0,0886 R), `dependente de um mercado` (sem ETH −0,0344;
> sem SOL −0,0308) e `dependente de metade` (2ª metade −0,0811 R, n 9). Custos ×2 levam a
> expectancy a **−0,0162 R**: a margem inteira da versão cabe no pedágio.
>
> **Veredito: `descartar`.** Não pela expectancy — ela é a melhor abertura desta casa — mas pela
> régua congelada do `SHADOW-LAB.md` §4, que diz que cada disparo do estresse é motivo suficiente
> para não gastar trinta dias de prospectivo; dispararam quatro, e a decomposição por dia mostra
> por quê (um dia carrega tudo). Depreciada em 2026-09-09T19:13:39Z, sem sucessora.
>
> **O que este experimento deixou:** (i) a KB-0006 não foi contrariada e ficou mais fraca — Δ
> +0,0337 R contra +0,0922 R da T3.34c, com a cauda esquerda 0,16 R pior sem invalidação;
> (ii) `rvol_min = 1,0` está medido como decoração e não pode ser reusado sem nova justificativa;
> (iii) 11 de 33 saídas por expiração mantêm `horizon_s = 28800` na fila de suspeitos.

## 13. ≤ 10 LINHAS PARA O EVERTON (frente `trendline_bounce`)

> 1. A `trendline_bounce v1` (repique em linha de suporte, sem invalidação) entrou no ar,
>    rodou 31 dias em 4 mercados e deu **+0,12 R por operação, fator de lucro 1,26** em 33
>    operações — a **melhor estreia** que uma estratégia nossa já teve.
> 2. A mãe dela, a `trendline_breakout`, dava −0,04 R na mesma janela. Tirar o rompimento e a
>    invalidação melhorou de verdade.
> 3. Só que aí eu apliquei a régua de estresse, que estava escrita **antes** de eu ver o número.
> 4. Com o dobro de custo a vantagem some (−0,02 R). Sem ETH ou sem SOL, some. Na segunda metade
>    do mês, some. Quatro dos cinco testes de robustez reprovaram.
> 5. E o motivo apareceu na decomposição por dia: **um único dia, 21 de agosto, vale +8,65 R** —
>    mais do que os +4,06 R que a estratégia inteira somou. Nos outros 11 dias ela perde 4,60 R.
> 6. O filtro de volume que eu tinha posto (RVOL ≥ 1,0) **não filtra nada**: o volume mais baixo
>    deu o melhor resultado e o mais alto o pior. Está registrado como erro meu de desenho.
> 7. **Aposentei a versão**, com recibo, na mesma sessão. A régua diz que fragilidade no estresse
>    é motivo suficiente para não gastar 30 dias de prospectivo com ela — e eu concordo com a régua.
> 8. Isso não é desperdício: a versão custou ~4 minutos de máquina e comprou três lições que
>    valem para as próximas (a invalidação, o volume e o horizonte de 8 h).
> 9. Uma delas contraria o que eu esperava: sem invalidação, as operações perdedoras ficam
>    **piores** (−0,88 R contra −0,72 R). Ela ganhava por acertar mais, não por perder menos.
> 10. Nada tocou carteira: `research_only` do começo ao fim, `ENABLE_LIVE_TRADING=false`.
