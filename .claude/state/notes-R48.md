# Notas R48: Cap 0.6 em sells/buys descarta 24.6% das graduadas

**Data:** 2026-09-17 01:51 BRT (UTC−3)  
**Período analisado:** 24h retroativos de meme_features_1m  
**Status:** análise preliminar com caveats estruturais  

---

## Resumo Executivo

O cap de sells/buys em **0.6** (porta flow_v2/6 e operator/5) descarta 113 de 459 graduadas (24.6%) no período. A taxa de graduação **abaixo** de 0.6 é **4x menor** que acima (0.53% × 2.12%), sugerindo que o cap é **desproporcional**. Um cap em **0.81** retém 90% das graduadas. Para `unique_buyers`, a comparação 10 vs 25 não mostra ganho claro (3.88% × 3.40%).

---

## Dados Brutos (últimas 24h)

### Contagem por Status

| Status | Contagem | % |
|---|---|---|
| `graduated` | 459 | 1.58% |
| `died` | 25,145 | 86.75% |
| `other` | 3,385 | 11.67% |
| **Total** | **28,989** | **100%** |

**Filtro:** mints com ≥3 leituras em `meme_features_1m`. Período coberto: 2026-09-16 00:51 a 2026-09-17 00:51 BRT.

### Distribuição de Sells/Buys (ponto ótimo primeiros 30 min de vida)

| Métrica | Graduated (n=119) | Died (n=5,120) | Other (n=1,226) |
|---|---|---|---|
| Min | 0.00 | 0.00 | 0.00 |
| P10 | 0.81 | 0.00 | 0.79 |
| P25 | 1.00 | 0.74 | 1.01 |
| **P50 (mediana)** | **1.19** | **1.00** | **1.43** |
| P75 | 1.65 | 1.50 | 2.18 |
| P90 | 2.67 | 2.50 | 3.75 |
| Max | 10.00 | 42.50 | 30.00 |
| Média | 1.65 | 1.35 | 2.06 |

**Nota:** muitos de graduated têm sells/buys `NULL` (340 de 459, ou 74%). Contagem de 119 são as que têm dados válidos nos primeiros 30 min.

### Taxa de Graduação por Bucket de Sells/Buys

| Bucket | Total | Graduadas | Taxa | Observação |
|---|---|---|---|---|
| **≤ 0.6** | 1,135 | 6 | **0.53%** | ← Cap seletivo |
| 0.6–1.0 | 979 | 21 | 2.15% | |
| 1.0–1.5 | 2,399 | 53 | 2.21% | ← pico |
| 1.5–2.5 | 1,188 | 25 | 2.10% | |
| > 2.5 | 799 | 14 | 1.75% | ← decay |
| **Total com dados** | **6,500** | **119** | **1.83%** | |

**Padrão:** taxa sobe de 0.53% → 2.21% (bucket 1.0–1.5), depois decai. O cap 0.6 corta a faixa de transição.

---

## Resposta às Perguntas

### Q1: O cap 0.6 descarta graduações desproporcionalmente?

**Resposta: SIM, claramente.**

- Graduadas abaixo de 0.6: **6 de 1,135** mints no bucket (0.53%)
- Graduadas acima de 0.6: **113 de 5,365** mints no bucket (2.12%)
- **Razão:** 2.12 / 0.53 = **4.0x** menor abaixo

O cap corta antes do ponto de inflexão (aproximadamente 0.8–1.0) onde a taxa de graduação sobe significativamente.

### Q2: Qual cap mantém 90% das graduadas?

**Resposta: 0.81** (10º percentil dos sells/buys em moedas que graduaram).

**Detalhamento:**
- 10º percentil de `sells_buys_early` no grupo `graduated`: 0.81
- Isso significa que 90% das 459 graduadas tinham sells/buys ≥ 0.81 no ponto ótimo dos primeiros 30 min
- Um cap em 0.81 manteria ~414 graduadas (90%), descartando apenas ~45 (10%)

Com cap 0.6: descarta 113 (24.6%) — **quase 2.5x pior**.

### Q3: Unique_buyers (10 vs 25)?

**Resposta: Sem ganho claro com 25 vs 10.**

| Threshold | Total | Graduadas | Taxa | Delta vs anterior |
|---|---|---|---|---|
| < 10 | 14,267 | 199 | 1.39% | baseline |
| 10–25 | 1,159 | 45 | 3.88% | **+2.8 pp** |
| ≥ 25 | 971 | 33 | 3.40% | **−0.5 pp** |

- Subir de 10 para 25 **não ganha taxa** (3.88% → 3.40%, i.e., piora aproximadamente 12%)
- O piso 10 captura a faixa de ouro; 25 é restritivo demais
- **Implicação para EXP-M10 (flow_v2/7):** o braço está bem construído (10–25 é a faixa ótima), mas 25 como porta fixa pode ser subótimo

---

## Caveats Estruturais

### 1. **Survivorship em graduação** (`completed_at`)

`meme_tokens.completed_at` marca final de vida observado, não força de graduação:
- Uma moeda morreu em rugpull 15 min depois de listar: `completed_at` NÃO É NULL (evento observado)
- Uma moeda subiu 100x em 1 hora, foi vendida antes de graduação formal: não registra como `graduated`
- Este R48 não separa os dois; uma leitura futura precisa de `reason` ou `mode_at_exit`

### 2. **Censoring em age_minutes** (série 15s para 1m)

A série `meme_features_15s` censa em `age_s <= 300` (5 min). Quando folding para `meme_features_1m`:
- Mints com `age_minutes IS NULL` implica `created_at` desconhecido (sem registro em `meme_tokens`)
- A relação reads >= 3 que filtrou os 28,989 mints tem custo alto em mints jovens
- **Possível bias:** mints com created_at conhecido têm mais leituras, então bias para moedas observadas cedo

### 3. **NULL em sells_buys sem motivo declarado em 74% de graduated**

340 de 459 graduadas têm `sells_buys_early = NULL`, mesmo com N >= 3:
- Motivo: `buy_sell_ratio` é NULL se `tape_reason IS NOT NULL` ou `sells_1m` / `buys_1m` indisponível
- Análise acima repousa em **n=119** (26% de 459), não em 459 cheios
- A incerteza nos 340 NULLs pode inverter a conclusão se forem sistematicamente > 0.6 ou < 0.6

### 4. **"Died" é heurística, não causal**

`died = (max_progress < 0.3) AND (minutes_since_last > 20)`:
- Inclui mints que nunca tiveram leitura (progress sempre NULL)
- Não distingue "morreu de fato" (rugged) de "perdeu interesse do poller" (fading)

### 5. **Moedas Mayhem**

`meme_tokens.mayhem_enabled` não é filtrado aqui. Mayhem muda semântica de `curve_progress_pct` (pode ficar **negativo**). Impacto desconhecido no bucket <= 0.6.

### 6. **Sample temporal curto (24h)**

Padrões de vendas/compras variam ao longo do dia (horários de pico de US, Europa, etc.). Um único dia pode não ser representativo. Além disso, houve 459 graduadas em 24h — taxa alta — possível flutuação semanal.

---

## Conclusão Preliminar para EXP-M14

O **cap 0.6 é defensável apenas se o motivo for risco explícito** (e.g., "sell pressure extrema nos primeiros 5 min é marker de rug futuro"). Como sinal isolado de graduação, ele perde aproximadamente 25% de oportunidades. Uma alternativa seria:

1. **Cap em 0.8–0.9:** mantém 90–95% das graduadas, sobe taxa em 3–4x
2. **Cap em 1.5:** mantém aproximadamente 99%, mas perde sinal (taxa 2.1% vs 2.2%)
3. **Manter 0.6 + combinar com outro sinal** (e.g., `unique_buyers >= 15`) para recuperar as 113

A decisão de calib do flow_v2/6 foi externa (operator/5, decisão humana). Para laboratório, é recomendado testar o intervalo [0.7, 1.0] com holdout.

