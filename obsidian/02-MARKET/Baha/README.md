---
tags: [market, fonte, noticias, baha, plantao]
status: vivo
owner: sexta-feira
updated: 2026-09-15
---

# baha.com/news — a fonte fixa de notícias (pedido do Everton, 15/09/2026 21:1x BRT)

**O que é:** o feed "baha breaking news" da baha GmbH (ex-TeleTrader, Viena) — notícias curtas 24/7 de mercados, economia,
política, guerra, tecnologia e cripto, com carimbo relativo ("1h ago"), categoria e fonte (TeleTrader). Página inicial
[https://www.baha.com/news](https://www.baha.com/news); categorias `/news/category/{Markets,Economy,Business,Politics,World,War-Terrorism,Technology,Crypto,Sports,Insights}`;
relatórios de mercado em `/news/marketreports`; sem RSS público. Licença gratuita **só para uso pessoal e não comercial** —
é o uso que fazemos (a mesa é do Everton); nada de redistribuir o texto.

**Como lemos (e por quê):** o site tem verificação anti-bot (Cloudflare): leitores automáticos (`WebFetch`, `curl`, o
navegador embutido) recebem 403 ou ficam na página "Um momento…", e **não contornamos verificação de bot** (regra da
casa). A leitura é feita **pelo Chrome do Everton** (sessão dele, só leitura, sem login), pela Sexta-feira, no início
de cada corrida da lane 2 do plantão meme e sempre que ele pedir; o extrato (título · categoria · "há X" → hora BRT ·
fonte) vai para `.claude/state/plantao-meme/baha-AAAA-MM-DD-HHMM.md` e a agente da lane 2 lê esse arquivo.

**O que entra (o "limpar"):** só o que muda o nosso risco ou o nosso mercado: (1) cripto — regulação (Clarity Act,
SEC/CFTC), BTC/ETH com movimento ≥ 3 % no dia, Solana, memecoins, lançamentos de figuras públicas, listagens, incidentes
(exploits, quedas de cadeia, drains); (2) macro que liga/desliga o apetite a risco — decisão do Fed, CPI/PPI, juros de
10 anos, petróleo, guerra; (3) tecnologia só quando toca cripto/IA de negociação. Política doméstica dos EUA, esportes e
o resto **não entram**. Cada item: uma linha, com hora BRT e o que muda para nós (uma frase) — opinião é rotulada opinião.

**Cadência do feed medida (15/09, 21:1x BRT):** página inicial com ~50 itens nas últimas 7 h (≈ 7/h; predominam
política e guerra); a categoria Crypto tem **10 itens em 20 dias** (≈ 1 a cada 2 dias) — para cripto ele é lento e
institucional (regulação, BTC/ETH, bancos); o pump.fun em si não aparece. Serve como **termômetro macro e regulatório**,
não como sinal de moeda.

## Diários
- [[02-MARKET/Baha/2026-09-15|2026-09-15]] — primeira varredura: Clarity Act barrado no Senado, BTC −3 %, juros de 10 anos no maior nível desde 2007, CPI e decisão do Fed amanhã.
