---
tags: [experimento, meme, evento, retencao, snipers, m4]
status: pre-registrado
owner: sexta-feira
updated: 2026-09-19
origem: Everton, 19/09/2026 00:4x BRT — "se está subindo, vendas rápidas e mudanças rápidas de subida: compra assim que tiver alta, dá para perceber" / "então está precisando melhorar, não?"
tipo: pesquisa
hipotese: —
variavel: —
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: —
classe_de_perda: —
mercado: meme
---

# EXP-M19 — Subida com gente atrás (retenção dos snipers + carteiras novas − vendas rápidas)

## Hipótese
A subida que paga é a que tem compradores novos entrando e os primeiros compradores (snipers, bloco 1–3) **segurando**; a que não paga é a distribuição (os primeiros vendendo para os que chegam). Um critério de porta lido do feed por trade — retenção dos snipers ≥ 70 % por ≥ 60 s, ≥ N carteiras novas nos últimos 30 s, vendas rápidas (compra e venda em < 20 s) ≤ 20 % dos trades — separa as duas com vantagem.

## Por que agora
O feed por evento (T4.52b, 3 000 trades/min) traz **quem** compra e vende; a porta atual só lê números de uma foto (snipers, holders, progresso). O teto de snipers (10) barra 45 moedas/30 min de madrugada sem saber se os snipers ficaram.

## Método (T4.66, papel primeiro)
Estado em memória por moeda: carteiras dos 3 primeiros blocos e seus saldos (via trades), carteiras novas por janela, trades "rápidos". Critério novo na porta de evento; braço `flow_v2/10` (`research_only`) = `flow_v2/6` + critério; controle `flow_v2/6`. Medir 3 dias: R médio, acerto, concentração, e a mesma leitura nas moedas que a mesa real comprou (teria vetado YOU/CITIZEN?).

## Regra de decisão
Vira mesa se R médio do braço > controle com ≥ 60 apostas e vetar ≥ 2 dos 3 rugs reais sem vetar a única vencedora (PS).

Ligações: [[KB-0119-entrada-depois-da-queda]] · [[KB-0120-piso-de-snipers]] · [[KB-0128-cadeia-vence-fita]] · [[KB-0136-carteiras-vencedoras-nao-sao-gatilho]] · [[EXP-M18-sniper-de-lancamento]]

## Braço semeado (T4.66)

**19/09/2026** — o braço existe no banco e a pista de evento passou a ler quem compra e quem vende.

| item | valor |
|---|---|
| migração | `0054_meme_gate_crowd_arm` (sobre `0053_meme_launch_lane_arm`), `docs/DATABASE.md` §61 |
| conjunto | **`flow_v2/10`** (`01994d00-6c1a-7000-8000-000000000018`), `research_only`, `exp_ref EXP-M19`, `status active`, relógio 15 s |
| base / controle | `flow_v2/6` (`0044`, com `pedigree_e2b: true`) — leitura honesta é `/10` contra `/6`, nunca contra `operator/5` |
| as quatro chaves novas | `min_early_retention_pct: "0.70"` · `min_early_age_s: 60` · `min_new_wallets_30s: 5` · `max_quick_flip_share_30s: "0.20"` (frações como string decimal; contagens como inteiro) |
| leituras | `hunter_indicators.meme.crowd` (`CrowdLedger`, 4 `FeatureDefinition` v1); fiação em `MintEventState.crowd` → `event_gate_rows.build_event_row` → `GateRow.early_retention_pct/early_age_s/new_wallets_30s/quick_flip_share_30s` |
| recusas | `early_retention_below_min`, `early_age_below_min`, `new_wallets_below_min`, `quick_flip_above_max`; desconhecido: `early_retention_unknown`, `new_wallets_unknown`, `quick_flip_unknown` |
| quem mede | **só a pista de evento** (`MEME_EVENT_GATE=on`); a pista de 15 s deixa `None` ⇒ `*_unknown` (falha fechada) |
| provas | `packages/indicators/tests/unit/test_meme_crowd.py` (13), `services/meme-worker/tests/test_event_crowd.py` (7, replay das fixtures T4.52b-1), `test_event_gate_crowd_integration.py` (Postgres: `flow_v2/10` recusa retenção 0,4 e passa 0,9; `flow_v2/6` passa as duas), `test_migration_0054.py` (8) |

**Definições operacionais congeladas com o braço** (mudar uma é versão nova da feature):
- carteiras iniciais = compradores (nunca o criador) dos 3 primeiros slots contados do `create` quando o slot é conhecido; senão os **10 primeiros compradores distintos** na ordem de chegada — hoje o slot do `create` não chega ao estado, então vale a regra dos 10;
- retenção = Σ max(comprado − vendido, 0) ÷ Σ comprado (por carteira, saldo negativo vira 0); idade = segundos desde a primeira compra inicial;
- carteira nova = primeiro trade **visto pela cobertura** nos últimos 30 s (a janela exige ≥ 30 s de cobertura); venda rápida = venda de carteira cuja primeira compra foi há < 20 s; a fração é sobre **todos** os trades da janela (compras, vendas, criador incluído);
- retenção ≥ 0,70 **e** idade ≥ 60 s (o "por ≥ 60 s" da hipótese); acima do teto de 0,20 recusa (estrito), igual passa.

**O que a semente sozinha não garante — a primeira leitura.** O conjunto inicial só é medido quando a assinatura cobriu o mint desde o nascimento (`covered_since ≤ first_seen_at + 5 s`). A sincronização de assinaturas do portão de evento roda a cada 5 s sobre `young_mints`, e os snipers compram nos primeiros ~1–2 s: se a maioria dos mints entra fora da graça, o braço recusa `early_retention_unknown` e mede a cegueira, não a multidão. **P0 (antes de ler R):** fração de `early_retention_unknown` entre as recusas de `flow_v2/10` ≤ 20 % nas primeiras 24 h. Se falhar, o próximo passo não é mexer no critério: é (a) assinar no instante do `create` (a pista de lançamento já recebe o `create` em ~100 ms) ou (b) preencher os primeiros slots por `getSignaturesForAddress` na assinatura — os dois fora do escopo da T4.66.

**P0 endereçado (T4.70, 19/09/2026).** `discovery._handle` agora chama `event_gate_subscriptions.subscribe_at_create` no mesmo gancho de `create` que a pista de lançamento já usa (T4.67a), independente de `MEME_LAUNCH_LANE` — quando o portão de evento é `shadow`/`on`, a assinatura `logsSubscribe`/`accountSubscribe` da PDA da curva abre no instante do `create`, não mais só a cada 5 s. `MintEventState.subscribed_at` fica a poucos ms de `first_seen_at` ⇒ `covered_from_birth` passa a ser estruturalmente verdadeiro para todo mint visto desde o nascimento (o próprio teto `max_mints`/as regras de despejo continuam as mesmas). O `create_slot` — antes nunca preenchido — agora vem da primeira notificação de trade após a assinatura (`expects_create_slot`), o que ativa a regra dos 3 primeiros slots (em vez do fallback dos 10 primeiros compradores); `creation_block_buyers` (o criador + qualquer comprador visto no mesmo slot da criação) fica registrado para auditoria. Métricas novas no heartbeat (`hb:meme:radar`, prefixo `event_gate_`): `subscribed_at_create_total`, `create_to_subscribe_ms_p50`/`_p95`, `early_retention_unknown_share_60s` — esta última é o próprio número de aceite do P0, agora medível ao vivo em vez de só nas recusas gravadas. Prova: `test_subscribe_at_create_then_trades_make_early_retention_known` (`test_event_gate_crowd_integration.py`, Postgres real) — `create` seguido de trades faz a retenção sair conhecida (`Decimal("0.9")`), não `early_retention_unknown`. Falta medir a fração ao vivo por 24 h (rollout, fora do escopo da T4.70).

**Como ler em 3 dias** (a regra de decisão acima): R médio e acerto de `flow_v2/10` contra `flow_v2/6`, `n ≥ 60`; a mesma leitura sobre as moedas que a mesa real comprou (teria vetado YOU/CITIZEN? teria deixado PS?). Um R melhor com `n` pequeno e `*_unknown` alto é cobertura, não vantagem.
