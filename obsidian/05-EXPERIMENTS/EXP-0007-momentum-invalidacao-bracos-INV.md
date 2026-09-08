---
tags: [experimento, shadow-lab, saidas, invalidacao]
updated: 2026-09-08
status: avaliado
owner: sexta-feira
exp: EXP-0007
strategy: "momentum / volume_anomaly"
version: "v1, v2"
result: inconclusivo
evaluable: 1681
days: 29
last_eval: 2026-09-08
---

# EXP-0007 — os braços de saída (INV/TGT/EXIT) sobre entradas congeladas

> **Arquivado pela Sexta-feira em 2026-09-08 (T3.32b)** a partir do rascunho da T3.32
> (`.claude/state/exp-drafts/EXP-0007-momentum-invalidacao-bracos-INV.md`). Nome de arquivo em ASCII
> de propósito (`bracos`, sem cedilha) para não depender de normalização de acento no vault.
> **Nada foi ativado, nada foi escrito.** As quatro corridas abrem a transação como
> `REPEATABLE READ, READ ONLY` (`replay/load.py::read_only_session`), então **nenhuma coorte nova
> foi criada** — este experimento não gera linha em `agent_signals` nem em `signal_outcomes`.

## Hipótese (congelada)

A regra de saída da `momentum`/`volume_anomaly` — em particular a **invalidação** (fechamento
alinhado abaixo da máxima dos 20 fechamentos anteriores) — destrói valor, e trocá-la por um dos
braços da [[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]] muda o sinal da expectancy.
Contra-hipótese pré-registrada da
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]: a diferença é indistinguível de zero
e/ou troca de sinal entre populações.

## Protocolo (congelado — nunca editar)

- **Método:** replay de **política de saída** sobre entradas **congeladas**, não estratégia nova.
  A mesma entrada, os mesmos níveis, a mesma barra; só a regra de saída muda. É o pareamento que a
  [[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]] pede
  (`Δ = média_i(R_i^alt − R_i^atual)`) e que uma `momentum_v2` prospectiva **não** produziria (ela
  re-arma sozinha e misturaria seleção de entrada com saída — T3.26/T3.27).
- **Ferramenta:** `infra/scripts/replay_exits.py` (T3.32 acrescentou os seletores de população
  `--only-version` e `--cohort`; sem eles a corrida dobra as duas coortes de replay da mesma versão
  e conta cada par duas vezes). As regras de saída **não** são reimplementadas: cada braço é dobrado
  por `hunter_strategy_worker.walker.walk` e liquidado por `settle.settle` — o código de produção.
- **Braços registrados** (`packages/indicators/hunter_indicators/replay/policies.py`, versão 1 de
  cada): `base` (INV-A, o que o Lab acompanhou), `INV-B` (sem invalidação), `INV-C` (invalidação só
  após dois fechamentos alinhados consecutivos), `INV-E` (invalidação em `L − 0,25 × ATR₀`),
  `TGT-3` / `TGT-4.5` (alvo em 3,0 / 4,5 ATR₀ — os `target2`/`target3` já persistidos),
  `EXIT-NOTGT` (sem alvo), `EXIT-CHAN` (sem alvo + saída de canal 15 m/10, invalidação mantida).
- **Contrastes declarados antes do resultado:** os sete de `policies.py::CONTRASTS`.
  Efeito mínimo **0,05 R**; Holm sempre sobre família **7**; inversão de sinal por **blocos de dia**,
  10 000 reamostras, semente 20260906.
- **Portão do passo 1:** nenhum contraste é computado se a reprodução de trajetória da base ficar
  abaixo de 0,99.
- **Custos assumidos:** spread 2 bps, slippage 5 bps/lado, taxa 4 bps/lado, funding assinado.
- **Corte de dados (`as_of`)**: `2026-09-08T04:00:00Z` nas duas coortes de replay (todas as entradas
  congeladas terminam em 2026-09-07 23:15Z) e `2026-09-08T15:00:00Z` nas duas prospectivas.
- **Populações (quatro, avaliadas separadamente — nunca somadas):**

| # | versão | coorte | mercados | janela das entradas | linhas |
|---|---|---|---|---|---:|
| P1 | momentum v2 | `replay:f8d8279c-1fba-42ae-95ef-202042f96c60` | ETH, SOL, XRP, DOGE | 2026-08-11 → 09-07 (24 dias) | 224 |
| P2 | volume_anomaly v2 | `replay:bac27c12-7e50-4dfa-9eee-35fccc4012d7` | ETH, SOL, XRP, DOGE | 2026-08-09 → 09-06 (29 dias) | 341 |
| P3 | momentum v2 | `prospective` | universo monitorado | 2026-09-08 (1 dia) | 210 |
| P4 | momentum v1 | `prospective` | universo monitorado | 2026-09-06 → 09-08 (3 dias) | 963 |

## Avaliações (acrescentadas, nunca reescritas)

### Avaliação de 2026-09-08 — `read_at = 2026-09-08T15:11Z–15:15Z`

**Comandos executados** (dentro do container `hunter-strategy-worker-1` da VPS, script copiado para
`/tmp` — a imagem **não** foi alterada; `sha256 = db4877d0…e626`, idêntico ao arquivo do repositório):

```
python /tmp/replay_exits_t332.py --database-url "$DATABASE_URL" \
    --versions momentum --only-version momentum_v2 \
    --cohort replay:f8d8279c-1fba-42ae-95ef-202042f96c60 \
    --as-of 2026-09-08T04:00:00Z --out /tmp/t332-momentum-v2.md          # P1
    ... --versions volume_anomaly --only-version volume_anomaly_v2 \
        --cohort replay:bac27c12-7e50-4dfa-9eee-35fccc4012d7 ...          # P2
    ... --only-version momentum_v2 --cohort prospective --as-of 2026-09-08T15:00:00Z ...   # P3
    ... --only-version momentum_v1 --cohort prospective --as-of 2026-09-08T15:00:00Z ...   # P4
```

**Recibos** (`input_digest` / `series_digest`, prefixo de 16):

| # | `input_digest` | `series_digest` | portão passo 1 |
|---|---|---|---|
| P1 | `6000867c3df37418` | `3bd45752b9f8bc3d` | 224/224 = **1,0000** |
| P2 | `0273c35e2cfb91db` | `e9fa4d96e48b6424` | 341/341 = **1,0000** |
| P3 | `70b5ee97a59a5bda` | `128d3b1119e36c70` | 202/202 = **1,0000** |
| P4 | `98a1ffd048090c69` | `dfeb03c4200a41e8` | 948 comparáveis, 915 reproduzidos = **0,9652** total, **1,0000** de trajetória (as 33 divergências são só de liquidação/funding) |

**Cobertura e métricas por braço — P1, `momentum v2`, coorte `replay:f8d8279c` (224 linhas):**

| braço | avaliáveis | gatilhos | taxa de alvo | taxa de lucro líq. | expectancy líq. (R) | PF |
|---|---:|---|---:|---:|---:|---:|
| base (INV-A) | 222 | invalidação 82 | 0,669 (91/136) | 0,414 | **−0,1717** | 0,645 |
| INV-B | 223 | — | 0,521 (110/211) | 0,498 | −0,1800 | 0,675 |
| INV-C | 222 | 2 fechamentos 47 | 0,588 (100/170) | 0,455 | −0,1651 | 0,676 |
| INV-E | 222 | invalidação 64 | 0,649 (100/154) | 0,455 | −0,1519 | 0,694 |
| TGT-3 | 223 | invalidação 95 | 0,540 (61/113) | 0,318 | −0,0631 | 0,886 |
| TGT-4.5 | 223 | invalidação 95 | 0,383 (36/94) | 0,287 | −0,0551 | 0,906 |
| **EXIT-NOTGT** | 223 | invalidação 97 | 0 (0/63) | 0,251 | **−0,0054** | **0,991** |
| EXIT-CHAN | 223 | canal 21 + inval. 97 | 0 (0/58) | 0,238 | −0,0188 | 0,969 |

**Contrastes pareados — P1** (222–223 pares, 24 blocos):

| contraste | Δ médio R | IC 95 % (blocos) | p | p Holm | rejeita? | \|Δ\| ≥ 0,05 R |
|---|---:|---|---:|---:|---|---|
| INV-B − base | −0,0062 | [−0,0846; 0,0725] | 0,889 | 1,000 | não | não |
| INV-C − base | +0,0065 | [−0,0336; 0,0467] | 0,768 | 1,000 | não | não |
| INV-E − base | +0,0198 | [−0,0273; 0,0664] | 0,458 | 1,000 | não | não |
| TGT-3 − base | +0,1036 | [−0,0112; 0,2053] | 0,119 | 0,831 | não | **sim** |
| TGT-4.5 − base | +0,1136 | [−0,0875; 0,3184] | 0,332 | 1,000 | não | **sim** |
| EXIT-NOTGT − base | **+0,1635** | [−0,2184; 0,5871] | 0,508 | 1,000 | não | **sim** |
| EXIT-CHAN − EXIT-NOTGT | −0,0133 | [−0,0403; 0,0109] | 0,374 | 1,000 | não | não |

**P2, `volume_anomaly v2`, coorte `replay:bac27c12` (341 linhas; 337 avaliáveis, 4 `no_entry`):**

| braço | expectancy líq. (R) | PF | Δ contra a base (337 pares, 29 blocos) | p Holm |
|---|---:|---:|---:|---:|
| base | −0,5957 | 0,280 | — | — |
| INV-B | −0,5641 | 0,340 | +0,0316 | 1,000 |
| INV-C | −0,5704 | 0,323 | +0,0253 | 1,000 |
| INV-E | −0,5944 | 0,308 | +0,0014 | 1,000 |
| EXIT-NOTGT | −0,4346 | 0,525 | +0,1654 | 1,000 |
| EXIT-CHAN | −0,4193 | 0,530 | +0,0153 (contra NOTGT) | 1,000 |
| TGT-3 / TGT-4.5 | — | — | **sem pares**: `volume_anomaly` persiste **um** alvo (`target2_missing` em 337) | — |

**P3 e P4 — a mesma máquina sobre as populações prospectivas** (Δ contra a base, R):

| contraste | P1 replay `momentum v2` (24 blocos) | P3 prospective `momentum v2` (1 bloco) | P4 prospective `momentum v1` (3 blocos) |
|---|---:|---:|---:|
| INV-B − base | −0,0062 | −0,0697 | −0,0382 |
| INV-C − base | +0,0065 | −0,0468 | −0,0313 |
| INV-E − base | +0,0198 | −0,0619 | −0,0091 |
| TGT-3 − base | +0,1036 | +0,0082 | −0,0184 |
| TGT-4.5 − base | +0,1136 | −0,1380 | −0,0125 |
| **EXIT-NOTGT − base** | **+0,1635** | **−0,2255** | **−0,1020** (IC [−0,116; −0,049]) |
| EXIT-CHAN − EXIT-NOTGT | −0,0133 | +0,0036 | +0,0107 |

- **Dias distintos com desfecho avaliável:** P1 24 · P2 29 · P3 1 · P4 3 (limiar: 30).
- **Desfechos avaliáveis:** P1 222 · P2 337 · P3 189 · P4 933 (limiar: 100).
- **Versão da métrica / proveniência:** `replay_exits.py` sobre `hunter_indicators.replay.policies`
  v1 de cada braço; tabelas `agent_signals` + `signal_outcomes` + `candles` + `funding_rates`.
- **PnL de carteira / Max Drawdown de carteira:** **não aplicável** — não há carteira no Shadow Lab,
  e um replay de política de saída não cria uma.
- **Result:** **inconclusivo** — nenhuma população chega a 30 dias distintos, e nenhum dos sete
  contrastes rejeita em nenhuma das quatro.
- **Conclusion:**
  1. **A invalidação não é a causa da perda.** Os três braços INV ficam entre −0,070 R e +0,032 R
     nas quatro populações; nenhum passa o efeito mínimo de 0,05 R, e o sinal **muda** entre
     populações. A [[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]] está certa ao descrever
     (a invalidação encerra 26–43 % das operações com ~0 ganhadoras) e **errada ao concluir que
     soltá-las salvaria dinheiro**: soltas, elas perdem igual. Isto **encerra o item 0 do brief
     T3.27** — a versão de código `momentum_v2` com `invalidation_mode` **não se justifica** por este
     resultado.
  2. **O maior contraste é o alvo, e ele não é confiável.** `EXIT-NOTGT − base` é +0,163 R em P1 e
     leva o PF de 0,645 para 0,991 — e é **−0,226 R** em P3 e **−0,102 R** em P4, com o IC de
     blocos de P4 inteiramente negativo. Populações diferentes, sinais opostos: exatamente a
     armadilha da [[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]. Não há decisão a
     tomar aqui sem uma janela reservada.
  3. **Nenhum braço salva a `volume_anomaly`.** O melhor (`EXIT-CHAN`) ainda entrega −0,419 R, porque
     o custo assumido dela vale 0,615 R por operação
     ([[KB-0076-por-que-perdemos-2026-09-08]]). Política de saída não conserta um custo de 0,6 R.
- **Next Action:** **não** derivar variante de invalidação. O que fica pré-registrado, em ordem:
  (a) medir a expectancy **bruta** por família de entrada — enquanto for ~0, nenhum braço de saída
  inverte sinal; (b) se o alvo voltar à pauta, ele tem de ser testado numa janela **reservada**
  (2026-09-08 em diante), nunca na janela que gerou a hipótese.

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| `momentum v4` (`atr_pct_min 0,003 → 0,0089`) | 2026-09-08 13:05Z | piso de custo ([[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]]) | [[EXP-0006-momentum-piso-de-custo]] |
| `momentum_v2` com `invalidation_mode` | — | **não derivada**: o item 0 do T3.27 mandava parar se os três contrastes INV fossem indistinguíveis de zero. São. | este EXP, conclusão 1 |

## Relacionadas

[[EXP-0004-politicas-de-saida]] · [[EXP-0006-momentum-piso-de-custo]] ·
[[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] ·
[[KB-0076-por-que-perdemos-2026-09-08]] ·
[[Experiments Index]] · [[Strategy Backlog]] · [[Registro de Tentativas]]

## Fontes

- `infra/scripts/replay_exits.py` (seletores `--only-version` / `--cohort` acrescentados pela T3.32,
  cobertos por `infra/scripts/tests/test_replay_exits_population.py`).
- `packages/indicators/hunter_indicators/replay/policies.py` — os oito braços e os sete contrastes,
  declarados antes de qualquer resultado.
- Recibos completos (Markdown + JSON canônico das quatro corridas):
  `.claude/state/exp-drafts/t332-replay/t332-{momentum-v2,va-v2,mom-v2-prosp,mom-v1-prosp}.{md,json}`.
- Rascunho de origem: `.claude/state/notes-T3.32.md`.
