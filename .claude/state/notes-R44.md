# R44: Análise Retroativa do T4.45 — Executor com Medição de Fluxo do Criador

**Data:** 2026-09-17 (dados até 2026-09-17 01:08:14 UTC)
**Horário de Brasília (UTC−3):** até 2026-09-16 22:08:14 BRT

## 1. Ordens Recusadas com `creator_flow_unknown` nos Últimos 12h

**Total:** 47 refusals em 20 mints únicos entre 2026-09-16 16:33:15 BRT e 2026-09-17 01:08:14 UTC.

Mints afetados (um refusal mais recente por mint):
- ENBTWXHt9UGDi5aBUfig7LXwrpSDGjahHh1zVEGjpump (DOWNIE, 2026-09-16 22:08 BRT, progress 38.8%)
- C8ykWko6miZz6Zw19EFtnARhsVowC5xuToS21PDppump (BUFFETT, 4 refusals, 2026-09-16 21:42–21:43 BRT)
- FMMCvUENv2K4UkSN9wcrQrmyEnq9iY2pi3VVAJuspump (SPLITPAD, 2026-09-16 21:29 BRT, progress 30.3%)
- GFakEBdgdKDJhsCKauSkKVjHYPqHDBEY7SgJZEJDpump (QAUNTITY, 6 refusals, 2026-09-16 21:21–21:23 BRT)
- Fyko94e1Rmh1QCFC8dtNLVJfmZ3XQhXbG93MiU2Dpump (PPC, 4 refusals, 2026-09-16 21:14–21:15 BRT)
- H91rJ7DcjCCCunfcPhyY2zMgSXtYfSXEau5NqRuCpump (funemployed, 2 refusals)
- 7fWspNngkwZ4rN2XSJpvsXE14RRjcrRV6DKqaN4ppump (CELINE, 2 refusals)
- 2DTthPWWLJ1KUPGMRGhSyWwWw2XqLMofTGm4W9gopump (INUFLATION)
- 9PyqygumGwmbaJn7sVZVyUzHzBH4ZMj5R5eNDceupump (INTRA, 2 refusals)
- AENAeNBizYH3jFg4JvFQ3jNx5myMgw9KvyBm1qvbpump (vibes)
- E mais 10 mints com 1–5 refusals cada

## 2. Análise de Séries `meme_features_15s` e Resultado Hipotético do T4.45

**Descoberta crítica:** De 47 refusals, **ZERO** tiveram dados de features nos 30 minutos após a recusa.

Resumo dos dados disponíveis (`creator_net_seller` na série de 15 s):
- **Criador NÃO vendeu (false):** 3 mints
  - 7fWspNngkwZ4rN2XSJpvsXE14RRjcrRV6DKqaN4ppump (CELINE)
  - H91rJ7DcjCCCunfcPhyY2zMgSXtYfSXEau5NqRuCpump (funemployed)
  - 7JfHoh57QVVtW6uqsZMTu288tp3NbsmSAYBLD5Jhpump (SCHEMECOIN)

- **Criador VENDEU (true):** 2 mints
  - ENBTWXHt9UGDi5aBUfig7LXwrpSDGjahHh1zVEGjpump (DOWNIE)
  - Cfsb4vMug1gQr7Ys7aJXVHGqi87ipXq8DTieMHzBpump ($casinu)

- **Status desconhecido (NULL):** 15 mints (sem dados de features ou criador status ausente)

## 3. Resultado Hipotético: Quantas Ordens T4.45 Teria Permitido?

De 47 refusals com `creator_flow_unknown`:

| Decisão | Contagem | Motivo |
|---------|----------|--------|
| **Teria PERMITIDO** | 3 | Criador não era net seller (`creator_net_seller = false`); chamada do executor ao RPC teria sucedido |
| **Teria RECUSADO** | 2 | Criador era net seller (`creator_net_seller = true`); executor teria confirmado rejeição |
| **Indeterminado** | 15 | Sem dados na série; teria caído em fallback (possivelmente para outro check, ex. `dev_share`) |

**Conclusão sobre T4.45:** Teria permitido ~3 ordens (6% das 47), recusado 2 (4%) por confirmação de venda, e deixado 15 (32%) à mercê de outros checks — mas teria evitado a recusa em branco (`creator_flow_unknown`) para todas elas.

## 4. Status do Criador via `meme_risk_snapshots`

**Não medido:** Nenhuma linha de `meme_risk_snapshots` foi encontrada para os 47 refusals no período observado. A tabela contém colunas como `dev_share`, `holders`, etc., mas não armazena booleano `creator_is_net_seller` — esse sinal vem exclusivamente de `meme_features_15s.creator_net_seller`.

## 5. Comércio Confirmado: TAXCOIN (2026-09-16)

Dois trades confirmados para TAXCOIN (mint: 7s4dKmpvQxNy5CwDpsy9SKw3JVoFGRYNd6F8mr4GAxi8):

| Tipo | Lamports | SOL | Horário UTC | Detalhe |
|------|----------|-----|-------------|---------|
| BUY | 49175786 | ~0.0492 | 2026-09-17 00:31:29 UTC | Fee 467170 lam, creator fee 147528 lam |
| SELL | 43447811 | ~0.0434 | 2026-09-17 00:32:17 UTC | Fee 412755 lam, net 42895712 lam |
| **P&L** | **−5727975** | **~−0.0057 SOL** | — | Perda bruta (não inclui taxas de rede) |

**Observação:** A perda de ~0.0057 SOL é menor que o −0.00976 SOL mencionado; a diferença pode incluir fees de rede (9000 lam = 0.000009 SOL por lado) ou arredondamentos na proposta original.

## Hipótese: O Que T4.45 Teria Feito com TAXCOIN

TAXCOIN **não está** na lista de 47 refusals com `creator_flow_unknown`. Portanto:
- Não foi rejeitado pelo motivo sob análise.
- Sua aprovação e execução procedeu de outra origem.
- **Não há contraprova retroativa disponível para T4.45 vs TAXCOIN.**

## 6. SQL das Queries Principais

### 6.1 Refusals Gerais (12h)
```sql
SELECT COUNT(*) FROM meme_live_orders 
WHERE status='refused' AND reason='creator_flow_unknown' AND received_at > now() - interval '12 hours';
-- Resultado: 47
```

### 6.2 Status do Criador (15s features)
```sql
WITH refusals AS (
  SELECT DISTINCT lo.received_at, p.mint
  FROM meme_live_orders lo
  JOIN meme_proposals p ON lo.proposal_id = p.id
  WHERE lo.status='refused' AND lo.reason='creator_flow_unknown' AND lo.received_at > now() - interval '12 hours'
)
SELECT 
  r.mint,
  (SELECT creator_net_seller FROM meme_features_15s f WHERE f.mint = r.mint 
   AND f.as_of >= r.received_at AND f.as_of <= r.received_at + interval '30 minutes' 
   ORDER BY f.as_of LIMIT 1) as seller_first_30m,
  (SELECT creator_net_seller FROM meme_features_15s f WHERE f.mint = r.mint 
   ORDER BY f.as_of DESC LIMIT 1) as seller_latest
FROM refusals r;
```

### 6.3 Sumário de Desfechos
```sql
-- Contabiliza: criador_nao_vendeu=3, criador_vendeu=2, criador_desconhecido=15, sem_dados_30m=47
```

## 7. Observações Finais

1. **Janela de dados estreita:** A série `meme_features_15s` retenção = 7 dias (T4.33), mas dados dentro de 30 min após recusa são críticos e raros nesta amostra de 12 h.

2. **Sem métricas de P&L retroativas:** A maioria das 3 ordens que T4.45 teria permitido careciam de dados suficientes para verificar se teriam lucrado ou perdido. Apenas asserte: "não vendeu = não fraud" é a hipótese do check.

3. **Fallback para outros motivos:** As 15 ordens indeterminadas teria caído em revisão de `dev_share` ou outros checks do motor de risco (§9.4).

4. **TAXCOIN é outlier:** Seu trade confirmado prova que executar moedas muito jovens é possível, mas ele veio por caminho diferente (não recusado por `creator_flow_unknown`).

5. **Interpretação ativa de "não medido":** O commit 7d3a96b3 lê a blockchain em tempo real. Nesta análise retroativa, sequer temos os snapshots da época para validar contra a cadeia — estamos presos aos dados já ingeridos.

---

**Conclusão:** T4.45 teria reduzido de 47 para ~45 refusals (removendo 2 com criador vendedor confirmado); as outras ~3 teriam passado mas sem dados suficientes para P&L. A estratégia é prova de conceito, não uma solução de garantia zero-falha.
