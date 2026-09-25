---
tags: [knowledge, meme, evento, burst, momentum, r58, m4]
status: vivo
owner: sexta-feira
updated: 2026-09-18
fonte: .claude/state/notes-R58.md
tipo: leitura
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

# KB-0138 — Explosão de compradores não tem vantagem; a fita do banco engana por sobrevivência (R58, 18/09/2026)

**Pergunta.** Com o feed por trade (portão de evento), entrar na "explosão" (≥ N compradores únicos em W s, SOL da curva subindo, criador parado) e sair na primeira queda de X % do pico tem vantagem?

**Medido.** Captura própria da cadeia inteira (`logsSubscribe` no programa pump, RPC público, 25 min, 14:38–15:03 BRT): 71 032 trades, 1 920 moedas, 0 quadros perdidos. Grid N ∈ {5, 8, 12}, W ∈ {10, 20, 30} s, X ∈ {10, 15, 20} %, T ∈ {2, 5} min, taxa 1,25 %/perna, slippage 3 % na compra, 2 s de atraso.
- **As 54 células dão R médio negativo**: −4,3 % (melhor) a −9,1 %; acerto 22–29 %; 550–1 750 sinais/h; ΣR negativa e pior sem o top-3 (não é cauda, é o sinal).
- Variantes: sem atraso −7,1 %; anti-bundle (formação ≥ 5 s, idade ≥ 60 s) −3,3 %; idade 120–600 s +0,8 % (n = 61, negativo sem top-3).
- **A fita do banco (`meme_trades`) engana**: nas 24 h ela dá −0,2 % … +6,8 %, mas só cobre 51 das 1 920 moedas da janela (2,7 %) — as que o radar já prioriza. O mesmo sinal ao vivo nessas 51: +3 a +8 %; nas outras 1 869: −9 a −14 %.
- Tempo físico (N = 8, W = 20): formação 1.º → 8.º comprador p50 11 s (22 % no mesmo bloco = bundle); janela após o gatilho p50 8 s (32 % fecha em ≤ 2 s); gatilho → pico p50 5 s, 26 % já passou quando a compra pousa; pico mediano +9 % contra custo de ida e volta ≈ 5,5 %.
- Ouvir o evento: `received_at − block_time` p50 1,50 s, p90 2,01 s; `confirmed` chega 0,06 s depois de `processed`; assinatura por PDA em `confirmed` viu 97 % dos trades.

**O que muda na operação.** Explosão de compradores **não vira gatilho**; pode ser veto/contexto. Toda pesquisa sobre a fita do banco precisa declarar a cobertura (2,7 % das moedas) antes de concluir. A velocidade (portão de evento) continua valendo para executar mais cedo o que a porta já aprova, não para inventar sinal.

**Ressalvas.** 25 min de um dia; preço marginal ao vivo vs preço médio no banco (favorece o banco); slippage de venda 0 (sensibilidade 3 % piora tudo).

Ligações: [[KB-0136-carteiras-vencedoras-nao-sao-gatilho]] · [[KB-0135-a-vantagem-nao-esta-na-saida]] · [[KB-0134-websocket-do-rpc-lag-medido-ao-vivo]] · [[KB-0119-entrada-depois-da-queda]]
