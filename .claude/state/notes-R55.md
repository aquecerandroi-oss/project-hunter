# R55 — Latência de Decisão do Bot (milissegundos para decisão, segundos para liquidação)

**Data:** 2026-09-17  
**Período medido:** últimas 24h (2026-09-16 14:46 → 2026-09-17 14:46 BRT)  
**Ordens reais:** 132 total (10 confirmadas, 120 recusadas, 2 falhadas)  
**5 Compras Stage 1:** TAXCOIN, Catbyte, RAMEN, DOPEY, PlanB (todas confirmadas)

---

## 1. Os 5 Mints Stage 1 — Latência Real

| Moeda | Total (s) | Prop->Rcv (s) | Rcv->Adm | Adm->Sim | Sim->Sgn | Sgn->Sub | Sub->Set |
|-------|-----------|-------------|--------|---------|---------|---------|---------|
| TAXCOIN | 6.263 | 4.788 | 0.000 | 0.174 | 0.174 | 0.000 | 1.128 |
| Catbyte | 9.993 | 8.106 | 0.000 | 0.586 | 0.000 | 0.000 | 1.302 |
| RAMEN | 5.949 | 4.089 | 0.000 | 0.568 | 0.000 | 0.000 | 1.292 |
| DOPEY | 8.057 | 5.223 | 0.000 | 0.399 | 0.000 | 0.000 | 2.435 |
| PlanB | 5.781 | 4.078 | 0.000 | 0.394 | 0.000 | 0.000 | 1.309 |

**Mediana (5 compras):** 6.3 s total (porta para liquidação)  
**Gargalo:** Proposal->Received = 4,8 s (76% da latência)

---

## 2. Estatísticas — Todas as Ordens Confirmadas (24h)

**Contagem:** 10 compras confirmadas (126 tentativas, 120 recusadas)

| Stage | p50 (s) | p95 (s) | Causa |
|-------|---------|---------|-------|
| **Proposal->Received** | 4.788 | 7.530 | Worker poll (entrante a cada ~5–10 s) |
| Received->Admitted | 0.000 | 0.000 | Admissão memória (inline) |
| Admitted->Simulated | 0.399 | 0.583 | Simulate RPC (1–2 chamadas) |
| Simulated->Signed | — | — | Assinatura local (< 100 ms) |
| Signed->Submitted | — | — | Send RPC (1 chamada) |
| Submitted->Settled | 0.000 | 0.000 | Webhook chain event |
| **TOTAL (proposta → liquidação)** | **1.860** | **2.645** | (sem Prop->Rcv) |

**Latência de ponta a ponta (chain → liquidação):** 6.6 s (p50) = 4.8 s (entrada) + 0.4 s (RPC) + 1.4 s (rede).

---

## 3. Por Que 76% da Latência é "Proposal->Received"

### 3.1 Fluxo de Camadas

1. **Radar (Worker, 15 s cada)**  
   - `fast_lane.py` lê curvas de mints < 300 s cada 15 s  
   - Escreve `meme_features_15s` (~4 ms de lag até BD)  
   - Proposta é lida/criada no loop `lab.py` (60 s, T4.2g)  
   - `meme_proposals.proposed_at` = instante dessa leitura  

2. **Executor (1 s loop `entries_once`, T4.28a)**  
   - Lê `meme_proposals WHERE status = 'proposed' AND proposed_at >= now - 600s`  
   - Índice: `ix_meme_proposals_status_proposed_at`  
   - Lag observado: **4.8 s p50** = pior dos casos do loop de radar (0–15 s) + atraso de escrita

3. **Admissão + RPC**  
   - Admission motor de 25 checks (memória, 0 ms)  
   - 3–5 leituras RPC (curve @ finalized, curve @ finalized para admissão, blockhash)  
   - p50 = 0.4 s, p95 = 0.6 s

4. **Submissão + Chain**  
   - Assinatura: < 100 ms local  
   - Envio: 1 chamada RPC (< 100 ms)  
   - Confirmação pelo `TradeEvent` no webhook: **~1.3 s** (slot ≈ 400 ms × 3–4 slots até `confirmed`)

### 3.2 Interrupções de Radar (Status Quo)

- `risk_cycle_s = 60` (padrão)  
- Radar só relê um mint se proposta envelhecer > 60 s  
- Hoje: 4.8 s observado = tick de radar até executor pickup

---

## 4. Refusas — Onde o Bot Está Preso

| Motivo | Contagem | % | Causador |
|--------|----------|---|----------|
| creator_flow_unknown | 57 | 47% | T4.28g: falta snapshot de risco |
| creator_net_seller | 23 | 19% | Verificação: criador está vendendo |
| progress_above_window | 21 | 17% | Progresso > 50% |
| progress_below_window | 15 | 12% | Progresso < 2% |
| bundled_share_* | 4 | 3% | Distribuição desconhecida |

**Insight:** 48% das recusas são por falta de "bundled_share" — que chega 103 s depois da ordem (R5).

---

## 5. Piso Físico

- Slot (Solana): ~400 ms  
- Latência processed -> confirmed: ~1–2 s  
- Latência confirmed -> finalized: ~12 s  
- Trade feed (webhook): ~100 ms lag vs 15 s polling  

**Stages que podem ser ~0:** Received->Admitted (já é 0), Simulated->Signed (< 100 ms)  
**Stages RPC:** Admitted->Simulated = 0.4 s (paralelizável para ~0.2 s)  
**Stages Chain:** Submitted->Settled = 1.3 s (piso = confirmed, bom)

---

## 6. Alvo: Redesenho Event-Driven

| Cenário | Proposta→Liquidação | Breakdown |
|---------|-------------------|-----------|
| Hoje (status quo) | **6.6 s** | 4.8 s (poll) + 0.4 s (RPC) + 1.4 s (chain) |
| Event-driven (Redis) | **~1.8 s** | 0.1 s (sub) + 0.3 s (RPC) + 1.4 s (chain) |
| Hipotético ideal | **~1.0 s** | 0.0 s (in-memory) + 0.0 s (cache) + 1.0 s (confirmed) |

**Decisão (pré-assinatura):** < 500 ms (hoje 4.8 s, 10× mais rápido com events).  
**Liquidação (chain):** 1–2 s (limitada por Solana).

---

## 7. Causas por Estágio (Código)

**Proposta->Recebida (4.8 s):**
- `fast_lane.py:fast_once()` — tick 15 s, lê mints < 300 s
- `lab.py:lab_once()` — tick 60 s, cria `meme_proposals` com `proposed_at`
- `entries.py:entries_once()` — tick 1 s, poll via índice `ix_meme_proposals_status_proposed_at`

**Recebida->Admitida (0 s):**
- `admission_context.py` — 25 checks em memória, escreve `meme_live_orders` inline

**Admitida->Simulada (0.4 s p50):**
- 3–5 RPCs em série: curve (finalized), risk snapshot, blockhash, simulate
- T4.28g risk snapshot pending: aguarda leitor a cada 60 s se bundled_share=NULL

**Enviada->Liquidada (1.3 s):**
- Piso = `confirmed` (~1 s), webhook lag (~300 ms)

---

## 8. Conclusão: Resposta ao Everton

A decisão **estruturada** está em ~4.8 s (poll de radar). Com event-driven (Redis/LISTEN) cai para < 500 ms — 10× ganho.

Bloqueador: 48% das propostas recusam por `bundled_share` = dado de risco que chega 103 s depois.

Execução (assinatura + envio + chain): ~1.3 s (ótimo, limitada pelo piso de Solana).

**Alvo executável:** Implementar Redis sub para radar; fechar tape (T4.28g §2.3) para admissões.
