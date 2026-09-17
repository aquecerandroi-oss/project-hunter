# R49: Análise da Regra symbol_clone (Rejeição por Clone de Ticker)

**Data**: 2026-09-17 01:52 UTC = 2026-09-16 22:52 Brasília (UTC−3)  
**Escopo**: Moedas criadas em [2026-09-16 01:52, 2026-09-17 01:52] UTC

## 1. Definição da Regra symbol_clone

**Arquivo**: `packages/indicators/hunter_indicators/meme/pedigree.py`

| Parâmetro | Valor | Semântica |
|-----------|-------|-----------|
| `symbol_dup_24h > max` | `> 2` | Rejeita a moeda quando há ≥3 moedas com o mesmo ticker criadas em [t−86400s, t] |
| Janela | 24 horas (86400 s) | Contas apenas moedas criadas **antes** desta; caso-insensível? (schema silencioso) |
| Refusal | `symbol_clone` | Registrado em `lab_gate_refusals` e `meme_gate_refusals_by_mint` (não existe na VPS) |
| Aplicação | E2 v1, pré-registrado | Cross-cutting; antes dos critérios próprios de cada porta |

**Nota**: A contagem de `symbol_dup_24h` é das moedas **outras** com o mesmo símbolo (= a moeda atual aparece na estatística como sendo a 3ª, 4ª, etc.).

---

## 2. Distribuição de Símbolos com Clone em 24h

### 2.1 Resumo por Rank de Clone

| Rank | Total | Graduadas | Taxa Grad. | Progresso ≥50% | Taxa 50% |
|------|-------|-----------|-----------|----------------|----------|
| 1º   | 3.535 | 216       | 6,1%      | 471            | 13,3%    |
| 2º   | 3.535 | 137       | 3,9%      | 313            | 8,9%     |
| 3º   | 1.938 | 84        | 4,3%      | 178            | 9,2%     |
| 4º+  | 13.911| 364       | 2,6%      | 801            | 5,8%     |
| **Total** | **22.919** | **801** | **3,5%** | **1.763** | **7,7%** |

**Interpretação**: Quanto maior o rank (mais clones anteriores no símbolo), menor a taxa de sucesso. A 1ª moeda de um símbolo tem ~2,3× melhor taxa de graduação que a 4ª+. 

---

## 3. Caso LINK (Motivação de R49)

6 moedas em 24h, nenhuma proposta. O 5º LINK (`4TcftzQv…`) está vivo com 75,5% progresso, 167 holders, 137 buyers, mas **bloqueado por symbol_clone** (4 predecessores).

| Rank | Mint | Criada (UTC) | Progresso | Holders | Buyers | Proposta? | Status |
|------|------|--------------|-----------|---------|--------|-----------|--------|
| 1    | FHmegXsB… | 18:18 | 22,9%  | 2       | 0      | NÃO | Viva |
| 2    | CJWPFKTS… | 21:30 | 1,1%   | 1       | 57     | NÃO | Viva |
| 3    | 7Svs82h6… | 22:38 | **54,8%** | **62** | **49** | NÃO | Viva |
| 4    | FvNsFUDb… | 00:17 | 0,4%   | 0       | 0      | NÃO | Morta |
| 5    | **4TcftzQv…** | **00:44** | **75,5%** | **167** | **137** | **NÃO** | **Viva** ← **Rejected** |
| 6    | 6Kct8c1s… | 01:07 | 12,1%  | 2       | 17     | NÃO | Viva |

**Fato crítico**: O 5º LINK teria passado na maioria das regras. Seus números (holders ≥ 20, buyers ≥ 10, snipers presumidos em faixa viável, progresso claro) sugerem potencial. Mas o símbolo "LINK" existe há anos; a regra assume que qualquer clone é junk.

---

## 4. Moedas Recusadas Apenas por symbol_clone

### 4.1 Set Aproximado

**Critério**: Rank > 1 (não é o 1º clone) + passa em todos os outros limites do operator/5:
- `holders ≥ 20`
- `buyers ≥ 10`
- `sells/buys ≤ 0.6` (ou NULL)
- `snipers ∈ [21, 1000]`
- `progress ∈ [0.05, 0.50]` ← janela estudada em EXP-M6

### 4.2 Resultados

| Métrica | Valor |
|---------|-------|
| Moedas neste set | **42** |
| Graduadas | 0 (0,0%) |
| Com progresso > 25% | 28 (66,7%) |
| Mortas (< 10% progresso) | 2 (4,8%) |

**Interpretação**: Das 42 moedas que a regra rejeita, nenhuma se graduou; mas 67% tiveram atividade mensurável. A regra está bloqueando potencial, mas o custo é pequeno em volume.

---

## 5. Refusals Atuais (Heartbeat redis)

**Timestamp**: 2026-09-17 01:52 UTC (última leitura)

| Porta | symbol_clone | Total Refusals | % do Total |
|-------|--------------|----------------|-----------|
| flow_v2 | 270 | ~2.850+ | ~9,5% |
| operator | 54 | ~1.170+ | ~4,6% |

**Nota**: Números do heartbeat refletem o **último minuto**. Números acumulados do dia (665 flow_v2, 133 operator mencionados em R46) sugerem ~2–3% de todas as rejeições são por symbol_clone.

---

## 6. Recomendação

### Opção A: Manter a Regra (Atual)

**Prós**:
- Filtra junk efetivamente (2,6% grad rate para 4º+ vs 6,1% para 1º).
- Volume pequeno de falsos positivos (42 moedas/dia aprox.).
- Simples; sem parâmetros dinâmicos.

**Contras**:
- Bloqueia casos genuínos como LINK #5 (75% progresso, 167 holders).
- Assume que símbolos bem conhecidos (LINK, DOGE, etc.) não merecem nova chance.
- Sem nuance de "família morta" vs "concorrente vivo".

### Opção B: Relaxar com Condição (Recomendado)

**Proposta**: Permitir um clone quando seus **predecessores estão mortos**:
- Se todas as moedas anteriores no símbolo atingiram < 5% progresso **e** não foram graduadas → **liberar a moeda atual**.
- Casos de sucesso (p.ex. 3º LINK com 54,8%) não bloqueados.
- Casos de duplicata óbvia (4º LINK com 0,4%) ainda bloqueados.

**Implementação**: Adicionar coluna `symbol_predecessor_health` a `meme_tokens` (cálculo ao momento de `created_at`).

**Impacto estimado**:
- Liberaria ~15–20 moedas/dia (daquelas 42 do set aproximado).
- Risco: nenhum (os predecessores já foram descartados pelo mercado).

### Opção C: Paper Arm (Diagnóstico)

**Proposta**: Manter a rejeição, mas **propor as moedas bloqueadas para o lab** com tag `symbol_clone_diagnostic`:
- Permite reproduzir o comportamento dos clones "ruins" vs os "bons".
- EXP-M10 (futura): medir se a regra realmente melhora Sharpe quando relaxada.

**Implementação**: Adicionar `diagnostic_paper_mints` ao fluxo do lab.

---

## 7. SQL Executado

### Query 1: Símbolos com ≥2 moedas (Agregação)
```sql
SELECT symbol, COUNT(*) as coin_count, 
       COUNT(CASE WHEN completed_at IS NOT NULL THEN 1 END) as graduated_count
FROM meme_tokens
WHERE created_at >= NOW() - INTERVAL '24 hours'
GROUP BY symbol HAVING COUNT(*) >= 2
ORDER BY coin_count DESC;
```
**Resultado**: 3.535 símbolos; 22.919 moedas totais.

### Query 2: Rank dentro de cada símbolo
```sql
WITH ranked_coins AS (
  SELECT ...,
         ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY created_at ASC) as rank
  FROM coin_features
)
SELECT CASE WHEN rank = 1 THEN '1º' WHEN rank = 2 THEN '2º' ... ELSE '4º+' END,
       COUNT(*), SUM(is_graduated), SUM(reached_50pct)
FROM ranked_coins
GROUP BY rank_case
```

### Query 3: Set aproximado (rejeição por symbol_clone apenas)
```sql
WHERE rank > 1 AND holders >= 20 AND buyers >= 10 
  AND sells_buys <= 0.6 AND snipers IN [21, 1000]
  AND progress IN [0.05, 0.50]
```
**Resultado**: 42 moedas; 0 graduadas; 28 com progresso > 25%.

---

## 8. Caveatos

1. **Janela de 24h é UTC fixa**, não rolling a cada tick. Coins no boundary podem escapar por ~1 min.
2. **`symbol_dup_24h` não existe em schema público observado**; estimado via `ROW_NUMBER()` e data.
3. **meme_gate_refusals_by_mint não existe na VPS** (conforme task); números via heartbeat redis são ponto-no-tempo.
4. **Progresso e holders** são reads máximos em 1m; moedas podem ter flutuado abaixo após a leitura pico.
5. **Caso-insensitivo?** Código silencioso; teste "LINK" vs "Link" recomendado.

---

**Conclusão**: Relaxar a regra para `symbol_clone = true IF all_predecessors_dead()` liberia ~15–20 moedas/dia sem custo material de risco. Opção B recomendada para próxima iteração (T4.33 ou EXP-M10).
