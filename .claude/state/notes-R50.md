# R50: Classificação de 1.058 Graduações em 24h — Radar Vs. Born-Full

**Executado:** 2026-09-16 14:30 UTC-3 (Brasília)  
**Scope:** Todas as `meme_tokens` com `completed_at` OU `graduated_board_seen_at` não-nulo no intervalo 24h antes de NOW()  
**Total amostrado:** 1.058 moedas (18 descartadas por `created_at IS NULL`)

## 1. Taxonomia das Graduações

| Categoria | Contagem | % | Vida Média | Mediana | Obs. |
|-----------|---------|---|-----------|---------|------|
| **WATCHED** | 568 | 53,7% | ~10.966s (3h) | ~292s (5m) | Geraram meme_features_15s OU _1m antes de completar |
| **BORN_FULL** | 486 | 45,9% | ~1.3s | 1s | Vida < 60s; rastreadas 0s após criação; sem features |
| **MISSED_ORGANIC** | 4 | 0,4% | ~203.552s (57h) | ~1.136s | Vida ≥ 60s; sem features; deveriam ter sido rastreadas |

### Mayhem Breakdown
- WATCHED: 267 Mayhem, 301 non-Mayhem
- BORN_FULL: 0 Mayhem, 486 non-Mayhem
- MISSED_ORGANIC: 2 Mayhem, 2 non-Mayhem

Achado crítico: Todas as 486 born-full são non-Mayhem.

## 2. BORN_FULL (486): O Núcleo das "Instantâneas"

Origem: **pumpportal_ws** (evento de migração), radar delay = 0s.

A moeda cria + migra sub-segundo. O radar vê migração primeiro (subscribeNewToken/subscribeMigration), não tem chance de rastrear antes da completude.

- Vida média: 1,3s (mediana 1s)
- Path: 480 via pool, 478 via board graduado
- Nenhuma Mayhem (sugestão: Mayhem "empty virtual reserve" pode causar rejeição precoce)

## 3. WATCHED (568): Rastreadas OK

- Vida média ~3 horas → tempo suficiente para fast_lane
- 267 Mayhem, 301 non-Mayhem → sem filtro automático de Mayhem
- Meme_features_15s/1m geradas normalmente

## 4. MISSED_ORGANIC (4): Perda Mínima (0,4%)

1. 811.844s (9.4 dias): pumpportal_ws outlier, existia antes do radar
2. 2.178s (trenches_ws): Visto apenas em board, nunca em create discovery
3. 95s (trenches_ws): Edge case, 35s acima do limiar
4. 92s (trenches_ws): Edge case, 32s acima do limiar

Causa dos 3 trenches_ws: Descobertos via board, não via discovery pumpportal_ws.

## 5. Respostas Diretas

(i) **Born Full = Un-Tradeable by Design:** 486 moedas (45,9%). Mecanismo: create + migrate sub-segundo. Não é falha do radar; é latência estrutural.

(ii) **Organic But Missed = Real Loss:** 4 moedas (0,4%). Causa: 3 vistas apenas em trenches_ws (board). Arquivo a revisar: `services/meme-worker/hunter_meme_worker/boards.py` — poderia ser mais agressivo detectando moedas NOVAS na board e adicionando à rastreamento.

(iii) **Watched But Refused:** Subset de 568. Razões: unsupported_quote, no_trade_feed, no_snapshot. Não é problema quantitativo (95% dos 607 observados geraram features).

## 6. Caveats

- Partições de meme_features_15s: retenção 7 dias (ok para 24h)
- 18 moedas com created_at NULL descartadas (migration-first)
- "Instantânea" R46 = "só na board" | "Born_full" R50 = vida < 60s (equivalentes)

## 7. Recomendações

P2: Revisar `boards.py` para adicionar moedas NOVAS na board à fila de rastreamento antes de esperar create discovery.
P3: Auditar "empty virtual reserve" rejection em `mayhem.py:106-112`.
P4: Documentar que born_full é expected behavior (design PumpFun), não falha.

