# R53: Por que nenhum trade hoje? — Análise de Atividade Pump.fun

## Dados: últimas 72 horas (14-16 setembro, Brasília UTC−3)

### Tabela 24h: Médias

| Hora BRT | Moedas/h | Graduações | Grad c/vida | % com vida | Característica |
|----------|----------|-----------|------------|-----------|----------------|
| 00-08 | 841 | 37 | 14 | 1.9% | **Noite morta** (−75%) |
| 09-13 | 1394 | 47 | 19 | 1.5% | Ramp matinal |
| **14-20** | **1808** | **50** | **24** | **1.3%** | **PICO orgânico** (madrugada NY/EU) |
| 21-23 | 1363 | 40 | 19 | 1.5% | Transição |

### Comparação Diária

| Data | Moedas | Graduações | % com vida | Status |
|------|--------|-----------|-----------|--------|
| 14/09 | 33.408 | 1.110 | 1.7% | Baseline |
| 15/09 | 33.588 | 1.311 | 2.1% | Estável |
| 16/09 | 28.917 | 848 | 1.6% | **−13% vs média / −35% de grad com vida** |

### Executor Fase 1 (~16:00-22:00 BRT em 16/09)

```
Ordens ao vivo (meme_live_orders):
• 11:00-17:00: 50+ rejeitadas (REFUSED) — admissão bloqueada
• 21:00: 2 confirmadas (CONFIRMED) — única vitória
• 22:00: 12 rejeitadas — falhas retornaram

Sem operator/5: nenhuma proposta de rule set (desk em hold)
Paper bets abertos: 0
```

### Recomendação para o Operador

**Janela viável:** 14-20 BRT (1800 moedas/h, 24% com vida)  
**Secundária:** 10-13 BRT (1400 moedas/h, aceitável)  
**Nunca:** 00-07 BRT (atividade −75%, vida −85%)  

**Conclusão:** Executor **não deve rodar overnight**. Mercado em −13% (Fed hike). Reavaliar admissão no Lab antes de retomar operations.

---
**SQL:** `r53.sql` (date_trunc hourly, 72h window, meme_tokens.created_at / .completed_at, meme_live_orders.status)  
**Timestamp:** 2026-09-16 23:00 BRT
