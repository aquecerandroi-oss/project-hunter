---
tags: [knowledge, indice, ideias, inbox]
tipo: consolidado
mercado: meme
status: vivo
owner: sexta-feira
updated: 2026-09-25
---

# Ideias do Everton — inbox

Uma linha por ideia dita em conversa, nas palavras dele (curtas), com o que aconteceu depois.
Alimenta a próxima leva de hipóteses e evita perder uma ideia entre uma conversa e a próxima.
**Status possíveis:** `virou H-0xx` (link) · `testada` → link do resultado · `descartada` → o
porquê em uma linha · `aplicada` → o que mudou em produção · `em aberto` → ainda sem artefato que a
responda.

| data | ideia (palavras dele) | status |
|---|---|---|
| 23/09/2026 ~19h BRT | "e se sairmos da pump.fun?" | **testada** — R66/[[KB-0148-a-graduacao-nao-e-a-saida-barata\|KB-0148]]: a graduação não é a saída barata (pós-graduação cobra 2,40 % de ida-e-volta contra 2,23 % da curva); **veredito: não abrir frente pós-graduação** |
| 23/09/2026 12:0x BRT | "na moeda sem ser meme precisamos analisar via gráfico colocando linha do tempo, notícias e tudo — lembra, junção de coisas" | **em aberto** — virou o desenho da tela de confluência (`docs/design/tela-confluencia-mercado.md`, T4.82); status do desenho em 25/09: **"nenhuma linha de componente, endpoint ou migração foi escrita"** — desenho aprovado, implementação ainda não despachada |
| ~19–23/09/2026 (conversas da mesa real) | prever a próxima vela, comprando antes e vendendo na alta | **testada** — [[KB-0150-a-proxima-vela-e-menor-que-o-pedagio]] (R68): a 1 minuto o custo de ida-e-volta é **3,1× a 12×** o movimento típico da vela seguinte; a taxa de acerto necessária para empatar (`p*`) já passa de 1 no horizonte de 1 min — nem acertar sempre empataria com esse custo |
| ~19–23/09/2026 | acompanhar a vela em tempo real, em milissegundos, e integrar mais sistemas de gráfico | **testada/aplicada parcialmente** — [[KB-0145-binance-como-sinal-solana-como-execucao]] (R63): a Binance lidera a Solana por **menos de 15 s**; em cripto normal a vantagem tem de vir do sinal, não da velocidade. A parte de integrar mais gráficos ficou para a tela de confluência (linha acima), ainda em desenho |
| 23/09/2026 17:1x BRT | "conforme vai acompanhando o gráfico, vai comprando e vendendo muito rápido: desceu comprou, subiu vendeu, desceu comprou, subiu vendeu, e lucra antes de alguém vender tudo" | **testada** — virou [[Fila de Hipoteses#H-009 — Giro rápido na oscilação (comprar a queda, vender o repique, repetir)\|H-009]]/[[KB-0152-a-oscilacao-existe-o-giro-nao-paga]]: a oscilação **existe** (mediana 3,5–4 giros de 3 % por posição), mas a política de giro **não confirma** — 0 de 12 células, melhor IC superior +0,103 contra a previsão de +0,05 |
| 23/09/2026 (spot/1 nasce) | ampliar para moedas maiores e o Lab em dinheiro real | **aplicada** — `spot/1` (Jupiter/Binance) ligada em 23/09 com 35–38 mercados habilitados, ficha 0,05 SOL, `mean_reversion v14`; primeira compra real **TAO/USDT em 25/09 11:30 BRT** ([[09-OPERATIONS/Diario/2026-09-25|Diário 25/09]]) |
| 23/09/2026 17:5x BRT | "manda medir essa do alvo então" (depois do fragmento da H-009 sobre vender o repique) | **testada** — [[Fila de Hipoteses#H-011 — Onde deve ficar o alvo (vender o primeiro repique e não voltar)\|H-011]]/[[KB-0154-subir-o-alvo-nao-paga]]: **refuta** — o melhor alvo (1,08×) é a borda da grade e o ganho vem de 5 moedas, invertendo com a cobertura da fita; regra atual (1,15×) mantida |
| (antes de 16/09/2026, referenciado no KB-0149) | copiar quem faz milhão (seguir carteira vencedora) | **descartada** — R57/[[KB-0136-carteiras-vencedoras-nao-sao-gatilho]]: seguir carteira vencedora não é gatilho; a família E2-b (R60/R61) também não sustentou |
| 23/09/2026 ~22h BRT | "arruma" — comprar no recuo em vez de no pico | **testada, em curso** — [[Fila de Hipoteses#H-016 — Entrar no recuo, não no pico (esperar a primeira correção depois do sinal)\|H-016]] **refutou** (esperar recuo grande não paga); o fragmento de preço melhor virou [[Fila de Hipoteses#H-017 — Recuo pequeno como melhora de preço (coorte nova, braço de papel)\|H-017]]/[[EXP-M24-entrada-no-recuo]], braço `recuo_v1/1` **em curso** (91 entradas, +2,61 %/entrada na ficha de 25/09) |
| 24/09/2026 ~11h BRT | pausar a mesa real | **em aberto** — autorizado por Everton, mas o comando (`MEME_LIVE_AUTO_APPROVE=false` + deploy) **não surtiu efeito**: a compra automática seguiu `true` em 24/09 e continuava `true` em 25/09 ([[09-OPERATIONS/Diario/2026-09-24|Diário 24/09]], [[09-OPERATIONS/Diario/2026-09-25|Diário 25/09]]) — Everton decide se mantém ligada |
| 23/09/2026 ~22:40 BRT | decidir com 10 entradas (verificar o braço `recuo_v1` rodando ao vivo) | **respondida** — registrado como **verificação do mecanismo, não julgamento**: 10 entradas não estimam os +2 pp previstos; o julgamento formal exige ≥150 decisões resolvidas ([[EXP-M24-entrada-no-recuo]]) |
| T4.93 (Everton, citado em `.claude/rules/obsidian-first.md`) | "sempre que for usar a estratégia tem que passar analisando via Obsidian primeiro" | **aplicada** — `meme_rule_set.py`, `activate_strategy_version.py` e `spot_desk_markets.py` recusam `--apply` sem `--note obsidian/...` que cite o alvo exato (`.claude/rules/obsidian-first.md`) |
| T4.92 (pedido implícito: parar de perder por não lembrar) | ficha automática — cada operação real com métricas e motivo, sem depender de alguém lembrar | **aplicada** — `infra/scripts/meme_daily_ficha.py` gera [[Ficha-2026-09-24]]/[[Ficha-2026-09-25]] diariamente, com a classe de perda automática ([[Perdas/Index|Perdas]]) |
| 23/09/2026 11:19 BRT | "tudo no talo" — usar o Helius sem economizar | **aplicada** — `.env` com as 8 linhas e recriação forçada: teto de moedas 120→300, orçamento pump.fun 60→30, `MEME_RPC_TOP_K` 100, `MEME_EVENT_GATE_MAX_MINTS` 400, concorrência 4 ([[09-OPERATIONS/Diario/2026-09-23|Diário 23/09]]) |
| (recorrente nas conversas de operação) | meta: ganhar mais do que perder por dia | **em aberto** — nenhum artefato encontrado que codifique isto como alvo formal (limite, alarme ou critério de sucesso); hoje só se lê no placar diário da ficha automática (net SOL do dia) — [[Ficha-2026-09-24]] fechou negativa, [[Ficha-2026-09-25]] foi o primeiro dia positivo |

## Relacionado

[[Mapa de Estrategias]] · [[Fila de Hipoteses]] · [[Dicionario de Variaveis]] · [[Perdas/Index|Perdas]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]] · [[09-OPERATIONS/Diario/2026-09-25|Diário 25/09]]
