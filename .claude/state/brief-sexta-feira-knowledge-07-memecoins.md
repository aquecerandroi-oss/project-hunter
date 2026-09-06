# Brief — Sexta-feira: rodada 7 de conhecimento — meme coins

**Pedido do Everton (2026-09-06):** "quero que estude sobre meme coin" — para usar as estratégias no virtual e validar tudo antes do dinheiro real.

**Regra operacional:** nunca Bash em background; comandos em primeiro plano com timeout ≤ 5 min. Método das rodadas anteriores (`obsidian/11-KNOWLEDGE/`; leia `Index.md`, `Strategy Backlog.md`, `Registro de Tentativas.md` antes). Escreva só em `obsidian/11-KNOWLEDGE/**`; commit e push só desses arquivos (`docs(knowledge): ...`, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`), a cada 3 notas. Síntese própria, fonte com URL, sem cópia, sem serviço pago.

## Recorte honesto do que o Lab consegue testar hoje
O Lab roda **só perpétuos USDT da Binance** (universo = top N por volume 24 h, hoje 50 na VPS, 200 provados). Meme coins com perpétuo (DOGE, SHIB, PEPE, WIF, BONK, FLOKI, e os que entram no top por volume, inclusive lançamentos com símbolo em chinês) **já estão no universo**. O que **não** temos: on-chain, DEX (pump.fun, Raydium), lançamentos pré-listagem, dados sociais (o flag `enable_social_intelligence` está desligado). Cada hipótese tem de dizer em qual lado da linha cai: "testável agora (perpétuo da Binance)" ou "depende de dado que não temos (on-chain/social) — fica para a fase com o flag".

## Temas (6–10 notas, KB numeradas em sequência)
1. **O que é uma meme coin como ativo**: sem fluxo de caixa, valor = atenção; o que a literatura aberta diz (arXiv/SSRN 2021–2025: "memecoin", "meme coins market efficiency", "Dogecoin", "attention-driven assets").
2. **Ciclo de vida e listagem**: efeito de listagem de perpétuo na Binance (anúncio → volume → OI → funding extremo nas primeiras horas/dias); evidência aberta sobre "exchange listing effect crypto"; o que o nosso market-worker vê (universo diff, `market.universe.changed`) e uma hipótese sobre os primeiros N dias de um perpétuo novo.
3. **Pump-and-dump e manipulação**: a literatura de detecção (Kamps & Kleinberg 2018; Xu & Livshits 2019; Hamrick et al.; "pump and dump cryptocurrency detection"), as assinaturas em volume/preço/book em minutos, e o que disso o M2 já mede (`VOLUME_SPIKE`, `relative_volume_*`, `orderbook_imbalance_20`, `trade_velocity`); hipótese: distinguir pump orquestrado de momentum orgânico pelas features que temos.
4. **Momentum e reversão em meme coins**: são mais "momentum" ou mais "mean reversion" que o resto do universo? Evidência aberta; hipótese: estratificar `momentum_v1`/`volume_anomaly_v1` por uma marcação de "meme" (lista explícita, versionada) e comparar populações no Lab (diagnóstico antes de estratégia).
5. **Volatilidade, spread e custo**: ATR% típico de memes vs BTC, spread e profundidade top-20 (medir no hot state/`market_snapshots` local com SQL quando o Docker estiver de pé), o que isso faz com o piso `atr_pct_min` e com os custos assumidos (2/5/4 bps).
6. **Funding e posicionamento em memes**: funding extremo, OI, liquidações em cascata (KB-0017/0025), hipótese contrarian específica de memes (com a ressalva da KB-0023).
7. **Correlação com BTC e "meme season"**: beta e correlação em stress (KB-0034), quando memes descolam; hipótese de regime.
8. **Dados sociais** (uma nota só, marcada "depende de flag"): o que a literatura diz sobre menções/Twitter/Telegram como preditor, e o que exigiria para entrar no pipeline (conversa com `intelligence_events`).
9. **Risco específico**: delistagem, quedas de 80–95%, gaps; regras de risco para o M3/M4 (o Lab não dimensiona; registrar para o Risk Engine).

## Para cada nota
Template `_TEMPLATE-NOTE.md`, com "Segunda opinião (Astra)" por nota (`bash infra/scripts/astra.sh ask KB-<slug> "..."`). Linha no `Index.md` (tema novo "Meme coins") e, quando houver hipótese, no `Strategy Backlog.md` com o lado da linha (testável agora / depende de flag), dado necessário, esforço. Ao final, seção **"Fila para a sombra — meme coins"** no backlog com as 2–4 candidatas testáveis agora, cada uma com regra, parâmetros, o que a refutaria, e a marcação de universo (lista de memes versionada, como `default_parameters`). Nada é ativado por você.

Relatório final em português: notas, fila para a sombra, o que depende de flag, discordâncias da Astra, fontes que não abriram.
