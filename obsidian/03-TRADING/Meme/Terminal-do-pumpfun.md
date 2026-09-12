---
tags: [trading, meme, pumpfun, terminal, ferramenta, m4]
status: vivo
owner: sexta-feira
updated: 2026-09-12
---

# O Terminal do pump.fun (trade.padre.gg) — o que ele mostra, o que o Everton opera nele e o que o radar precisa saber

**Como esta nota nasceu:** 12/09/2026, 11:20–11:40 BRT, o Everton abriu o Terminal logado no Chrome dele e
autorizou ("pode fuçar e tirar print de tudo e anotar no Obsidian"). Tudo aqui foi lido pela sessão dele,
**só leitura**: nenhum botão de compra, venda, depósito, transferência ou configuração foi tocado. Capturas de tela lidas na sessão dele (não arquivadas no repositório); textos das páginas em
`.claude/state/design/2026-09-12-terminal/`. O Terminal é o antigo Padre, hoje do próprio pump.fun
([[11-KNOWLEDGE/README-meme|hub]]; `docs/plans/T4-FERRAMENTAS.md`).

## 1. A conta e a carteira (fatos, 11:25 BRT)

- Carteira de negociação: **"Starting Solana Wallet" `6nAh8drzAYfFZuTFFRgwRdV8tNndFiX1E8NGRAGzSk5F`**, 4,83 SOL
  (≈ US$ 493), "1 ficha" (só SOL); é a carteira **embutida do Terminal** (chave custodiada pelo Terminal,
  exportável nas configurações). A carteira do site pump.fun (`pump.fun`, avatar "G") está em **$ 0,00**.
- Portfólio às 11:38: uma posição (SOL 4,83, US$ 492), **nenhuma troca ainda**, "Lucro líquido não realizado
  $0,00". Ou seja: o dinheiro está lá, mas o Everton ainda não comprou nada.
- **Para o sistema:** só o endereço público importa ([[06-DECISIONS/2026-09-12-mesa-do-operador-e-caminho-inerte|decisão do dia]]);
  a chave nunca passa por aqui. A reconciliação das operações reais dele é a T4.12
  (`.claude/state/brief-T4.12-carteira-observada.md`).

## 2. A estrutura da interface (rótulos em português como o site mostra)

| Área | O que tem | Equivalente no nosso radar |
|---|---|---|
| Barra superior | Tendências · Portfólio · Acompanhar · Recompensas · Trincheiras · busca por nome/CA · **Depósito** · saldo (4,83) | — |
| **Trincheiras** (`/trenches`) | três colunas ao vivo: **Novo** (curva, segundos de idade), **Breve** (perto de graduar; mostra `%` e "Migrando…") e **Migrado** (PumpSwap) | os boards `new` / `graduating` / `graduated` do `advanced-indexer` que o T4.2c grava em `meme_board_observations` |
| Card de moeda | ticker + nome, `MC` (mcap US$), `V` (volume), `F` (taxas em SOL), idade, holders, nº de transações `x/y`, **top-10 %**, **dev %**, snipers %, sociais (@X, links), "Boost"/"Paid" e o botão **"0 SOL"** (compra rápida com o preset — o valor 0 é o default; NUNCA clicar) | `nh`, `t10`, `dh`, `sn`, `hs/tw` do board; `bo` = bundles |
| Tendências (`/trending`) | abas Tendências · Dex · Novo · **Bomba ao vivo** (lives) · Usuários; filtros MC/Tempo; presets P1 | board `movers` + `lv` (live) |
| Página da moeda (`/trade/solana/<mint>`) | gráfico TradingView (1s…1h, preço ou MCap), abas **Trocas** (Todos · Meu · Desenvolvedor · KOL · Rastreado), **Cargos** (posições), **Pedidos**, **Portadores** (holders), **Melhores negociadores**, **Tokens de desenvolvedor**, "Negociação instantânea", "Alimentar" (feed) | nossa `/meme/{mint}`: série da curva, features por minuto, fita do `swap-api` (T4.2c), holders/top-10/dev do indexer |
| Painel de negociação (direita) | presets **P1/P2/P3**; **Buy / Sell**; tipo **Mercado**; valor em SOL com atalhos **0,1 · 0,2 · 0,5 · 1**; **Estratégia de Saída** (alvo/stop pré-configurados); **Gás** (prioridade) 0,001 · 0,01 SOL; **slippage 20 %** por default; botão **Buy <ticker>**; abaixo, variação 5M/1H/6H/24H | a mesa `/meme/mesa` (aval, alvo, trailing, espera) — em papel |
| "Dados e segurança do token" | Top 10 H. %, **Dev segurando %**, **Atiradores de elite** (snipers, nº e %), **Informantes H.** (insiders), **Pacotes H.** (bundles), Líquido queimado %, Compras recentes, Reserva fresca %, "Autêntico" (mint authority) e "Congelar autorização" (freeze authority) Não/Sim, Pro Vol. 1h, CA e DA (dev address) | `in-memory-coin` do indexer (65 campos, T4.2c `meme_risk_snapshots`) + rugcheck lido no plantão |
| Portfólio | **Carteiras** (endereço, saldo, grupos, importar/criar, carteiras de saque, transferir), **Vagas abertas**, Desempenho, Trocas, Pedidos em aberto; PnL realizado/não realizado | `/meme/lab` e a seção "Reais — carteira observada" (T4.12) |
| Rodapé | Lista de observação · Carteiras · PnL · Alimentar · Trincheiras · Tendências · Alfa · Alertas · Chamadas; cotações (SOL ≈ US$ 101,97) | — |

## 3. O que se aprende operando nele (para a doutrina e para o Lab)

1. **Slippage de 20 % por default e gás em presets** — é o custo que um comprador humano aceita no Terminal;
   o nosso papel simula 1,75 % de taxa por ponta e fill na fotografia seguinte (T4.5): o Terminal é
   **mais caro** na entrada do que o nosso papel assume quando o slippage é consumido. Registrar `slippage`
   e `gas` das operações reais do Everton (T4.12) para calibrar `docs/RISK_ENGINE_MEME.md` §10.2.
2. **"Estratégia de Saída"** = alvo/stop automáticos do próprio Terminal. Se o Everton usar, a saída dele
   é executada pela plataforma; a reconciliação vê só a transação.
3. **A fita do Terminal mostra o vendedor com rótulo "DESENVOLVIMENTO"** (dev). No caso da **RISE**
   (`5v7yY3N2…pump`, uma das nossas apostas de papel de hoje, saída por trailing às 10:19 BRT), a fita do
   Terminal às 11:35 mostrava: o dev comprou 4 × ≈ 1 SOL entre 58 min e 1 h antes, e **vendeu 343,34 M tokens
   por 14,25 SOL (US$ 1 452) aos 55 min** — a moeda caiu de 6,09 K para 4,23 K de mcap. O nosso papel saiu
   por trailing, não por `creator_dump`, porque a fita do `swap-api` daquele minuto veio `rate_limited`
   ([[02-MARKET/Meme/2026-09-12|nota do dia]] §cruzamento). É a prova concreta de que a cobertura
   da fita (T4.2f) é a feature que faltava para a saída certa.
4. Os cards de **Trincheiras** mostram `top-10 %` e `dev %` já no primeiro minuto; o plantão (run 7 e 9) mediu
   que esses campos do indexer **mudam em minutos** para o mesmo mint (M-D5): o número do card não é o
   número "resolvido".
5. A carteira embutida do Terminal é **custodiada** (chave exportável). Para o bot, a doutrina exige
   carteira dedicada com chave só no `.env` da VPS; exportar a desta e reusá-la é opção do Everton, mas
   então ela deixa de ser operada na mão.

## 4. Regras de uso pela sessão dele (para mim e para qualquer agente)

- Só leitura: navegar, ler, capturar. **Nunca** clicar em "0 SOL", "Buy", "Sell", "Depósito", "Transferir",
  "Importar/Criar carteira", "Exportar chave" ou qualquer configuração.
- Nada de digitar segredo; nada de copiar chave; o endereço público pode ser lido e anotado.
- Quando ele operar, o dado entra pela cadeia (T4.12), não pela interface.

## Ligações
[[11-KNOWLEDGE/README-meme|Meme (Conhecimento)]] · [[02-MARKET/Meme/2026-09-12|Meme 2026-09-12]] · [[06-DECISIONS/2026-09-12-mesa-do-operador-e-caminho-inerte|Mesa do operador]]
