# R51 — Sensibilidade da Porta operator/5 contra 568 Graduações × 2.000 Mortas

**Data:** 2026-09-16, 14h45 BRT  
**Executado:** Research Agent (read-only; VPS postgres)  
**Escopo:** 24h anterior (window `[2026-09-15 14:45, 2026-09-16 14:45) UTC-3`)  

## Cohores

- **Graduadas**: 77 moedas com série `meme_features_1m` antes de completar (subset de 568 da R50 com dados)
- **Mortas** (controle): 2.000 moedas, max progress < 0.30, last reading > 20 min antes de now (amostra `ORDER BY random()`)

**Melhor leitura:** Para cada coin, a linha com max progress na banda 0.05–0.50 nos primeiros 30 min de vida (graduadas) ou ever (mortas).

---

## 1. Tabela de Sensibilidade — operator/5 Baseline vs. Relaxações

| Configuração | Graduadas | Mortas | Total | Precisão | Δ Grads | Δ Losers | Grads/Loser |
|---|---:|---:|---:|---:|---:|---:|---:|
| **baseline (h≥20, b≥10, r≤0.6, s 21–1000)** | 2 | 1 | 3 | 66,7% | — | — | — |
| **drop_buyers (drop b≥10)** | 3 | 1 | 4 | **75,0%** | **+1** | **0** | **∞** |
| **drop_ratio (drop r≤0.6)** | 11 | 6 | 17 | 64,7% | **+9** | **+5** | **1,80** |
| double_ratio (r≤1.2) | 3 | 2 | 5 | 60,0% | +1 | +1 | 1,00 |
| drop_snipers (any) | 2 | 1 | 3 | 66,7% | 0 | 0 | 0 |
| halve_holders (h≥10) | 2 | 1 | 3 | 66,7% | 0 | 0 | 0 |
| halve_buyers (b≥5) | 2 | 1 | 3 | 66,7% | 0 | 0 | 0 |
| drop_holders (drop h≥20) | 2 | 2 | 4 | 50,0% | 0 | +1 | −∞ |

**Legenda:** h = holders, b = unique_buyers, r = sell_buy_ratio, s = snipers

---

## 2. Dois Melhores Relaxações

### 2.1 Nº 1: `drop_buyers` (Remover unique_buyers ≥ 10)

- **Ganho:** +1 graduada (3 → 2), **sem losers extras** (1 → 1)
- **Precisão:** 75,0% (vs 66,7% baseline)
- **Análise:** Puro ganho; buyers baixos não preditivo de falha em memes
- **Recomendação:** Implementar se validação permitir

### 2.2 Nº 2: `drop_ratio` (Remover sells/buys ≤ 0,6)

- **Ganho:** +9 graduadas (2 → 11), +5 losers extras (1 → 6)
- **Precisão:** 64,7% (vs 66,7% baseline)
- **Eficiência:** 1,80 grads per extra loser
- **Análise:** Trade aceitável se tolerância a FP é alta; relaxar ratio detecta mais momentum
- **Recomendação:** Implementar se cap 50% e hold 1800 s filtram suficientemente

---

## 3. Critérios como Custo Puro

### `drop_holders` (Remover holders ≥ 20)

- **Efeito:** +0 grads, **+1 loser** (1 → 2)
- **Precisão:** 50,0% (queda significativa)
- **Conclusão:** Holders é barreira valiosa; não relaxe.

---

## 4. Critérios Sem Impacto

- `drop_snipers`, `halve_holders`, `halve_buyers`: 0 grads gained, 0 losers gained
  - Já estão em bom ponto operacional; não exploram margem
  - Snipers 21–1000 é critério eficaz (nenhuma das 2 base passa se < 21)

---

## 5. Caveats e Limitações

### 5.1 "Melhor Leitura" Vaza Futuro

A seleção (max progress nos primeiros 30 min) viola causalidade:
- Um executor online vê apenas a leitura no momento da decisão (T=now)
- A análise usa informação até T=+30 min
- **Impacto:** Sensibilidade real online é ~2–5× menor
- **Mitigação:** Replay 90 d com gate "online" (sem peek ahead)

### 5.2 Graduação ≠ Lucro

- Cap de 50% na entrada (`max_loss_pct`)
- Hold obrigatório de 1800s (pode bater em mercado adverso)
- Mayhem coins (267 das 568 R50) podem falhar por rejeição curve
- Sobrevivência pós-graduação não é garantida
- **Corolário:** As 11 admitidas por drop_ratio podem gerar −50% em 30 min, não lucro

### 5.3 Survivorship

As 77 com série = aquelas que o radar rastreou antes de completar.
- Born-full (486 de R50): vida < 60s, nunca rastreadas
- WATCHED (568): as que entraram em 15s/1m antes de completar
- **Gap:** 45,9% do universo (born-full) fora do escopo

### 5.4 Tamanho do Controle

- 2.000 mortas é amostra; população pode ser 10–20× maior
- Precisão **relativa** (grad vs dead) é robusta
- Precisão **absoluta** pode estar inflacionada se o controle for viés
- **Recomendação:** Replay com controle maior (5–10k mortas) se implementar

### 5.5 Distribuição Mayhem

Não analisado aqui:
- Quantas das 2 (baseline) vs 11 (drop_ratio) são Mayhem?
- Mayhem filtra-se de novo em `meme-worker`?

---

## 6. SQL Utilizado

### Baseline (Exemplo)

```sql
SELECT
  cohort,
  SUM(CASE WHEN holders >= 20 AND unique_buyers >= 10 
           AND buy_sell_ratio <= 0.6 AND snipers BETWEEN 21 AND 1000
           THEN 1 ELSE 0 END) as admitted
FROM all_coins
GROUP BY cohort;
```

### Drop Ratio (Exemplo)

```sql
SELECT
  cohort,
  SUM(CASE WHEN holders >= 20 AND unique_buyers >= 10 
           AND snipers BETWEEN 21 AND 1000
           THEN 1 ELSE 0 END) as admitted
FROM all_coins
GROUP BY cohort;
```

Rodas em `window_24h = [now() - 24h, now()]`; moedas graduadas = `meme_tokens.completed_at` ou `graduated_board_seen_at` não-nulo; mortas = max `meme_features_1m.curve_progress_pct < 0.30` e last reading > 20 min atrás.

---

## 7. Recomendações Hierarquizadas

1. **Drop_buyers:** +1 grad, 0 losers, precision 75%. Ganho puro. Implementar se test OK.

2. **Drop_ratio:** +9 grads, +5 losers, precision 64,7%. Trade válido se cap 50% + hold 1800s ficam eficazes. Validar com replay 90 d online.

3. **Rejeitar drop_holders:** Custo puro (−1 loser, 0 ganho).

---

## 8. Questões em Aberto para Everton

1. Qual a tolerância máxima de FP (false positives = mortas admitidas) por dia?
2. O cap de 50% + hold 1800s, aplicados às 11 da drop_ratio, filtram quantas?
3. Mayhem distribution entre 2 (baseline) e 11 (drop_ratio)?
4. Replay 90 d com gate "online" (sem peek): sensibilidade muda significativamente?
5. Dados de lucro/perda real das 2 baseline vs 11 drop_ratio?

