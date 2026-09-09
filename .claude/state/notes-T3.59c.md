# notes-T3.59c — EXP-0023 medida: a janela 12–15 UTC não sobrevive nem ao dado que a escolheu

**Quando:** 2026-09-09, 15:20 → 16:20 BRT (UTC−3) · em UTC, 18:20Z → 19:20Z.
**Quem:** quant-engineer. **VPS:** `3c9a8d8` em `api` e `strategy-worker`, imagem
`hunter-api:3c9a8d8`, migração `0017_eligibility_policy`. **Nada commitado.**
**Nenhum container parado, recriado ou reiniciado. Nenhum `.env*` tocado. Nenhum `git pull`
na VPS.** **Escritas na VPS:** só pelos scripts auditados (`derive_variant.py` ×4 com ×4
dry-run antes, `activate_strategy_version.py` ×4 ativações e ×4 depreciações, cada uma com
dry-run antes) e 8 corridas de replay. Todo o resto foi lido em
`begin transaction isolation level repeatable read read only`.

---

## STATUS

**DONE.** Os quatro braços foram derivados, ativados `research_only`, replayados 31 d × 4
mercados com `--explain-ledger` e coortes explícitas, pareados por (mercado, barra) contra o
pai, avaliados por bootstrap de blocos de dia — e **os quatro foram descartados e depreciados**,
pela regra pré-registrada, no mesmo turno.

**O resultado em uma frase:** a janela 12–15 UTC **não sobrevive nem à falsificação dentro da
amostra que a escolheu** — nenhum braço chega aos 30 desfechos de K1, e o braço H2, o único com
população perto disso, sai **−0,2865 R pior que o pai com IC 95 % inteiramente abaixo de zero**:
a janela seleciona as *piores* decisões do `momentum v11`, não as melhores.

| braço | versão | portão | n | K1 (n ≥ 30) | Δ vs pai (R) | IC 95 % blocos de dia | veredito |
|---|---|---|---:|---|---:|---|---|
| **H1** | `mean_reversion v12` | `hours=12-15` | **7** | ✗ | +0,1874 | [−0,9770; +0,6630] | **descartar** |
| **H2** | `momentum v12` | `regime=btc:BTC_BULL,HIGH_VOLATILITY` + `hours=12-15` | **21** | ✗ | **−0,2865** | **[−0,4781; −0,0562]** | **descartar** |
| **C1** | `mean_reversion v13` | `hours=13-16` | **5** | ✗ | +0,1852 | [−1,1832; +0,6929] | **descartar** |
| **C2** | `momentum v13` | `regime=…` + `hours=13-16` | **29** | ✗ | +0,0292 | [−0,4148; +0,4613] | **descartar** |

Regra pré-registrada (EXP-0023, "Critério de sucesso"): sobrevive quem tiver **n ≥ 30 E
Δ ≥ +0,05 R E IC inteiramente acima de zero**. *Qualquer coisa menos que isso é `descartar`.*
Nenhum braço passa o primeiro item; **nenhum estresse foi rodado**, porque o pré-registro manda
estressar só o que sobrevive a K1.

---

## ARQUIVOS

| Arquivo | O quê |
|---|---|
| `infra/scripts/sql/research/2026-09-09-t359c-q00-estado.sql` | estado antes de qualquer escrita |
| `infra/scripts/sql/research/2026-09-09-t359c-q01-coortes.sql` | coortes de replay existentes |
| `infra/scripts/sql/research/2026-09-09-t359c-q02-politicas.sql` | as 4 políticas congeladas (e o tipo do limite) |
| `infra/scripts/sql/research/2026-09-09-t359c-q10-populacoes.sql` | populações, pedágio, expectativa, PF |
| `infra/scripts/sql/research/2026-09-09-t359c-q11-pareado.sql` | pareamento por (mercado, barra, lado) |
| `infra/scripts/sql/research/2026-09-09-t359c-q12-dump-csv.sql` | dump por decisão (CSV) |
| `infra/scripts/sql/research/2026-09-09-t359c-q30-portas-k.sql` | K5 (cobertura de R), sinais × desfechos |
| `infra/scripts/sql/research/2026-09-09-t359c-q40-catalogo-depois.sql` | catálogo depois + recibos |
| `.claude/state/exp-drafts/t359c/janela.py` | Δ com o dia como bloco, reusando `t342-blocos/blocos.py` **sem alterar uma linha** |
| `.claude/state/exp-drafts/t359c-decisoes.csv` | o dump lido da VPS (326 linhas) |
| `.claude/state/notes-T3.59c.md` | este arquivo |

Todos com raiz em `C:\dev\project-hunter\`.

---

## 1. ESTADO ANTES — `read_at = 2026-09-09 18:21:38,983869+00` (15:21:38 BRT)

`alembic_version = 0017_eligibility_policy`. Os dois pais existem, ativos e `research_only`:

```
mean_reversion v10 | active | research_only | (sem política) | code_ref …a970c9d9…
momentum       v11 | active | research_only | {"regime": {"rule": "previous_closed_hour",
                     "allow": ["BTC_BULL","HIGH_VOLATILITY"], "scope": "btc",
                     "classifier_version": "regime_hourly_v1"}} | code_ref …ab2e0398…
```

Coortes de replay dos pais, que são as contrapartes do pareamento:
`mean_reversion v10 → replay:71c76d86…` (54 sinais) e `momentum v11 → replay:4a60a3dc…`
(101 sinais).

## 2. AS QUATRO DERIVAÇÕES (dry-run antes de cada escrita)

Os quatro `--dry-run` passaram e a escrita repetiu palavra por palavra, trocando "derivaria"
por "derivada". A **numeração saiu como a EXP-0023 previu** (a ordem de escrita foi H1, C1, H2,
C2, de propósito, para que os números batessem com o pré-registro):

```
derivada mean_reversion v12 de v10 … : policy -> hours=12-15                              [params_hash d4fcf66f9449]
derivada mean_reversion v13 de v10 … : policy -> hours=13-16                              [params_hash d4fcf66f9449]
derivada momentum       v12 de v11 … : policy -> btc:BTC_BULL,HIGH_VOLATILITY;hours=12-15 [params_hash 69152dbc9173]
derivada momentum       v13 de v11 … : policy -> btc:BTC_BULL,HIGH_VOLATILITY;hours=13-16 [params_hash 69152dbc9173]
```

`params_hash` **idêntico ao do pai** nos quatro, de propósito: o que muda é só
`eligibility_policy`. **A recusa da T3.59 §2.3 foi exercida na prática:** H2/C2 tiveram de
reenunciar o portão de regime do pai por extenso; largá-lo em silêncio é recusado pelo script.

### 2.1 A correção da T3.59 §3.1 está provada contra o banco de produção

A coluna guarda **inteiros**, não strings — que era o defeito que teria emudecido a coorte
inteira atrás de um `/ready` verde:

```
versao             | tipo_do_limite | policy
mean_reversion v12 | number         | {"hours": {"utc": [[12, 15]]}}
mean_reversion v13 | number         | {"hours": {"utc": [[13, 16]]}}
momentum v12       | number         | {"hours": {"utc": [[12, 15]]}, "regime": {…"allow": ["BTC_BULL","HIGH_VOLATILITY"]…}}
momentum v13       | number         | {"hours": {"utc": [[13, 16]]}, "regime": {…}}
```

Nenhuma versão saiu do roster por `policy_unreadable`, e as quatro decidiram — a prova
empírica que a T3.59 só tinha em testcontainer.

## 3. AS ATIVAÇÕES

Quatro, `research_only` preservado (o script não tem `--purpose`, T3.52d §2.3 — desvio já
registrado, não é novo):

```
activated mean_reversion v12 (purpose research_only) at 2026-09-09T18:24:43.334572+00:00 …a970c9d9…
activated mean_reversion v13 (purpose research_only) at 2026-09-09T18:24:50.590653+00:00 …a970c9d9…
activated momentum       v12 (purpose research_only) at 2026-09-09T18:24:57.387544+00:00 …ab2e0398…
activated momentum       v13 (purpose research_only) at 2026-09-09T18:25:04.681658+00:00 …ab2e0398…
```

## 4. OS OITO REPLAYS — 31 d × 4 mercados (ETH, SOL, XRP, DOGE), 0 erros

Duas fatias por braço (08-08→08-23 e 08-23→09-08), `--explain-ledger` nas oito, coorte própria
por braço, `context_minutes = 1560` em todas, `docker exec hunter-strategy-worker-1` (precedente
da T3.52d §3), `timeout 280` por fatia.

| braço | coorte | barras | `ineligible` | `unavailable` | `not_triggered` | `triggered` | **sinais** | s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| H1 `mean_reversion v12` | `4ed2ec88` | 11 904 | 10 416 | 48 | 1 431 | 9 | **7** | 161,7 |
| C1 `mean_reversion v13` | `29bc81bf` | 11 904 | 10 416 | 48 | 1 431 | 9 | **5** | 154,4 |
| H2 `momentum v12` | `fbb65b47` | 11 904 | 11 328 | 0 | 538 | 38 | **21** | 156,2 |
| C2 `momentum v13` | `9a48a940` | 11 904 | 11 328 | 0 | 513 | 63 | **30** | 150,0 |

(`replay_runs.signals` é cumulativo por `run_id` — T3.54 §3.6; os totais acima já são os reais.)

### 4.1 O ledger fecha na aritmética, e a previsão da população acerta no ponto

```
== H1 e C1 (só janela)            == H2 (janela + regime)          == C2 (janela + regime)
   10416 hours_gate:*                10416 hours_gate:*                10416 hours_gate:*
                                       448 regime_gate:unknown           432 regime_gate:unknown
                                       288 regime_gate:SIDEWAYS          320 regime_gate:SIDEWAYS
                                       112 regime_gate:BTC_BEAR           80 regime_gate:BTC_BEAR
                                        64 regime_gate:LOW_VOLATILITY     80 regime_gate:LOW_VOLATILITY
```

- **10 416 / 11 904 = 87,50 % exatos.** A EXP-0023 previu 87,5 % (3 de 24 horas) e é isso, ao
  dígito: a perda de população é aritmética, não estatística, como a ACTIVATION §7c diz.
- **A precedência declarada é visível no ledger.** Em H2/C2 a fatia de `hours_gate` vem **antes**
  da de `regime_gate` (T3.59 §2.2), então essas 912/928 recusas de regime são só as das barras
  **dentro** da janela — e por isso **não** são comparáveis com as 3 664 `regime_gate:unknown`
  da T3.52d §3.2. A previsão 4 da EXP-0023 acerta.
- **Barras elegíveis:** 1 488 em H1/C1 (12,50 %); **576** em H2/C2 (**4,84 %**) — a interseção
  que a EXP-0023 previu como "~3,8 %, e a coorte pode não chegar a dez decisões". Chegou a 21 e
  a 30, porque a barreira do slot re-arma mais rápido quando quase toda barra é `ineligible`.
- Somas conferidas linha a linha: 1 488 = 48 + 1 431 + 9; 576 = 538 + 38 = 513 + 63.

## 5. AS POPULAÇÕES — `read_at = 2026-09-09 18:44:24,802178+00` (15:44:24 BRT)

| versão | coorte | n | dias | mercados | pedágio (R) | exp. bruta (R) | exp. líquida (R) | soma R | PF | acerto |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `mean_reversion v10` (pai) | `71c76d86` | 54 | 16 | 4 | 0,1038 | +0,3071 | **+0,2013** | +10,871 | 2,4956 | 68,5 % |
| **H1** `v12` | `4ed2ec88` | **7** | 4 | 3 | 0,1047 | +0,4964 | **+0,3887** | +2,721 | 3,4322 | 85,7 % |
| **C1** `v13` | `29bc81bf` | **5** | 3 | 3 | 0,1143 | +0,5034 | **+0,3866** | +1,933 | 2,7277 | 80,0 % |
| `momentum v11` (pai) | `4a60a3dc` | 101 | 14 | 4 | 0,1158 | +0,1904 | **+0,0737** | +7,441 | 1,2510 | 32,7 % |
| **H2** `v12` | `fbb65b47` | **21** | 6 | 4 | 0,1112 | −0,1328 | **−0,2446** | −5,136 | 0,4350 | 14,3 % |
| **C2** `v13` | `9a48a940` | **29** | 7 | 4 | 0,1158 | +0,1092 | **−0,0074** | −0,214 | 0,9807 | 20,7 % |

**H2 perde no bruto.** A expectativa **bruta** dele é −0,1328 R: a janela não escolheu decisões
caras, escolheu decisões ruins. Não há pedágio a corrigir.

## 6. O PAREAMENTO POR (MERCADO, BARRA) — e a regressão que ele prova

| braço | classe | n | exp. pai (R) | exp. filha (R) | divergem no R |
|---|---|---:|---:|---:|---:|
| H1 | 1 nos dois | 6 | +0,3887 | +0,3887 | **0** |
| H1 | 2 só no pai (removida pela janela) | 48 | +0,1779 | — | 0 |
| H1 | 3 **só na filha** (o slot divergiu) | **1** | — | +0,3887 | 0 |
| C1 | 1 nos dois | 5 | +0,3866 | +0,3866 | **0** |
| C1 | 2 só no pai | 49 | +0,1824 | — | 0 |
| H2 | 1 nos dois | 14 | **−0,2128** | **−0,2128** | **0** |
| H2 | 2 só no pai | 87 | +0,1198 | — | 0 |
| H2 | 3 **só na filha** | **7** | — | −0,3080 | 0 |
| C2 | 1 nos dois | 21 | +0,1029 | +0,1029 | **0** |
| C2 | 2 só no pai | 80 | +0,0660 | — | 0 |
| C2 | 3 **só na filha** | **8** | — | −0,2969 | 0 |

1. **Zero divergência de `r_multiple` em 46 decisões compartilhadas.** O portão de horas **só
   remove**; ele não muda uma decisão que deixa passar. É a mesma prova que a T3.52d §4.1 deu
   para o portão de regime, agora para a regra nova.
2. **A filha continua não sendo subconjunto das decisões do pai** (PIPELINE §4b item 11): 1, 7 e
   8 decisões que o pai nunca tomou. O desenho pareado por (mercado, barra) é obrigatório e foi
   o usado; parear por decisão teria inventado 16 pares.
3. **A leitura que mata H2 está na linha "1 nos dois":** nas 14 barras que a janela deixou
   passar, o **próprio pai** rende **−0,2128 R**, contra **+0,1198 R** nas 87 que ela removeu.
   A janela 12–15 UTC, sobre `momentum v11`, é um filtro que **inverte o sinal**.

## 7. BLOCOS DE DIA — `t359c/janela.py`, reusando `t342-blocos/blocos.py` sem alterar uma linha

10 000 reamostragens, dias inteiros com reposição, semente `20260908` (a do estimador herdado).
A marca por decisão é "a filha manteve esta barra" no lugar do piso de ATR%; piso 0,5 —
exatamente o adaptador que a T3.52d §4.3 usou.

```
H1 — mean_reversion v12 (hours=12-15) vs v10: 55 linhas
  r_net    | só a população do pai    | dias 16 | n_pai  54 | n_filha   6 | exp_pai +0.2013 | exp_filha +0.3887 | delta +0.1874 | IC95 [-0.9770; +0.6630]
  r_bruto  | só a população do pai    | dias 16 | n_pai  54 | n_filha   6 | exp_pai +0.3071 | exp_filha +0.4984 | delta +0.1913 | IC95 [-0.9199; +0.6585]
  r_net    | com as extras da filha   | dias 16 | n_pai  55 | n_filha   7 | exp_pai +0.2047 | exp_filha +0.3887 | delta +0.1840 | IC95 [-0.9770; +0.6605]
H2 — momentum v12 (regime+hours=12-15) vs v11: 108 linhas
  r_net    | só a população do pai    | dias 14 | n_pai 101 | n_filha  14 | exp_pai +0.0737 | exp_filha -0.2128 | delta -0.2865 | IC95 [-0.4781; -0.0562]
  r_bruto  | só a população do pai    | dias 14 | n_pai 101 | n_filha  14 | exp_pai +0.1904 | exp_filha -0.0951 | delta -0.2855 | IC95 [-0.4840; -0.0394]
  r_net    | com as extras da filha   | dias 14 | n_pai 108 | n_filha  21 | exp_pai +0.0489 | exp_filha -0.2446 | delta -0.2935 | IC95 [-0.5885; +0.0364]
C1 — mean_reversion v13 (hours=13-16) vs v10: 54 linhas
  r_net    | só a população do pai    | dias 16 | n_pai  54 | n_filha   5 | exp_pai +0.2013 | exp_filha +0.3866 | delta +0.1852 | IC95 [-1.1832; +0.6929]
  r_bruto  | só a população do pai    | dias 16 | n_pai  54 | n_filha   5 | exp_pai +0.3071 | exp_filha +0.5034 | delta +0.1963 | IC95 [-1.1202; +0.6936]
  r_net    | com as extras da filha   | dias 16 | n_pai  54 | n_filha   5 | exp_pai +0.2013 | exp_filha +0.3866 | delta +0.1852 | IC95 [-1.1832; +0.6929]
C2 — momentum v13 (regime+hours=13-16) vs v11: 109 linhas
  r_net    | só a população do pai    | dias 14 | n_pai 101 | n_filha  21 | exp_pai +0.0737 | exp_filha +0.1029 | delta +0.0292 | IC95 [-0.4148; +0.4613]
  r_bruto  | só a população do pai    | dias 14 | n_pai 101 | n_filha  21 | exp_pai +0.1904 | exp_filha +0.2208 | delta +0.0304 | IC95 [-0.4208; +0.4902]
  r_net    | com as extras da filha   | dias 14 | n_pai 109 | n_filha  29 | exp_pai +0.0465 | exp_filha -0.0074 | delta -0.0538 | IC95 [-0.4721; +0.3354]
```

Três dos quatro IC cruzam zero. **O quarto (H2) não cruza — e está inteiramente do lado errado.**
É o único resultado estatisticamente distinguível deste experimento e ele **falsifica** a
hipótese em vez de confirmá-la.

## 8. AS PORTAS K

| braço | K1 (<20 mata na régua da casa; **a EXP-0023 exige ≥ 30**) | K2 (>1500) | K3 | K4 | K5 (cobertura de R) |
|---|---|---|---|---|---|
| H1 | **7** — dispara nas duas réguas | não | n/a (n<100) | **não mensurável** | 7/7 = **100 %** |
| C1 | **5** — dispara nas duas | não | n/a | **não mensurável** | 5/5 = **100 %** |
| H2 | **21** — passa a régua da casa, **falha a do EXP** | não | n/a | **não mensurável** | 21/21 = **100 %** |
| C2 | **29** — idem | não | n/a | **não mensurável** | 29/30 = **96,7 %** |

**K4 não é mensurável em nenhum dos quatro** (PIPELINE §4b item 12 / SHADOW-LAB §4): o portão
avalia antes da checagem de contexto, então `unavailable` vira `ineligible` e o zero é falso
verde. A leitura honesta é a **do pai**, na mesma janela. Nota de reforço medida aqui: H1/C1
medem `unavailable = 48` (não zero), porque o `hours_gate` deixa passar as barras de aquecimento
que caem dentro de 12–15; H2/C2 medem **0** porque o portão de regime as absorve. **Duas versões
da mesma família medindo `unavailable` diferente sem que a qualidade do dado tenha mudado é a
demonstração empírica de que, sob portão, essa métrica não é sobre o dado.**

## 9. VEREDITOS E DEPRECIAÇÕES (auditadas, dry-run antes de cada uma)

Regra pré-registrada aplicada sem folga. **Cláusula de falsificação:** C1/C2 não passaram o
critério, então ela não foi acionada — mas C1 sai com Δ **positivo** (+0,1852), do mesmo tamanho
do de H1 (+0,1874), o que é exatamente o aviso do item 4 dos braços: **um Δ positivo do tamanho
do de H1 aparece também na janela que a T3.54 mediu como negativa.** Com n de 5 a 7 e 16 blocos
de dia, o estimador produz Δ de ~+0,18 R por seleção, não por sinal.

```
deprecated mean_reversion v12 (purpose research_only) at 2026-09-09T19:13:10.236954+00:00, successor=none
deprecated mean_reversion v13 (purpose research_only) at 2026-09-09T19:13:17.857566+00:00, successor=none
deprecated momentum       v12 (purpose research_only) at 2026-09-09T19:13:25.283327+00:00, successor=none
deprecated momentum       v13 (purpose research_only) at 2026-09-09T19:13:32.412316+00:00, successor=none
```

Catálogo depois (`read_at = 2026-09-09 19:13:53,700894+00`): **11 versões ativas, byte a byte as
mesmas de antes desta tarefa** — `mean_reversion v1/v2/v3/v6/v7/v8/v10`, `mean_reversion_h1 v1`,
`momentum v3 (paper)/v8/v11`. Nenhuma linha viva se moveu; os quatro braços nasceram, mediram e
morreram no mesmo turno. 14 recibos em `system_events` (`component = activate_strategy_version`):
4 `strategy_version_variant_derived`, 5 `strategy_version_activated` (as 4 daqui + a da T3.57b),
5 `strategy_version_deprecated` (as 4 daqui + a da T3.57b).

**Ressalva de latência do roster** (ACTIVATION §7b, medida na T3.56): o `strategy-worker`
recarrega o roster a cada 60 s, então cada braço pôde decidir por até um minuto depois do
`deprecated_at` na faixa viva. As quatro coortes desta nota são `replay` e não são afetadas.

## 10. O QUE ESTE EXPERIMENTO PROVOU E O QUE NÃO PROVOU

**Provou** (e é o que a EXP-0023 dizia que o replay podia fazer):
1. A regra `hours` funciona exatamente como especificada: 87,50 % das barras recusadas ao
   dígito, `AND` com o regime, precedência hora → regime visível no ledger, e **zero** alteração
   nas decisões que ela deixa passar (46 pares idênticos).
2. A correção de escrita da T3.59 §3.1 sobrevive ao round-trip do banco de produção.
3. A hipótese "12–15 UTC é sistematicamente melhor" **é falsa no `momentum`**, com IC inteiramente
   abaixo de zero — e falsa **no dado que a sugeriu**, que é o teste mais fácil que ela poderia
   ter. A pista da T3.54 §5 (+0,70 R na hora 12, n = 16) era ruído de melhor-de-24.

**Não provou**, e ninguém deve ler assim:
1. **Nada sobre `mean_reversion`.** Com 7 e 5 decisões não há amostra; `inconclusivo`, nunca
   "a janela não funciona lá". A EXP-0023 já dizia que K1 sozinho é inconclusivo.
2. **Nada prospectivo.** As quatro coortes são `replay`, dentro da amostra, na mesma janela em
   que a hipótese foi garimpada. Nenhuma delas poderia confirmar coisa alguma — e como as quatro
   estão depreciadas, **não existe leitura prospectiva desta hipótese**, por decisão.
3. **Nada sobre outras janelas.** Testar uma terceira janela agora seria a multiplicidade que a
   KB-0010 cobra: o espaço de janelas contíguas tem centenas de pares e este experimento gastou
   dois.

## 11. NÚMEROS E SUPOSIÇÕES QUE TIVE DE ASSUMIR

1. **A fatia do replay em duas metades (08-08→08-23, 08-23→09-08)** é operacional (o teto de
   `timeout 290` por fatia), não de desenho: as duas metades entram na mesma coorte e o
   `run_id` é o mesmo. Precedente da T3.52d §3.
2. **`REPLAY_DECISION_LAG_S = 2 s`** é o padrão do replay (PIPELINE §6c) e não foi tocado.
3. **A semente do bootstrap** é a do estimador herdado (`20260908`), não escolhida aqui.
4. **`r_bruto` é reconstruído** como `(exit_base − entry/1,0006)/initial_risk`, a identidade da
   T3.52d q10 / T3.54 q10 — o `1,0006` é o custo de entrada assumido, não medido nesta tarefa.
5. **A elegibilidade replayada é a de hoje** (PIPELINE §6c, "o que um replay não prova"): os
   quatro mercados são o conjunto atual, não o da janela de agosto.
6. **O `unavailable = 48` de H1/C1** foi lido do ledger, não decomposto por causa — o campo
   `detail` do JSONL carrega só `eligibility_reason` (CONCERN 3 da T3.52d, ainda aberto).
7. **A ordem de escrita das derivações (H1, C1, H2, C2)** foi escolhida por mim para que a
   numeração do banco batesse com o pré-registro. `next_free_version` decide sozinho; se outra
   tarefa tivesse escrito entre duas chamadas, os números seriam outros e o que identifica cada
   braço continuaria sendo a coorte + o portão, como a EXP-0023 nota 1 diz.

## 12. ADENDO A ACRESCENTAR À EXP-0023 (rascunho; o EXP é append-only no obsidian, não editei)

> ### Avaliação 1 — 2026-09-09 (REPLAY, dentro da amostra) · quant-engineer
>
> Quatro braços derivados, ativados `research_only`, replayados 31 d × 4 mercados
> (ETH/SOL/XRP/DOGE), coortes `replay:4ed2ec88…` (H1), `replay:29bc81bf…` (C1),
> `replay:fbb65b47…` (H2), `replay:9a48a940…` (C2). Recibos e método:
> `.claude/state/notes-T3.59c.md`.
>
> | data | braço | n | Δ R pareado | IC 95 % (blocos de dia) | veredito |
> |---|---|---:|---:|---|---|
> | 2026-09-09 | H1 `mean_reversion v12` | 7 | +0,1874 | [−0,9770; +0,6630] | **descartar** (K1) |
> | 2026-09-09 | H2 `momentum v12` | 21 | **−0,2865** | **[−0,4781; −0,0562]** | **descartar** (K1 + Δ negativo) |
> | 2026-09-09 | C1 `mean_reversion v13` | 5 | +0,1852 | [−1,1832; +0,6929] | **descartar** (K1) |
> | 2026-09-09 | C2 `momentum v13` | 29 | +0,0292 | [−0,4148; +0,4613] | **descartar** (K1) |
>
> **As previsões registradas antes da corrida, conferidas:**
> - *População (previsão 1):* 87,5 % das barras recusadas — **acertou ao dígito** (10 416 de
>   11 904). O braço H2 foi previsto como "em risco de morrer no K1" e morreu (21 < 30). O que
>   a previsão errou foi para **mais**: ela dizia "pode não chegar a dez decisões" e H2 chegou a
>   21, porque a barreira do slot re-arma mais depressa quando quase toda barra é `ineligible`.
> - *Sinal (previsão 2):* "H1 e H2 devem sair com Δ positivo — é o que a seleção garante".
>   **Errou em H2, e a direção do erro é o achado:** Δ **−0,2865 R**, IC inteiramente abaixo de
>   zero. Nas 14 barras que a janela deixou passar, o próprio pai rende −0,2128 R contra
>   +0,1198 R nas 87 removidas.
> - *Controle (previsão 3):* "C1/C2 devem sair com Δ ≤ 0". **Errou nos dois** (+0,1852 e
>   +0,0292), e é uma lição sobre o estimador, não sobre o mercado: com n de 5 a 7 e 16 blocos,
>   o Δ pontual do controle é do mesmo tamanho do de H1. A cláusula de falsificação não foi
>   acionada porque C1/C2 não passaram os três itens — mas o alerta do item 4 dos braços vale
>   integralmente.
> - *`ineligible` (previsão 4):* confirmada — em H2/C2 a fatia `hours_gate` vem antes da de
>   `regime_gate`, e as duas fatias não são comparáveis com as da T3.52d.
>
> **Conclusão pré-registrada:** nenhum braço sobreviveu; os quatro foram depreciados na mesma
> sessão (recibos em `system_events`). Não há coorte prospectiva desta hipótese, por decisão.
> A hipótese "só operar de manhã" morreu barata, hoje, sem gastar um mês de calendário — que é
> exatamente para o que este desenho existia.

## 13. ≤ 10 LINHAS PARA O EVERTON (frente EXP-0023)

> 1. Testei a ideia "operar só de manhã" (12h–15h UTC = 9h–12h de Brasília) do jeito honesto:
>    quatro versões, duas com a janela boa e duas com a janela de Nova York como controle.
> 2. As quatro rodaram 31 dias em 4 mercados. O portão funcionou perfeito: recusou 87,50 % das
>    barras, exatamente as 21 horas de 24 que ele devia recusar.
> 3. **A ideia morreu.** Nenhuma das quatro chegou às 30 operações que eu tinha exigido por
>    escrito antes de olhar o resultado.
> 4. E a pior notícia é a mais útil: no `momentum`, a janela da manhã ficou **0,29 R por operação
>    pior** que a versão sem janela, com intervalo de confiança inteiro do lado negativo.
> 5. Ou seja: naquelas 14 operações que a janela deixou passar, a versão original também perdia.
>    A manhã não seleciona as boas — seleciona as ruins.
> 6. Aquele "+0,70 R na hora das 9h" que apareceu na T3.54 era ruído: foi a melhor de 24 horas
>    com 16 operações. Escolher a melhor de 24 e depois confirmar é o erro que eu escrevi antes
>    justamente para não cometer.
> 7. As quatro versões foram **aposentadas na mesma sessão**, com recibo. O catálogo ficou
>    idêntico ao de antes: nasceram, mediram e morreram no mesmo turno.
> 8. Custo total: 8 replays, ~20 minutos de máquina, zero dias de calendário.
> 9. Nada disso tocou carteira: `research_only` do começo ao fim, `ENABLE_LIVE_TRADING=false`.
> 10. O que sobrou de valor: a regra de janela de horas está **provada em produção** e pronta
>     para a próxima hipótese que a justifique — esta não justificou.
