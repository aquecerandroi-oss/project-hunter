# Notas T4.0b — aplicação da revisão da Astra em docs/plans/T4-MEME-RADAR.md

Fonte da revisão: `.claude/state/astra-review-t40-plano-meme-radar.md` (commit b648ee7).
Arquivo alterado: `docs/plans/T4-MEME-RADAR.md`. Nenhum outro arquivo tocado.

## O que mudou (com referência de linha no arquivo final)

1. **Nota de topo (linhas 11–17):** "Revisão da Astra (12/09) aplicada" com provenance
   (arquivo + commit b648ee7) e aviso de que MUST-FIX 2/3 não foram fechados nesta rodada.

2. **§2 Fontes (tabela, linhas 51–56):**
   - RPC público Solana: adicionado limite de 40 chamadas/método/10s (linha 51).
   - Helius: trocado "Free: 10 req/s" por "Free: 1.000.000 créditos/mês"; adicionado Developer
     US$49/mês (10M créditos/50 RPC/s) e Business US$499/mês (piso do gRPC/Geyser) (linha 52).
   - QuickNode: trocado incerteza "trial 7 dias vs. permanente" por dado confirmado — trial de
     1 mês, 10M créditos/15 req/s; Build US$49/mês (US$34/mês anual) (linha 53).
   - Bitquery: adicionado quota de streaming do trial (17 stream-min/0,2GB), nota de que Personal
     não inclui streaming, preços Pro US$99/mês e Scale US$299/mês (linha 55).
   - Nova nota "Ressalvas da revisão da Astra sobre esta tabela" (linhas 58–65): GET único não
     prova quota/SLA; PumpPortal testado com chave, não prova acesso anônimo.
   - Fix de cross-reference: "ver §6" → "ver §8" (linha 67, decisões estão em §8, não §6).
   - Parágrafo "Decisão proposta para T4.1" corrigido para 1M créditos/mês em vez de 10 req/s
     (linhas 67–75).

3. **§3 Curva de bonding (linhas 92–118):**
   - Preço marginal: adicionada ressalva de unidades normalizadas e "não é preço executável"
     (linhas 93–98).
   - Critério de graduação reescrito: `real_token_reserves = 0` E `complete = true`, migração é
     instrução separada; "~85 SOL/US$69k" explicitamente marcado como não comprovado como limiar
     universal (linhas 100–108).
   - Taxa PumpSwap: removida a alegação de 0,30% fixo; agora descrita como faixa 1,25%–0,30% por
     capitalização/quote, com pares USDC (linhas 113–118).

4. **§4 Números do mercado (linhas 124–132):** nota explicando que 0,198% é limite inferior de
   uma janela de ~6 min de cobertura efetiva, não estimativa comparável — fonte: preprint
   corrigido `arxiv.org/abs/2607.02823`.

5. **§5 Modelo de dados (linhas 150–206):**
   - `meme_tokens`: adicionado `initial_real_token_reserves` (denominador fixo do progresso);
     `complete` deixou de ter `NOT NULL DEFAULT false` — agora nullable, NULL = não observado
     (linhas 159–171).
   - `meme_trades`: comentário PENDENTE apontando que a PK `(signature, ts)` ainda perde trades
     multiplos na mesma tx — MUST-FIX 2 não fechado nesta rodada, só documentado (linhas 188–191).
   - `meme_snapshots.curve_progress_pct`: fórmula trocada de `real_sol_reserves/limiar de SOL`
     para `1 − real_token_reserves/initial_real_token_reserves` (linhas 198–200).

6. **§6 T4.1 — critério de aceite (linhas 242–262):** expandido com IDL fixada por versão,
   heartbeat separado de atividade, orçamento RPC compartilhado, tratamento de 429/quota, dedupe
   por instrução/evento, fixtures de duplicatas/múltiplos trades/atraso/finalidade/gaps
   recuperáveis-irrecuperáveis; nota de que "1 evento em 60s" prova conectividade, não cobertura.
   Cross-reference "ver §7" → "ver §8" corrigida (linha 228).

7. **§6 T4.2 — escopo e critério de aceite (linhas 264–301):**
   - Escopo: nova nota de que `unique_buyers_1m`/`buy_sell_ratio_1m`/`creator_sold` dependem de
     `meme_trades` só existir no subconjunto pago/backfill — fora dele, `null` com motivo
     `not_subscribed`, nunca `0`/`false` (linhas 271–276, MUST-FIX 1).
   - Critério de aceite: linha-por-minuto-ou-nulo-justificado em vez de "sem buraco" absoluto;
     `curve_progress_pct` pela fórmula corrigida; `top10_holder_share_pct` agregado por owner,
     excluindo curva/pool/burn; `creator_sold` distinguindo transferência de venda; retenção
     testada com mesma janela para graduados e não graduados (linhas 278–301).

8. **§6 T4.3 — critério de aceite (linhas 310–325):** exige exposição de fonte, instante
   observado/disponível, atraso, universo selecionado, gaps; estados nomeados
   (`not_subscribed`/`insufficient_coverage`/`rate_limited`/`unsupported_quote`) em vez de
   zero/null indistinto; testes desses estados na API e na tela.

9. **§8 Decisões para o Everton — reescrita completa (linhas 353–393):** reordenada para a ordem
   da Astra (features → retenção → RPC), com os custos que ela cita:
   - Decisão 1 (features): discovery+conclusão/migração+RPC sob demanda grátis; trades só em
     subconjunto explícito, 0,01 SOL/10k eventos.
   - Decisão 2 (retenção): mesma janela para graduados e não graduados — proposta original de
     "podar não-graduados após 30 dias" explicitamente rejeitada.
   - Decisão 3 (RPC): Helius Free US$0/mês para ensaio limitado; Developer US$49/mês (10M
     créditos/50 RPC/s) só se a medição justificar; gRPC só no Business US$499/mês; chave não
     garante capacidade — exige teto de consumo + política de degradação aprovados antes.

10. **Nova §8b (linhas 395–411):** lista o que a revisão desta rodada NÃO fechou — MUST-FIX 2
    (parcial: dedupe por instrução/finalidade/quote-decimals) e MUST-FIX 3 (procedência completa,
    `available_at`, versionamento, checkpoints/gaps duráveis, testes de restart/backfill) — e
    reafirma o veredito da Astra de não liberar T4.1 até esses pontos serem fechados num novo
    desenho.

## O que ficou fora do escopo desta rodada (T4.0b), de propósito

Os itens de MUST-FIX 2 e MUST-FIX 3 do parecer da Astra que não estavam na lista explícita desta
tarefa (índice de instrução/evento na PK de `meme_trades`, finalidade, quote/decimals,
`available_at` formal nas três tabelas, versionamento de IDL/schema, checkpoints/gaps duráveis,
testes de restart/backfill, tipos/UUID/privilégios e partições antecipadas contra
`docs/DATABASE.md`) foram **documentados como pendência em §8b**, não implementados no desenho —
evita reescrever o schema além do que foi pedido e mantém honesto que T4.1 continua bloqueado.

Nenhum arquivo de código, `.env*` ou os arquivos em
`packages/exchange-adapters/hunter_exchanges/pumpfun/**` / `docs/EXCHANGE_INTEGRATION.md` foram
tocados. Nenhum commit foi feito.
